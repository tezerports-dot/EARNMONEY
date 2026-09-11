/**
 * The fixed vocabulary of faults a candidate can report.
 *
 * This exists because grading previously compared the candidate's free-text
 * answer to the scenario's stored code with `===`. A candidate who correctly
 * spotted a name mismatch but typed "name mismatch" instead of
 * "name_mismatch" was marked wrong — the test measured typing, not skill.
 *
 * The list is served to the app so it can render a picker, and grading
 * normalises whatever arrives, so an older client sending prose still grades
 * correctly.
 */
export const KYC_ISSUES = [
  { code: 'name_mismatch', label: 'Name does not match the form' },
  { code: 'dob_mismatch', label: 'Date of birth does not match' },
  { code: 'gender_mismatch', label: 'Gender does not match' },
  { code: 'address_mismatch', label: 'Address does not match' },
  { code: 'expired', label: 'Document has expired' },
  { code: 'not_yet_valid', label: 'Document is not valid yet' },
  { code: 'invalid_number_format', label: 'ID number format is wrong' },
  { code: 'tampered', label: 'Document looks altered or tampered with' },
  { code: 'illegible', label: 'Scan is unreadable' },
  { code: 'photo_mismatch', label: 'Photo does not match the applicant' },
  { code: 'signature_missing', label: 'Signature missing or does not match' },
  { code: 'unacceptable_document', label: 'This document type is not accepted' },
  { code: 'duplicate_submission', label: 'Already submitted by another applicant' },
  { code: 'mobile_not_linked', label: 'Mobile number is not linked to this ID' },
  { code: 'underage', label: 'Applicant is under the minimum age' },
] as const;

export type KycIssueCode = (typeof KYC_ISSUES)[number]['code'];

const VALID_CODES = new Set<string>(KYC_ISSUES.map((i) => i.code));

/**
 * Maps whatever the client sent onto a canonical code.
 *
 * Accepts the code itself, the human label, and common prose forms, so a
 * candidate is graded on whether they identified the right fault rather than
 * on how they phrased it. Returns null when nothing matches, which grades as
 * incorrect — it does not guess.
 */
export function normaliseIssue(raw: string | undefined): KycIssueCode | null {
  if (!raw) return null;

  const squashed = raw
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');

  if (VALID_CODES.has(squashed)) return squashed as KycIssueCode;

  // Match against the labels, similarly squashed.
  const byLabel = KYC_ISSUES.find(
    (i) => i.label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') === squashed,
  );
  if (byLabel) return byLabel.code;

  // A few prose forms that are unambiguous.
  const aliases: Record<string, KycIssueCode> = {
    name_does_not_match: 'name_mismatch',
    names_do_not_match: 'name_mismatch',
    wrong_name: 'name_mismatch',
    dob_does_not_match: 'dob_mismatch',
    date_of_birth_mismatch: 'dob_mismatch',
    wrong_dob: 'dob_mismatch',
    document_expired: 'expired',
    out_of_date: 'expired',
    altered: 'tampered',
    edited: 'tampered',
    forged: 'tampered',
    fake: 'tampered',
    blurry: 'illegible',
    unreadable: 'illegible',
    too_blurry_to_read: 'illegible',
    bad_number: 'invalid_number_format',
    wrong_number_format: 'invalid_number_format',
    duplicate: 'duplicate_submission',
    already_used: 'duplicate_submission',
  };
  return aliases[squashed] ?? null;
}
