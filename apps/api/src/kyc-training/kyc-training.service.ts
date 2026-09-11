import { BadRequestException, Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { EligibilityService } from '../eligibility/eligibility.service';
import { AuditLogService } from '../audit/audit-log.service';
import { SubmitChallengeDto } from './dto/submit-challenge.dto';
import { KYC_ISSUES, normaliseIssue } from './kyc-issues';

const CHALLENGE_TTL_MINUTES = 15;

@Injectable()
export class KycTrainingService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly eligibility: EligibilityService,
    private readonly audit: AuditLogService,
  ) {}

  /**
   * Issues the next challenge.
   *
   * Scenarios REPEAT. An earlier version excluded any scenario the candidate
   * had already passed, which meant a target above the size of the scenario
   * bank could never be met — a candidate simply ran out of material partway
   * and was stuck forever. Now the target is whatever the admin sets: 5 or
   * 200, candidates complete that many reviews either way.
   *
   * Selection is least-recently-seen rather than uniformly random, so a small
   * bank cycles instead of showing the same document twice in a row. Ties
   * (including scenarios never seen) are broken randomly.
   */
  async issueNextChallenge(candidateUserId: string) {
    const active = await this.prisma.kycTrainingScenario.findMany({
      where: { isActive: true },
      select: { id: true, title: true, syntheticDocument: true },
    });

    if (active.length === 0) {
      // Only reachable when an admin has retired every scenario.
      throw new BadRequestException(
        'No KYC training scenarios are available right now. Please try again later.',
      );
    }

    // When this candidate last saw each scenario. Indexed on candidateUserId,
    // and bounded by the size of the scenario bank rather than by attempts.
    const lastSeen = await this.prisma.challengeAttempt.groupBy({
      by: ['scenarioId'],
      where: { candidateUserId },
      _max: { createdAt: true },
    });
    const lastSeenAt = new Map(
      lastSeen.map((r: { scenarioId: string; _max: { createdAt: Date | null } }) => [
        r.scenarioId,
        r._max.createdAt?.getTime() ?? 0,
      ]),
    );

    // Oldest first; never-seen scenarios sort to the front with 0.
    const oldest = Math.min(...active.map((sc) => lastSeenAt.get(sc.id) ?? 0));
    const leastRecent = active.filter((sc) => (lastSeenAt.get(sc.id) ?? 0) === oldest);
    const scenario = leastRecent[Math.floor(Math.random() * leastRecent.length)];

    const attempt = await this.prisma.challengeAttempt.create({
      data: {
        candidateUserId,
        scenarioId: scenario.id,
        status: 'ISSUED',
        expiresAt: new Date(Date.now() + CHALLENGE_TTL_MINUTES * 60 * 1000),
      },
    });

    return {
      attemptId: attempt.id,
      title: scenario.title,
      // The candidate reviews this exactly like a real KYC document — but
      // every field here is synthetic. See KycTrainingScenario model.
      document: scenario.syntheticDocument,
      expiresAt: attempt.expiresAt,
    };
  }

  /** The fixed list of faults the app offers as answers. */
  listIssues() {
    return { issues: KYC_ISSUES };
  }

  async submitChallenge(candidateUserId: string, attemptId: string, dto: SubmitChallengeDto) {
    const attempt = await this.prisma.challengeAttempt.findUnique({
      where: { id: attemptId },
      include: { scenario: true },
    });

    if (!attempt || attempt.candidateUserId !== candidateUserId) {
      throw new NotFoundException('Challenge attempt not found.');
    }

    if (attempt.status !== 'ISSUED') {
      throw new BadRequestException('This challenge has already been completed.');
    }

    if (attempt.expiresAt < new Date()) {
      await this.prisma.challengeAttempt.update({
        where: { id: attempt.id },
        data: { status: 'EXPIRED', completedAt: new Date() },
      });
      throw new BadRequestException('This challenge expired. Request a new one.');
    }

    const expected = attempt.scenario.expectedOutcome as { valid: boolean; issue?: string };

    // Compare canonical codes, not raw strings. The previous `===` marked a
    // candidate wrong for typing "name mismatch" instead of "name_mismatch",
    // which tested spelling rather than whether they spotted the fault.
    const answeredIssue = normaliseIssue(dto.issue);
    const expectedIssue = normaliseIssue(expected.issue);
    const isCorrect =
      dto.valid === expected.valid && (expected.valid ? true : answeredIssue === expectedIssue);

    const updated = await this.prisma.challengeAttempt.update({
      where: { id: attempt.id },
      data: {
        status: isCorrect ? 'PASSED' : 'FAILED',
        submittedOutcome: { valid: dto.valid, issue: dto.issue ?? null },
        isCorrect,
        attempts: { increment: 1 },
        completedAt: new Date(),
      },
    });

    await this.audit.record({
      actorUserId: candidateUserId,
      action: isCorrect ? 'KYC_CHALLENGE_PASSED' : 'KYC_CHALLENGE_FAILED',
      entityType: 'ChallengeAttempt',
      entityId: attempt.id,
    });

    let promoted = false;
    if (isCorrect) {
      const result = await this.eligibility.checkAndPromote(candidateUserId);
      promoted = result.promoted;
    }

    return {
      attemptId: updated.id,
      correct: isCorrect,
      // Always tell them the right answer immediately — this is training,
      // withholding it would defeat the point.
      correctOutcome: expected,
      promotedToApplicationEligible: promoted,
    };
  }
}
