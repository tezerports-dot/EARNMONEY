import { PrismaClient } from '@prisma/client';
import * as argon2 from 'argon2';

const prisma = new PrismaClient();

async function main() {
  // --- Admin-tunable thresholds -------------------------------------------
  // These are the two numbers you asked to set to 3. Change them here (or via
  // the admin panel once it's built) — never hardcode them in application code.
  await prisma.systemConfig.upsert({
    where: { key: 'referral_threshold' },
    update: {},
    create: {
      key: 'referral_threshold',
      value: 200,
      description:
        'Number of credited referrals a candidate needs before application becomes eligible.',
    },
  });

  await prisma.systemConfig.upsert({
    where: { key: 'kyc_challenge_threshold' },
    update: {},
    create: {
      key: 'kyc_challenge_threshold',
      value: 200,
      description:
        'Number of KYC training scenarios a candidate must pass correctly before application becomes eligible.',
    },
  });

  await prisma.systemConfig.upsert({
    where: { key: 'fraud_strike_limit' },
    update: {},
    create: {
      key: 'fraud_strike_limit',
      value: 8,
      description:
        'Confirmed fake referrals a candidate may accumulate before the account is suspended.',
    },
  });

  await prisma.systemConfig.upsert({
    where: { key: 'kyc_rejection_attempts' },
    update: {},
    create: {
      key: 'kyc_rejection_attempts',
      value: 3,
      description:
        'Independent verification rejections needed before a referred account is treated as conclusively fake.',
    },
  });

  await prisma.systemConfig.upsert({
    where: { key: 'referral_attribution_window_days' },
    update: {},
    create: {
      key: 'referral_attribution_window_days',
      value: 30,
      description: 'Days after signup during which referral attribution can still be credited.',
    },
  });

  // --- Sample synthetic KYC training scenarios ----------------------------
  // Entirely fictitious documents. None of this is real applicant data.
  const scenarios = [
    {
      title: 'Name mismatch between ID and application form',
      syntheticDocument: {
        idType: 'sample_id_card',
        idName: 'Rahul K. Sharma',
        formName: 'Rahul Sharma',
        dob: '1998-04-12',
        idNumber: 'SAMPLE-0001-XXXX',
        photoDescription: 'Placeholder illustration, not a real photo',
      },
      expectedOutcome: { valid: false, issue: 'name_mismatch' },
      difficulty: 'standard',
    },
    {
      title: 'Expired sample document',
      syntheticDocument: {
        idType: 'sample_id_card',
        idName: 'Priya Verma',
        formName: 'Priya Verma',
        issueDate: '2015-01-01',
        expiryDate: '2020-01-01',
        idNumber: 'SAMPLE-0002-XXXX',
      },
      expectedOutcome: { valid: false, issue: 'expired' },
      difficulty: 'standard',
    },
    {
      title: 'Valid, consistent sample document',
      syntheticDocument: {
        idType: 'sample_id_card',
        idName: 'Anil Kumar Yadav',
        formName: 'Anil Kumar Yadav',
        dob: '2000-09-30',
        issueDate: '2022-01-01',
        expiryDate: '2032-01-01',
        idNumber: 'SAMPLE-0003-XXXX',
      },
      expectedOutcome: { valid: true },
      difficulty: 'standard',
    },
    {
      title: 'Photo/DOB inconsistency (age mismatch)',
      syntheticDocument: {
        idType: 'sample_id_card',
        idName: 'Sunita Devi',
        formName: 'Sunita Devi',
        dob: '1975-03-11',
        photoDescription: 'Placeholder illustration described as appearing under 18',
        idNumber: 'SAMPLE-0004-XXXX',
      },
      expectedOutcome: { valid: false, issue: 'age_inconsistency' },
      difficulty: 'harder',
    },
    {
      title: 'Tampered-looking sample document number',
      syntheticDocument: {
        idType: 'sample_id_card',
        idName: 'Deepak Choudhary',
        formName: 'Deepak Choudhary',
        idNumber: 'SAMPLE-00X5-####',
        notes: 'ID number contains non-standard characters for this document type',
      },
      expectedOutcome: { valid: false, issue: 'suspected_tampering' },
      difficulty: 'harder',
    },
  ];

  for (const scenario of scenarios) {
    await prisma.kycTrainingScenario.upsert({
      where: { id: scenario.title.toLowerCase().replace(/[^a-z0-9]+/g, '-') },
      update: {},
      create: {
        id: scenario.title.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
        title: scenario.title,
        syntheticDocument: scenario.syntheticDocument,
        expectedOutcome: scenario.expectedOutcome,
        difficulty: scenario.difficulty,
      },
    });
  }

  // --- Dev-only superadmin (synthetic credentials, change immediately) ----
  if (process.env.NODE_ENV !== 'production') {
    const passwordHash = await argon2.hash('ChangeMe123!DevOnly');
    await prisma.user.upsert({
      where: { mobileE164: '+910000000000' },
      update: {},
      create: {
        mobileE164: '+910000000000',
        passwordHash,
        role: 'ADMIN_SUPERADMIN',
        status: 'ACTIVE',
        referralCode: 'ADMIN0001',
      },
    });
    console.log('Seeded dev superadmin +910000000000 / ChangeMe123!DevOnly — DEV ONLY, do not use in production.');
  }

  // Sample vacancies so the home screen renders something real on a fresh
  // install. Replace these with the actual openings before launch.
  const vacancies = [
    { state: 'Rajasthan', tier: 'tier1', title: 'Retail Outlet Associate', postCount: 40, salaryMonthlyPaise: 1800000n },
    { state: 'Uttar Pradesh', tier: 'tier1', title: 'Retail Outlet Associate', postCount: 60, salaryMonthlyPaise: 1800000n },
    { state: 'Gujarat', tier: 'tier2', title: 'Store Supervisor', postCount: 25, salaryMonthlyPaise: 2400000n },
    { state: 'Madhya Pradesh', tier: 'tier2', title: 'Store Supervisor', postCount: 20, salaryMonthlyPaise: 2400000n },
    { state: 'Maharashtra', tier: 'tier3', title: 'Area Coordinator', postCount: 10, salaryMonthlyPaise: 3200000n },
  ];
  for (const v of vacancies) {
    const id = `${v.state}-${v.tier}`.toLowerCase().replace(/[^a-z0-9]+/g, '-');
    await prisma.vacancy.upsert({ where: { id }, update: {}, create: { id, ...v } });
  }
  console.log(`Seeded ${vacancies.length} sample vacancies.`);

  console.log('Seed complete.');
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
