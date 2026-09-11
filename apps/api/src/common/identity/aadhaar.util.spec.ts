import { isWellFormedAadhaar, normaliseAadhaar, hashAadhaar, aadhaarLast4 } from './aadhaar.util';
import { BadRequestException } from '@nestjs/common';

// Verhoeff-valid, but not issued to anyone — generated for tests only.
const VALID = '234567890124';
const ALSO_VALID = '345678901238';

describe('aadhaar.util', () => {
  describe('isWellFormedAadhaar', () => {
    it('accepts a checksum-valid number', () => {
      expect(isWellFormedAadhaar(VALID)).toBe(true);
    });

    it('rejects a number whose last digit was mistyped', () => {
      // A plain length/regex check would pass this; the checksum is what
      // catches the single most common data-entry error.
      expect(isWellFormedAadhaar('234567890125')).toBe(false);
    });

    it('rejects numbers starting with 0 or 1, which UIDAI never issues', () => {
      expect(isWellFormedAadhaar('012345678901')).toBe(false);
      expect(isWellFormedAadhaar('112345678901')).toBe(false);
    });

    it('rejects wrong lengths and non-digits', () => {
      expect(isWellFormedAadhaar('23456789012')).toBe(false);
      expect(isWellFormedAadhaar('2345678901234')).toBe(false);
      expect(isWellFormedAadhaar('23456789012a')).toBe(false);
    });

    it('tolerates the spaces and dashes people actually type', () => {
      expect(isWellFormedAadhaar('2345 6789 0124')).toBe(true);
      expect(isWellFormedAadhaar('2345-6789-0124')).toBe(true);
    });
  });

  describe('normaliseAadhaar', () => {
    it('strips formatting down to 12 digits', () => {
      expect(normaliseAadhaar('2345 6789 0124')).toBe(VALID);
    });

    it('throws rather than returning something unusable', () => {
      expect(() => normaliseAadhaar('123')).toThrow(BadRequestException);
    });
  });

  describe('hashAadhaar', () => {
    it('is deterministic for the same number and pepper', () => {
      expect(hashAadhaar(VALID, 'pepper')).toBe(hashAadhaar(VALID, 'pepper'));
    });

    it('ignores formatting, so the same number always dedupes', () => {
      expect(hashAadhaar('2345 6789 0124', 'pepper')).toBe(hashAadhaar(VALID, 'pepper'));
    });

    it('differs between numbers', () => {
      expect(hashAadhaar(VALID, 'pepper')).not.toBe(hashAadhaar(ALSO_VALID, 'pepper'));
    });

    it('differs between peppers, so a leaked hash is useless without the key', () => {
      expect(hashAadhaar(VALID, 'pepper-a')).not.toBe(hashAadhaar(VALID, 'pepper-b'));
    });

    it('never contains the digits it hashed', () => {
      expect(hashAadhaar(VALID, 'pepper')).not.toContain(VALID);
    });

    it('refuses to hash with an empty pepper instead of silently weakening', () => {
      // An empty key would produce a plain, offline-brute-forceable digest of
      // a 10^12 keyspace — worse than useless, because it looks fine.
      expect(() => hashAadhaar(VALID, '')).toThrow(/AADHAAR_HASH_PEPPER/);
    });
  });

  it('aadhaarLast4 returns only the final four digits', () => {
    expect(aadhaarLast4('2345 6789 0124')).toBe('0124');
  });
});
