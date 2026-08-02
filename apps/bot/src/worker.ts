import 'dotenv/config';
import cron from 'node-cron';
import { Telegram } from 'telegraf';
import { prisma } from '@platform/database';
import {
  PAYOUT_MIN_INR,
  PAYOUT_MAX_INR,
  getPayoutEligibilityCutoffUtc,
  currentMonthIst,
} from '@platform/shared';
import { checkDualMembership, evaluateActivationState } from './services/activation';
import { evaluateFraud } from './services/fraudScoring';
import { isMaintenanceMode } from './middleware/maintenance';

const BOT_TOKEN = process.env.BOT_TOKEN;
if (!BOT_TOKEN) {
  throw new Error('BOT_TOKEN is required. Set it in your .env file.');
}
const telegram = new Telegram(BOT_TOKEN);

/** Re-checks membership for every JOINING/ACTIVE user, then re-evaluates activation state. */
export async function runMembershipRevalidation(): Promise<void> {
  if (isMaintenanceMode()) {
    console.log('[worker] skipping membership revalidation — maintenance mode is on');
    return;
  }
  console.log(`[worker] membership revalidation started at ${new Date().toISOString()}`);
  const users = await prisma.user.findMany({
    where: { status: { in: ['JOINING', 'ACTIVE'] } },
    select: { id: true, ipHash: true, deviceFingerprint: true },
  });

  for (const user of users) {
    try {
      await checkDualMembership(telegram, user.id);
      await evaluateFraud({ userId: user.id, ipHash: user.ipHash, deviceFingerprint: user.deviceFingerprint });
      await evaluateActivationState(user.id);
    } catch (err) {
      console.error(`[worker] failed to revalidate user ${user.id}:`, err);
    }
  }
  console.log(`[worker] membership revalidation finished, processed ${users.length} users`);
}

/**
 * Recomputes every user's cached referral counts (real-time active count and
 * payout-eligible count for the current month) and writes them to
 * User.cachedActiveReferralCount / cachedPayoutEligibleReferralCount.
 *
 * The public website (/check) and the bot's /status command read ONLY these
 * cached fields — they never compute live counts on request — so the site
 * effectively "updates" once every 24 hours, which is what this job provides.
 *
 * Uses two groupBy aggregate queries (not one query per user) so this stays
 * cheap even at very large user counts.
 */
export async function runDailySnapshot(): Promise<{ updated: number }> {
  if (isMaintenanceMode()) {
    console.log('[worker] skipping daily snapshot — maintenance mode is on');
    return { updated: 0 };
  }
  console.log(`[worker] daily snapshot started at ${new Date().toISOString()}`);
  const month = currentMonthIst();
  const cutoff = getPayoutEligibilityCutoffUtc(month);

  const [activeCounts, eligibleCounts, allUsers] = await Promise.all([
    prisma.user.groupBy({
      by: ['referredById'],
      where: { status: 'ACTIVE', referredById: { not: null } },
      _count: { _all: true },
    }),
    prisma.user.groupBy({
      by: ['referredById'],
      where: { status: 'ACTIVE', referredById: { not: null }, activatedAt: { lte: cutoff } },
      _count: { _all: true },
    }),
    prisma.user.findMany({ select: { id: true } }),
  ]);

  const activeMap = new Map(activeCounts.map((r) => [r.referredById as string, r._count._all]));
  const eligibleMap = new Map(eligibleCounts.map((r) => [r.referredById as string, r._count._all]));

  let updated = 0;
  for (const { id } of allUsers) {
    await prisma.user.update({
      where: { id },
      data: {
        cachedActiveReferralCount: activeMap.get(id) ?? 0,
        cachedPayoutEligibleReferralCount: eligibleMap.get(id) ?? 0,
        statusCachedAt: new Date(),
      },
    });
    updated++;
  }

  console.log(`[worker] daily snapshot finished, updated ${updated} users`);
  return { updated };
}

/**
 * Creates one MonthlyPayout row per user with a payout-ELIGIBLE referral
 * count > 0, using the admin-set rate for the given month.
 *
 * Eligibility rule: a referral only counts toward MONTH's payout if that
 * referred user's `activatedAt` is on or before the 15th of MONTH, Indian
 * Standard Time (see packages/shared/src/payout.ts). A referral who
 * activates on the 23rd, for example, is excluded from that month's run
 * even though they are ACTIVE — they simply carry over and count starting
 * the following month if they're still active by its 15th.
 *
 * Idempotent: existing rows for the month are left untouched thanks to the
 * @@unique([userId, month]) constraint.
 */
export async function runMonthlyPayout(month: string, ratePerReferralInr: number): Promise<{ created: number }> {
  if (isMaintenanceMode()) {
    console.log('[worker] refusing to run monthly payout — maintenance mode is on');
    return { created: 0 };
  }
  if (ratePerReferralInr < PAYOUT_MIN_INR || ratePerReferralInr > PAYOUT_MAX_INR) {
    throw new Error(`ratePerReferralInr must be between ${PAYOUT_MIN_INR} and ${PAYOUT_MAX_INR}`);
  }

  const cutoff = getPayoutEligibilityCutoffUtc(month);
  console.log(
    `[worker] monthly payout run started for ${month} at rate ₹${ratePerReferralInr} ` +
      `(eligibility cutoff: activatedAt <= ${cutoff.toISOString()})`,
  );

  const usersWithEligibleReferrals = await prisma.user.findMany({
    where: { referrals: { some: { status: 'ACTIVE', activatedAt: { lte: cutoff } } } },
    select: { id: true, bankAccountHolder: true, bankAccountNumber: true, bankIfsc: true, bankUpiId: true },
  });

  let created = 0;
  for (const u of usersWithEligibleReferrals) {
    const activeReferralCount = await prisma.user.count({
      where: { referredById: u.id, status: 'ACTIVE', activatedAt: { lte: cutoff } },
    });
    if (activeReferralCount <= 0) continue;

    const totalAmountInr = ratePerReferralInr * activeReferralCount;

    try {
      await prisma.monthlyPayout.create({
        data: {
          userId: u.id,
          month,
          activeReferralCount,
          ratePerReferralInr,
          totalAmountInr,
          status: 'PENDING',
          bankAccountSnapshot: {
            bankAccountHolder: u.bankAccountHolder,
            bankAccountNumber: u.bankAccountNumber,
            bankIfsc: u.bankIfsc,
            bankUpiId: u.bankUpiId,
          },
        },
      });
      created++;
    } catch (err: unknown) {
      // Unique constraint violation means this user/month already has a row — skip.
      const message = err instanceof Error ? err.message : String(err);
      if (!message.includes('Unique constraint')) {
        console.error(`[worker] failed to create payout for user ${u.id}:`, err);
      }
    }
  }

  console.log(`[worker] monthly payout run finished for ${month}, created ${created} rows`);
  return { created };
}

async function getMonthlyRateOrDefault(month: string): Promise<number> {
  // The admin sets this via /admin/payouts. We look at the most recent
  // AuditLog entry recording a rate change for THIS month; if none exists
  // yet, default to the minimum allowed rate so the run never silently no-ops.
  const lastRateChange = await prisma.auditLog.findFirst({
    where: { action: 'PAYOUT_RATE_SET' },
    orderBy: { createdAt: 'desc' },
  });
  const metadata = lastRateChange?.metadata as { rate?: number; month?: string } | null;
  return metadata?.month === month ? (metadata?.rate ?? PAYOUT_MIN_INR) : PAYOUT_MIN_INR;
}

export function startScheduler() {
  // Every 6 hours: membership revalidation (fallback safety net; see
  // README for the event-driven chat_member webhook path, which is the
  // primary mechanism once configured).
  cron.schedule('0 */6 * * *', () => {
    runMembershipRevalidation().catch((err) => console.error('[worker] revalidation cron failed:', err));
  });

  // Once daily (~00:30 IST / 19:00 UTC): refresh the cached counts the
  // website and /status read from.
  cron.schedule('0 19 * * *', () => {
    runDailySnapshot().catch((err) => console.error('[worker] daily snapshot cron failed:', err));
  });

  // 30th of each month at ~09:00 IST (03:30 UTC): monthly payout run.
  // Months with fewer than 30 days (e.g. February) won't trigger this cron
  // tick — for those, use the "Run Monthly Payout" button in /admin/payouts
  // instead, which runs the exact same eligibility logic on demand.
  cron.schedule('30 3 30 * *', async () => {
    try {
      const month = currentMonthIst();
      const rate = await getMonthlyRateOrDefault(month);
      await runMonthlyPayout(month, rate);
    } catch (err) {
      console.error('[worker] monthly payout cron failed:', err);
    }
  });

  console.log(
    '[worker] scheduler started: revalidation every 6h, daily snapshot ~00:30 IST, payout run on the 30th (IST)',
  );
}

/** Starts cron + runs the initial passes. Safe to call from the standalone
 *  worker service OR from the combined runtime (apps/web/server.js). */
export function bootstrapWorker(): void {
  startScheduler();
  runMembershipRevalidation().catch((err) => console.error('[worker] initial revalidation failed:', err));
  runDailySnapshot().catch((err) => console.error('[worker] initial snapshot failed:', err));
}

if (require.main === module) {
  bootstrapWorker();
}
