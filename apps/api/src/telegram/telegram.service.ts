import { BadRequestException, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { PrismaService } from '../prisma/prisma.service';
import { UsersService } from '../users/users.service';
import { AuditLogService } from '../audit/audit-log.service';
import { TelegramBotService } from './telegram-bot.service';
import { hashAadhaar } from '../common/identity/aadhaar.util';

/**
 * Candidate verification over Telegram, in the order the bot walks them through:
 *
 *   1. /start            → bot asks for the Aadhaar number they signed up with
 *   2. <12 digits>       → bot looks up the account by HMAC, never by plaintext
 *   3. share contact     → Telegram itself vouches that the number belongs to
 *                          this Telegram account; we compare it to the number
 *                          given at signup
 *   4. join both chats   → public chat must show membership; private chat
 *                          accepts a pending join request
 *   5. "confirm" / poll  → once both are satisfied the account is activated
 *
 * Step 3 is the security-carrying one. A candidate cannot type a number they
 * do not control: `contact.phone_number` is attached by Telegram's servers,
 * and we additionally require `contact.user_id` to equal the sender, which is
 * what stops someone forwarding a friend's contact card.
 */
@Injectable()
export class TelegramService {
  private readonly logger = new Logger(TelegramService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly users: UsersService,
    private readonly audit: AuditLogService,
    private readonly config: ConfigService,
    private readonly bot: TelegramBotService,
  ) {}

  /** Chats a candidate must be in. Configuration error if either is unset. */
  private requiredChats(): { publicChatId: bigint; privateChatId: bigint } {
    const publicChatId = this.config.get<bigint>('telegram.publicChatId');
    const privateChatId = this.config.get<bigint>('telegram.privateChatId');
    if (publicChatId === undefined || privateChatId === undefined) {
      // Never fall through to "no chats required = step satisfied". That would
      // silently disable the whole gate on a half-configured deployment.
      throw new Error(
        'TELEGRAM_PUBLIC_CHAT_ID and TELEGRAM_PRIVATE_CHAT_ID must both be set. Refusing to treat the Telegram step as satisfied while they are missing.',
      );
    }
    return { publicChatId, privateChatId };
  }

  /** What the app shows on the "verify on Telegram" screen. */
  async getLinkInfo(userId: string) {
    const botUsername = this.config.get<string>('telegram.botUsername');
    if (!botUsername) {
      throw new Error('TELEGRAM_BOT_USERNAME is not set — cannot build a usable bot deep link.');
    }
    const account = await this.prisma.telegramAccount.findUnique({ where: { userId } });
    return {
      botLink: `https://t.me/${botUsername}`,
      botUsername,
      publicChatInviteLink: this.config.get<string>('telegram.publicChatInviteLink') ?? null,
      privateChatInviteLink: this.config.get<string>('telegram.privateChatInviteLink') ?? null,
      connected: !!account && account.status === 'CONNECTED',
      contactVerified: !!account?.contactVerifiedAt,
    };
  }

  /** Per-candidate progress, so the app can render a live checklist. */
  async getVerificationState(userId: string) {
    const { publicChatId, privateChatId } = this.requiredChats();
    const [user, account, memberships] = await Promise.all([
      this.prisma.user.findUnique({ where: { id: userId } }),
      this.prisma.telegramAccount.findUnique({ where: { userId } }),
      this.prisma.telegramMembership.findMany({ where: { userId } }),
    ]);

    const inPublic = memberships.some(
      (m: { telegramChatId: bigint; status: string }) =>
        m.telegramChatId === publicChatId && m.status === 'APPROVED',
    );
    // A pending request is enough for the private chat by design — approval
    // there is a human decision that can lag by hours.
    const inPrivate = memberships.some(
      (m: { telegramChatId: bigint; status: string }) =>
        m.telegramChatId === privateChatId && ['APPROVED', 'REQUESTED'].includes(m.status),
    );

    return {
      botStarted: !!account,
      contactVerified: !!account?.contactVerifiedAt,
      joinedPublicChat: inPublic,
      joinedPrivateChat: inPrivate,
      complete: !!account?.contactVerifiedAt && inPublic && inPrivate,
      userStatus: user?.status ?? null,
    };
  }

  /**
   * Every Telegram update lands here. Deliberately tolerant of shapes we do
   * not handle: a webhook that 500s makes Telegram retry and eventually
   * disable itself.
   */
  async handleUpdate(update: any): Promise<void> {
    try {
      if (update.message?.contact) {
        await this.handleSharedContact(update.message);
        return;
      }
      if (update.message?.text) {
        await this.handleText(update.message);
        return;
      }
      if (update.chat_member) {
        await this.handleChatMemberUpdate(update.chat_member);
        return;
      }
      if (update.chat_join_request) {
        await this.handleJoinRequest(update.chat_join_request);
        return;
      }
    } catch (err) {
      // Swallow and log: Telegram must always get its 200.
      this.logger.error(`Failed handling update: ${err}`);
    }
  }

  private async handleText(message: any): Promise<void> {
    const telegramUserId = BigInt(message.from.id);
    const text = (message.text as string).trim();

    if (text.startsWith('/start')) {
      await this.bot.sendMessage(
        telegramUserId,
        'Welcome to BBAZAAR group of companies.\n\nReply with the 12-digit Aadhaar number you used to sign up in the app, and I will connect this Telegram account to it.',
      );
      return;
    }

    const digits = text.replace(/\s|-/g, '');
    if (/^[0-9]{12}$/.test(digits)) {
      await this.bindByAadhaar(telegramUserId, digits, message.from.username ?? null);
      return;
    }

    if (/^confirm$/i.test(text)) {
      await this.recheckAndReport(telegramUserId);
      return;
    }

    await this.bot.sendMessage(
      telegramUserId,
      'Please reply with your 12-digit Aadhaar number, or type "confirm" once you have joined both channels.',
    );
  }

  /**
   * Looks up the signup by Aadhaar hash. The number is hashed on arrival and
   * the plaintext never leaves this function.
   */
  private async bindByAadhaar(
    telegramUserId: bigint,
    aadhaarDigits: string,
    username: string | null,
  ): Promise<void> {
    const pepper = this.config.get<string>('identity.aadhaarHashPepper') ?? '';
    let aadhaarHash: string;
    try {
      aadhaarHash = hashAadhaar(aadhaarDigits, pepper);
    } catch {
      await this.bot.sendMessage(telegramUserId, 'That does not look like a valid Aadhaar number. Please check and send it again.');
      return;
    }

    const user = await this.prisma.user.findUnique({ where: { aadhaarHash } });
    if (!user) {
      // Same message whether the number is unregistered or malformed — the bot
      // must not become a way to test which Aadhaar numbers hold accounts.
      await this.bot.sendMessage(
        telegramUserId,
        'No account was found for that number. Please sign up in the BBAZAAR app first, then come back here.',
      );
      return;
    }

    // One Telegram account cannot serve two candidates.
    const existingForTelegram = await this.prisma.telegramAccount.findUnique({
      where: { telegramUserId },
    });
    if (existingForTelegram && existingForTelegram.userId !== user.id) {
      await this.bot.sendMessage(
        telegramUserId,
        'This Telegram account is already linked to a different candidate.',
      );
      return;
    }

    // ...and one candidate cannot hop between Telegram accounts once verified.
    const existingForUser = await this.prisma.telegramAccount.findUnique({
      where: { userId: user.id },
    });
    if (
      existingForUser &&
      existingForUser.telegramUserId !== telegramUserId &&
      existingForUser.contactVerifiedAt
    ) {
      await this.bot.sendMessage(
        telegramUserId,
        'This account has already been verified from another Telegram account.',
      );
      return;
    }

    await this.prisma.telegramAccount.upsert({
      where: { userId: user.id },
      update: { telegramUserId, telegramUsername: username, status: 'PENDING' },
      create: { userId: user.id, telegramUserId, telegramUsername: username, status: 'PENDING' },
    });

    await this.audit.record({
      actorUserId: user.id,
      action: 'TELEGRAM_AADHAAR_MATCHED',
      entityType: 'TelegramAccount',
      entityId: user.id,
    });

    await this.bot.sendMessageWithContactButton(
      telegramUserId,
      'Account found. Now tap the button below to share your contact, so we can confirm this Telegram account uses your Aadhaar-linked mobile number.',
    );
  }

  /**
   * Telegram attaches `phone_number` itself, so this is evidence rather than
   * user input — provided we check `contact.user_id` is the sender, which
   * stops a forwarded contact card from passing as the sender's own.
   */
  private async handleSharedContact(message: any): Promise<void> {
    const telegramUserId = BigInt(message.from.id);
    const contact = message.contact;

    if (!contact.user_id || BigInt(contact.user_id) !== telegramUserId) {
      await this.bot.sendMessage(
        telegramUserId,
        'Please share your own contact using the button, not another person’s contact card.',
      );
      return;
    }

    const account = await this.prisma.telegramAccount.findUnique({ where: { telegramUserId } });
    if (!account) {
      await this.bot.sendMessage(telegramUserId, 'Please send your Aadhaar number first.');
      return;
    }

    const user = await this.prisma.user.findUnique({ where: { id: account.userId } });
    if (!user) return;

    if (normalisePhone(contact.phone_number) !== normalisePhone(user.mobileE164)) {
      await this.audit.record({
        actorUserId: user.id,
        action: 'TELEGRAM_CONTACT_MISMATCH',
        entityType: 'TelegramAccount',
        entityId: account.id,
      });
      await this.bot.sendMessage(
        telegramUserId,
        'The mobile number on this Telegram account does not match the number you signed up with. Both must be the number linked to your Aadhaar.',
      );
      return;
    }

    await this.prisma.telegramAccount.update({
      where: { id: account.id },
      data: { contactVerifiedAt: new Date(), status: 'CONNECTED' },
    });

    await this.audit.record({
      actorUserId: user.id,
      action: 'TELEGRAM_CONTACT_VERIFIED',
      entityType: 'TelegramAccount',
      entityId: account.id,
    });

    if (user.status === 'TELEGRAM_PENDING') {
      await this.prisma.user.update({ where: { id: user.id }, data: { status: 'GROUP_PENDING' } });
    }

    const pub = this.config.get<string>('telegram.publicChatInviteLink') ?? '(link not configured)';
    const priv = this.config.get<string>('telegram.privateChatInviteLink') ?? '(link not configured)';
    await this.bot.sendMessage(
      telegramUserId,
      `Number confirmed.\n\nLast step — join both of these:\n1. ${pub}\n2. ${priv}\n\nThe second one needs admin approval; sending the request is enough. Type "confirm" when you have done both.`,
    );
  }

  private async handleChatMemberUpdate(chatMember: any): Promise<void> {
    const telegramUserId = BigInt(chatMember.new_chat_member.user.id);
    const chatId = BigInt(chatMember.chat.id);
    const status = chatMember.new_chat_member.status as string;

    const account = await this.prisma.telegramAccount.findUnique({ where: { telegramUserId } });
    if (!account) return;

    const isMember = ['member', 'administrator', 'creator'].includes(status);
    const hasLeft = ['left', 'kicked'].includes(status);

    await this.prisma.telegramMembership.upsert({
      where: { userId_telegramChatId: { userId: account.userId, telegramChatId: chatId } },
      update: {
        status: isMember ? 'APPROVED' : hasLeft ? 'LEFT' : 'REQUESTED',
        joinedAt: isMember ? new Date() : undefined,
        leftAt: hasLeft ? new Date() : undefined,
      },
      create: {
        userId: account.userId,
        telegramChatId: chatId,
        chatType: chatMember.chat.type === 'channel' ? 'CHANNEL' : 'GROUP',
        status: isMember ? 'APPROVED' : 'REQUESTED',
        joinedAt: isMember ? new Date() : undefined,
      },
    });

    await this.tryActivate(account.userId, telegramUserId);
  }

  /**
   * Records the request without approving it. Who gets into a group carrying
   * the company's name stays a human decision.
   */
  private async handleJoinRequest(joinRequest: any): Promise<void> {
    const telegramUserId = BigInt(joinRequest.from.id);
    const chatId = BigInt(joinRequest.chat.id);

    const account = await this.prisma.telegramAccount.findUnique({ where: { telegramUserId } });
    if (!account) return;

    await this.prisma.telegramMembership.upsert({
      where: { userId_telegramChatId: { userId: account.userId, telegramChatId: chatId } },
      update: { status: 'REQUESTED' },
      create: {
        userId: account.userId,
        telegramChatId: chatId,
        chatType: 'GROUP',
        status: 'REQUESTED',
      },
    });

    await this.tryActivate(account.userId, telegramUserId);
  }

  /** "confirm" in chat: re-read membership from Telegram, then report back. */
  private async recheckAndReport(telegramUserId: bigint): Promise<void> {
    const account = await this.prisma.telegramAccount.findUnique({ where: { telegramUserId } });
    if (!account) {
      await this.bot.sendMessage(telegramUserId, 'Please send your Aadhaar number first.');
      return;
    }
    if (!account.contactVerifiedAt) {
      await this.bot.sendMessage(telegramUserId, 'Please share your contact first, using the button above.');
      return;
    }

    const { publicChatId, privateChatId } = this.requiredChats();

    // Ask Telegram directly rather than trusting our own mirror: chat_member
    // updates can be missed while the webhook is down.
    for (const [chatId, chatType] of [
      [publicChatId, 'CHANNEL'],
      [privateChatId, 'GROUP'],
    ] as const) {
      const member = await this.bot.getChatMember(chatId, telegramUserId);
      if (!member) continue;
      const isMember = ['member', 'administrator', 'creator'].includes(member.status);
      if (!isMember) continue;
      await this.prisma.telegramMembership.upsert({
        where: { userId_telegramChatId: { userId: account.userId, telegramChatId: chatId } },
        update: { status: 'APPROVED', joinedAt: new Date() },
        create: {
          userId: account.userId,
          telegramChatId: chatId,
          chatType,
          status: 'APPROVED',
          joinedAt: new Date(),
        },
      });
    }

    const activated = await this.tryActivate(account.userId, telegramUserId);
    if (!activated) {
      const state = await this.getVerificationState(account.userId);
      const missing = [
        state.joinedPublicChat ? null : 'the public channel',
        state.joinedPrivateChat ? null : 'the private channel',
      ].filter(Boolean);
      await this.bot.sendMessage(
        telegramUserId,
        `Not done yet — still waiting on: ${missing.join(' and ')}. Join and type "confirm" again.`,
      );
    }
  }

  /** Activates only when every step is genuinely satisfied. Idempotent. */
  private async tryActivate(userId: string, telegramUserId: bigint): Promise<boolean> {
    const state = await this.getVerificationState(userId);
    if (!state.complete) return false;

    const user = await this.prisma.user.findUnique({ where: { id: userId } });
    if (!user) return false;
    if (user.status === 'GROUP_PENDING') {
      await this.users.markTelegramVerified(userId);
      await this.bot.sendMessage(
        telegramUserId,
        'You are verified. You can now log in to the BBAZAAR app with your mobile number and password.',
      );
    }
    return true;
  }

  /** App-side "I've joined, check again" button. */
  async recheckForUser(userId: string) {
    const account = await this.prisma.telegramAccount.findUnique({ where: { userId } });
    if (!account) {
      throw new BadRequestException('Start the Telegram bot and send your Aadhaar number first.');
    }
    await this.recheckAndReport(account.telegramUserId);
    return this.getVerificationState(userId);
  }
}

/** Compares phone numbers by their last 10 digits, so +91/0/spacing agree. */
function normalisePhone(raw: string): string {
  return raw.replace(/\D/g, '').slice(-10);
}
