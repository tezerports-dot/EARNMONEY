import { Test } from '@nestjs/testing';
import { ConfigService } from '@nestjs/config';
import { JwtService } from '@nestjs/jwt';
import { ConflictException, UnauthorizedException, BadRequestException } from '@nestjs/common';
import * as argon2 from 'argon2';
import { createHash } from 'crypto';
import { AuthService } from './auth.service';
import { PrismaService } from '../prisma/prisma.service';
import { AuditLogService } from '../audit/audit-log.service';

describe('AuthService', () => {
  let service: AuthService;
  let prisma: any;
  let captcha: any;

  const baseConfig: Record<string, any> = {
    'argon2.memoryCost': 8192, // small for fast tests
    'argon2.timeCost': 2,
    'argon2.parallelism': 1,
    'jwt.accessSecret': 'test-access-secret',
    'jwt.accessTtl': '15m',
    'jwt.refreshTtlDays': 30,
    'identity.aadhaarHashPepper': 'test-pepper-not-a-real-secret',
  };

  // Verhoeff-valid test numbers. Real Aadhaar numbers must never appear in
  // tests or fixtures.
  const VALID_AADHAAR = '234567890124';

  beforeEach(async () => {
    prisma = {
      user: {
        findUnique: jest.fn(),
        findFirst: jest.fn(),
        create: jest.fn(),
        update: jest.fn(),
      },
      referral: {
        create: jest.fn(),
      },
      refreshToken: {
        create: jest.fn(),
        findUnique: jest.fn(),
        update: jest.fn(),
        updateMany: jest.fn(),
      },
      $transaction: jest.fn(async (fn: any) => fn(prisma)),
    };

    captcha = { verify: jest.fn().mockResolvedValue(true) };

    const moduleRef = await Test.createTestingModule({
      providers: [
        AuthService,
        { provide: PrismaService, useValue: prisma },
        { provide: JwtService, useValue: new JwtService({}) },
        {
          provide: ConfigService,
          useValue: { get: (key: string) => baseConfig[key] },
        },
        { provide: AuditLogService, useValue: { record: jest.fn() } },
        { provide: 'CaptchaService', useValue: captcha },
      ],
    }).compile();

    service = moduleRef.get(AuthService);
  });

  describe('signup', () => {
    const dto = {
      aadhaarNumber: VALID_AADHAAR,
      mobile: '+919812345678',
      password: 'GoodPassw0rd',
      confirmPassword: 'GoodPassw0rd',
      captchaToken: 'tok',
      consentAccepted: true as const,
    };

    it('creates a new user with a hashed password and no referral', async () => {
      prisma.user.findFirst.mockResolvedValueOnce(null); // mobile + aadhaar both free
      prisma.user.findUnique.mockResolvedValueOnce(null); // referral code uniqueness check
      prisma.user.create.mockImplementation(async ({ data }: any) => ({
        id: 'user-1',
        ...data,
      }));

      const result = await service.signup(dto as any);

      expect(result.userId).toBe('user-1');
      expect(prisma.user.create).toHaveBeenCalledTimes(1);
      const createdData = prisma.user.create.mock.calls[0][0].data;
      expect(createdData.passwordHash).not.toEqual(dto.password);
      expect(await argon2.verify(createdData.passwordHash, dto.password)).toBe(true);
    });

    it('rejects signup when the mobile number is already registered', async () => {
      prisma.user.findFirst.mockResolvedValueOnce({ id: 'existing-user' });

      await expect(service.signup(dto as any)).rejects.toBeInstanceOf(ConflictException);
      expect(prisma.user.create).not.toHaveBeenCalled();
    });

    it('rejects a second signup on an Aadhaar number already registered', async () => {
      // The dedupe query is a single OR over mobile and aadhaarHash, so a hit
      // on either arm must be refused — this is what stops one person holding
      // two verified accounts under different mobile numbers.
      prisma.user.findFirst.mockResolvedValueOnce({ id: 'existing-aadhaar-user' });

      await expect(
        service.signup({ ...dto, mobile: '+919800000000' } as any),
      ).rejects.toBeInstanceOf(ConflictException);
      expect(prisma.user.create).not.toHaveBeenCalled();
    });

    it('queries for duplicates by Aadhaar hash, never by the raw number', async () => {
      prisma.user.findFirst.mockResolvedValueOnce(null);
      prisma.user.findUnique.mockResolvedValueOnce(null);
      prisma.user.create.mockImplementation(async ({ data }: any) => ({ id: 'user-9', ...data }));

      await service.signup(dto as any);

      const where = prisma.user.findFirst.mock.calls[0][0].where;
      const serialised = JSON.stringify(where);
      expect(serialised).not.toContain(VALID_AADHAAR);
      expect(where.OR[1].aadhaarHash).toMatch(/^[0-9a-f]{64}$/);
    });

    it('never persists the raw Aadhaar number, only its hash and last 4 digits', async () => {
      prisma.user.findFirst.mockResolvedValueOnce(null);
      prisma.user.findUnique.mockResolvedValueOnce(null);
      prisma.user.create.mockImplementation(async ({ data }: any) => ({ id: 'user-3', ...data }));

      await service.signup(dto as any);

      const created = prisma.user.create.mock.calls[0][0].data;
      expect(JSON.stringify(created)).not.toContain(VALID_AADHAAR);
      expect(created.aadhaarHash).toMatch(/^[0-9a-f]{64}$/);
      expect(created.aadhaarLast4).toBe('0124');
    });

    it('rejects an Aadhaar number that fails the Verhoeff checksum', async () => {
      await expect(
        service.signup({ ...dto, aadhaarNumber: '234567890125' } as any),
      ).rejects.toBeInstanceOf(BadRequestException);
      expect(prisma.user.create).not.toHaveBeenCalled();
    });

    it('rejects signup when the two password fields differ', async () => {
      await expect(
        service.signup({ ...dto, confirmPassword: 'SomethingElse1' } as any),
      ).rejects.toBeInstanceOf(BadRequestException);
      expect(prisma.user.create).not.toHaveBeenCalled();
    });

    it('starts a new candidate at TELEGRAM_PENDING, not ACTIVE', async () => {
      prisma.user.findFirst.mockResolvedValueOnce(null);
      prisma.user.findUnique.mockResolvedValueOnce(null);
      prisma.user.create.mockImplementation(async ({ data }: any) => ({ id: 'user-4', ...data }));

      const result = await service.signup(dto as any);

      expect(prisma.user.create.mock.calls[0][0].data.status).toBe('TELEGRAM_PENDING');
      expect(result.status).toBe('TELEGRAM_PENDING');
    });

    it('rejects signup with an invalid referral code', async () => {
      prisma.user.findFirst.mockResolvedValueOnce(null); // mobile + aadhaar free
      prisma.user.findUnique.mockResolvedValueOnce(null); // referral code lookup -> not found

      await expect(
        service.signup({ ...dto, referralCode: 'DOES-NOT-EXIST' } as any),
      ).rejects.toBeInstanceOf(BadRequestException);
    });

    it('attributes a referral server-side when a valid code is supplied', async () => {
      prisma.user.findFirst.mockResolvedValueOnce(null); // mobile + aadhaar free
      prisma.user.findUnique.mockResolvedValueOnce({ id: 'referrer-1' }); // referral code lookup
      prisma.user.findUnique.mockResolvedValueOnce(null); // referral code uniqueness check for new user
      prisma.user.create.mockImplementation(async ({ data }: any) => ({ id: 'user-2', ...data }));

      await service.signup({ ...dto, referralCode: 'ABC123' } as any);

      expect(prisma.referral.create).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({ referrerUserId: 'referrer-1', referredUserId: 'user-2' }),
        }),
      );
    });

    it('rejects signup when CAPTCHA verification fails', async () => {
      captcha.verify.mockResolvedValueOnce(false);
      await expect(service.signup(dto as any)).rejects.toBeInstanceOf(BadRequestException);
      expect(prisma.user.findFirst).not.toHaveBeenCalled();
    });
  });

  describe('login', () => {
    it('logs in successfully with correct credentials', async () => {
      const passwordHash = await argon2.hash('CorrectPassw0rd', { memoryCost: 8192, timeCost: 2, parallelism: 1 });
      prisma.user.findUnique.mockResolvedValueOnce({
        id: 'user-1',
        role: 'CANDIDATE',
        status: 'ACTIVE',
        passwordHash,
      });
      prisma.refreshToken.create.mockResolvedValueOnce({});

      const result = await service.login({
        mobile: '+919812345678',
        password: 'CorrectPassw0rd',
        captchaToken: 'tok',
      } as any);

      expect(result.user.id).toBe('user-1');
      expect(result.tokens.accessToken).toEqual(expect.any(String));
      expect(result.tokens.refreshToken).toEqual(expect.any(String));
    });

    it('rejects login with the wrong password without revealing which field was wrong', async () => {
      const passwordHash = await argon2.hash('CorrectPassw0rd', { memoryCost: 8192, timeCost: 2, parallelism: 1 });
      prisma.user.findUnique.mockResolvedValueOnce({
        id: 'user-1',
        role: 'CANDIDATE',
        status: 'ACTIVE',
        passwordHash,
      });

      await expect(
        service.login({ mobile: '+919812345678', password: 'WrongPassword', captchaToken: 'tok' } as any),
      ).rejects.toBeInstanceOf(UnauthorizedException);
    });

    it('rejects login for a non-existent account with the same error as wrong password', async () => {
      prisma.user.findUnique.mockResolvedValueOnce(null);

      await expect(
        service.login({ mobile: '+919999999999', password: 'Whatever123', captchaToken: 'tok' } as any),
      ).rejects.toBeInstanceOf(UnauthorizedException);
    });

    it('rejects login for a suspended account', async () => {
      const passwordHash = await argon2.hash('CorrectPassw0rd', { memoryCost: 8192, timeCost: 2, parallelism: 1 });
      prisma.user.findUnique.mockResolvedValueOnce({
        id: 'user-1',
        role: 'CANDIDATE',
        status: 'SUSPENDED',
        passwordHash,
      });

      await expect(
        service.login({ mobile: '+919812345678', password: 'CorrectPassw0rd', captchaToken: 'tok' } as any),
      ).rejects.toBeInstanceOf(UnauthorizedException);
    });
  });

  describe('refresh', () => {
    it('rotates the refresh token and revokes the old one', async () => {
      const raw = 'raw-refresh-token';
      const tokenHash = createHash('sha256').update(raw).digest('hex');

      prisma.refreshToken.findUnique.mockResolvedValueOnce({
        id: 'rt-1',
        userId: 'user-1',
        tokenHash,
        revokedAt: null,
        expiresAt: new Date(Date.now() + 100000),
      });
      prisma.refreshToken.update.mockResolvedValueOnce({});
      prisma.refreshToken.create.mockResolvedValueOnce({});

      const result = await service.refresh(raw);

      expect(prisma.refreshToken.update).toHaveBeenCalledWith(
        expect.objectContaining({ where: { id: 'rt-1' }, data: expect.objectContaining({ revokedAt: expect.any(Date) }) }),
      );
      expect(result.refreshToken).not.toEqual(raw);
    });

    it('rejects an expired refresh token', async () => {
      prisma.refreshToken.findUnique.mockResolvedValueOnce({
        id: 'rt-1',
        userId: 'user-1',
        tokenHash: 'whatever',
        revokedAt: null,
        expiresAt: new Date(Date.now() - 1000),
      });

      await expect(service.refresh('raw')).rejects.toBeInstanceOf(UnauthorizedException);
    });

    it('rejects a revoked (already-used) refresh token — replay protection', async () => {
      prisma.refreshToken.findUnique.mockResolvedValueOnce({
        id: 'rt-1',
        userId: 'user-1',
        tokenHash: 'whatever',
        revokedAt: new Date(),
        expiresAt: new Date(Date.now() + 100000),
      });

      await expect(service.refresh('raw')).rejects.toBeInstanceOf(UnauthorizedException);
    });
  });
});
