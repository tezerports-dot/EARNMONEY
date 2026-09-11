import { BadRequestException, Injectable, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { EligibilityService } from '../eligibility/eligibility.service';
import { AuditLogService } from '../audit/audit-log.service';
import { SubmitChallengeDto } from './dto/submit-challenge.dto';
import { answerMatches, buildReadingChallenge } from './number-reading.util';

const CHALLENGE_TTL_MINUTES = 15;

@Injectable()
export class KycTrainingService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly eligibility: EligibilityService,
    private readonly audit: AuditLogService,
  ) {}

  /**
   * Issues the next challenge: a generated number and one question about it.
   *
   * Nothing is stored in advance. The number is produced on the fly and the
   * expected answer is computed from it, so the supply is unlimited, there is
   * no answer key to maintain, and the target can be any number the admin
   * sets.
   *
   * The number is generated, never a real person's — which is both the legal
   * position and the practical one: the grader always knows the right answer.
   */
  async issueNextChallenge(candidateUserId: string) {
    const challenge = buildReadingChallenge();

    const attempt = await this.prisma.challengeAttempt.create({
      data: {
        candidateUserId,
        kind: 'NUMBER_READING',
        prompt: {
          number: challenge.number,
          numberDisplay: challenge.numberDisplay,
          question: challenge.question.text,
          answerHint: challenge.question.answerHint,
        },
        // Server-side only; never returned before the candidate submits.
        expectedAnswer: challenge.expectedAnswer,
        status: 'ISSUED',
        expiresAt: new Date(Date.now() + CHALLENGE_TTL_MINUTES * 60 * 1000),
      },
    });

    return {
      attemptId: attempt.id,
      numberDisplay: challenge.numberDisplay,
      question: challenge.question.text,
      answerHint: challenge.question.answerHint,
      expiresAt: attempt.expiresAt,
    };
  }

  async submitChallenge(candidateUserId: string, attemptId: string, dto: SubmitChallengeDto) {
    // No join: a reading challenge carries its own answer, so there is
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

    // Reading challenges grade by comparing the typed answer to the one
    // computed from the generated number. Spacing is ignored — a candidate who
    // read the digits correctly but grouped them differently has passed.
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
