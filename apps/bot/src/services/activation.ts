import { Telegram } from 'telegraf';
import { prisma } from '@platform/database';
import {
  ACTIVATION_DUAL_MEMBERSHIP_HOURS,
  DEACTIVATION_ABSENCE_HOURS,
  FRAUD_THRESHOLDS,
} from '@platform/shared';

const HOUR_MS = 60 * 60 * 1000;

/**
 * Checks a user's membership in BOTH their assigned channel and group via
 * ctx.telegram.getChatMember, updating channelLastSeenAt/groupLastSeenAt.
 * Returns whether the user is currently present in both.
 */
export async function checkDualMembership(
  telegram: Telegram,
  userId: string,
): Promise<{ inChannel: boolean; inGroup: boolean }> {
  const user = await prisma.user.findUnique({
    where: { id: userId },
    include: { assignedChannel: true, assignedGroup: true },
  });
  if (!user || !user.assignedChannel || !user.assignedGroup) {
    return { inChannel: false, inGroup: false };
  }

  const activeStatuses = new Set(['creator', 'administrator', 'member', 'restricted']);

  let inChannel = false;
  let inGroup = false;

  try {
    const member = await telegram.getChatMember(
      Number(user.assignedChannel.telegramChatId),
      Number(user.telegramId),
    );
    inChannel = activeStatuses.has(member.status);
  } catch {
    inChannel = false;
  }

  try {
    const member = await telegram.getChatMember(
      Number(user.assignedGroup.telegramChatId),
      Number(user.telegramId),
    );
    inGroup = activeStatuses.has(member.status);
  } catch {
    inGroup = false;
  }

  const now = new Date();
  await prisma.user.update({
    where: { id: user.id },
    data: {
      channelJoinedAt: inChannel && !user.channelJoinedAt ? now : user.channelJoinedAt,
      groupJoinedAt: inGroup && !user.groupJoinedAt ? now : user.groupJoinedAt,
      channelLastSeenAt: inChannel ? now : user.channelLastSeenAt,
      groupLastSeenAt: inGroup ? now : user.groupLastSeenAt,
    },
  });

  return { inChannel, inGroup };
}

/**
 * Evaluates one user against the activation/deactivation rules (Section 3).
 * Intended to be called both right after a membership check action and by
 * the 6-hourly worker job for every JOINING/ACTIVE user.
 */
export async function evaluateActivationState(userId: string): Promise<void> {
  const user = await prisma.user.findUnique({ where: { id: userId } });
  if (!user) return;
  if (user.status === 'SUSPENDED') return; // fraud suspension is final until admin action

  const now = Date.now();

  // ---- Deactivation checks first ----
  if (user.status === 'ACTIVE') {
    const channelAbsentMs = user.channelLastSeenAt
      ? now - user.channelLastSeenAt.getTime()
      : Infinity;
    const groupAbsentMs = user.groupLastSeenAt ? now - user.groupLastSeenAt.getTime() : Infinity;

    const absentTooLong =
      channelAbsentMs >= DEACTIVATION_ABSENCE_HOURS * HOUR_MS ||
      groupAbsentMs >= DEACTIVATION_ABSENCE_HOURS * HOUR_MS;

    if (absentTooLong) {
      await prisma.user.update({
        where: { id: user.id },
        data: { status: 'INACTIVE', deactivatedAt: new Date() },
      });
      await prisma.auditLog.create({
        data: {
          action: 'USER_DEACTIVATED',
          targetType: 'User',
          targetId: user.id,
          metadata: { reason: 'absent_72h_from_channel_or_group' },
        },
      });
      return;
    }
  }

  // ---- Activation checks ----
  if (user.status === 'JOINING') {
    if (user.fraudScore >= FRAUD_THRESHOLDS.SUSPEND) return; // handled by fraud service already

    const channelOk =
      user.channelJoinedAt &&
      user.channelLastSeenAt &&
      now - user.channelJoinedAt.getTime() >= ACTIVATION_DUAL_MEMBERSHIP_HOURS * HOUR_MS;
    const groupOk =
      user.groupJoinedAt &&
      user.groupLastSeenAt &&
      now - user.groupJoinedAt.getTime() >= ACTIVATION_DUAL_MEMBERSHIP_HOURS * HOUR_MS;

    // Continuous presence proxy: last-seen must be recent (within one worker
    // interval) so a user who joined then immediately left doesn't qualify.
    const recentlySeenChannel =
      user.channelLastSeenAt && now - user.channelLastSeenAt.getTime() < 7 * HOUR_MS;
    const recentlySeenGroup =
      user.groupLastSeenAt && now - user.groupLastSeenAt.getTime() < 7 * HOUR_MS;

    if (channelOk && groupOk && recentlySeenChannel && recentlySeenGroup) {
      await prisma.user.update({
        where: { id: user.id },
        data: { status: 'ACTIVE', activatedAt: new Date() },
      });
      await prisma.auditLog.create({
        data: { action: 'USER_ACTIVATED', targetType: 'User', targetId: user.id },
      });
    }
  }
}
