/**
 * Helpers for the number-reading test.
 *
 * The numbers and their answers are authored by an admin (see
 * `NumberReadingItem`), not generated here. What lives in this file is the
 * handling that has to be identical on both sides of the test: how a number is
 * displayed, and what counts as the same answer.
 */

/** Digits only — how a number is stored and compared, whatever was typed. */
export function normaliseNumber(value: string): string {
  return value.replace(/[\s-]/g, '');
}

/** True for exactly 12 digits, once spacing is stripped. */
export function isTwelveDigits(value: string): boolean {
  return /^\d{12}$/.test(normaliseNumber(value));
}

/** Grouped 4-4-4 the way the number appears on a card. */
export function formatGrouped(digits: string): string {
  const d = normaliseNumber(digits);
  return `${d.slice(0, 4)} ${d.slice(4, 8)} ${d.slice(8, 12)}`;
}

/**
 * Compares an answer to the one the admin set.
 *
 * Spaces and dashes are stripped, because a candidate who types the digits
 * correctly but groups them differently has read the number correctly — which
 * is what is being measured. Surrounding whitespace from a phone keyboard is
 * not a wrong answer either.
 */
export function answerMatches(given: string | undefined, expected: string): boolean {
  if (!given) return false;
  const clean = (v: string) => v.replace(/[\s-]/g, '');
  return clean(given) === clean(expected);
}
