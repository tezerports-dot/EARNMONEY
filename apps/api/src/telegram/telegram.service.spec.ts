import { Test } from '@nestjs/testing';
import { ConfigService } from '@nestjs/config';
import { TelegramService } from './telegram.service';
import { TelegramBotService } from './telegram-bot.service';
import { PrismaService } from '../prisma/prisma.service';
import { UsersService } from '../users/users.service';
import { AuditLogService } from '../audit/audit-log.service';
import { hashAadhaar } from '../common/identity/aadhaar.util';

const PEPPER = 'test-pepper-not-a-real-secret';
const VALID_AADHAAR = '234567890124';
const PUBLIC_CHAT = -1001111111111n;
const PRIVATE_CHAT = -1002222222222n;

describe('TelegramService', () => {
  let service: TelegramService;
  let prisma: any;
  let bot: any;
  let users: any;

  const config: Record<string, unknown> = {
    'identity.aadhaarHashPepper': PEPPER,
    'telegram.botUsername': 'bbazaar_bot',
    'telegram.publicChatId': PUBLIC_CHAT,
    'telegram.privateChatId': PRIVATE_CHAT,
    'telegram.publicChatInviteLink': 'https://t.me/bbazaar_public',
    'telegram.privateChatInviteLink': 'https://t.me/+privatehash',
  };

  beforeEach(async () => {
    prisma = {
      user: { findUnique: jest.fn(), update: jest.fn() },
      telegramAccount: { findUnique: jest.fn(), upsert: jest.fn(), update: jest.fn() },
      telegramMembership: { findMany: jest.fn().mockResolvedValue([]), upsert: jest.fn() },
    };
    bot = {
      sendMessage: jest.fn(),
      sendMessageWithContactButton: jest.fn(),
      getChatMember: jest.fn().mockResolvedValue(null),
    };
    users = { markTelegramVerified: jest.fn() };

    const moduleRef = await Test.createTestingModule({
      providers: [
        TelegramService,
        { provide: PrismaService, useValue: prisma },
        { provide: UsersService, useValue: users },
        { provide: AuditLogService, useValue: { record: jest.fn() } },
        { provide: ConfigService, useValue: { get: (k: string) => config[k] } },
        { provide: TelegramBotService, useValue: bot },
      ],
    }).compile();

    service = moduleRef.get(TelegramService);
  });

  describe('Aadhaar binding', () => {
    it('finds the account by hash and asks for a contact, never echoing the number', async () => {
      prisma.user.findUnique.mockResolvedValue({ id: 'user-1', mobileE164: '+919812345678' });
      prisma.telegramAccount.findUnique.mockResolvedValue(null);

      await service.handleUpdate({ message: { from: { id: 555 }, text: VALID_AADHAAR } });

      expect(prisma.user.findUnique).toHaveBeenCalledWith({
        where: { aadhaarHash: hashAadhaar(VALID_AADHAAR, PEPPER) },
      });
      expect(bot.sendMessageWithContactButton).toHaveBeenCalled();
      const said = bot.sendMessageWithContactButton.mock.calls[0][1];
      expect(said).not.toContain(VALID_AADHAAR);
    });

    it('gives the same answer for an unregistered number as for a malformed one', async () => {
      prisma.user.findUnique.mockResolvedValue(null);
      await service.handleUpdate({ message: { from: { id: 555 }, text: VALID_AADHAAR } });
      const unregistered = bot.sendMessage.mock.calls[0][1];

      bot.sendMessage.mockClear();
      await service.handleUpdate({ message: { from: { id: 555 }, text: '999999999999' } });
      const malformed = bot.sendMessage.mock.calls[0][1];

      // Otherwise the bot is an oracle for "does this Aadhaar have an account".
      expect(unregistered).toBe(malformed);
    });

    it('refuses to rebind a Telegram account already linked to someone else', async () => {
      prisma.user.findUnique.mockResolvedValue({ id: 'user-1' });
      prisma.telegramAccount.findUnique.mockResolvedValue({ userId: 'someone-else' });

      await service.handleUpdate({ message: { from: { id: 555 }, text: VALID_AADHAAR } });

      expect(prisma.telegramAccount.upsert).not.toHaveBeenCalled();
      expect(bot.sendMessage.mock.calls[0][1]).toMatch(/already linked/i);
    });
  });

  describe('shared contact', () => {
    const contactMessage = (phone: string, contactUserId?: number) => ({
      message: {
        from: { id: 555 },
        contact: { phone_number: phone, user_id: contactUserId ?? 555 },
      },
    });

    it('verifies when the shared number matches the signup number', async () => {
      prisma.telegramAccount.findUnique.mockResolvedValue({ id: 'tg-1', userId: 'user-1' });
      prisma.user.findUnique.mockResolvedValue({
        id: 'user-1',
        mobileE164: '+919812345678',
        status: 'TELEGRAM_PENDING',
      });

      await service.handleUpdate(contactMessage('+919812345678'));

      expect(prisma.telegramAccount.update).toHaveBeenCalledWith(
        expect.objectContaining({ data: expect.objectContaining({ status: 'CONNECTED' }) }),
      );
      expect(prisma.user.update).toHaveBeenCalledWith({
        where: { id: 'user-1' },
        data: { status: 'GROUP_PENDING' },
      });
    });

    it('accepts the same number written in a different format', async () => {
      prisma.telegramAccount.findUnique.mockResolvedValue({ id: 'tg-1', userId: 'user-1' });
      prisma.user.findUnique.mockResolvedValue({
        id: 'user-1',
        mobileE164: '+919812345678',
        status: 'TELEGRAM_PENDING',
      });

      await service.handleUpdate(contactMessage('09812345678'));

      expect(prisma.telegramAccount.update).toHaveBeenCalled();
    });

    it('rejects a contact whose number differs from the signup number', async () => {
      prisma.telegramAccount.findUnique.mockResolvedValue({ id: 'tg-1', userId: 'user-1' });
      prisma.user.findUnique.mockResolvedValue({ id: 'user-1', mobileE164: '+919812345678' });

      await service.handleUpdate(contactMessage('+919899999999'));

      expect(prisma.telegramAccount.update).not.toHaveBeenCalled();
      expect(bot.sendMessage.mock.calls[0][1]).toMatch(/does not match/i);
    });

    it("rejects someone else's forwarded contact card", async () => {
      prisma.telegramAccount.findUnique.mockResolvedValue({ id: 'tg-1', userId: 'user-1' });

      // Right number, but the card belongs to a different Telegram user.
      await service.handleUpdate(contactMessage('+919812345678', 999));

      expect(prisma.telegramAccount.update).not.toHaveBeenCalled();
      expect(bot.sendMessage.mock.calls[0][1]).toMatch(/your own contact/i);
    });
  });

  describe('verification state', () => {
    it('is incomplete until both chats are satisfied', async () => {
      prisma.user.findUnique.mockResolvedValue({ id: 'user-1', status: 'GROUP_PENDING' });
      prisma.telegramAccount.findUnique.mockResolvedValue({ contactVerifiedAt: new Date() });
      prisma.telegramMembership.findMany.mockResolvedValue([
        { telegramChatId: PUBLIC_CHAT, status: 'APPROVED' },
      ]);

      const state = await service.getVerificationState('user-1');

      expect(state.joinedPublicChat).toBe(true);
      expect(state.joinedPrivateChat).toBe(false);
      expect(state.complete).toBe(false);
    });

    it('counts a pending request as satisfying the private chat', async () => {
      prisma.user.findUnique.mockResolvedValue({ id: 'user-1', status: 'GROUP_PENDING' });
      prisma.telegramAccount.findUnique.mockResolvedValue({ contactVerifiedAt: new Date() });
      prisma.telegramMembership.findMany.mockResolvedValue([
        { telegramChatId: PUBLIC_CHAT, status: 'APPROVED' },
        { telegramChatId: PRIVATE_CHAT, status: 'REQUESTED' },
      ]);

      const state = await service.getVerificationState('user-1');

      expect(state.complete).toBe(true);
    });

    it('is not complete on chat membership alone if the contact was never verified', async () => {
      prisma.user.findUnique.mockResolvedValue({ id: 'user-1', status: 'TELEGRAM_PENDING' });
      prisma.telegramAccount.findUnique.mockResolvedValue({ contactVerifiedAt: null });
      prisma.telegramMembership.findMany.mockResolvedValue([
        { telegramChatId: PUBLIC_CHAT, status: 'APPROVED' },
        { telegramChatId: PRIVATE_CHAT, status: 'APPROVED' },
      ]);

      const state = await service.getVerificationState('user-1');

      expect(state.complete).toBe(false);
    });

    it('refuses to treat the step as satisfied when the chats are not configured', async () => {
      const unconfigured: Record<string, unknown> = {
        ...config,
        'telegram.publicChatId': undefined,
        'telegram.privateChatId': undefined,
      };
      const moduleRef = await Test.createTestingModule({
        providers: [
          TelegramService,
          { provide: PrismaService, useValue: prisma },
          { provide: UsersService, useValue: users },
          { provide: AuditLogService, useValue: { record: jest.fn() } },
          { provide: ConfigService, useValue: { get: (k: string) => unconfigured[k] } },
          { provide: TelegramBotService, useValue: bot },
        ],
      }).compile();

      await expect(
        moduleRef.get(TelegramService).getVerificationState('user-1'),
      ).rejects.toThrow(/must both be set/i);
    });
  });

  it('activates the candidate once every step is done', async () => {
    prisma.telegramAccount.findUnique.mockResolvedValue({ userId: 'user-1', telegramUserId: 555n });
    prisma.user.findUnique.mockResolvedValue({ id: 'user-1', status: 'GROUP_PENDING' });
    prisma.telegramMembership.findMany.mockResolvedValue([
      { telegramChatId: PUBLIC_CHAT, status: 'APPROVED' },
      { telegramChatId: PRIVATE_CHAT, status: 'REQUESTED' },
    ]);
    prisma.telegramAccount.findUnique.mockResolvedValue({
      userId: 'user-1',
      telegramUserId: 555n,
      contactVerifiedAt: new Date(),
    });

    await service.handleUpdate({
      chat_member: {
        chat: { id: Number(PUBLIC_CHAT), type: 'channel' },
        new_chat_member: { user: { id: 555 }, status: 'member' },
      },
    });

    expect(users.markTelegramVerified).toHaveBeenCalledWith('user-1');
  });

  it('never lets a webhook handler throw, so Telegram keeps the webhook alive', async () => {
    prisma.user.findUnique.mockRejectedValue(new Error('database is down'));
    await expect(
      service.handleUpdate({ message: { from: { id: 555 }, text: VALID_AADHAAR } }),
    ).resolves.toBeUndefined();
  });
});
