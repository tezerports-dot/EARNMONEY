import { Test } from '@nestjs/testing';
import { EligibilityService } from './eligibility.service';
import { PrismaService } from '../prisma/prisma.service';
import { SystemConfigService } from '../system-config/system-config.service';
import { AuditLogService } from '../audit/audit-log.service';

describe('EligibilityService', () => {
  let service: EligibilityService;
  let prisma: any;
  let systemConfig: any;

  beforeEach(async () => {
    prisma = {
      user: { findUnique: jest.fn(), update: jest.fn() },
      referralCredit: { count: jest.fn() },
      challengeAttempt: { findMany: jest.fn(), count: jest.fn() },
    };
    systemConfig = {
      getReferralThreshold: jest.fn().mockResolvedValue(3),
      getKycChallengeThreshold: jest.fn().mockResolvedValue(3),
    };

    const moduleRef = await Test.createTestingModule({
      providers: [
        EligibilityService,
        { provide: PrismaService, useValue: prisma },
        { provide: SystemConfigService, useValue: systemConfig },
        { provide: AuditLogService, useValue: { record: jest.fn() } },
      ],
    }).compile();

    service = moduleRef.get(EligibilityService);
  });

  it('does nothing for a user not in a promotable status', async () => {
    prisma.user.findUnique.mockResolvedValueOnce({ id: 'u1', status: 'IDENTITY_PENDING' });
    const result = await service.checkAndPromote('u1');
    expect(result.promoted).toBe(false);
    expect(prisma.user.update).not.toHaveBeenCalled();
  });

  it('does not promote when only the referral bar is met', async () => {
    prisma.user.findUnique.mockResolvedValueOnce({ id: 'u1', status: 'REFERRAL_IN_PROGRESS' });
    prisma.referralCredit.count.mockResolvedValueOnce(3);
    prisma.challengeAttempt.count.mockResolvedValueOnce(1); // only 1 of 3

    const result = await service.checkAndPromote('u1');

    expect(result.promoted).toBe(false);
    expect(prisma.user.update).not.toHaveBeenCalled();
  });

  it('does not promote when only the KYC-challenge bar is met', async () => {
    prisma.user.findUnique.mockResolvedValueOnce({ id: 'u1', status: 'REFERRAL_IN_PROGRESS' });
    prisma.referralCredit.count.mockResolvedValueOnce(1); // only 1 of 3
    prisma.challengeAttempt.count.mockResolvedValueOnce(3);

    const result = await service.checkAndPromote('u1');

    expect(result.promoted).toBe(false);
    expect(prisma.user.update).not.toHaveBeenCalled();
  });

  it('promotes to APPLICATION_ELIGIBLE when both bars are met', async () => {
    prisma.user.findUnique.mockResolvedValueOnce({ id: 'u1', status: 'REFERRAL_IN_PROGRESS' });
    prisma.referralCredit.count.mockResolvedValueOnce(3);
    prisma.challengeAttempt.count.mockResolvedValueOnce(3);

    const result = await service.checkAndPromote('u1');

    expect(result.promoted).toBe(true);
    expect(prisma.user.update).toHaveBeenCalledWith({
      where: { id: 'u1' },
      data: { status: 'APPLICATION_ELIGIBLE' },
    });
  });

  it('moves a freshly-ACTIVE user to REFERRAL_IN_PROGRESS when neither bar is met yet', async () => {
    prisma.user.findUnique.mockResolvedValueOnce({ id: 'u1', status: 'ACTIVE' });
    prisma.referralCredit.count.mockResolvedValueOnce(0);
    prisma.challengeAttempt.count.mockResolvedValueOnce(0);

    await service.checkAndPromote('u1');

    expect(prisma.user.update).toHaveBeenCalledWith({
      where: { id: 'u1' },
      data: { status: 'REFERRAL_IN_PROGRESS' },
    });
  });

  it('respects admin-configured thresholds rather than any hardcoded number', async () => {
    systemConfig.getReferralThreshold.mockResolvedValueOnce(1);
    systemConfig.getKycChallengeThreshold.mockResolvedValueOnce(1);
    prisma.user.findUnique.mockResolvedValueOnce({ id: 'u1', status: 'ACTIVE' });
    prisma.referralCredit.count.mockResolvedValueOnce(1);
    prisma.challengeAttempt.count.mockResolvedValueOnce(1);

    const result = await service.checkAndPromote('u1');

    expect(result.promoted).toBe(true);
  });
});
