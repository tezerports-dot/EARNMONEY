import { BadRequestException, Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { EligibilityService } from '../eligibility/eligibility.service';
import { AuditLogService } from '../audit/audit-log.service';
import { SubmitChallengeDto } from './dto/submit-challenge.dto';

const CHALLENGE_TTL_MINUTES = 15;

@Injectable()
export class KycTrainingService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly eligibility: EligibilityService,
    private readonly audit: AuditLogService,
  ) {}

  /**
   * Issues the next challenge for a candidate: a random active scenario they
   * have not already passed. Scenarios they previously failed can recur, so
   * they can learn from the correction and retry — this is a training tool,
   * not a one-shot gate.
   */
  async issueNextChallenge(candidateUserId: string) {
    const passedScenarioIds = (
      await this.prisma.challengeAttempt.findMany({
        where: { candidateUserId, status: 'PASSED' },
        select: { scenarioId: true },
        distinct: ['scenarioId'],
      })
    ).map((a: { scenarioId: string }) => a.scenarioId);

    const candidates = await this.prisma.kycTrainingScenario.findMany({
      where: { isActive: true, id: { notIn: passedScenarioIds } },
    });

    if (candidates.length === 0) {
      throw new BadRequestException(
        'No further KYC training scenarios available — you may have completed them all.',
      );
    }

    const scenario = candidates[Math.floor(Math.random() * candidates.length)];

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
    const isCorrect =
      dto.valid === expected.valid && (expected.valid ? true : dto.issue === expected.issue);

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
