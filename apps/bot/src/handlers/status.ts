import { prisma } from '@platform/database';
import { BotContext } from '../context';
import { currentMonthIst } from '@platform/shared';

export async function handleStatus(ctx: BotContext) {
  const from = ctx.from;
  if (!from) return;

  const user = await prisma.user.findUnique({ where: { telegramId: BigInt(from.id) } });
  if (!user) {
    await ctx.reply('Please start with /start REF_XXXXXXXX first.');
    return;
  }

  // Read cached counts (refreshed once daily by the worker) rather than
  // computing live — keeps this fast even with a very large referral tree.
  const thisMonthPayout = await prisma.monthlyPayout.findUnique({
    where: { userId_month: { userId: user.id, month: currentMonthIst() } },
  });

  const asOf = user.statusCachedAt ? new Date(user.statusCachedAt).toLocaleString('en-IN') : 'not yet calculated';

  await ctx.reply(
    `Referral code: ${user.referralCode}\n` +
      `Status: ${user.status}\n` +
      `Active referrals: ${user.cachedActiveReferralCount}\n` +
      `Eligible for this month's payout: ${user.cachedPayoutEligibleReferralCount}\n` +
      `This month's payout: ${thisMonthPayout ? `₹${thisMonthPayout.totalAmountInr} (${thisMonthPayout.status})` : 'not calculated yet'}\n\n` +
      `(Numbers as of ${asOf}, refreshed daily. A referral only counts toward a month's payout ` +
      `if they were active by the 15th of that month.)\n\n` +
      `Check full history anytime at the website using your referral code.`,
  );
}
