import { randomInt } from 'crypto';

/**
 * The number-reading test.
 *
 * A 12-digit number is generated, a question about it is asked, and the answer
 * is computed from the number — so every challenge grades itself instantly and
 * there is no answer key to author or maintain.
 *
 * The numbers are GENERATED, never taken from a real account. That is not only
 * a legal necessity (identity numbers may not be disclosed to third parties)
 * but the practical choice: generated numbers give an unlimited supply, and
 * the grader always knows the right answer with certainty.
 */

/** Verhoeff tables — the checksum scheme used by 12-digit Indian ID numbers. */
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
const INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9];

/**
 * Generates a checksum-valid 12-digit number in the same shape as a real one,
 * so candidates practise on something that looks like the real thing.
 */
export function generateNumber(): string {
  // Real numbers never begin 0 or 1; matching that keeps the drill realistic.
  let digits = String(randomInt(2, 10));
  for (let i = 0; i < 10; i++) digits += String(randomInt(0, 10));

  let c = 0;
  const reversed = digits.split('').reverse().map(Number);
  for (let i = 0; i < reversed.length; i++) c = D[c][P[(i + 1) % 8][reversed[i]]];
  return digits + INV[c];
}

/** Grouped 4-4-4 the way the number appears on a card. */
export function formatGrouped(digits: string): string {
  return `${digits.slice(0, 4)} ${digits.slice(4, 8)} ${digits.slice(8, 12)}`;
}

export type ReadingQuestion = {
  kind: 'FULL' | 'FIRST_FOUR' | 'MIDDLE_FOUR' | 'LAST_FOUR' | 'DIGIT_COUNT';
  /** Shown to the candidate. */
  text: string;
  /** What a correct answer looks like, for the input hint. */
  answerHint: string;
};

export type ReadingChallenge = {
  number: string;
  numberDisplay: string;
  question: ReadingQuestion;
  expectedAnswer: string;
};

/**
 * Builds a challenge. Every question is answerable purely by reading the
 * number carefully — which is the whole skill being checked.
 */
export function buildReadingChallenge(): ReadingChallenge {
  const number = generateNumber();
  const kinds: ReadingQuestion['kind'][] = [
    'FULL',
    'FIRST_FOUR',
    'MIDDLE_FOUR',
    'LAST_FOUR',
    'DIGIT_COUNT',
  ];
  const kind = kinds[randomInt(0, kinds.length)];

  switch (kind) {
    case 'FIRST_FOUR':
      return {
        number,
        numberDisplay: formatGrouped(number),
        question: { kind, text: 'Enter the FIRST 4 digits of the number above.', answerHint: '4 digits' },
        expectedAnswer: number.slice(0, 4),
      };
    case 'MIDDLE_FOUR':
      return {
        number,
        numberDisplay: formatGrouped(number),
        question: { kind, text: 'Enter the MIDDLE 4 digits of the number above.', answerHint: '4 digits' },
        expectedAnswer: number.slice(4, 8),
      };
    case 'LAST_FOUR':
      return {
        number,
        numberDisplay: formatGrouped(number),
        question: { kind, text: 'Enter the LAST 4 digits of the number above.', answerHint: '4 digits' },
        expectedAnswer: number.slice(8, 12),
      };
    case 'DIGIT_COUNT': {
      // Pick a digit that actually occurs, so the answer is never 0 — a
      // question whose answer is "none" can be guessed without reading.
      const present = Array.from(new Set(number.split('')));
      const digit = present[randomInt(0, present.length)];
      const count = number.split('').filter((d) => d === digit).length;
      return {
        number,
        numberDisplay: formatGrouped(number),
        question: {
          kind,
          text: `How many times does the digit ${digit} appear in the number above?`,
          answerHint: 'a number',
        },
        expectedAnswer: String(count),
      };
    }
    case 'FULL':
    default:
      return {
        number,
        numberDisplay: formatGrouped(number),
        question: {
          kind: 'FULL',
          text: 'Type the full 12-digit number exactly as shown, without spaces.',
          answerHint: '12 digits',
        },
        expectedAnswer: number,
      };
  }
}

/**
 * Compares an answer to the expected one.
 *
 * Spaces and dashes are stripped, because a candidate who types the digits
 * correctly but groups them differently has read the number correctly — which
 * is what is being measured.
 */
export function answerMatches(given: string | undefined, expected: string): boolean {
  if (!given) return false;
  const clean = (v: string) => v.replace(/[\s-]/g, '');
  return clean(given) === clean(expected);
}
