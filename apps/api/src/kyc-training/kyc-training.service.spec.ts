import { Test } from '@nestjs/testing';
import { BadRequestException, NotFoundException } from '@nestjs/common';
import { KycTrainingService } from './kyc-training.service';
import { PrismaService } from '../prisma/prisma.service';
import { EligibilityService } from '../eligibility/eligibility.service';
import { AuditLogService } from '../audit/audit-log.service';

describe('KycTrainingService', () => {
  let service: KycTrainingService;
  let prisma: any;
  let eligibility: any;

  beforeEach(async () => {
    prisma = {
      challengeAttempt: {
        findMany: jest.fn(),
        groupBy: jest.fn().mockResolvedValue([]),
        count: jest.fn(),
        create: jest.fn(),
        findUnique: jest.fn(),
        update: jest.fn(),
      },
      kycTrainingScenario: { findMany: jest.fn() },
    };
    eligibility = { checkAndPromote: jest.fn().mockResolvedValue({ promoted: false }) };

    const moduleRef = await Test.createTestingModule({
      providers: [
        KycTrainingService,
        { provide: PrismaService, useValue: prisma },
        { provide: EligibilityService, useValue: eligibility },
        { provide: AuditLogService, useValue: { record: jest.fn() } },
      ],
    }).compile();

    service = moduleRef.get(KycTrainingService);
  });

  describe('issueNextChallenge', () => {
    const withCreate = () =>
      prisma.challengeAttempt.create.mockImplementation(async ({ data }: any) => ({
        id: 'attempt-1',
        ...data,
      }));

    it('returns a number to read and a question about it', async () => {
      withCreate();

      const issued = await service.issueNextChallenge('u1');

      expect(issued.attemptId).toBe('attempt-1');
      // 4-4-4 grouping, the way the number appears on a card.
      expect(issued.numberDisplay).toMatch(/^\d{4} \d{4} \d{4}$/);
      expect(issued.question.length).toBeGreaterThan(0);
      expect(issued.answerHint.length).toBeGreaterThan(0);
      expect(issued.expiresAt.getTime()).toBeGreaterThan(Date.now());
    });

    it('keeps the answer server-side instead of returning it as a field', async () => {
      withCreate();

      const issued = await service.issueNextChallenge('u1');

      // The answer is of course derivable from the number shown — reading it
      // off is the task. What must not happen is the server handing it over
      // pre-computed, which would let a client pass without reading at all.
      expect(Object.keys(issued)).toEqual([
        'attemptId',
        'numberDisplay',
        'question',
        'answerHint',
        'expiresAt',
      ]);
      const stored = prisma.challengeAttempt.create.mock.calls[0][0].data;
      expect(stored.expectedAnswer).toEqual(expect.any(String));
    });

    it('needs no stored scenario, so any admin-set target is reachable', async () => {
      withCreate();

      await service.issueNextChallenge('u1');

      // Numbers are generated per attempt: there is no bank to exhaust and
      // nothing to look up, which is why a target of 5 or 200 both work.
      expect(prisma.kycTrainingScenario.findMany).not.toHaveBeenCalled();
      const stored = prisma.challengeAttempt.create.mock.calls[0][0].data;
      expect(stored.scenarioId).toBeUndefined();
      expect(stored.kind).toBe('NUMBER_READING');
    });

    it('generates a fresh number each time rather than repeating one', async () => {
      withCreate();

      await service.issueNextChallenge('u1');
      await service.issueNextChallenge('u1');
      await service.issueNextChallenge('u1');

      const numbers = prisma.challengeAttempt.create.mock.calls.map(
        (call: any) => call[0].data.prompt.number,
      );
      expect(new Set(numbers).size).toBe(3);
      for (const number of numbers) expect(number).toMatch(/^[2-9]\d{11}$/);
    });
  });

  describe('submitChallenge', () => {
    const attemptWithAnswer = (expectedAnswer: string, overrides: Record<string, unknown> = {}) => ({
      id: 'attempt-1',
      candidateUserId: 'u1',
      status: 'ISSUED',
      expiresAt: new Date(Date.now() + 60_000),
      kind: 'NUMBER_READING',
      prompt: { number: '234567890123', numberDisplay: '2345 6789 0123' },
      expectedAnswer,
      scenario: null,
      ...overrides,
    });

    it('rejects an attempt that does not belong to the requesting candidate', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(
        attemptWithAnswer('0123', { candidateUserId: 'someone-else' }),
      );

      await expect(
        service.submitChallenge('u1', 'attempt-1', { answer: '0123' }),
      ).rejects.toBeInstanceOf(NotFoundException);
    });

    it('passes an answer that matches the number that was shown', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(attemptWithAnswer('0123'));
      prisma.challengeAttempt.update.mockResolvedValueOnce({ id: 'attempt-1' });

      const result = await service.submitChallenge('u1', 'attempt-1', { answer: '0123' });

      expect(result.correct).toBe(true);
      expect(prisma.challengeAttempt.update).toHaveBeenCalledWith(
        expect.objectContaining({ data: expect.objectContaining({ status: 'PASSED' }) }),
      );
      expect(eligibility.checkAndPromote).toHaveBeenCalledWith('u1');
    });

    it('ignores spacing, because grouping digits differently is still reading them right', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(
        attemptWithAnswer('234567890123'),
      );
      prisma.challengeAttempt.update.mockResolvedValueOnce({ id: 'attempt-1' });

      const result = await service.submitChallenge('u1', 'attempt-1', {
        answer: '2345 6789 0123',
      });

      expect(result.correct).toBe(true);
    });

    it('fails an answer with the digits transposed', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(attemptWithAnswer('0123'));
      prisma.challengeAttempt.update.mockResolvedValueOnce({ id: 'attempt-1' });

      // Misreading is exactly what the test is meant to catch, so a near-miss
      // has to fail — otherwise the drill measures nothing.
      const result = await service.submitChallenge('u1', 'attempt-1', { answer: '0132' });

      expect(result.correct).toBe(false);
      expect(eligibility.checkAndPromote).not.toHaveBeenCalled();
    });

    it('reveals the right answer after submitting, so a miss teaches something', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(attemptWithAnswer('0123'));
      prisma.challengeAttempt.update.mockResolvedValueOnce({ id: 'attempt-1' });

      const result = await service.submitChallenge('u1', 'attempt-1', { answer: '9999' });

      expect(result.correct).toBe(false);
      expect(result.correctAnswer).toBe('0123');
    });

    it('records what the candidate typed', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(attemptWithAnswer('0123'));
      prisma.challengeAttempt.update.mockResolvedValueOnce({ id: 'attempt-1' });

      await service.submitChallenge('u1', 'attempt-1', { answer: '0123' });

      expect(prisma.challengeAttempt.update).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({ submittedOutcome: { answer: '0123' } }),
        }),
      );
    });

    it('rejects submission after expiry and marks the attempt EXPIRED', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(
        attemptWithAnswer('0123', { expiresAt: new Date(Date.now() - 1000) }),
      );

      await expect(
        service.submitChallenge('u1', 'attempt-1', { answer: '0123' }),
      ).rejects.toBeInstanceOf(BadRequestException);

      expect(prisma.challengeAttempt.update).toHaveBeenCalledWith(
        expect.objectContaining({ data: expect.objectContaining({ status: 'EXPIRED' }) }),
      );
    });

    it('rejects double-submission on an already-completed attempt', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(
        attemptWithAnswer('0123', { status: 'PASSED' }),
      );

      await expect(
        service.submitChallenge('u1', 'attempt-1', { answer: '0123' }),
      ).rejects.toBeInstanceOf(BadRequestException);
    });
  });
});
