import { BadRequestException, Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { EligibilityService } from '../eligibility/eligibility.service';
import { AuditLogService } from '../audit/audit-log.service';
import { SubmitChallengeDto } from './dto/submit-challenge.dto';
import { answerMatches, formatGrouped } from './number-reading.util';

const CHALLENGE_TTL_MINUTES = 15;

@Injectable()
export class KycTrainingService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly eligibility: EligibilityService,
    private readonly audit: AuditLogService,
  ) {}

  /**
   * Issues the next challenge from the admin-authored bank.
   *
   * Items repeat: the one this candidate has seen least recently comes next,
   * and one never seen comes before any that has been. That is what lets a
   * target of 200 be met from a bank of 5 — the bank sets how much repetition
   * candidates see, not a ceiling on the target.
   *
   * The number, question and answer are copied onto the attempt. Grading then
   * reads that copy, so an admin correcting an item mid-attempt cannot fail a
   * candidate for answering what they were actually shown.
   */
  async issueNextChallenge(candidateUserId: string) {
    const items = await this.prisma.numberReadingItem.findMany({
      where: { isActive: true },
      select: { id: true, number: true, question: true, expectedAnswer: true, answerHint: true },
    });

    if (items.length === 0) {
      throw new BadRequestException(
        'No practice numbers are available yet. An administrator needs to add some.',
      );
    }

    const lastSeen = await this.prisma.challengeAttempt.groupBy({
      by: ['itemId'],
      where: { candidateUserId, itemId: { in: items.map((i) => i.id) } },
      _max: { createdAt: true },
    });
    const seenAt = new Map(
      lastSeen.map((row: { itemId: string | null; _max: { createdAt: Date | null } }) => [
        row.itemId,
        row._max.createdAt?.getTime() ?? 0,
      ]),
    );

    // Shuffle first so that items the candidate has never seen — all tied at
    // "never" — are not handed out in the same order to everyone.
    const ordered = shuffle(items).sort(
      (a, b) => (seenAt.get(a.id) ?? -1) - (seenAt.get(b.id) ?? -1),
    );
    const item = ordered[0];

    const attempt = await this.prisma.challengeAttempt.create({
      data: {
        candidateUserId,
        itemId: item.id,
        kind: 'NUMBER_READING',
        prompt: {
          number: item.number,
          numberDisplay: formatGrouped(item.number),
          question: item.question,
          answerHint: item.answerHint,
        },
        // Server-side only; never returned before the candidate submits.
        expectedAnswer: item.expectedAnswer,
        status: 'ISSUED',
        expiresAt: new Date(Date.now() + CHALLENGE_TTL_MINUTES * 60 * 1000),
      },
    });

    return {
      attemptId: attempt.id,
      numberDisplay: formatGrouped(item.number),
      question: item.question,
      answerHint: item.answerHint ?? '',
      expiresAt: attempt.expiresAt,
    };
  }

  async submitChallenge(candidateUserId: string, attemptId: string, dto: SubmitChallengeDto) {
    // No join: the attempt carries its own copy of the answer, so there is
    // nothing to look up alongside it.
    const attempt = await this.prisma.challengeAttempt.findUnique({
      where: { id: attemptId },
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

    // Graded against the answer the admin set, as snapshotted at issue time.
    // Spacing is ignored — a candidate who read the digits correctly but
    // grouped them differently has passed.
    const isCorrect = answerMatches(dto.answer, attempt.expectedAnswer ?? '');

    const updated = await this.prisma.challengeAttempt.update({
      where: { id: attempt.id },
      data: {
        status: isCorrect ? 'PASSED' : 'FAILED',
        submittedOutcome: { answer: dto.answer ?? null },
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
      // Shown straight away so a candidate learns from a miss — this is
      // training, and withholding the answer would defeat the point.
      correctAnswer: attempt.expectedAnswer,
      promotedToApplicationEligible: promoted,
    };
  }
}

/** Fisher-Yates, on a copy. */
function shuffle<T>(input: T[]): T[] {
  const out = [...input];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}
