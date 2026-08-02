import { prisma } from '@platform/database';
import { BotContext } from '../context';
import { checkDualMembership, evaluateActivationState } from '../services/activation';
import { evaluateFraud } from '../services/fraudScoring';
import { ACTIVATION_DUAL_MEMBERSHIP_HOURS } from '@platform/shared';

export async function handleVerifyMembership(ctx: BotContext) {
  const from = ctx.from;
  if (!from) return;
  await ctx.answerCbQuery();

  const user = await prisma.user.findUnique({ where: { telegramId: BigInt(from.id) } });
  if (!user) {
    await ctx.reply('Please start with /start REF_XXXXXXXX first.');
    return;
  }

  const { inChannel, inGroup } = await checkDualMembership(ctx.telegram, user.id);

  await evaluateFraud({ userId: user.id, ipHash: user.ipHash, deviceFingerprint: user.deviceFingerprint });
  await evaluateActivationState(user.id);

  if (inChannel && inGroup) {
    await ctx.reply(
      `Great, you're in both! Your ${ACTIVATION_DUAL_MEMBERSHIP_HOURS}-hour activation timer has started. ` +
        `We recheck every 6 hours — stay in both to activate automatically. Use /status anytime to check progress.`,
    );
  } else {
    const missing = [!inChannel ? 'the channel' : null, !inGroup ? 'the group' : null]
      .filter(Boolean)
      .join(' and ');
    await ctx.reply(`It looks like you haven't joined ${missing} yet. Please join and tap the button again.`);
  }
}
