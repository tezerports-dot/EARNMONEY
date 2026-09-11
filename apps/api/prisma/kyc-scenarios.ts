/**
 * The KYC practice-document bank.
 *
 * EVERY DOCUMENT HERE IS FICTIONAL. Names, numbers, addresses and dates are
 * invented for training. No real person's identity data belongs in this file,
 * in the database, or in any scenario added later through the admin API —
 * routing a real applicant's government-ID data through an untrained peer is
 * the practice docs/SPEC-DEVIATIONS.md exists to prevent, and consent does not
 * make it lawful (the Aadhaar Act restricts disclosure to entities authorised
 * under it, and DPDP consent is not "free" when a job depends on giving it).
 *
 * The skill being trained is real and ordinary: given a customer's document
 * and the form they filled in, decide whether the two agree and, if not, say
 * what is wrong. That is day-one retail KYC work.
 *
 * Design notes for whoever extends this:
 *  - Roughly a third of scenarios are CLEAN. Without them a candidate scores
 *    well by answering "invalid" every time, and the test measures nothing.
 *  - Faults are single and unambiguous. A document with two problems has two
 *    defensible answers and cannot be graded fairly.
 *  - `issue` must be a code from src/kyc-training/kyc-issues.ts, since that is
 *    the list the app offers and grading compares against.
 */

export type SeedScenario = {
  title: string;
  syntheticDocument: Record<string, string>;
  expectedOutcome: { valid: boolean; issue?: string };
  difficulty: 'easy' | 'standard' | 'hard';
};

export const KYC_SCENARIOS: SeedScenario[] = [
  // ---------------------------------------------------------------- clean --
  {
    title: 'Everything agrees — accept',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Anil Kumar Yadav',
      nameOnForm: 'Anil Kumar Yadav',
      dateOfBirthOnDocument: '2000-09-30',
      dateOfBirthOnForm: '2000-09-30',
      addressOnDocument: '14 Sample Road, Jaipur, Rajasthan',
      addressOnForm: '14 Sample Road, Jaipur, Rajasthan',
      issueDate: '2022-01-01',
      expiryDate: '2032-01-01',
      documentNumber: 'SAMPLE-0003-0001',
    },
    expectedOutcome: { valid: true },
    difficulty: 'easy',
  },
  {
    title: 'Middle name on document, absent on form — still the same person',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Sunita Devi Chauhan',
      nameOnForm: 'Sunita Chauhan',
      note: 'Applicant confirmed Devi is a middle name, not a surname change.',
      dateOfBirthOnDocument: '1995-02-11',
      dateOfBirthOnForm: '1995-02-11',
      issueDate: '2021-06-15',
      expiryDate: '2031-06-15',
      documentNumber: 'SAMPLE-0011-0002',
    },
    // Deliberately tests over-rejection: a middle name is not a mismatch.
    expectedOutcome: { valid: true },
    difficulty: 'hard',
  },
  {
    title: 'Address written differently but identical — accept',
    syntheticDocument: {
      documentType: 'Sample utility bill',
      nameOnDocument: 'Farhan Ali',
      nameOnForm: 'Farhan Ali',
      addressOnDocument: 'Flat 4B, Green View Apartments, Sector 21, Gurugram',
      addressOnForm: '4B Green View Apts., Sector 21, Gurugram',
      issueDate: '2026-07-02',
      documentNumber: 'SAMPLE-BILL-0093',
    },
    expectedOutcome: { valid: true },
    difficulty: 'hard',
  },
  {
    title: 'Recently issued document — accept',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Meera Nair',
      nameOnForm: 'Meera Nair',
      dateOfBirthOnDocument: '1999-12-05',
      dateOfBirthOnForm: '1999-12-05',
      issueDate: '2026-08-20',
      expiryDate: '2036-08-20',
      documentNumber: 'SAMPLE-0044-0007',
    },
    expectedOutcome: { valid: true },
    difficulty: 'easy',
  },
  {
    title: 'Maiden name on document, married name on form, with supporting note',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Kavita Joshi',
      nameOnForm: 'Kavita Deshmukh',
      supportingDocument: 'Sample marriage certificate attached, names match on both',
      dateOfBirthOnDocument: '1993-03-19',
      dateOfBirthOnForm: '1993-03-19',
      documentNumber: 'SAMPLE-0058-0011',
    },
    expectedOutcome: { valid: true },
    difficulty: 'hard',
  },
  {
    title: 'Photo described as matching — accept',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Rohit Bansal',
      nameOnForm: 'Rohit Bansal',
      photoDescription: 'Placeholder illustration; reviewer notes it matches the applicant',
      dateOfBirthOnDocument: '1997-07-07',
      dateOfBirthOnForm: '1997-07-07',
      expiryDate: '2030-01-01',
      documentNumber: 'SAMPLE-0062-0003',
    },
    expectedOutcome: { valid: true },
    difficulty: 'easy',
  },
  {
    title: 'Abbreviated first initial on form — accept',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Vijay Raghavan',
      nameOnForm: 'V. Raghavan',
      dateOfBirthOnDocument: '1991-11-23',
      dateOfBirthOnForm: '1991-11-23',
      documentNumber: 'SAMPLE-0071-0004',
    },
    expectedOutcome: { valid: true },
    difficulty: 'hard',
  },
  {
    title: 'Document valid for several more years — accept',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Imran Sheikh',
      nameOnForm: 'Imran Sheikh',
      issueDate: '2020-02-02',
      expiryDate: '2030-02-02',
      dateOfBirthOnDocument: '1996-05-14',
      dateOfBirthOnForm: '1996-05-14',
      documentNumber: 'SAMPLE-0080-0009',
    },
    expectedOutcome: { valid: true },
    difficulty: 'easy',
  },
  {
    title: 'Gender recorded consistently — accept',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Pooja Rani',
      nameOnForm: 'Pooja Rani',
      genderOnDocument: 'Female',
      genderOnForm: 'Female',
      dateOfBirthOnDocument: '2001-01-30',
      dateOfBirthOnForm: '2001-01-30',
      documentNumber: 'SAMPLE-0090-0012',
    },
    expectedOutcome: { valid: true },
    difficulty: 'easy',
  },
  {
    title: 'Applicant just turned eighteen — accept',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Deepak Rawat',
      nameOnForm: 'Deepak Rawat',
      dateOfBirthOnDocument: '2008-01-15',
      dateOfBirthOnForm: '2008-01-15',
      applicationDate: '2026-03-01',
      minimumAge: '18',
      documentNumber: 'SAMPLE-0101-0014',
    },
    expectedOutcome: { valid: true },
    difficulty: 'hard',
  },

  // ------------------------------------------------------------- mismatch --
  {
    title: 'Name spelled differently on form',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Rahul Kumar Sharma',
      nameOnForm: 'Rahul Kumar Sharman',
      dateOfBirthOnDocument: '1998-04-12',
      dateOfBirthOnForm: '1998-04-12',
      documentNumber: 'SAMPLE-0001-0021',
    },
    expectedOutcome: { valid: false, issue: 'name_mismatch' },
    difficulty: 'standard',
  },
  {
    title: 'Surname and given name swapped',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Patel Nirav',
      nameOnForm: 'Nirav Chauhan',
      dateOfBirthOnDocument: '1994-08-08',
      dateOfBirthOnForm: '1994-08-08',
      documentNumber: 'SAMPLE-0002-0022',
    },
    expectedOutcome: { valid: false, issue: 'name_mismatch' },
    difficulty: 'standard',
  },
  {
    title: 'Year of birth differs by one',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Sneha Pillai',
      nameOnForm: 'Sneha Pillai',
      dateOfBirthOnDocument: '1999-06-21',
      dateOfBirthOnForm: '1998-06-21',
      documentNumber: 'SAMPLE-0003-0023',
    },
    expectedOutcome: { valid: false, issue: 'dob_mismatch' },
    difficulty: 'hard',
  },
  {
    title: 'Day and month transposed in date of birth',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Aarti Singh',
      nameOnForm: 'Aarti Singh',
      dateOfBirthOnDocument: '1997-03-09',
      dateOfBirthOnForm: '1997-09-03',
      documentNumber: 'SAMPLE-0004-0024',
    },
    expectedOutcome: { valid: false, issue: 'dob_mismatch' },
    difficulty: 'hard',
  },
  {
    title: 'Gender on form contradicts the document',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Rajesh Gupta',
      nameOnForm: 'Rajesh Gupta',
      genderOnDocument: 'Male',
      genderOnForm: 'Female',
      dateOfBirthOnDocument: '1990-10-10',
      dateOfBirthOnForm: '1990-10-10',
      documentNumber: 'SAMPLE-0005-0025',
    },
    expectedOutcome: { valid: false, issue: 'gender_mismatch' },
    difficulty: 'standard',
  },
  {
    title: 'Different city on the form',
    syntheticDocument: {
      documentType: 'Sample utility bill',
      nameOnDocument: 'Harpreet Kaur',
      nameOnForm: 'Harpreet Kaur',
      addressOnDocument: '22 Model Town, Ludhiana, Punjab',
      addressOnForm: '22 Model Town, Amritsar, Punjab',
      documentNumber: 'SAMPLE-BILL-0101',
    },
    expectedOutcome: { valid: false, issue: 'address_mismatch' },
    difficulty: 'standard',
  },

  // ------------------------------------------------------------- validity --
  {
    title: 'Document expired last year',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Priya Verma',
      nameOnForm: 'Priya Verma',
      issueDate: '2015-01-01',
      expiryDate: '2025-01-01',
      applicationDate: '2026-02-10',
      documentNumber: 'SAMPLE-0006-0026',
    },
    expectedOutcome: { valid: false, issue: 'expired' },
    difficulty: 'easy',
  },
  {
    title: 'Expired by a matter of days',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Suresh Menon',
      nameOnForm: 'Suresh Menon',
      issueDate: '2016-03-01',
      expiryDate: '2026-02-25',
      applicationDate: '2026-03-01',
      documentNumber: 'SAMPLE-0007-0027',
    },
    expectedOutcome: { valid: false, issue: 'expired' },
    difficulty: 'hard',
  },
  {
    title: 'Issue date is in the future',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Neha Agarwal',
      nameOnForm: 'Neha Agarwal',
      issueDate: '2027-01-01',
      expiryDate: '2037-01-01',
      applicationDate: '2026-05-05',
      documentNumber: 'SAMPLE-0008-0028',
    },
    expectedOutcome: { valid: false, issue: 'not_yet_valid' },
    difficulty: 'hard',
  },
  {
    title: 'Applicant is below the minimum age',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Karan Bhatt',
      nameOnForm: 'Karan Bhatt',
      dateOfBirthOnDocument: '2011-04-04',
      dateOfBirthOnForm: '2011-04-04',
      applicationDate: '2026-04-04',
      minimumAge: '18',
      documentNumber: 'SAMPLE-0009-0029',
    },
    expectedOutcome: { valid: false, issue: 'underage' },
    difficulty: 'standard',
  },

  // ----------------------------------------------------------- document ----
  {
    title: 'ID number is too short',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Manish Tiwari',
      nameOnForm: 'Manish Tiwari',
      documentNumber: 'SAMPLE-12',
      expectedFormat: 'SAMPLE-nnnn-nnnn',
    },
    expectedOutcome: { valid: false, issue: 'invalid_number_format' },
    difficulty: 'standard',
  },
  {
    title: 'ID number contains letters where digits belong',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Ritu Malhotra',
      nameOnForm: 'Ritu Malhotra',
      documentNumber: 'SAMPLE-00X5-##45',
      expectedFormat: 'SAMPLE-nnnn-nnnn',
    },
    expectedOutcome: { valid: false, issue: 'invalid_number_format' },
    difficulty: 'standard',
  },
  {
    title: 'Date of birth appears overwritten',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Ajay Deshpande',
      nameOnForm: 'Ajay Deshpande',
      dateOfBirthOnDocument: '1992-01-01',
      reviewerNote: 'Digits in the year sit higher than the rest of the line and use a different font',
      documentNumber: 'SAMPLE-0010-0030',
    },
    expectedOutcome: { valid: false, issue: 'tampered' },
    difficulty: 'standard',
  },
  {
    title: 'Photograph area shows a visible edge',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Sanjay Bose',
      nameOnForm: 'Sanjay Bose',
      reviewerNote: 'A rectangular seam is visible around the photograph; the lamination is broken there',
      documentNumber: 'SAMPLE-0012-0031',
    },
    expectedOutcome: { valid: false, issue: 'tampered' },
    difficulty: 'standard',
  },
  {
    title: 'Scan too blurred to read',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: '(not legible)',
      nameOnForm: 'Ramesh Chandra',
      reviewerNote: 'Upload is out of focus; neither the number nor the date can be read',
      documentNumber: '(not legible)',
    },
    expectedOutcome: { valid: false, issue: 'illegible' },
    difficulty: 'easy',
  },
  {
    title: 'Only a corner of the document was photographed',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Lakshmi Iyer',
      nameOnForm: 'Lakshmi Iyer',
      reviewerNote: 'Bottom half of the card is outside the frame; expiry and number not visible',
      documentNumber: '(cropped out)',
    },
    expectedOutcome: { valid: false, issue: 'illegible' },
    difficulty: 'standard',
  },
  {
    title: 'Photo on the document is clearly a different person',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Gaurav Saxena',
      nameOnForm: 'Gaurav Saxena',
      photoDescription: 'Placeholder illustration of an elderly man',
      applicantDescription: 'Applicant present in branch is in their twenties',
      documentNumber: 'SAMPLE-0013-0032',
    },
    expectedOutcome: { valid: false, issue: 'photo_mismatch' },
    difficulty: 'standard',
  },
  {
    title: 'Signature block is empty',
    syntheticDocument: {
      documentType: 'Sample application form',
      nameOnDocument: 'Bhavna Shah',
      nameOnForm: 'Bhavna Shah',
      reviewerNote: 'The declaration is unsigned',
      documentNumber: 'SAMPLE-FORM-0044',
    },
    expectedOutcome: { valid: false, issue: 'signature_missing' },
    difficulty: 'easy',
  },
  {
    title: 'A library card offered as proof of identity',
    syntheticDocument: {
      documentType: 'Sample library membership card',
      nameOnDocument: 'Nitin Kulkarni',
      nameOnForm: 'Nitin Kulkarni',
      acceptedDocumentTypes: 'Sample ID card, sample passport, sample driving licence',
      documentNumber: 'LIB-2291',
    },
    expectedOutcome: { valid: false, issue: 'unacceptable_document' },
    difficulty: 'standard',
  },
  {
    title: 'Same document number already used by another applicant',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Asha Rao',
      nameOnForm: 'Asha Rao',
      documentNumber: 'SAMPLE-0014-0033',
      reviewerNote: 'This number is already recorded against a different applicant in the sample register',
    },
    expectedOutcome: { valid: false, issue: 'duplicate_submission' },
    difficulty: 'standard',
  },
  {
    title: 'Mobile number not linked to the ID',
    syntheticDocument: {
      documentType: 'Sample ID card',
      nameOnDocument: 'Yogesh Patil',
      nameOnForm: 'Yogesh Patil',
      mobileOnForm: '+9190000 00011',
      linkedMobileLastFour: '7788',
      reviewerNote: 'Linked-number check returned a different last four digits',
      documentNumber: 'SAMPLE-0015-0034',
    },
    expectedOutcome: { valid: false, issue: 'mobile_not_linked' },
    difficulty: 'standard',
  },
];
