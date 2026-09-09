import { BadRequestException, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { randomBytes } from 'crypto';
import { PrismaService } from '../prisma/prisma.service';
import { UsersService } from '../users/users.service';
import { AuditLogService } from '../audit/audit-log.service';
import { TelegramBotService } from './telegram-bot.service';

const LINK_TOKEN_TTL_MINUTES = 30;

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

  /** Candidate calls this to get a deep link that binds their Telegram account. */
  async createLinkToken(userId: string): Promise<{ deepLink: string; expiresAt: Date }> {
    const user = await this.prisma.user.findUnique({ where: { id: userId } });
    if (!user || user.status !== 'TELEGRAM_PENDING') {
      throw new BadRequestException('Telegram binding is not applicable at this stage.');
    }

    const token = randomBytes(16).toString('hex');
    const expiresAt = new Date(Date.now() + LINK_TOKEN_TTL_MINUTES * 60 * 1000);

    await this.prisma.telegramLinkToken.create({ data: { userId, token, expiresAt } });

    const botUsername = this.config.get<string>('telegram.botUsername') ?? 'your_bot';
    return { deepLink: `https://t.me/${botUsername}?start=${token}`, expiresAt };
  }

  /**
   * Entry point for every Telegram webhook update. Kept deliberately
   * tolerant of unrecognized update shapes — Telegram sends many update
   * types we don't act on, and a webhook endpoint must never 500 on those,
   * or Telegram will keep retrying and eventually disable the webhook.
   */
  async handleUpdate(update: any): Promise<void> {
    if (update.message?.text?.startsWith('/start')) {
      await this.handleStartCommand(update.message);
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
    // Anything else (edited_message, my_chat_member, etc.) is ignored by design.
  }

  private async handleStartCommand(message: any): Promise<void> {
    const token = (message.text as string).split(' ')[1]?.trim();
    const telegramUserId = BigInt(message.from.id);

    if (!token) {
      await this.bot.sendMessage(
        telegramUserId,
        'Please use the link provided in the app to connect your account.',
      );
      return;
    }

    const linkToken = await this.prisma.telegramLinkToken.findUnique({ where: { token } });
    if (!linkToken || linkToken.consumedAt || linkToken.expiresAt < new Date()) {
      await this.bot.sendMessage(telegramUserId, 'This link has expired. Please request a new one in the app.');
      return;
    }

    const existingBinding = await this.prisma.telegramAccount.findUnique({ where: { telegramUserId } });
    if (existingBinding && existingBinding.userId !== linkToken.userId) {
      await this.bot.sendMessage(telegramUserId, 'This Telegram account is already linked to a different candidate.');
      return;
    }

    await this.prisma.$transaction(async (tx: any) => {
      await tx.telegramLinkToken.update({ where: { id: linkToken.id }, data: { consumedAt: new Date() } });
      await tx.telegramAccount.upsert({
        where: { userId: linkToken.userId },
        update: {
          telegramUserId,
          telegramUsername: message.from.username ?? null,
          contactVerifiedAt: new Date(),
          status: 'CONNECTED',
        },
        create: {
          userId: linkToken.userId,
          telegramUserId,
          telegramUsername: message.from.username ?? null,
          contactVerifiedAt: new Date(),
          status: 'CONNECTED',
        },
      });
      await tx.user.update({ where: { id: linkToken.userId }, data: { status: 'GROUP_PENDING' } });
    });

    await this.audit.record({
      actorUserId: linkToken.userId,
      action: 'TELEGRAM_ACCOUNT_CONNECTED',
      entityType: 'User',
      entityId: linkToken.userId,
    });

    const requiredChats = this.config.get<bigint[]>('telegram.requiredChatIds') ?? [];
    const chatList = requiredChats.length > 0 ? '\n\nNext, join the required group(s)/channel(s) from the app.' : '';
    await this.bot.sendMessage(telegramUserId, `Account connected.${chatList}`);
  }

  private async handleChatMemberUpdate(chatMember: any): Promise<void> {
    const telegramUserId = BigInt(chatMember.new_chat_member.user.id);
    const chatId = BigInt(chatMember.chat.id);
    const status = chatMember.new_chat_member.status as string;

    const account = await this.prisma.telegramAccount.findUnique({ where: { telegramUserId } });
    if (!account) return; // membership change for someone who hasn't bound an account — ignore

    const isMember = ['member', 'administrator', 'creator'].includes(status);

    await this.prisma.telegramMembership.upsert({
      where: { userId_telegramChatId: { userId: account.userId, telegramChatId: chatId } },
      update: {
        status: isMember ? 'APPROVED' : status === 'left' || status === 'kicked' ? 'LEFT' : 'REQUESTED',
        joinedAt: isMember ? new Date() : undefined,
        leftAt: !isMember ? new Date() : undefined,
      },
      create: {
        userId: account.userId,
        telegramChatId: chatId,
        chatType: chatMember.chat.type === 'channel' ? 'CHANNEL' : 'GROUP',
        status: isMember ? 'APPROVED' : 'REQUESTED',
        joinedAt: isMember ? new Date() : undefined,
      },
    });

    if (isMember) {
      await this.checkAllRequiredChatsJoined(account.userId);
    }
  }

  /**
   * Deliberately does NOT auto-approve join requests — that's left to
   * whoever administers the actual Telegram group, so a human stays in the
   * loop on who gets into a group carrying the institute's name. We just
   * record that a request happened; approval arrives later as a
   * `chat_member` update once a group admin acts on it.
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
  }

  private async checkAllRequiredChatsJoined(userId: string): Promise<void> {
    const requiredChatIds = this.config.get<bigint[]>('telegram.requiredChatIds') ?? [];
    if (requiredChatIds.length === 0) {
      this.logger.warn('TELEGRAM_REQUIRED_CHAT_IDS is empty — treating Telegram step as satisfied by default.');
      await this.users.markTelegramVerified(userId);
      return;
    }

    const memberships = await this.prisma.telegramMembership.findMany({
      where: { userId, telegramChatId: { in: requiredChatIds }, status: 'APPROVED' },
    });

    if (memberships.length >= requiredChatIds.length) {
      await this.users.markTelegramVerified(userId);
    }
  }
}
