/**
 * Turning what someone types into an E.164 number.
 *
 * This matters more than it looks. The number stored at signup is the one
 * Telegram verification later compares the shared contact against, so a number
 * that is merely *accepted* but wrong leaves the candidate permanently stuck:
 * they can never verify, and so can never refer, train, or apply.
 *
 * The previous rule was `startsWith('+') ? value : '+' + digits`, which turned
 * a plain Indian mobile — 9824065912, exactly what the field invites — into
 * +9824065912. That is a valid-looking E.164 string for country code 98, and
 * it is not the user's number.
 */

/** Indian mobile numbers are 10 digits and never start 0-5. */
const INDIAN_MOBILE = /^[6-9]\d{9}$/;

export const DEFAULT_COUNTRY_CODE = '91';

/**
 * Normalises to E.164, assuming India when no country code is given.
 *
 * Returns null when the input cannot be read as a phone number, so the caller
 * can say so rather than sending something wrong to the server.
 */
export function normaliseMobile(input: string): string | null {
  const trimmed = input.trim();
  if (!trimmed) return null;

  const hadPlus = trimmed.startsWith('+');
  const digits = trimmed.replace(/\D/g, '');
  if (!digits) return null;

  // An explicit country code is taken at face value — someone typing +44 …
  // means it.
  if (hadPlus) {
    return /^[1-9]\d{7,14}$/.test(digits) ? `+${digits}` : null;
  }

  // 00 is the other way of writing +.
  if (digits.startsWith('00')) {
    const rest = digits.slice(2);
    return /^[1-9]\d{7,14}$/.test(rest) ? `+${rest}` : null;
  }

  // 91 followed by a valid Indian mobile: the country code without the +.
  if (digits.length === 12 && digits.startsWith(DEFAULT_COUNTRY_CODE)) {
    const local = digits.slice(2);
    return INDIAN_MOBILE.test(local) ? `+${DEFAULT_COUNTRY_CODE}${local}` : null;
  }

  // A leading 0 is the domestic trunk prefix, dropped in E.164.
  if (digits.length === 11 && digits.startsWith('0')) {
    const local = digits.slice(1);
    return INDIAN_MOBILE.test(local) ? `+${DEFAULT_COUNTRY_CODE}${local}` : null;
  }

  // The common case: ten digits, no country code. This is the one the old
  // rule got wrong.
  if (digits.length === 10) {
    return INDIAN_MOBILE.test(digits) ? `+${DEFAULT_COUNTRY_CODE}${digits}` : null;
  }

  return null;
}

/** For display next to the input, so what will be sent is never a surprise. */
export function describeMobile(input: string): string | null {
  const e164 = normaliseMobile(input);
  if (!e164) return null;
  if (e164.startsWith('+91') && e164.length === 13) {
    return `+91 ${e164.slice(3, 8)} ${e164.slice(8)}`;
  }
  return e164;
}
