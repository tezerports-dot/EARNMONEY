import { Markup } from 'telegraf';
import { createHash } from 'crypto';
import { prisma } from '@platform/database';
import { BotContext } from '../context';
import { assignShards, NoAvailableChannelError, NoAvailableGroupError } from '../services/shardAssignment';

function normalizePhone(raw: string): string {
  return raw.replace(/[^\d+]/g, '');
}

export async function handleContact(ctx: BotContext) {
  const from = ctx.from;
  const message = ctx.message;
  if (!from || !message || !('contact' in message)) return;

  const contact = message.contact;
  if (contact.user_id !== from.id) {
    await ctx.reply('Please share your own contact, not someone else’s.');
    return;
  }

  const user = await prisma.user.findUnique({ where: { telegramId: BigInt(from.id) } });
  if (!user) {
    await ctx.reply('Please start with /start REF_XXXXXXXX first.');
    return;
  }

  const phoneNumber = normalizePhone(contact.phone_number);

  // One phone number = one referral account.
  const phoneOwner = await prisma.user.findUnique({ where: { phoneNumber } });
  if (phoneOwner && phoneOwner.id !== user.id) {
    await ctx.reply('This phone number is already linked to another account. Each phone number can only be used once.');
    return;
  }

  // Best-effort IP/device fingerprint hash placeholder (Telegram bots don't
  // get IP addresses directly; if you front the bot with a webhook behind
  // Nginx, forward X-Forwarded-For into a header your webhook route reads
  // and hash it here instead of this placeholder).
  const ipHash = createHash('sha256').update(`tg:${from.id}`).digest('hex').slice(0, 32);

  await prisma.user.update({
    where: { id: user.id },
    data: { phoneNumber, ipHash },
  });

  try {
    const { channelInviteLink, groupInviteLink } = await assignShards(user.id);

    await ctx.reply(
      'Thanks! You are verified. Please join BOTH of the following to activate your account:\n\n' +
        `📢 Channel: ${channelInviteLink}\n` +
        `👥 Group: ${groupInviteLink}\n\n` +
        'Once you have joined both, tap the button below to confirm.',
      Markup.removeKeyboard(),
    );
    await ctx.reply(
      'Confirm membership',
      Markup.inlineKeyboard([Markup.button.callback('✅ I joined both', 'verify_membership')]),
    );
  } catch (err) {
    if (err instanceof NoAvailableChannelError || err instanceof NoAvailableGroupError) {
      await ctx.reply(
        'We are at capacity right now and adding new shards shortly. Please try again in a few minutes.',
      );
    } else {
      throw err;
    }
  }
}
