'use client';

import { useState } from 'react';
import { AdSlot } from '@/components/AdSlot';

interface CheckResult {
  referralCode: string;
  status: string;
  activeReferralCount: number;
  payoutEligibleReferralCount: number;
  statusAsOf: string | null;
  thisMonthPayoutInr: number | null;
  thisMonthPayoutStatus: string | null;
  lifetimePaidInr: number;
}

export default function CheckPage() {
  const [code, setCode] = useState('');
  const [result, setResult] = useState<CheckResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`/api/check?code=${encodeURIComponent(code.trim())}`);
      const data = await res.json();
      if (!res.ok) {
        setError(data.error ?? 'Something went wrong.');
        return;
      }
      setResult(data);
    } catch {
      setError('Network error. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <AdSlot label="header" height={90} />

      <div className="card max-w-md mx-auto">
        <h1 className="text-xl font-semibold mb-4">Check your referral status</h1>
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            className="input"
            placeholder="REF_XXXXXXXX"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
          />
          <button className="btn-primary whitespace-nowrap" disabled={loading}>
            {loading ? 'Checking…' : 'Check'}
          </button>
        </form>

        {error && <p className="text-red-600 text-sm mt-3">{error}</p>}

        {result && (
          <div>
            <dl className="mt-5 space-y-2 text-sm">
              <Row label="Referral code" value={result.referralCode} />
              <Row label="Status" value={result.status} />
              <Row label="Active referrals" value={String(result.activeReferralCount)} />
              <Row
                label="Eligible for this month's payout"
                value={String(result.payoutEligibleReferralCount)}
              />
              <Row
                label="This month's payout"
                value={
                  result.thisMonthPayoutInr !== null
                    ? `₹${result.thisMonthPayoutInr} (${result.thisMonthPayoutStatus})`
                    : 'Not calculated yet'
                }
              />
              <Row label="Lifetime paid" value={`₹${result.lifetimePaidInr}`} />
            </dl>
            <p className="text-xs text-gray-400 mt-3">
              Numbers refresh once every 24 hours
              {result.statusAsOf ? ` — last updated ${new Date(result.statusAsOf).toLocaleString()}` : ''}.
              A referral only counts toward a month's payout if they were active by the 15th of that month.
            </p>
          </div>
        )}
      </div>

      <AdSlot label="in-content" height={250} />
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b border-gray-100 pb-2">
      <dt className="text-gray-500">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}
