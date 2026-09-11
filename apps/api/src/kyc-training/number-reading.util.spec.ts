import {
  answerMatches,
  buildReadingChallenge,
  formatGrouped,
  generateNumber,
} from './number-reading.util';

/** The Verhoeff check the real number format uses, computed independently. */
function verhoeffValid(digits: string): boolean {
  const d = [
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
  const p = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
  ];
  let c = 0;
  digits
    .split('')
    .reverse()
    .forEach((ch, i) => {
      c = d[c][p[i % 8][Number(ch)]];
    });
  return c === 0;
}

describe('generateNumber', () => {
  it('produces 12 digits that pass the checksum, so the drill looks real', () => {
    for (let i = 0; i < 200; i++) {
      const number = generateNumber();
      expect(number).toMatch(/^\d{12}$/);
      expect(verhoeffValid(number)).toBe(true);
    }
  });

  it('never starts with 0 or 1, matching the real format', () => {
    for (let i = 0; i < 200; i++) {
      expect(generateNumber()[0] >= '2').toBe(true);
    }
  });

  it('does not repeat itself over a large run', () => {
    const seen = new Set(Array.from({ length: 500 }, () => generateNumber()));
    expect(seen.size).toBe(500);
  });
});

describe('formatGrouped', () => {
  it('groups 4-4-4 the way the number is printed on a card', () => {
    expect(formatGrouped('234567890123')).toBe('2345 6789 0123');
  });
});

describe('buildReadingChallenge', () => {
  it('always computes an answer that can be checked against the number', () => {
    // Every question type has to be answerable by reading alone; if any one
    // of them drifted out of sync with its answer, the candidate would be
    // marked wrong for reading correctly.
    for (let i = 0; i < 500; i++) {
      const c = buildReadingChallenge();
      const digits = c.number;

      switch (c.question.kind) {
        case 'FULL':
          expect(c.expectedAnswer).toBe(digits);
          break;
        case 'FIRST_FOUR':
          expect(c.expectedAnswer).toBe(digits.slice(0, 4));
          break;
        case 'MIDDLE_FOUR':
          expect(c.expectedAnswer).toBe(digits.slice(4, 8));
          break;
        case 'LAST_FOUR':
          expect(c.expectedAnswer).toBe(digits.slice(8, 12));
          break;
        case 'DIGIT_COUNT': {
          const digit = /digit (\d)/.exec(c.question.text)?.[1];
          expect(digit).toBeDefined();
          const actual = digits.split('').filter((x) => x === digit).length;
          expect(c.expectedAnswer).toBe(String(actual));
          // A "how many" question whose answer is 0 is guessable without
          // reading, so the digit asked about must actually occur.
          expect(actual).toBeGreaterThan(0);
          break;
        }
      }
    }
  });

  it('shows the number grouped and asks a non-empty question', () => {
    const c = buildReadingChallenge();
    expect(c.numberDisplay).toBe(formatGrouped(c.number));
    expect(c.question.text.length).toBeGreaterThan(0);
    expect(c.question.answerHint.length).toBeGreaterThan(0);
  });

  it('varies the question, so the drill is not one memorised move', () => {
    const kinds = new Set(
      Array.from({ length: 300 }, () => buildReadingChallenge().question.kind),
    );
    expect(kinds.size).toBeGreaterThan(1);
  });
});

describe('answerMatches', () => {
  it('accepts the exact answer', () => {
    expect(answerMatches('0123', '0123')).toBe(true);
  });

  it('accepts the same digits spaced or dashed differently', () => {
    expect(answerMatches('2345 6789 0123', '234567890123')).toBe(true);
    expect(answerMatches('2345-6789-0123', '234567890123')).toBe(true);
  });

  it('rejects transposed digits', () => {
    expect(answerMatches('0132', '0123')).toBe(false);
  });

  it('rejects a missing or empty answer', () => {
    expect(answerMatches(undefined, '0123')).toBe(false);
    expect(answerMatches('', '0123')).toBe(false);
  });

  it('rejects a partial answer', () => {
    expect(answerMatches('012', '0123')).toBe(false);
  });
});
