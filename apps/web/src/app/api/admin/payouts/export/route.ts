import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@platform/database';

function csvEscape(value: unknown): string {
  const s = value === null || value === undefined ? '' : String(value);
  if (s.includes(',') || s.includes('"') || s.includes('\n')) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

function toCsv(header: string[], rows: unknown[][]): string {
  return [header.join(','), ...rows.map((r) => r.map(csvEscape).join(','))].join('\n');
}

/**
 * Three export formats, selected with ?format=:
 *
 *  - bulk (default): ready to hand to your bank's bulk-transfer / bulk-NEFT
 *    upload tool. Only PENDING rows that actually have a usable payment
 *    method (bank account+IFSC, or a UPI ID as fallback) are included.
 *  - full: every row for the month with full status/audit detail, for your
 *    own records or reconciliation.
 *  - missing: PENDING rows for the month where the user has NOT added a
 *    usable payment method yet — use this list to chase them for /bankdetails.
 */
export async function GET(req: NextRequest) {
  const month = req.nextUrl.searchParams.get('month');
  const format = req.nextUrl.searchParams.get('format') ?? 'bulk';
  if (!month) {
    return NextResponse.json({ error: 'month query param is required (YYYY-MM).' }, { status: 400 });
  }

  const payouts = await prisma.monthlyPayout.findMany({
    where: { month },
    include: {
      user: {
        select: {
          referralCode: true,
          telegramUsername: true,
          bankAccountHolder: true,
          bankAccountNumber: true,
          bankIfsc: true,
          bankUpiId: true,
        },
      },
    },
    orderBy: { totalAmountInr: 'desc' },
  });

  const hasBankAccount = (u: { bankAccountNumber: string | null; bankIfsc: string | null }) =>
    Boolean(u.bankAccountNumber && u.bankIfsc);
  const hasUpi = (u: { bankUpiId: string | null }) => Boolean(u.bankUpiId);
  const hasAnyPaymentMethod = (u: { bankAccountNumber: string | null; bankIfsc: string | null; bankUpiId: string | null }) =>
    hasBankAccount(u) || hasUpi(u);

  let csv: string;
  let filename: string;

  if (format === 'missing') {
    const rows = payouts
      .filter((p) => p.status === 'PENDING' && !hasAnyPaymentMethod(p.user))
      .map((p) => [p.user.referralCode, p.user.telegramUsername, p.totalAmountInr.toString()]);
    csv = toCsv(['referral_code', 'telegram_username', 'amount_due_inr'], rows);
    filename = `payouts-${month}-missing-bank-details.csv`;
  } else if (format === 'full') {
    const rows = payouts.map((p) => [
      p.user.referralCode,
      p.user.telegramUsername,
      p.activeReferralCount,
      p.ratePerReferralInr.toString(),
      p.totalAmountInr.toString(),
      p.status,
      p.user.bankAccountHolder,
      p.user.bankAccountNumber,
      p.user.bankIfsc,
      p.user.bankUpiId,
      p.transactionRef,
    ]);
    csv = toCsv(
      [
        'referral_code',
        'telegram_username',
        'eligible_referral_count',
        'rate_per_referral_inr',
        'total_amount_inr',
        'status',
        'bank_account_holder',
        'bank_account_number',
        'bank_ifsc',
        'bank_upi_id',
        'transaction_ref',
      ],
      rows,
    );
    filename = `payouts-${month}-full.csv`;
  } else {
    // bulk (default): only PENDING rows with a usable payment method,
    // in the shape most banks' bulk-upload tools expect.
    const rows = payouts
      .filter((p) => p.status === 'PENDING' && hasAnyPaymentMethod(p.user))
      .map((p) => [
        p.user.bankAccountHolder ?? p.user.referralCode,
        hasBankAccount(p.user) ? p.user.bankAccountNumber : '',
        hasBankAccount(p.user) ? p.user.bankIfsc : '',
        hasUpi(p.user) ? p.user.bankUpiId : '',
        p.totalAmountInr.toString(),
        `REFPAY-${p.user.referralCode}-${month}`,
      ]);
    csv = toCsv(
      ['beneficiary_name', 'account_number', 'ifsc_code', 'upi_id', 'amount_inr', 'narration'],
      rows,
    );
    filename = `payouts-${month}-bulk-upload.csv`;
  }

  return new NextResponse(csv, {
    headers: {
      'Content-Type': 'text/csv',
      'Content-Disposition': `attachment; filename="${filename}"`,
    },
  });
}
