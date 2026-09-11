import { Test } from '@nestjs/testing';
import { FraudService } from './fraud.service';
import { PrismaService } from '../prisma/prisma.service';
import { AuditLogService } from '../audit/audit-log.service';
import { SystemConfigService } from '../system-config/system-config.service';

describe('FraudService', () => {
  let service: FraudService;
  let prisma: any;
  let config: any;

  beforeEach(async () => {
    prisma = {
      identityVerification: { findUnique: jest.fn(), update: jest.fn() },
      user: { findUnique: jest.fn(), update: jest.fn() },
      referral: { findUnique: jest.fn(), update: jest.fn() },
      referralCredit: { deleteMany: jest.fn() },
      refreshToken: { updateMany: jest.fn() },
      $transaction: jest.fn(async (fn: any) => fn(prisma)),
    };
    config = {
      getKycRejectionAttempts: jest.fn().mockResolvedValue(3),
      getFraudStrikeLimit: jest.fn().mockResolvedValue(8),
    };

    const moduleRef = await Test.createTestingModule({
      providers: [
        FraudService,
        { provide: PrismaService, useValue: prisma },
        { provide: AuditLogService, useValue: { record: jest.fn() } },
        { provide: SystemConfigService, useValue: config },
      ],
    }).compile();

    service = moduleRef.get(FraudService);
  });

  it('does not punish anyone on the first rejection', async () => {
    prisma.identityVerification.findUnique.mockResolvedValue({ id: 'iv-1' });
    prisma.identityVerification.update.mockResolvedValue({ id: 'iv-1', rejectionCount: 1 });

    await service.recordVerificationRejection('user-1', 'BLURRY_DOCUMENT');

    // Flagged for another look, but not written off, and no strike passed on.
    expect(prisma.user.update).toHaveBeenCalledWith({
      where: { id: 'user-1' },
      data: { status: 'REVIEW_REQUIRED' },
    });
    expect(prisma.referral.update).not.toHaveBeenCalled();
  });

  it('still does not punish on the second rejection', async () => {
    prisma.identityVerification.findUnique.mockResolvedValue({ id: 'iv-1' });
    prisma.identityVerification.update.mockResolvedValue({ id: 'iv-1', rejectionCount: 2 });

    await service.recordVerificationRejection('user-1');

    expect(prisma.referral.update).not.toHaveBeenCalled();
  });

  it('confirms the referral fake on the third rejection and strikes the referrer', async () => {
    prisma.identityVerification.findUnique.mockResolvedValue({ id: 'iv-1' });
    prisma.identityVerification.update.mockResolvedValue({ id: 'iv-1', rejectionCount: 3 });
    prisma.referral.findUnique.mockResolvedValue({ id: 'ref-1', referrerUserId: 'referrer-1' });
    prisma.user.findUnique.mockResolvedValue({ id: 'referrer-1', fakeReferralCount: 1, status: 'ACTIVE' });

    await service.recordVerificationRejection('user-1', 'FAKE_DOCUMENT');

    expect(prisma.user.update).toHaveBeenCalledWith({
      where: { id: 'user-1' },
      data: { status: 'KYC_REJECTED' },
    });
    expect(prisma.referral.update).toHaveBeenCalledWith(
      expect.objectContaining({ data: expect.objectContaining({ status: 'REJECTED' }) }),
    );
    expect(prisma.user.update).toHaveBeenCalledWith({
      where: { id: 'referrer-1' },
      data: { fakeReferralCount: { increment: 1 } },
    });
  });

  it('withdraws a credit that was already banked for a referral later proved fake', async () => {
    prisma.identityVerification.findUnique.mockResolvedValue({ id: 'iv-1' });
    prisma.identityVerification.update.mockResolvedValue({ id: 'iv-1', rejectionCount: 3 });
    prisma.referral.findUnique.mockResolvedValue({ id: 'ref-1', referrerUserId: 'referrer-1' });
    prisma.user.findUnique.mockResolvedValue({ id: 'referrer-1', fakeReferralCount: 1, status: 'ACTIVE' });

    await service.recordVerificationRejection('user-1');

    expect(prisma.referralCredit.deleteMany).toHaveBeenCalledWith({
      where: { referrerUserId: 'referrer-1', referredUserId: 'user-1' },
    });
  });

  it('suspends the referrer once strikes reach the limit, and kills their sessions', async () => {
    prisma.identityVerification.findUnique.mockResolvedValue({ id: 'iv-1' });
    prisma.identityVerification.update.mockResolvedValue({ id: 'iv-1', rejectionCount: 3 });
    prisma.referral.findUnique.mockResolvedValue({ id: 'ref-1', referrerUserId: 'referrer-1' });
    // Already at the limit after this strike lands.
    prisma.user.findUnique.mockResolvedValue({ id: 'referrer-1', fakeReferralCount: 8, status: 'ACTIVE' });

    await service.recordVerificationRejection('user-1');

    expect(prisma.user.update).toHaveBeenCalledWith({
      where: { id: 'referrer-1' },
      data: { status: 'SUSPENDED' },
    });
    // A suspended user must not be able to quietly refresh back in.
    expect(prisma.refreshToken.updateMany).toHaveBeenCalledWith({
      where: { userId: 'referrer-1', revokedAt: null },
      data: { revokedAt: expect.any(Date) },
    });
  });

  it('leaves a referrer below the limit alone', async () => {
    prisma.identityVerification.findUnique.mockResolvedValue({ id: 'iv-1' });
    prisma.identityVerification.update.mockResolvedValue({ id: 'iv-1', rejectionCount: 3 });
    prisma.referral.findUnique.mockResolvedValue({ id: 'ref-1', referrerUserId: 'referrer-1' });
    prisma.user.findUnique.mockResolvedValue({ id: 'referrer-1', fakeReferralCount: 7, status: 'ACTIVE' });

    await service.recordVerificationRejection('user-1');

    expect(prisma.user.update).not.toHaveBeenCalledWith({
      where: { id: 'referrer-1' },
      data: { status: 'SUSPENDED' },
    });
  });

  it('does not re-suspend an account that is already suspended', async () => {
    prisma.identityVerification.findUnique.mockResolvedValue({ id: 'iv-1' });
    prisma.identityVerification.update.mockResolvedValue({ id: 'iv-1', rejectionCount: 3 });
    prisma.referral.findUnique.mockResolvedValue({ id: 'ref-1', referrerUserId: 'referrer-1' });
    prisma.user.findUnique.mockResolvedValue({ id: 'referrer-1', fakeReferralCount: 12, status: 'SUSPENDED' });

    await service.recordVerificationRejection('user-1');

    expect(prisma.refreshToken.updateMany).not.toHaveBeenCalled();
  });

  it('handles a rejected user who was never referred by anyone', async () => {
    prisma.identityVerification.findUnique.mockResolvedValue({ id: 'iv-1' });
    prisma.identityVerification.update.mockResolvedValue({ id: 'iv-1', rejectionCount: 3 });
    prisma.referral.findUnique.mockResolvedValue(null);

    await expect(service.recordVerificationRejection('user-1')).resolves.toBeUndefined();
    expect(prisma.user.update).toHaveBeenCalledWith({
      where: { id: 'user-1' },
      data: { status: 'KYC_REJECTED' },
    });
  });
});
