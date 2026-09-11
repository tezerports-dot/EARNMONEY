import { Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';

// Keys that are expected to exist (seeded by prisma/seed.ts). Business logic
// should always read thresholds through this service — never hardcode a
// number like "3" or "200" directly in a controller/service.
export const CONFIG_KEYS = {
  REFERRAL_THRESHOLD: 'referral_threshold',
  KYC_CHALLENGE_THRESHOLD: 'kyc_challenge_threshold',
  REFERRAL_ATTRIBUTION_WINDOW_DAYS: 'referral_attribution_window_days',
  // How many confirmed-fake referrals a candidate may accumulate before the
  // account is suspended.
  FRAUD_STRIKE_LIMIT: 'fraud_strike_limit',
  // How many independent rejections make a referred user's KYC conclusively
  // fake, rather than a one-off failure worth re-checking.
  KYC_REJECTION_ATTEMPTS: 'kyc_rejection_attempts',
} as const;

@Injectable()
export class SystemConfigService {
  constructor(private readonly prisma: PrismaService) {}

  async get<T = unknown>(key: string, fallback: T): Promise<T> {
    const row = await this.prisma.systemConfig.findUnique({ where: { key } });
    if (!row) return fallback;
    return row.value as T;
  }

  async set(key: string, value: unknown, updatedBy: string, description?: string): Promise<void> {
    await this.prisma.systemConfig.upsert({
      where: { key },
      update: { value: value as any, updatedBy, ...(description ? { description } : {}) },
      create: { key, value: value as any, updatedBy, description },
    });
  }

  getReferralThreshold(): Promise<number> {
    return this.get<number>(CONFIG_KEYS.REFERRAL_THRESHOLD, 3);
  }

  getKycChallengeThreshold(): Promise<number> {
    return this.get<number>(CONFIG_KEYS.KYC_CHALLENGE_THRESHOLD, 3);
  }

  getFraudStrikeLimit(): Promise<number> {
    return this.get<number>(CONFIG_KEYS.FRAUD_STRIKE_LIMIT, 8);
  }

  getKycRejectionAttempts(): Promise<number> {
    return this.get<number>(CONFIG_KEYS.KYC_REJECTION_ATTEMPTS, 3);
  }
}
