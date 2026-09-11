import {
  ConflictException,
  Injectable,
  Inject,
  UnauthorizedException,
  BadRequestException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { JwtService } from '@nestjs/jwt';
import * as argon2 from 'argon2';
import { createHash, randomBytes } from 'crypto';
import { PrismaService } from '../prisma/prisma.service';
import { hashAadhaar, aadhaarLast4, normaliseAadhaar } from '../common/identity/aadhaar.util';
import { AuditLogService } from '../audit/audit-log.service';
import { SignupDto } from './dto/signup.dto';
import { LoginDto } from './dto/login.dto';
import { CaptchaService } from './captcha.service';

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
  refreshTokenExpiresAt: Date;
}

@Injectable()
export class AuthService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly jwt: JwtService,
    private readonly config: ConfigService,
    private readonly audit: AuditLogService,
    @Inject('CaptchaService') private readonly captcha: CaptchaService,
  ) {}

  async signup(dto: SignupDto, ip?: string) {
    const captchaOk = await this.captcha.verify(dto.captchaToken, ip);
    if (!captchaOk) {
      throw new BadRequestException('CAPTCHA verification failed.');
    }

    if (dto.password !== dto.confirmPassword) {
      throw new BadRequestException('Password and confirm password do not match.');
    }

    // Throws if the number fails shape or Verhoeff checksum, before anything
    // touches the database. Never log or persist `aadhaar` itself.
    const aadhaar = normaliseAadhaar(dto.aadhaarNumber);
    const pepper = this.config.get<string>('identity.aadhaarHashPepper') ?? '';
    const aadhaarHash = hashAadhaar(aadhaar, pepper);

    const existing = await this.prisma.user.findFirst({
      where: { OR: [{ mobileE164: dto.mobile }, { aadhaarHash }] },
    });
    if (existing) {
      // Deliberately vague, and deliberately the same message for both cases:
      // distinguishing them would turn signup into an oracle for "is this
      // Aadhaar/mobile already registered here?".
      throw new ConflictException('Unable to create account with the details provided.');
    }

    let referredByUserId: string | undefined;
    if (dto.referralCode) {
      const referrer = await this.prisma.user.findUnique({
        where: { referralCode: dto.referralCode },
      });
      if (!referrer) {
        throw new BadRequestException('Referral code is not valid.');
      }
      referredByUserId = referrer.id;
    }

    const passwordHash = await argon2.hash(dto.password, {
      type: argon2.argon2id,
      memoryCost: this.config.get('argon2.memoryCost'),
      timeCost: this.config.get('argon2.timeCost'),
      parallelism: this.config.get('argon2.parallelism'),
    });

    const referralCode = await this.generateUniqueReferralCode();

    // Typed `any` here only because this sandbox can't reach binaries.prisma.sh
    // to run `prisma generate` (network allowlist). Once you run
    // `npx prisma generate` on a machine with normal internet access (any dev
    // machine, or the Hostinger VPS), replace with `Prisma.TransactionClient`
    // for full type safety.
    const user = await this.prisma.$transaction(async (tx: any) => {
      const created = await tx.user.create({
        data: {
          mobileE164: dto.mobile,
          passwordHash,
          aadhaarHash,
          aadhaarLast4: aadhaarLast4(aadhaar),
          referralCode,
          referredByUserId,
          // Candidate exists but has proved nothing yet. The Telegram bot flow
          // is what moves them forward from here.
          status: 'TELEGRAM_PENDING',
        },
      });

      // Self-referral is structurally impossible here since referredByUserId
      // is resolved from a code owned by an *existing* user before this row
      // is created — created.id cannot equal referredByUserId. We assert it
      // anyway as a defence-in-depth check (Agent Rule 3: server authoritative).
      if (referredByUserId === created.id) {
        throw new BadRequestException('Self-referral is not permitted.');
      }

      if (referredByUserId) {
        await tx.referral.create({
          data: {
            referrerUserId: referredByUserId,
            referredUserId: created.id,
            status: 'PENDING',
          },
        });
      }

      return created;
    });

    await this.audit.record({
      actorUserId: user.id,
      action: 'USER_SIGNUP',
      entityType: 'User',
      entityId: user.id,
      // Never put the Aadhaar number (or its hash) in an audit row.
      metadata: { hadReferralCode: !!dto.referralCode },
      ip,
    });

    return { userId: user.id, status: user.status, referralCode: user.referralCode };
  }

  async login(dto: LoginDto, ip?: string): Promise<{ user: { id: string; role: string }; tokens: TokenPair }> {
    const captchaOk = await this.captcha.verify(dto.captchaToken, ip);
    if (!captchaOk) {
      throw new BadRequestException('CAPTCHA verification failed.');
    }

    const user = await this.prisma.user.findUnique({ where: { mobileE164: dto.mobile } });

    // Constant-shape response whether the user exists or the password is
    // wrong — never reveal which one failed.
    const dummyHash =
      '$argon2id$v=19$m=19456,t=2,p=1$c29tZXNhbHRzb21lc2FsdA$Q6workingDummyHashPlaceholder';
    const hashToVerify = user?.passwordHash ?? dummyHash;
    const passwordOk = await argon2.verify(hashToVerify, dto.password).catch(() => false);

    if (!user || !passwordOk) {
      throw new UnauthorizedException('Invalid mobile number or password.');
    }

    if (user.status === 'SUSPENDED') {
      throw new UnauthorizedException('This account has been suspended. Contact support.');
    }

    await this.prisma.user.update({ where: { id: user.id }, data: { lastLoginAt: new Date() } });

    const tokens = await this.issueTokenPair(user.id);

    await this.audit.record({
      actorUserId: user.id,
      action: 'USER_LOGIN',
      entityType: 'User',
      entityId: user.id,
      ip,
    });

    return { user: { id: user.id, role: user.role }, tokens };
  }

  async refresh(rawRefreshToken: string): Promise<TokenPair> {
    const tokenHash = this.hashToken(rawRefreshToken);
    const stored = await this.prisma.refreshToken.findUnique({ where: { tokenHash } });

    if (!stored || stored.revokedAt || stored.expiresAt < new Date()) {
      throw new UnauthorizedException('Session expired. Please log in again.');
    }

    // Rotate: revoke the used token, issue a brand new pair. If a revoked
    // token is ever presented again, that's a strong signal of theft/replay.
    await this.prisma.refreshToken.update({
      where: { id: stored.id },
      data: { revokedAt: new Date() },
    });

    return this.issueTokenPair(stored.userId);
  }

  async logout(rawRefreshToken: string | undefined, userId: string, ip?: string) {
    if (rawRefreshToken) {
      const tokenHash = this.hashToken(rawRefreshToken);
      await this.prisma.refreshToken.updateMany({
        where: { tokenHash, userId },
        data: { revokedAt: new Date() },
      });
    }
    await this.audit.record({ actorUserId: userId, action: 'USER_LOGOUT', entityType: 'User', entityId: userId, ip });
  }

  // ---------------------------------------------------------------------

  private async issueTokenPair(userId: string): Promise<TokenPair> {
    const accessToken = await this.jwt.signAsync(
      { sub: userId },
      {
        secret: this.config.get('jwt.accessSecret'),
        expiresIn: this.config.get('jwt.accessTtl'),
      },
    );

    const rawRefreshToken = randomBytes(48).toString('hex');
    const refreshTtlDays = this.config.get<number>('jwt.refreshTtlDays') ?? 30;
    const refreshTokenExpiresAt = new Date(Date.now() + refreshTtlDays * 24 * 60 * 60 * 1000);

    await this.prisma.refreshToken.create({
      data: {
        userId,
        tokenHash: this.hashToken(rawRefreshToken),
        expiresAt: refreshTokenExpiresAt,
      },
    });

    return { accessToken, refreshToken: rawRefreshToken, refreshTokenExpiresAt };
  }

  private hashToken(raw: string): string {
    return createHash('sha256').update(raw).digest('hex');
  }

  private async generateUniqueReferralCode(): Promise<string> {
    for (let i = 0; i < 5; i++) {
      const code = randomBytes(4).toString('hex').toUpperCase();
      const exists = await this.prisma.user.findUnique({ where: { referralCode: code } });
      if (!exists) return code;
    }
    throw new Error('Could not generate a unique referral code after 5 attempts.');
  }
}
