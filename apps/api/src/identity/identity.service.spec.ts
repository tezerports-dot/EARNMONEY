import { Test } from '@nestjs/testing';
import { BadRequestException } from '@nestjs/common';
import { createHmac } from 'crypto';
import { IdentityService } from './identity.service';
import { PrismaService } from '../prisma/prisma.service';
import { UsersService } from '../users/users.service';
import { FraudService } from '../fraud/fraud.service';
import { AuditLogService } from '../audit/audit-log.service';
import { ConfigService } from '@nestjs/config';

describe('IdentityService', () => {
  let service: IdentityService;
  let prisma: any;
  let users: any;
  let fraud: any;
  let provider: any;

  beforeEach(async () => {
    prisma = {
      user: { findUnique: jest.fn(), update: jest.fn() },
      identityVerification: { upsert: jest.fn(), findFirst: jest.fn(), update: jest.fn() },
      protectedIdentity: { upsert: jest.fn() },
    };
    users = { markIdentityVerified: jest.fn(), markIdentityRejected: jest.fn() };
    fraud = { recordVerificationRejection: jest.fn() };
    provider = {
      startVerification: jest.fn().mockResolvedValue({ providerReference: 'ref-1' }),
      handleWebhook: jest.fn(),
    };

    const moduleRef = await Test.createTestingModule({
      providers: [
        IdentityService,
        { provide: PrismaService, useValue: prisma },
        { provide: UsersService, useValue: users },
        { provide: FraudService, useValue: fraud },
        { provide: AuditLogService, useValue: { record: jest.fn() } },
        { provide: ConfigService, useValue: { get: () => 'test-webhook-secret' } },
        { provide: 'IdentityProvider', useValue: provider },
      ],
    }).compile();

    service = moduleRef.get(IdentityService);
  });

  describe('startVerification', () => {
    it('rejects when the user is already past the identity step', async () => {
      prisma.user.findUnique.mockResolvedValueOnce({ id: 'u1', status: 'ACTIVE' });
      await expect(service.startVerification('u1')).rejects.toBeInstanceOf(BadRequestException);
    });

    it('records the verification and moves REGISTERED -> IDENTITY_PENDING', async () => {
      prisma.user.findUnique.mockResolvedValueOnce({ id: 'u1', status: 'REGISTERED' });

      await service.startVerification('u1');

      expect(prisma.identityVerification.upsert).toHaveBeenCalled();
      expect(prisma.user.update).toHaveBeenCalledWith({
        where: { id: 'u1' },
        data: { status: 'IDENTITY_PENDING' },
      });
    });
  });

  describe('webhook signature verification', () => {
    it('accepts a correctly signed payload', () => {
      const body = '{"foo":"bar"}';
      const sig = createHmac('sha256', 'test-webhook-secret').update(body).digest('hex');
      expect(service.verifyWebhookSignature(body, sig)).toBe(true);
    });

    it('rejects a tampered payload', () => {
      const body = '{"foo":"bar"}';
      const sig = createHmac('sha256', 'test-webhook-secret').update('{"foo":"different"}').digest('hex');
      expect(service.verifyWebhookSignature(body, sig)).toBe(false);
    });

    it('rejects when no signature header is present', () => {
      expect(service.verifyWebhookSignature('{}', undefined)).toBe(false);
    });
  });

  describe('handleWebhook', () => {
    it('marks the user verified and stores a masked identifier on VERIFIED', async () => {
      provider.handleWebhook.mockResolvedValueOnce({
        providerReference: 'ref-1',
        result: { status: 'VERIFIED', maskedIdentifier: 'XXXX-1234' },
      });
      prisma.identityVerification.findFirst.mockResolvedValueOnce({ id: 'iv-1', userId: 'u1' });

      await service.handleWebhook({}, 'sig');

      expect(users.markIdentityVerified).toHaveBeenCalledWith('u1');
      expect(prisma.protectedIdentity.upsert).toHaveBeenCalled();
    });

    it('marks the user rejected on REJECTED without touching protected identity', async () => {
      provider.handleWebhook.mockResolvedValueOnce({
        providerReference: 'ref-1',
        result: { status: 'REJECTED', failureReasonCode: 'document_unreadable' },
      });
      prisma.identityVerification.findFirst.mockResolvedValueOnce({ id: 'iv-1', userId: 'u1' });

      await service.handleWebhook({}, 'sig');

      // Rejections no longer flag the account directly — FraudService counts
      // them and only acts once the rejection is conclusive.
      expect(fraud.recordVerificationRejection).toHaveBeenCalledWith('u1', 'document_unreadable');
      expect(users.markIdentityRejected).not.toHaveBeenCalled();
      expect(prisma.protectedIdentity.upsert).not.toHaveBeenCalled();
    });
  });
});
