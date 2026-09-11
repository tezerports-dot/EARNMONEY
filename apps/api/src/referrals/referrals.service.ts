import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { EligibilityService } from '../eligibility/eligibility.service';
import { AuditLogService } from '../audit/audit-log.service';
import { SystemConfigService } from '../system-config/system-config.service';

@Injectable()
export class ReferralsService {
  private readonly logger = new Logger(ReferralsService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly eligibility: EligibilityService,
    private readonly audit: AuditLogService,
    private readonly systemConfig: SystemConfigService,
  ) {}

  /**
   * Called when `referredUserId` reaches ACTIVE (identity verified + Telegram
   * bound + both channels joined). Crediting is guarded by unique constraints
   * on both `referrals.referred_user_id` and the `referral_credits` triple, so
   * calling it twice cannot pay twice.
   */
  async creditReferralIfEligible(referredUserId: string): Promise<void> {
    const referral = await this.prisma.referral.findUnique({ where: { referredUserId } });
    if (!referral || referral.status !== 'PENDING') return;

    await this.prisma.$transaction(async (tx: any) => {
      await tx.referral.update({
        where: { id: referral.id },
        data: { status: 'CREDITED', creditedAt: new Date() },
      });
      await tx.referralCredit.upsert({
        where: {
          referrerUserId_referredUserId_creditType: {
            referrerUserId: referral.referrerUserId,
            referredUserId,
            creditType: 'SIGNUP_ACTIVATED',
          },
        },
        update: {},
        create: {
          referrerUserId: referral.referrerUserId,
          referredUserId,
          creditType: 'SIGNUP_ACTIVATED',
          sourceReferralId: referral.id,
        },
      });
    });

    await this.audit.record({
      actorUserId: referredUserId,
      action: 'REFERRAL_CREDITED',
      entityType: 'Referral',
      entityId: referral.id,
      metadata: { referrerUserId: referral.referrerUserId },
    });

    this.logger.log(`Referral ${referral.id} credited to ${referral.referrerUserId}.`);
    await this.eligibility.checkAndPromote(referral.referrerUserId);
  }

  /**
   * Referral list for the candidate's own dashboard. Status only — a referrer
   * never learns anything about the person behind a referral beyond what they
   * already knew from sharing the code.
   */
  async listMyReferrals(referrerUserId: string) {
    return this.prisma.referral.findMany({
      where: { referrerUserId },
      orderBy: { createdAt: 'desc' },
      select: { id: true, status: true, createdAt: true, creditedAt: true, rejectionReasonCode: true },
    });
  }

  /**
   * The numbers the referral screen shows: how many were brought in, how many
   * cleared KYC, how many were rejected, and how many remain before the
   * ceiling. `verified` is the only one that counts toward eligibility.
   */
  async getReferralStats(referrerUserId: string) {
    const [ceiling, strikeLimit] = await Promise.all([
      this.systemConfig.getReferralThreshold(),
      this.systemConfig.getFraudStrikeLimit(),
    ]);

    const [grouped, verified, user] = await Promise.all([
      this.prisma.referral.groupBy({
        by: ['status'],
        where: { referrerUserId },
        _count: { _all: true },
      }),
      this.prisma.referralCredit.count({ where: { referrerUserId } }),
      this.prisma.user.findUnique({ where: { id: referrerUserId } }),
    ]);

    const byStatus = Object.fromEntries(
      grouped.map((g: { status: string; _count: { _all: number } }) => [g.status, g._count._all]),
    ) as Record<string, number>;

    const total = Object.values(byStatus).reduce((a, b) => a + b, 0);
    const rejected = byStatus.REJECTED ?? 0;
    const pending = (byStatus.PENDING ?? 0) + (byStatus.ELIGIBLE ?? 0);

    return {
      ceiling,
      total,
      // Cleared identity verification and were credited.
      verified,
      // Conclusively failed verification — these also count as fraud strikes.
      rejected,
      // Signed up but haven't finished verifying yet.
      pending,
      // Never negative, and never more than the ceiling.
      remaining: Math.max(0, ceiling - verified),
      ceilingReached: verified >= ceiling,
      fraud: {
        strikes: user?.fakeReferralCount ?? 0,
        limit: strikeLimit,
        // Surfaced so the app can warn before the account is suspended.
        remainingBeforeSuspension: Math.max(0, strikeLimit - (user?.fakeReferralCount ?? 0)),
      },
    };
  }
}
