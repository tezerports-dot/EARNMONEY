import { customAlphabet } from 'nanoid';
import { prisma } from '@platform/database';
import { REFERRAL_CODE_PREFIX, REFERRAL_CODE_LENGTH } from '@platform/shared';

// Unambiguous alphabet (no 0/O/1/I) to avoid confusion when users share codes.
const nanoid = customAlphabet('ABCDEFGHJKMNPQRSTUVWXYZ23456789', REFERRAL_CODE_LENGTH);

/** Generates a referral code guaranteed unique in the database. */
export async function generateUniqueReferralCode(): Promise<string> {
  for (let attempt = 0; attempt < 10; attempt++) {
    const code = `${REFERRAL_CODE_PREFIX}${nanoid()}`;
    const existing = await prisma.user.findUnique({ where: { referralCode: code } });
    if (!existing) return code;
  }
  throw new Error('Failed to generate a unique referral code after 10 attempts');
}

/** Parses the payload of a /start deep link, e.g. "REF_AB23CD45" -> the code, or null if invalid shape. */
export function parseReferralParam(startPayload: string | undefined): string | null {
  if (!startPayload) return null;
  const trimmed = startPayload.trim();
  if (!trimmed.startsWith(REFERRAL_CODE_PREFIX)) return null;
  if (trimmed.length !== REFERRAL_CODE_PREFIX.length + REFERRAL_CODE_LENGTH) return null;
  return trimmed;
}

/** Looks up the referring user by code. Returns null if it doesn't exist. */
export async function findReferrerByCode(code: string) {
  return prisma.user.findUnique({ where: { referralCode: code } });
}
