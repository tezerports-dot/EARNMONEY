import { prisma } from '@platform/database';
import {
  FRAUD_WEIGHTS,
  FRAUD_THRESHOLDS,
  SAME_IP_ACCOUNTS_PER_DAY_THRESHOLD,
  MASS_REFERRAL_PER_DAY_THRESHOLD,
  RAPID_CYCLE_WINDOW_HOURS,
  RAPID_CYCLE_MIN_EVENTS,
} from '@platform/shared';
import type { FraudCheckInput, FraudCheckResult } from '@platform/shared';

function scoreToAction(score: number): FraudCheckResult['action'] {
  if (score >= FRAUD_THRESHOLDS.SUSPEND) return 'SUSPEND';
  if (score >= FRAUD_THRESHOLDS.FLAG_FOR_REVIEW) return 'FLAG';
  return 'NORMAL';
}

/**
 * Recomputes a user's fraud score from the four signals in the spec:
 *  - same IP creating 5+ accounts/day          (+20)
 *  - same device fingerprint reused             (+30)
 *  - rapid join/leave cycling                   (+25)
 *  - mass referral creation                      (+15)
 */
export async function evaluateFraud(input: FraudCheckInput): Promise<FraudCheckResult> {
  const user = await prisma.user.findUnique({ where: { id: input.userId } });
  if (!user) throw new Error('User not found for fraud evaluation');

  let score = 0;
  const reasons: string[] = [];
  const since24h = new Date(Date.now() - 24 * 60 * 60 * 1000);

  // Same IP creates 5+ accounts/day
  if (input.ipHash) {
    const sameIpCount = await prisma.user.count({
      where: { ipHash: input.ipHash, createdAt: { gte: since24h } },
    });
    if (sameIpCount >= SAME_IP_ACCOUNTS_PER_DAY_THRESHOLD) {
      score += FRAUD_WEIGHTS.SAME_IP_MULTI_ACCOUNT;
      reasons.push(`same_ip_${sameIpCount}_accounts_24h`);
    }
  }

  // Same device fingerprint reused across more than one account
  if (input.deviceFingerprint) {
    const sameDeviceCount = await prisma.user.count({
      where: { deviceFingerprint: input.deviceFingerprint },
    });
    if (sameDeviceCount > 1) {
      score += FRAUD_WEIGHTS.DEVICE_FINGERPRINT_REUSE;
      reasons.push(`device_fingerprint_reused_${sameDeviceCount}x`);
    }
  }

  // Rapid join/leave cycling: many join/leave transitions within the window.
  // We approximate "cycles" using how often channelLastSeenAt/groupLastSeenAt
  // has been reset relative to channelJoinedAt/groupJoinedAt within the window.
  const rapidCycleWindowStart = new Date(Date.now() - RAPID_CYCLE_WINDOW_HOURS * 60 * 60 * 1000);
  if (
    user.channelJoinedAt &&
    user.channelJoinedAt > rapidCycleWindowStart &&
    user.deactivatedAt &&
    user.deactivatedAt > rapidCycleWindowStart
  ) {
    // A user who has both joined and been deactivated within the same window
    // at least RAPID_CYCLE_MIN_EVENTS times is cycling. Since we don't keep a
    // separate event log table in this schema, we treat a single recent
    // deactivate-then-rejoin as one detected cycle event and flag repeats via
    // the audit log count.
    const recentCycleEvents = await prisma.auditLog.count({
      where: {
        targetId: user.id,
        targetType: 'User',
        action: { in: ['MEMBERSHIP_JOIN', 'MEMBERSHIP_LEAVE'] },
        createdAt: { gte: rapidCycleWindowStart },
      },
    });
    if (recentCycleEvents >= RAPID_CYCLE_MIN_EVENTS) {
      score += FRAUD_WEIGHTS.RAPID_JOIN_LEAVE_CYCLING;
      reasons.push(`rapid_cycle_${recentCycleEvents}_events_24h`);
    }
  }

  // Mass referral creation: this user referring an unusually large number of
  // accounts in a short period.
  const referralsLast24h = await prisma.user.count({
    where: { referredById: user.id, createdAt: { gte: since24h } },
  });
  if (referralsLast24h >= MASS_REFERRAL_PER_DAY_THRESHOLD) {
    score += FRAUD_WEIGHTS.MASS_REFERRAL_CREATION;
    reasons.push(`mass_referrals_${referralsLast24h}_24h`);
  }

  const action = scoreToAction(score);

  await prisma.user.update({
    where: { id: user.id },
    data: {
      fraudScore: score,
      status: action === 'SUSPEND' ? 'SUSPENDED' : user.status,
    },
  });

  if (action !== 'NORMAL') {
    await prisma.auditLog.create({
      data: {
        action: action === 'SUSPEND' ? 'FRAUD_AUTO_SUSPEND' : 'FRAUD_FLAGGED',
        targetType: 'User',
        targetId: user.id,
        metadata: { score, reasons },
      },
    });
  }

  return { score, reasons, action };
}
