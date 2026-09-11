import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { SystemConfigService } from '../system-config/system-config.service';
import { AuditLogService } from '../audit/audit-log.service';

const PROMOTABLE_STATUSES = ['ACTIVE', 'REFERRAL_IN_PROGRESS'];

@Injectable()
export class EligibilityService {
  private readonly logger = new Logger(EligibilityService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly systemConfig: SystemConfigService,
    private readonly audit: AuditLogService,
  ) {}

  /**
   * Re-checks one candidate's progress against the current admin-configured
   * thresholds and promotes them to APPLICATION_ELIGIBLE if both are met.
   * Safe to call repeatedly/idempotently — it only ever moves a candidate
   * forward, and only from a small set of "in progress" statuses.
   */
  async checkAndPromote(userId: string): Promise<{ promoted: boolean }> {
    const user = await this.prisma.user.findUnique({ where: { id: userId } });
    if (!user || !PROMOTABLE_STATUSES.includes(user.status)) {
      return { promoted: false };
    }

    const [referralThreshold, challengeThreshold] = await Promise.all([
      this.systemConfig.getReferralThreshold(),
      this.systemConfig.getKycChallengeThreshold(),
    ]);

    const [creditedReferralCount, passedChallengeCount] = await Promise.all([
      this.prisma.referralCredit.count({ where: { referrerUserId: userId } }),
      // TOTAL passes, not distinct scenarios. Scenarios repeat, so the target
      // is reachable at any value regardless of how large the scenario bank
      // is — an admin can set 5 or 200 and candidates complete that many
      // reviews either way.
      this.prisma.challengeAttempt.count({
        where: { candidateUserId: userId, status: 'PASSED' },
      }),
    ]);

    const meetsReferralBar = creditedReferralCount >= referralThreshold;
    const meetsChallengeBar = passedChallengeCount >= challengeThreshold;

    if (!meetsReferralBar || !meetsChallengeBar) {
      // Not there yet — move to REFERRAL_IN_PROGRESS so the candidate's UI
      // can show partial progress, if they aren't already past that point.
      if (user.status === 'ACTIVE') {
        await this.prisma.user.update({
          where: { id: userId },
          data: { status: 'REFERRAL_IN_PROGRESS' },
        });
      }
      return { promoted: false };
    }

    await this.prisma.user.update({
      where: { id: userId },
      data: { status: 'APPLICATION_ELIGIBLE' },
    });

    await this.audit.record({
      actorUserId: userId,
      action: 'CANDIDATE_APPLICATION_ELIGIBLE',
      entityType: 'User',
      entityId: userId,
      metadata: {
        creditedReferralCount,
        passedChallengeCount,
        referralThreshold,
        challengeThreshold,
      },
    });

    this.logger.log(`User ${userId} reached APPLICATION_ELIGIBLE.`);
    return { promoted: true };
  }

  /** Read-only progress view for the candidate dashboard. */
  async getProgress(userId: string) {
    const [referralThreshold, challengeThreshold] = await Promise.all([
      this.systemConfig.getReferralThreshold(),
      this.systemConfig.getKycChallengeThreshold(),
    ]);

    const [creditedReferralCount, passedChallengeCount] = await Promise.all([
      this.prisma.referralCredit.count({ where: { referrerUserId: userId } }),
      this.prisma.challengeAttempt.count({
        where: { candidateUserId: userId, status: 'PASSED' },
      }),
    ]);

    return {
      referrals: { completed: creditedReferralCount, required: referralThreshold },
      kycChallenges: { completed: passedChallengeCount, required: challengeThreshold },
    };
  }
}
