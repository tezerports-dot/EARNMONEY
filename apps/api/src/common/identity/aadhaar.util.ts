import { BadRequestException } from '@nestjs/common';
import { createHmac, timingSafeEqual } from 'crypto';

/**
 * Aadhaar handling rules for this codebase — do not work around these:
 *
 *  1. The 12-digit number is NEVER persisted, logged, or returned by any API.
 *     Only `hashAadhaar()`'s output and the last 4 digits are stored.
 *  2. The hash is an HMAC keyed with AADHAAR_HASH_PEPPER, which lives in the
 *     environment and not in the database. A plain SHA-256 would be useless
 *     here: the whole keyspace is 10^12, small enough to exhaust offline in
 *     minutes, so a database leak would expose every number. The pepper means
 *     an attacker needs the application secret as well as the database.
 *  3. The hash column is UNIQUE. That is what makes "one verified account per
 *     person" a constraint the database enforces, rather than a check some
 *     future code path can forget to run.
 *
 * This stores a derived identifier for de-duplication only. It is not, and
 * must not be presented as, Aadhaar authentication — that requires a
 * UIDAI-authorised agency. See docs/SPEC-DEVIATIONS.md.
 */

/** Verhoeff checksum table — the algorithm UIDAI uses for Aadhaar numbers. */
const D = [
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
  [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
  [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
  [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
  [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
  [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
  [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
  [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
  [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
];
const P = [
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
  [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
  [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
  [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
  [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
  [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
  [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
];

/**
 * Rejects typos and obviously invented numbers before anything is stored.
 * Passing this proves the digits are well-formed, NOT that the number is
 * issued to anyone — only a licensed provider can establish that.
 */
export function isWellFormedAadhaar(raw: string): boolean {
  const digits = raw.replace(/\s|-/g, '');
  if (!/^[2-9][0-9]{11}$/.test(digits)) return false; // UIDAI never issues numbers starting 0 or 1
  let c = 0;
  const reversed = digits.split('').reverse().map(Number);
  for (let i = 0; i < reversed.length; i++) {
    c = D[c][P[i % 8][reversed[i]]];
  }
  return c === 0;
}

export function normaliseAadhaar(raw: string): string {
  const digits = raw.replace(/\s|-/g, '');
  if (!isWellFormedAadhaar(digits)) {
    throw new BadRequestException('Please enter a valid 12-digit Aadhaar number.');
  }
  return digits;
}

export function hashAadhaar(raw: string, pepper: string): string {
  if (!pepper) {
    // Failing closed matters here: silently hashing with an empty key would
    // produce stable-looking values that are trivially reversible.
    throw new Error('AADHAAR_HASH_PEPPER is not set. Refusing to hash identity data with an empty key.');
  }
  return createHmac('sha256', pepper).update(normaliseAadhaar(raw)).digest('hex');
}

export function aadhaarLast4(raw: string): string {
  return normaliseAadhaar(raw).slice(-4);
}

/** Constant-time compare, so hash checks can't be timed. */
export function hashesMatch(a: string, b: string): boolean {
  const ab = Buffer.from(a, 'utf8');
  const bb = Buffer.from(b, 'utf8');
  if (ab.length !== bb.length) return false;
  return timingSafeEqual(ab, bb);
}
