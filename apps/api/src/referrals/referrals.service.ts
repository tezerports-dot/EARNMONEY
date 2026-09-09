import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { EligibilityService } from '../eligibility/eligibility.service';
import { AuditLogService } from '../audit/audit-log.service';

@Injectable()
export class ReferralsService {
  private readonly logger = new Logger(ReferralsService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly eligibility: EligibilityService,
    private readonly audit: AuditLogService,
  ) {}

  /**
   * Called when `referredUserId` reaches ACTIVE status (identity verified +
   * Telegram bound + group joined). If that user was referred by someone,
   * the referral is credited and the referrer's eligibility is re-checked.
   * A referral can only ever be credited once (unique constraint on
   * referred_user_id in `referrals`, and a compound unique on
   * `referral_credits`) — safe to call more than once.
   */
  async creditReferralIfEligible(referredUserId: string): Promise<void> {
    const referral = await this.prisma.referral.findUnique({
      where: { referredUserId },
    });

    if (!referral || referral.status !== 'PENDING') {
      return; // no referrer, or already handled
    }

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

  /** Candidate-facing: list of this user's referrals and their live status. */
  async listMyReferrals(referrerUserId: string) {
    const referrals = await this.prisma.referral.findMany({
      where: { referrerUserId },
      orderBy: { createdAt: 'desc' },
      select: {
        id: true,
        status: true,
        createdAt: true,
        creditedAt: true,
        // Deliberately not selecting/joining the referred user's identity
        // fields — a referrer only ever sees status, never who it is beyond
        // what they already know from having shared the code themselves.
      },
    });
    return referrals;
  }
}
