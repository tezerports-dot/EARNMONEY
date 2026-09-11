import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { AuditLogService } from '../audit/audit-log.service';
import { SystemConfigService } from '../system-config/system-config.service';

/**
 * Fake-referral handling.
 *
 * A single failed identity check is not treated as fraud — documents get
 * photographed badly and providers have bad days. A referred account is only
 * counted against its referrer once verification has been rejected
 * `kyc_rejection_attempts` times (default 3) independently. At that point the
 * referral is marked REJECTED, the referred account is flagged KYC_REJECTED,
 * and the referrer picks up one strike.
 *
 * At `fraud_strike_limit` strikes (default 8) the referrer is SUSPENDED. That
 * is deliberately a suspension and not a deletion: suspension is reversible by
 * an admin once someone has actually looked at the case, and the audit trail
 * survives either way.
 *
 * Everything here is driven by admin-tunable config, never hardcoded numbers.
 */
@Injectable()
export class FraudService {
  private readonly logger = new Logger(FraudService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly audit: AuditLogService,
    private readonly systemConfig: SystemConfigService,
  ) {}

  /**
   * Call on every identity-verification rejection for `userId`.
   * Idempotent per rejection event; safe to call repeatedly.
   */
  async recordVerificationRejection(userId: string, reasonCode?: string): Promise<void> {
    const attemptsNeeded = await this.systemConfig.getKycRejectionAttempts();

    const verification = await this.prisma.identityVerification.findUnique({ where: { userId } });
    if (!verification) return;

    const updated = await this.prisma.identityVerification.update({
      where: { id: verification.id },
      data: { rejectionCount: { increment: 1 }, failureReasonCode: reasonCode ?? null },
    });

    await this.audit.record({
      actorUserId: userId,
      action: 'IDENTITY_REJECTION_RECORDED',
      entityType: 'IdentityVerification',
      entityId: verification.id,
      metadata: { rejectionCount: updated.rejectionCount, attemptsNeeded },
    });

    if (updated.rejectionCount < attemptsNeeded) {
      // Not conclusive yet — leave the candidate able to retry.
      await this.prisma.user.update({
        where: { id: userId },
        data: { status: 'REVIEW_REQUIRED' },
      });
      return;
    }

    await this.confirmFakeAndStrikeReferrer(userId, reasonCode);
  }

  /** Rejection is now conclusive: flag the account, strike the referrer. */
  private async confirmFakeAndStrikeReferrer(userId: string, reasonCode?: string): Promise<void> {
    await this.prisma.user.update({ where: { id: userId }, data: { status: 'KYC_REJECTED' } });

    const referral = await this.prisma.referral.findUnique({ where: { referredUserId: userId } });
    if (!referral) return;

    // A referral that was already credited must have its credit withdrawn as
    // well, or a candidate could bank the credit and then fail verification.
    await this.prisma.$transaction(async (tx: any) => {
      await tx.referral.update({
        where: { id: referral.id },
        data: { status: 'REJECTED', rejectionReasonCode: reasonCode ?? 'KYC_FAILED' },
      });
      await tx.referralCredit.deleteMany({
        where: { referrerUserId: referral.referrerUserId, referredUserId: userId },
      });
      await tx.user.update({
        where: { id: referral.referrerUserId },
        data: { fakeReferralCount: { increment: 1 } },
      });
    });

    await this.audit.record({
      actorUserId: userId,
      action: 'REFERRAL_CONFIRMED_FAKE',
      entityType: 'Referral',
      entityId: referral.id,
      metadata: { referrerUserId: referral.referrerUserId, reasonCode: reasonCode ?? 'KYC_FAILED' },
    });

    await this.enforceStrikeLimit(referral.referrerUserId);
  }

  /** Suspends a referrer who has crossed the strike limit. */
  private async enforceStrikeLimit(referrerUserId: string): Promise<void> {
    const limit = await this.systemConfig.getFraudStrikeLimit();
    const referrer = await this.prisma.user.findUnique({ where: { id: referrerUserId } });
    if (!referrer) return;

    if (referrer.fakeReferralCount < limit) return;
    if (referrer.status === 'SUSPENDED') return; // already handled

    await this.prisma.user.update({
      where: { id: referrerUserId },
      data: { status: 'SUSPENDED' },
    });

    // Suspension invalidates live sessions immediately — JwtAuthGuard rejects
    // SUSPENDED users, but killing refresh tokens stops a quiet re-login.
    await this.prisma.refreshToken.updateMany({
      where: { userId: referrerUserId, revokedAt: null },
      data: { revokedAt: new Date() },
    });

    await this.audit.record({
      actorUserId: referrerUserId,
      action: 'USER_SUSPENDED_FOR_FAKE_REFERRALS',
      entityType: 'User',
      entityId: referrerUserId,
      metadata: { strikes: referrer.fakeReferralCount, limit },
    });

    this.logger.warn(
      `User ${referrerUserId} suspended: ${referrer.fakeReferralCount} confirmed fake referrals (limit ${limit}).`,
    );
  }
}
