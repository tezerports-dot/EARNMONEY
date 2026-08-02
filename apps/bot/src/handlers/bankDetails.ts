import { z } from 'zod';
import { prisma } from '@platform/database';
import { BotContext } from '../context';

const accountNumberSchema = z.string().regex(/^\d{6,20}$/, 'Account number must be 6-20 digits');
const ifscSchema = z.string().regex(/^[A-Z]{4}0[A-Z0-9]{6}$/, 'IFSC must look like HDFC0001234');

export async function startBankDetails(ctx: BotContext) {
  const from = ctx.from;
  if (!from) return;
  const user = await prisma.user.findUnique({ where: { telegramId: BigInt(from.id) } });
  if (!user) {
    await ctx.reply('Please start with /start REF_XXXXXXXX first.');
    return;
  }
  ctx.session.bankDetailsStep = 'AWAITING_HOLDER_NAME';
  ctx.session.bankDetailsDraft = {};
  await ctx.reply(
    "Let's set up your payout account. First, what is the account holder's full name (as it appears on your bank account)?",
  );
}

/** Continues an in-progress /bankdetails conversation. Returns true if it handled the message. */
export async function continueBankDetails(ctx: BotContext): Promise<boolean> {
  const step = ctx.session.bankDetailsStep;
  if (!step) return false;

  const message = ctx.message;
  const text = message && 'text' in message ? message.text.trim() : '';

  if (step === 'AWAITING_HOLDER_NAME') {
    if (text.length < 2) {
      await ctx.reply('Please enter a valid full name.');
      return true;
    }
    ctx.session.bankDetailsDraft.bankAccountHolder = text;
    ctx.session.bankDetailsStep = 'AWAITING_ACCOUNT_NUMBER';
    await ctx.reply('Got it. Now enter your bank account number (digits only):');
    return true;
  }

  if (step === 'AWAITING_ACCOUNT_NUMBER') {
    const parsed = accountNumberSchema.safeParse(text.replace(/\s/g, ''));
    if (!parsed.success) {
      await ctx.reply('That doesn\'t look like a valid account number. Please enter 6-20 digits only.');
      return true;
    }
    ctx.session.bankDetailsDraft.bankAccountNumber = parsed.data;
    ctx.session.bankDetailsStep = 'AWAITING_IFSC';
    await ctx.reply('Now enter your bank IFSC code (e.g. HDFC0001234):');
    return true;
  }

  if (step === 'AWAITING_IFSC') {
    const parsed = ifscSchema.safeParse(text.toUpperCase());
    if (!parsed.success) {
      await ctx.reply('That doesn\'t look like a valid IFSC code. Please try again (e.g. HDFC0001234):');
      return true;
    }
    ctx.session.bankDetailsDraft.bankIfsc = parsed.data;
    ctx.session.bankDetailsStep = 'AWAITING_UPI_OPTIONAL';
    await ctx.reply('Optional: send your UPI ID (e.g. name@bank), or send "skip" to leave it blank.');
    return true;
  }

  if (step === 'AWAITING_UPI_OPTIONAL') {
    const from = ctx.from;
    if (!from) return true;
    const upi = text.toLowerCase() === 'skip' ? null : text;

    const user = await prisma.user.findUnique({ where: { telegramId: BigInt(from.id) } });
    if (!user) return true;

    await prisma.user.update({
      where: { id: user.id },
      data: {
        bankAccountHolder: ctx.session.bankDetailsDraft.bankAccountHolder,
        bankAccountNumber: ctx.session.bankDetailsDraft.bankAccountNumber,
        bankIfsc: ctx.session.bankDetailsDraft.bankIfsc,
        bankUpiId: upi,
      },
    });

    ctx.session.bankDetailsStep = null;
    ctx.session.bankDetailsDraft = {};
    await ctx.reply('Your bank details have been saved. You will be paid to this account in the monthly payout run.');
    return true;
  }

  return false;
}
