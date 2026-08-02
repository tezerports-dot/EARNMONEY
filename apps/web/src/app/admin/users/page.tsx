'use client';

import { useEffect, useState, useCallback } from 'react';

interface AdminUserRow {
  id: string;
  telegramId: string;
  telegramUsername: string | null;
  referralCode: string;
  status: string;
  fraudScore: number;
  createdAt: string;
  activatedAt: string | null;
}

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (status) params.set('status', status);
    const res = await fetch(`/api/admin/users?${params.toString()}`);
    const data = await res.json();
    setUsers(data.users ?? []);
    setLoading(false);
  }, [q, status]);

  useEffect(() => {
    load();
  }, [load]);

  async function toggleSuspend(userId: string, currentlySuspended: boolean) {
    await fetch('/api/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ userId, action: currentlySuspended ? 'UNSUSPEND' : 'SUSPEND' }),
    });
    load();
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Users</h1>

      <div className="flex gap-2 mb-4">
        <input
          className="input"
          placeholder="Search by referral code, username, or phone"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select className="input w-48" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          <option value="PENDING">Pending</option>
          <option value="JOINING">Joining</option>
          <option value="ACTIVE">Active</option>
          <option value="INACTIVE">Inactive</option>
          <option value="SUSPENDED">Suspended</option>
        </select>
        <button className="btn-primary" onClick={load}>
          Search
        </button>
      </div>

      <div className="card overflow-x-auto">
        {loading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500">
                <th className="pb-2">Referral Code</th>
                <th className="pb-2">Username</th>
                <th className="pb-2">Status</th>
                <th className="pb-2">Fraud Score</th>
                <th className="pb-2">Joined</th>
                <th className="pb-2"></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-gray-100">
                  <td className="py-2 font-mono">{u.referralCode}</td>
                  <td className="py-2">{u.telegramUsername ?? '—'}</td>
                  <td className="py-2">{u.status}</td>
                  <td className="py-2">
                    <span
                      className={
                        u.fraudScore >= 70
                          ? 'text-red-600 font-semibold'
                          : u.fraudScore >= 40
                            ? 'text-amber-600 font-semibold'
                            : ''
                      }
                    >
                      {u.fraudScore}
                    </span>
                  </td>
                  <td className="py-2">{new Date(u.createdAt).toLocaleDateString()}</td>
                  <td className="py-2 text-right">
                    <button
                      className="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-50"
                      onClick={() => toggleSuspend(u.id, u.status === 'SUSPENDED')}
                    >
                      {u.status === 'SUSPENDED' ? 'Unsuspend' : 'Suspend'}
                    </button>
                  </td>
                </tr>
              ))}
              {users.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-gray-400">
                    No users found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
