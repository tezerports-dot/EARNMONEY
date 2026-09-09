import { Test } from '@nestjs/testing';
import { ReferralsService } from './referrals.service';
import { PrismaService } from '../prisma/prisma.service';
import { EligibilityService } from '../eligibility/eligibility.service';
import { AuditLogService } from '../audit/audit-log.service';

describe('ReferralsService', () => {
  let service: ReferralsService;
  let prisma: any;
  let eligibility: any;

  beforeEach(async () => {
    prisma = {
      referral: { findUnique: jest.fn(), update: jest.fn() },
      referralCredit: { upsert: jest.fn() },
      $transaction: jest.fn(async (fn: any) => fn(prisma)),
    };
    eligibility = { checkAndPromote: jest.fn() };

    const moduleRef = await Test.createTestingModule({
      providers: [
        ReferralsService,
        { provide: PrismaService, useValue: prisma },
        { provide: EligibilityService, useValue: eligibility },
        { provide: AuditLogService, useValue: { record: jest.fn() } },
      ],
    }).compile();

    service = moduleRef.get(ReferralsService);
  });

  it('does nothing if the activated user was not referred by anyone', async () => {
    prisma.referral.findUnique.mockResolvedValueOnce(null);

    await service.creditReferralIfEligible('user-with-no-referrer');

    expect(prisma.referral.update).not.toHaveBeenCalled();
    expect(eligibility.checkAndPromote).not.toHaveBeenCalled();
  });

  it('is idempotent — does nothing if the referral was already credited', async () => {
    prisma.referral.findUnique.mockResolvedValueOnce({
      id: 'ref-1',
      referrerUserId: 'referrer-1',
      status: 'CREDITED',
    });

    await service.creditReferralIfEligible('referred-user-1');

    expect(prisma.referral.update).not.toHaveBeenCalled();
    expect(eligibility.checkAndPromote).not.toHaveBeenCalled();
  });

  it('credits the referral and re-checks the referrer eligibility', async () => {
    prisma.referral.findUnique.mockResolvedValueOnce({
      id: 'ref-1',
      referrerUserId: 'referrer-1',
      status: 'PENDING',
    });

    await service.creditReferralIfEligible('referred-user-1');

    expect(prisma.referral.update).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { id: 'ref-1' },
        data: expect.objectContaining({ status: 'CREDITED' }),
      }),
    );
    expect(prisma.referralCredit.upsert).toHaveBeenCalled();
    expect(eligibility.checkAndPromote).toHaveBeenCalledWith('referrer-1');
  });
});
