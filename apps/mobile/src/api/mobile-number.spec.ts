import { describeMobile, normaliseMobile } from './mobile-number';

describe('normaliseMobile', () => {
  it('assumes India for a bare 10-digit mobile', () => {
    // The bug this replaced turned this into +9824065912 — country code 98,
    // not the user's number — and the account could then never be verified
    // against the contact shared on Telegram.
    expect(normaliseMobile('9824065912')).toBe('+919824065912');
  });

  it('accepts the number however it is spaced', () => {
    expect(normaliseMobile('98240 65912')).toBe('+919824065912');
    expect(normaliseMobile('98240-65912')).toBe('+919824065912');
    expect(normaliseMobile('  9824065912  ')).toBe('+919824065912');
  });

  it('accepts an explicit +91', () => {
    expect(normaliseMobile('+919824065912')).toBe('+919824065912');
    expect(normaliseMobile('+91 98240 65912')).toBe('+919824065912');
  });

  it('accepts 91 written without the plus', () => {
    expect(normaliseMobile('919824065912')).toBe('+919824065912');
  });

  it('drops the domestic trunk 0', () => {
    expect(normaliseMobile('09824065912')).toBe('+919824065912');
  });

  it('treats 00 as the international prefix', () => {
    expect(normaliseMobile('00919824065912')).toBe('+919824065912');
  });

  it('takes another country code at face value', () => {
    expect(normaliseMobile('+442071838750')).toBe('+442071838750');
  });

  it('rejects a 10-digit number that cannot be an Indian mobile', () => {
    // Indian mobiles start 6-9; 1234567890 is a typo, not a number, and
    // accepting it would strand that account exactly like the old bug did.
    expect(normaliseMobile('1234567890')).toBeNull();
    expect(normaliseMobile('0123456789')).toBeNull();
  });

  it('rejects numbers that are too short or too long', () => {
    expect(normaliseMobile('98240')).toBeNull();
    expect(normaliseMobile('98240659121234567')).toBeNull();
  });

  it('rejects empty and non-numeric input', () => {
    expect(normaliseMobile('')).toBeNull();
    expect(normaliseMobile('   ')).toBeNull();
    expect(normaliseMobile('not a number')).toBeNull();
  });

  it('rejects 91 followed by something that is not a mobile', () => {
    expect(normaliseMobile('911234567890')).toBeNull();
  });
});

describe('describeMobile', () => {
  it('shows the full number that will actually be sent', () => {
    // Shown under the field so a wrong number is caught before signup, not
    // after the candidate is already stuck.
    expect(describeMobile('9824065912')).toBe('+91 98240 65912');
  });

  it('shows nothing while the input is not yet a number', () => {
    expect(describeMobile('982')).toBeNull();
    expect(describeMobile('')).toBeNull();
  });
});
