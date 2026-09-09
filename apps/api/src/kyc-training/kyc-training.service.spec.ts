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
      challengeAttempt: { findMany: jest.fn(), create: jest.fn(), findUnique: jest.fn(), update: jest.fn() },
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
    it('throws when every scenario has already been passed', async () => {
      prisma.challengeAttempt.findMany.mockResolvedValueOnce([{ scenarioId: 'a' }]);
      prisma.kycTrainingScenario.findMany.mockResolvedValueOnce([]);

      await expect(service.issueNextChallenge('u1')).rejects.toBeInstanceOf(BadRequestException);
    });

    it('excludes already-passed scenarios from the candidate pool', async () => {
      prisma.challengeAttempt.findMany.mockResolvedValueOnce([{ scenarioId: 'passed-1' }]);
      prisma.kycTrainingScenario.findMany.mockResolvedValueOnce([{ id: 'new-1', title: 'X', syntheticDocument: {} }]);
      prisma.challengeAttempt.create.mockImplementation(async ({ data }: any) => ({
        id: 'attempt-1',
        expiresAt: new Date(),
        ...data,
      }));

      await service.issueNextChallenge('u1');

      expect(prisma.kycTrainingScenario.findMany).toHaveBeenCalledWith(
        expect.objectContaining({ where: { isActive: true, id: { notIn: ['passed-1'] } } }),
      );
    });
  });

  describe('submitChallenge', () => {
    const baseAttempt = {
      id: 'attempt-1',
      candidateUserId: 'u1',
      status: 'ISSUED',
      expiresAt: new Date(Date.now() + 60_000),
      scenario: { expectedOutcome: { valid: false, issue: 'name_mismatch' } },
    };

    it('rejects an attempt that does not belong to the requesting candidate', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce({ ...baseAttempt, candidateUserId: 'someone-else' });

      await expect(
        service.submitChallenge('u1', 'attempt-1', { valid: false, issue: 'name_mismatch' }),
      ).rejects.toBeInstanceOf(NotFoundException);
    });

    it('marks correct when valid/issue match the expected outcome exactly', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(baseAttempt);
      prisma.challengeAttempt.update.mockResolvedValueOnce({ id: 'attempt-1' });

      const result = await service.submitChallenge('u1', 'attempt-1', {
        valid: false,
        issue: 'name_mismatch',
      });

      expect(result.correct).toBe(true);
      expect(prisma.challengeAttempt.update).toHaveBeenCalledWith(
        expect.objectContaining({ data: expect.objectContaining({ status: 'PASSED' }) }),
      );
      expect(eligibility.checkAndPromote).toHaveBeenCalledWith('u1');
    });

    it('marks incorrect when the issue does not match, even if valid=false matches', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce(baseAttempt);
      prisma.challengeAttempt.update.mockResolvedValueOnce({ id: 'attempt-1' });

      const result = await service.submitChallenge('u1', 'attempt-1', {
        valid: false,
        issue: 'expired', // wrong — actual issue is name_mismatch
      });

      expect(result.correct).toBe(false);
      expect(eligibility.checkAndPromote).not.toHaveBeenCalled();
    });

    it('rejects submission after expiry and marks the attempt EXPIRED', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce({
        ...baseAttempt,
        expiresAt: new Date(Date.now() - 1000),
      });

      await expect(
        service.submitChallenge('u1', 'attempt-1', { valid: false, issue: 'name_mismatch' }),
      ).rejects.toBeInstanceOf(BadRequestException);

      expect(prisma.challengeAttempt.update).toHaveBeenCalledWith(
        expect.objectContaining({ data: expect.objectContaining({ status: 'EXPIRED' }) }),
      );
    });

    it('rejects double-submission on an already-completed attempt', async () => {
      prisma.challengeAttempt.findUnique.mockResolvedValueOnce({ ...baseAttempt, status: 'PASSED' });

      await expect(
        service.submitChallenge('u1', 'attempt-1', { valid: false, issue: 'name_mismatch' }),
      ).rejects.toBeInstanceOf(BadRequestException);
    });
  });
});
