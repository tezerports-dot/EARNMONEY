'use client';

import { useEffect, useState, useCallback } from 'react';
import { currentMonthIst } from '@platform/shared';

interface PayoutRow {
  id: string;
  referralCode: string;
  telegramUsername: string | null;
  activeReferralCount: number;
  ratePerReferralInr: number;
  totalAmountInr: number;
  status: string;
  transactionRef: string | null;
}

export default function AdminPayoutsPage() {
  const [month, setMonth] = useState(currentMonthIst());
  const [rate, setRate] = useState(1);
  const [payouts, setPayouts] = useState<PayoutRow[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [txRefDrafts, setTxRefDrafts] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    const res = await fetch(`/api/admin/payouts?month=${month}`);
    const data = await res.json();
    setPayouts(data.payouts ?? []);
    if (data.currentRate) setRate(data.currentRate);
  }, [month]);

  useEffect(() => {
    load();
  }, [load]);

  async function setRateOnly() {
    setError(null);
    setMessage(null);
    const res = await fetch('/api/admin/payouts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'SET_RATE', month, rate }),
    });
    const data = await res.json();
    if (!res.ok) return setError(data.error);
    setMessage(`Rate of ₹${rate} set for ${month}.`);
  }

  async function triggerRun() {
    setError(null);
    setMessage(null);
    const res = await fetch('/api/admin/payouts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'TRIGGER_RUN', month, rate }),
    });
    const data = await res.json();
    if (!res.ok) return setError(data.error);
    setMessage(`Payout run complete — created ${data.created} new rows for ${month}.`);
    load();
  }

  async function markPaid(payoutId: string) {
    const transactionRef = txRefDrafts[payoutId]?.trim();
    if (!transactionRef) {
      setError('Enter a transaction reference before marking paid.');
      return;
    }
    await fetch('/api/admin/payouts', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ payoutId, transactionRef }),
    });
    load();
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Monthly Payouts</h1>

      <div className="card mb-6 flex flex-wrap gap-3 items-end">
        <div>
          <label className="text-xs text-gray-500 block mb-1">Month</label>
          <input className="input" value={month} onChange={(e) => setMonth(e.target.value)} placeholder="YYYY-MM" />
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Rate per active referral (₹1–5)</label>
          <input
            className="input w-32"
            type="number"
            min={1}
            max={5}
            step={0.5}
            value={rate}
            onChange={(e) => setRate(Number(e.target.value))}
          />
        </div>
        <button className="btn-primary" onClick={setRateOnly}>
          Save Rate
        </button>
        <button className="btn-primary" onClick={triggerRun}>
          Run Monthly Payout
        </button>
        <div className="ml-auto flex flex-col items-end gap-1">
          <a className="text-sm underline text-brand" href={`/api/admin/payouts/export?month=${month}&format=bulk`}>
            Export Bulk Bank Upload CSV
          </a>
          <div className="flex gap-3 text-xs">
            <a className="underline text-gray-500" href={`/api/admin/payouts/export?month=${month}&format=full`}>
              Full detail CSV
            </a>
            <a className="underline text-gray-500" href={`/api/admin/payouts/export?month=${month}&format=missing`}>
              Missing bank details
            </a>
          </div>
        </div>
      </div>

      <p className="text-xs text-gray-500 mb-4">
        A referral only counts toward a month's payout if they became <b>ACTIVE on or before the 15th</b> of
        that month (IST). Someone activated on the 23rd, for example, carries over to next month's run instead.
      </p>

      {message && <p className="text-green-700 text-sm mb-4">{message}</p>}
      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500">
              <th className="pb-2">Referral Code</th>
              <th className="pb-2">Eligible Refs</th>
              <th className="pb-2">Rate</th>
              <th className="pb-2">Total (₹)</th>
              <th className="pb-2">Status</th>
              <th className="pb-2"></th>
            </tr>
          </thead>
          <tbody>
            {payouts.map((p) => (
              <tr key={p.id} className="border-t border-gray-100">
                <td className="py-2 font-mono">{p.referralCode}</td>
                <td className="py-2">{p.activeReferralCount}</td>
                <td className="py-2">₹{p.ratePerReferralInr}</td>
                <td className="py-2 font-semibold">₹{p.totalAmountInr}</td>
                <td className="py-2">{p.status}</td>
                <td className="py-2 text-right">
                  {p.status === 'PAID' ? (
                    <span className="text-xs text-gray-400">{p.transactionRef}</span>
                  ) : (
                    <div className="flex gap-1 justify-end">
                      <input
                        className="input text-xs w-32"
                        placeholder="Txn ref"
                        value={txRefDrafts[p.id] ?? ''}
                        onChange={(e) => setTxRefDrafts({ ...txRefDrafts, [p.id]: e.target.value })}
                      />
                      <button
                        className="text-xs px-2 py-1 rounded bg-brand text-white"
                        onClick={() => markPaid(p.id)}
                      >
                        Mark Paid
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {payouts.length === 0 && (
              <tr>
                <td colSpan={6} className="py-6 text-center text-gray-400">
                  No payout rows for this month yet. Set a rate and run the payout above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
