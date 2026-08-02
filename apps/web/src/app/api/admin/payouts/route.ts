import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { prisma } from '@platform/database';
import { getAdminFromRequest } from '@/lib/auth';
import { PAYOUT_MIN_INR, PAYOUT_MAX_INR, getPayoutEligibilityCutoffUtc, currentMonthIst } from '@platform/shared';

export async function GET(req: NextRequest) {
  const month = req.nextUrl.searchParams.get('month') ?? currentMonthIst();

  const payouts = await prisma.monthlyPayout.findMany({
    where: { month },
    include: { user: { select: { referralCode: true, telegramUsername: true } } },
    orderBy: { totalAmountInr: 'desc' },
  });

  const lastRateChange = await prisma.auditLog.findFirst({
    where: { action: 'PAYOUT_RATE_SET' },
    orderBy: { createdAt: 'desc' },
  });
  const metadata = lastRateChange?.metadata as { rate?: number; month?: string } | null;
  const currentRate = metadata?.month === month ? metadata?.rate : null;

  return NextResponse.json({
    month,
    currentRate,
    payouts: payouts.map((p) => ({
      id: p.id,
      userId: p.userId,
      referralCode: p.user.referralCode,
      telegramUsername: p.user.telegramUsername,
      activeReferralCount: p.activeReferralCount,
      ratePerReferralInr: Number(p.ratePerReferralInr),
      totalAmountInr: Number(p.totalAmountInr),
      status: p.status,
      transactionRef: p.transactionRef,
      paidAt: p.paidAt,
    })),
  });
}

const setRateSchema = z.object({
  month: z.string().regex(/^\d{4}-\d{2}$/),
  rate: z.number().min(PAYOUT_MIN_INR).max(PAYOUT_MAX_INR),
});

export async function POST(req: NextRequest) {
  const admin = getAdminFromRequest(req);
  const body = await req.json().catch(() => null);

  // Two sub-actions share this endpoint: setting the rate, and triggering the run.
  if (body?.action === 'SET_RATE') {
    const parsed = setRateSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json({ error: 'Rate must be between ₹1 and ₹5.' }, { status: 400 });
    }
    await prisma.auditLog.create({
      data: {
        adminId: admin?.sub,
        action: 'PAYOUT_RATE_SET',
        targetType: 'MonthlyPayout',
        metadata: { month: parsed.data.month, rate: parsed.data.rate },
      },
    });
    return NextResponse.json({ ok: true });
  }

  if (body?.action === 'TRIGGER_RUN') {
    const parsed = setRateSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json({ error: 'A valid month and rate (₹1-5) are required to run payouts.' }, { status: 400 });
    }
    const { month, rate } = parsed.data;
    const cutoff = getPayoutEligibilityCutoffUtc(month);

    // Eligibility: a referral only counts toward this month's payout if it
    // became ACTIVE on or before the 15th of `month`, Indian Standard Time.
    const usersWithEligibleReferrals = await prisma.user.findMany({
      where: { referrals: { some: { status: 'ACTIVE', activatedAt: { lte: cutoff } } } },
      select: { id: true, bankAccountHolder: true, bankAccountNumber: true, bankIfsc: true, bankUpiId: true },
    });

    let created = 0;
    for (const u of usersWithEligibleReferrals) {
      const activeReferralCount = await prisma.user.count({
        where: { referredById: u.id, status: 'ACTIVE', activatedAt: { lte: cutoff } },
      });
      if (activeReferralCount <= 0) continue;
      const totalAmountInr = rate * activeReferralCount;

      try {
        await prisma.monthlyPayout.create({
          data: {
            userId: u.id,
            month,
            activeReferralCount,
            ratePerReferralInr: rate,
            totalAmountInr,
            status: 'PENDING',
            bankAccountSnapshot: {
              bankAccountHolder: u.bankAccountHolder,
              bankAccountNumber: u.bankAccountNumber,
              bankIfsc: u.bankIfsc,
              bankUpiId: u.bankUpiId,
            },
          },
        });
        created++;
      } catch {
        // Unique constraint on [userId, month] — row already exists for this month, skip.
      }
    }

    await prisma.auditLog.create({
      data: {
        adminId: admin?.sub,
        action: 'PAYOUT_RUN_TRIGGERED',
        targetType: 'MonthlyPayout',
        metadata: { month, rate, created },
      },
    });

    return NextResponse.json({ ok: true, created });
  }

  return NextResponse.json({ error: 'Unknown action.' }, { status: 400 });
}

const markPaidSchema = z.object({
  payoutId: z.string().min(1),
  transactionRef: z.string().min(1),
});

export async function PATCH(req: NextRequest) {
  const admin = getAdminFromRequest(req);
  const parsed = markPaidSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: 'A transaction reference is required.' }, { status: 400 });
  }

  const payout = await prisma.monthlyPayout.update({
    where: { id: parsed.data.payoutId },
    data: {
      status: 'PAID',
      transactionRef: parsed.data.transactionRef,
      paidAt: new Date(),
      paidByAdminId: admin?.sub,
    },
  });

  await prisma.auditLog.create({
    data: {
      adminId: admin?.sub,
      action: 'PAYOUT_MARKED_PAID',
      targetType: 'MonthlyPayout',
      targetId: payout.id,
      metadata: { transactionRef: parsed.data.transactionRef },
    },
  });

  return NextResponse.json({ ok: true });
}
