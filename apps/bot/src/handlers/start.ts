import { Markup } from 'telegraf';
import { prisma } from '@platform/database';
import { BotContext } from '../context';
import { parseReferralParam, findReferrerByCode, generateUniqueReferralCode } from '../services/referral';

export async function handleStart(ctx: BotContext) {
  const from = ctx.from;
  if (!from) return;

  const existing = await prisma.user.findUnique({ where: { telegramId: BigInt(from.id) } });
  if (existing) {
    await ctx.reply(
      `Welcome back! Your referral code is ${existing.referralCode}.\n` +
        `Use /status to see your current standing, or /bankdetails to update your payout account.`,
    );
    return;
  }

  const messageText = 'text' in ctx.message! ? ctx.message.text : '';
  const startPayload = messageText.split(' ').slice(1).join(' ');
  const referralCode = parseReferralParam(startPayload);

  if (!referralCode) {
    await ctx.reply(
      "Welcome! To join, please use an invite link from an existing member (format: /start REF_XXXXXXXX). " +
        "If you don't have one, ask a friend already using the platform to invite you.",
    );
    return;
  }

  const referrer = await findReferrerByCode(referralCode);
  if (!referrer) {
    await ctx.reply('That referral code does not exist. Please double-check the link and try again.');
    return;
  }

  if (referrer.telegramId === BigInt(from.id)) {
    await ctx.reply("You can't refer yourself. Please use a link from a friend instead.");
    return;
  }

  // Create a PENDING user, referrer recorded once and never changed.
  const referralCodeForNewUser = await generateUniqueReferralCode();
  await prisma.user.create({
    data: {
      telegramId: BigInt(from.id),
      telegramUsername: from.username ?? null,
      languageCode: from.language_code ?? null,
      phoneNumber: `PENDING_${from.id}`, // placeholder until contact is shared; unique per user
      referralCode: referralCodeForNewUser,
      referredById: referrer.id,
      status: 'PENDING',
    },
  });

  await ctx.reply(
    'Thanks for joining! To finish setting up your account, please share your phone number using the button below.',
    Markup.keyboard([Markup.button.contactRequest('📱 Share my phone number')])
      .oneTime()
      .resize(),
  );
}
