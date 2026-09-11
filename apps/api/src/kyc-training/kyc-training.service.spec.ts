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
        groupBy: jest.fn().mockResolvedValue([]),
        count: jest.fn(),
        create: jest.fn(),
        findUnique: jest.fn(),
        update: jest.fn(),
      },
      numberReadingItem: { findMany: jest.fn() },
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
    const item = (over: Record<string, unknown> = {}) => ({
      id: 'item-1',
      number: '284713905612',
      question: 'Enter the LAST 4 digits of the number above.',
      expectedAnswer: '5612',
      answerHint: '4 digits',
      ...over,
    });

    const withCreate = () =>
      prisma.challengeAttempt.create.mockImplementation(async ({ data }: any) => ({
        id: 'attempt-1',
        ...data,
      }));

    it('serves the number and question the admin wrote', async () => {
      prisma.numberReadingItem.findMany.mockResolvedValueOnce([item()]);
      withCreate();

      const issued = await service.issueNextChallenge('u1');

      expect(issued.attemptId).toBe('attempt-1');
      // Grouped 4-4-4 for display; the admin stores plain digits.
      expect(issued.numberDisplay).toBe('2847 1390 5612');
      expect(issued.question).toBe('Enter the LAST 4 digits of the number above.');
      expect(issued.answerHint).toBe('4 digits');
      expect(issued.expiresAt.getTime()).toBeGreaterThan(Date.now());
    });

    it('keeps the admin-set answer server-side instead of returning it', async () => {
      prisma.numberReadingItem.findMany.mockResolvedValueOnce([item()]);
      withCreate();

      const issued = await service.issueNextChallenge('u1');

      // Reading the answer off the number is the task; handing it over
      // pre-computed would let a client pass without reading at all.
      expect(Object.keys(issued)).toEqual([
        'attemptId',
        'numberDisplay',
        'question',
        'answerHint',
        'expiresAt',
      ]);
      expect(prisma.challengeAttempt.create.mock.calls[0][0].data.expectedAnswer).toBe('5612');
    });

    it('copies the answer onto the attempt, so a later edit cannot fail a candidate', async () => {
      prisma.numberReadingItem.findMany.mockResolvedValueOnce([item()]);
      withCreate();

      await service.issueNextChallenge('u1');

      const stored = prisma.challengeAttempt.create.mock.calls[0][0].data;
      expect(stored.itemId).toBe('item-1');
      expect(stored.expectedAnswer).toBe('5612');
      expect(stored.prompt).toMatchObject({
        number: '284713905612',
        numberDisplay: '2847 1390 5612',
        question: 'Enter the LAST 4 digits of the number above.',
      });
    });

    it('says so plainly when the admin has not added any numbers yet', async () => {
      prisma.numberReadingItem.findMany.mockResolvedValue([]);

      // An empty bank is an admin task, not a candidate error, so the message
      // has to name what is missing.
      await expect(service.issueNextChallenge('u1')).rejects.toBeInstanceOf(BadRequestException);
      await expect(service.issueNextChallenge('u1')).rejects.toThrow(/administrator/i);
    });

    it('re-issues an item the candidate already answered', async () => {
      // Without repetition a target larger than the bank could never be
      // finished, and the admin sets the target independently of the bank.
      prisma.numberReadingItem.findMany.mockResolvedValueOnce([item({ id: 'only-one' })]);
      prisma.challengeAttempt.groupBy.mockResolvedValueOnce([
        { itemId: 'only-one', _max: { createdAt: new Date('2026-01-01') } },
      ]);
      withCreate();

      const issued = await service.issueNextChallenge('u1');

      expect(issued.numberDisplay).toBe('2847 1390 5612');
      expect(prisma.challengeAttempt.create).toHaveBeenCalled();
    });

    it('prefers the least recently seen item, so a small bank cycles', async () => {
      prisma.numberReadingItem.findMany.mockResolvedValueOnce([
        item({ id: 'recent', number: '111111111111' }),
        item({ id: 'stale', number: '222222222222' }),
      ]);
      prisma.challengeAttempt.groupBy.mockResolvedValueOnce([
        { itemId: 'recent', _max: { createdAt: new Date('2026-06-01') } },
        { itemId: 'stale', _max: { createdAt: new Date('2026-01-01') } },
      ]);
      withCreate();

      const issued = await service.issueNextChallenge('u1');

      // Serving 'recent' again straight away would be the same number twice
      // in a row, which least-recently-seen ordering exists to avoid.
      expect(issued.numberDisplay).toBe('2222 2222 2222');
    });

    it('prefers a never-seen item over any that has been seen', async () => {
      prisma.numberReadingItem.findMany.mockResolvedValueOnce([
        item({ id: 'seen', number: '111111111111' }),
        item({ id: 'fresh', number: '333333333333' }),
      ]);
      prisma.challengeAttempt.groupBy.mockResolvedValueOnce([
        { itemId: 'seen', _max: { createdAt: new Date('2026-01-01') } },
      ]);
      withCreate();

      const issued = await service.issueNextChallenge('u1');

      expect(issued.numberDisplay).toBe('3333 3333 3333');
    });

    it('only draws from active items', async () => {
      prisma.numberReadingItem.findMany.mockResolvedValueOnce([item()]);
      withCreate();

      await service.issueNextChallenge('u1');

      expect(prisma.numberReadingItem.findMany).toHaveBeenCalledWith(
        expect.objectContaining({ where: { isActive: true } }),
      );
    });

    it('falls back to an empty hint rather than showing "null" in the app', async () => {
      prisma.numberReadingItem.findMany.mockResolvedValueOnce([item({ answerHint: null })]);
      withCreate();

      const issued = await service.issueNextChallenge('u1');

      expect(issued.answerHint).toBe('');
    });
  });

  describe('submitChallenge', () => {
    const attempt = (expectedAnswer: string, over: Record<string, unknown> = {}) => ({
      id: 'attempt-1',
      candidateUserId: 'u1',
      status: 'ISSUED',
      expiresAt: new Date(Date.now() + 60_000),
      kind: 'NUMBER_READING',
      itemId: 'item-1',
      prompt: { number: '284713905612', numberDisplay: '2847 1390 5612' },
      expectedAnswer,
      ...over,
    });

    it('rejects an attempt that does not belong to the requesting candidate', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(
        attempt('5612', { candidateUserId: 'someone-else' }),
      );

      await expect(
        service.submitChallenge('u1', 'attempt-1', { answer: '5612' }),
      ).rejects.toBeInstanceOf(NotFoundException);
    });

    it('passes an answer matching the one the admin set', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(attempt('5612'));
      prisma.challengeAttempt.update.mockResolvedValueOnce({ id: 'attempt-1' });

      const result = await service.submitChallenge('u1', 'attempt-1', { answer: '5612' });

      expect(result.correct).toBe(true);
      expect(prisma.challengeAttempt.update).toHaveBeenCalledWith(
        expect.objectContaining({ data: expect.objectContaining({ status: 'PASSED' }) }),
      );
      expect(eligibility.checkAndPromote).toHaveBeenCalledWith('u1');
    });

    it('grades against the attempt, not the item, so an edit mid-attempt is harmless', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(attempt('5612'));
      prisma.challengeAttempt.update.mockResolvedValueOnce({ id: 'attempt-1' });

      await service.submitChallenge('u1', 'attempt-1', { answer: '5612' });

      // Re-reading the item here would fail a candidate who correctly answered
      // what they were shown, if an admin corrected it in between.
      expect(prisma.numberReadingItem.findMany).not.toHaveBeenCalled();
      expect(prisma.challengeAttempt.findUnique).toHaveBeenCalledWith({
        where: { id: 'attempt-1' },
      });
    });

    it('ignores spacing, because grouping digits differently is still reading them right', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(attempt('284713905612'));
      prisma.challengeAttempt.update.mockResolvedValueOnce({ id: 'attempt-1' });

      const result = await service.submitChallenge('u1', 'attempt-1', {
        answer: '2847 1390 5612',
      });

      expect(result.correct).toBe(true);
    });

    it('fails an answer with the digits transposed', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(attempt('5612'));
      prisma.challengeAttempt.update.mockResolvedValueOnce({ id: 'attempt-1' });

      // Misreading is what the test is meant to catch, so a near-miss has to
      // fail — otherwise the drill measures nothing.
      const result = await service.submitChallenge('u1', 'attempt-1', { answer: '5621' });

      expect(result.correct).toBe(false);
      expect(eligibility.checkAndPromote).not.toHaveBeenCalled();
    });

    it('reveals the right answer after submitting, so a miss teaches something', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(attempt('5612'));
      prisma.challengeAttempt.update.mockResolvedValueOnce({ id: 'attempt-1' });

      const result = await service.submitChallenge('u1', 'attempt-1', { answer: '9999' });

      expect(result.correct).toBe(false);
      expect(result.correctAnswer).toBe('5612');
    });

    it('records what the candidate typed', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(attempt('5612'));
      prisma.challengeAttempt.update.mockResolvedValueOnce({ id: 'attempt-1' });

      await service.submitChallenge('u1', 'attempt-1', { answer: '5612' });

      expect(prisma.challengeAttempt.update).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({ submittedOutcome: { answer: '5612' } }),
        }),
      );
    });

    it('rejects submission after expiry and marks the attempt EXPIRED', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(
        attempt('5612', { expiresAt: new Date(Date.now() - 1000) }),
      );

      await expect(
        service.submitChallenge('u1', 'attempt-1', { answer: '5612' }),
      ).rejects.toBeInstanceOf(BadRequestException);

      expect(prisma.challengeAttempt.update).toHaveBeenCalledWith(
        expect.objectContaining({ data: expect.objectContaining({ status: 'EXPIRED' }) }),
      );
    });

    it('rejects double-submission on an already-completed attempt', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(
        attempt('5612', { status: 'PASSED' }),
      );

      await expect(
        service.submitChallenge('u1', 'attempt-1', { answer: '5612' }),
      ).rejects.toBeInstanceOf(BadRequestException);
    });
  });
});
