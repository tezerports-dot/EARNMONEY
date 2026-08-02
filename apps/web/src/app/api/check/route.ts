import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { prisma } from '@platform/database';
import { currentMonthIst } from '@platform/shared';

const querySchema = z.object({
  code: z.string().min(1).max(32),
});

export async function GET(req: NextRequest) {
  const parsed = querySchema.safeParse({ code: req.nextUrl.searchParams.get('code') });
  if (!parsed.success) {
    return NextResponse.json({ error: 'A referral code is required.' }, { status: 400 });
  }

  const user = await prisma.user.findUnique({ where: { referralCode: parsed.data.code.trim() } });
  if (!user) {
    return NextResponse.json({ error: 'No account found for that referral code.' }, { status: 404 });
  }

  // Read cached counts (refreshed once daily by the worker's snapshot job)
  // instead of computing live counts on every request — this is what keeps
  // the public site cheap to serve at high user volume.
  const thisMonthPayout = await prisma.monthlyPayout.findUnique({
    where: { userId_month: { userId: user.id, month: currentMonthIst() } },
  });

  const paidAggregate = await prisma.monthlyPayout.aggregate({
    where: { userId: user.id, status: 'PAID' },
    _sum: { totalAmountInr: true },
  });

  return NextResponse.json({
    referralCode: user.referralCode,
    status: user.status,
    activeReferralCount: user.cachedActiveReferralCount,
    payoutEligibleReferralCount: user.cachedPayoutEligibleReferralCount,
    statusAsOf: user.statusCachedAt,
    thisMonthPayoutInr: thisMonthPayout ? Number(thisMonthPayout.totalAmountInr) : null,
    thisMonthPayoutStatus: thisMonthPayout?.status ?? null,
    lifetimePaidInr: Number(paidAggregate._sum.totalAmountInr ?? 0),
  });
}
