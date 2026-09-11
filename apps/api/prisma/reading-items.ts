/**
 * Starter practice numbers.
 *
 * These exist so the challenge works the moment the system is seeded — an
 * empty bank means no candidate can train at all. They are a starting point,
 * not the content: an admin adds, edits and retires entries through
 * `/admin/reading-items`, and each entry's answer is whatever the admin sets.
 *
 * The numbers are made up for practice. None belongs to a real person, and
 * none should: putting a real number here would put someone's identity details
 * in front of every candidate, which is what docs/SPEC-DEVIATIONS.md rules out.
 */
export type SeedReadingItem = {
  number: string;
  question: string;
  expectedAnswer: string;
  answerHint: string;
};

export const READING_ITEMS: SeedReadingItem[] = [
  {
    number: '284713905612',
    question: 'Type the full 12-digit number exactly as shown.',
    expectedAnswer: '284713905612',
    answerHint: '12 digits',
  },
  {
    number: '739024681537',
    question: 'Enter the FIRST 4 digits of the number above.',
    expectedAnswer: '7390',
    answerHint: '4 digits',
  },
  {
    number: '905186273049',
    question: 'Enter the MIDDLE 4 digits of the number above.',
    expectedAnswer: '8627',
    answerHint: '4 digits',
  },
  {
    number: '461209837451',
    question: 'Enter the LAST 4 digits of the number above.',
    expectedAnswer: '7451',
    answerHint: '4 digits',
  },
  {
    number: '628394017265',
    question: 'How many times does the digit 2 appear in the number above?',
    expectedAnswer: '2',
    answerHint: 'a number',
  },
  {
    number: '517402839164',
    question: 'Enter the LAST 4 digits of the number above.',
    expectedAnswer: '9164',
    answerHint: '4 digits',
  },
  {
    number: '830657194283',
    question: 'Enter the FIRST 4 digits of the number above.',
    expectedAnswer: '8306',
    answerHint: '4 digits',
  },
  {
    number: '294736150827',
    question: 'Type the full 12-digit number exactly as shown.',
    expectedAnswer: '294736150827',
    answerHint: '12 digits',
  },
  {
    number: '671829045316',
    question: 'How many times does the digit 1 appear in the number above?',
    expectedAnswer: '2',
    answerHint: 'a number',
  },
  {
    number: '350918274605',
    question: 'Enter the MIDDLE 4 digits of the number above.',
    expectedAnswer: '1827',
    answerHint: '4 digits',
  },
];
