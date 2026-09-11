import { KYC_ISSUES, normaliseIssue } from './kyc-issues';

describe('normaliseIssue', () => {
  it('accepts the canonical code unchanged', () => {
    expect(normaliseIssue('name_mismatch')).toBe('name_mismatch');
  });

  it('accepts the prose a candidate actually types', () => {
    // The bug this fixes: grading compared raw strings with ===, so spotting
    // the right fault but typing it naturally was marked wrong.
    expect(normaliseIssue('name mismatch')).toBe('name_mismatch');
    expect(normaliseIssue('Name Mismatch')).toBe('name_mismatch');
    expect(normaliseIssue('  name-mismatch  ')).toBe('name_mismatch');
    expect(normaliseIssue('names do not match')).toBe('name_mismatch');
  });

  it('accepts the human label shown in the app', () => {
    expect(normaliseIssue('Document has expired')).toBe('expired');
    expect(normaliseIssue('Scan is unreadable')).toBe('illegible');
  });

  it('accepts common synonyms', () => {
    expect(normaliseIssue('document expired')).toBe('expired');
    expect(normaliseIssue('forged')).toBe('tampered');
    expect(normaliseIssue('blurry')).toBe('illegible');
    expect(normaliseIssue('duplicate')).toBe('duplicate_submission');
  });

  it('returns null rather than guessing at something unrecognised', () => {
    // Guessing would mark a wrong answer correct, which is worse than a miss.
    expect(normaliseIssue('something else entirely')).toBeNull();
    expect(normaliseIssue('')).toBeNull();
    expect(normaliseIssue(undefined)).toBeNull();
  });

  it('does not collapse two different faults onto one code', () => {
    expect(normaliseIssue('dob_mismatch')).not.toBe(normaliseIssue('name_mismatch'));
    expect(normaliseIssue('expired')).not.toBe(normaliseIssue('not_yet_valid'));
  });

  it('round-trips every code in the taxonomy', () => {
    for (const { code, label } of KYC_ISSUES) {
      expect(normaliseIssue(code)).toBe(code);
      expect(normaliseIssue(label)).toBe(code);
    }
  });
});
