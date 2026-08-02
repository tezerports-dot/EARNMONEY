'use client';

import { useEffect, useState, useCallback } from 'react';

interface Shard {
  id: string;
  shardKey: string;
  telegramChatId: string;
  inviteLink: string;
  memberCount: number;
  capacityLimit: number;
  status: string;
}

export default function AdminGroupsPage() {
  const [shards, setShards] = useState<Shard[]>([]);
  const [form, setForm] = useState({ shardKey: '', telegramChatId: '', inviteLink: '' });
  const [editingCapacity, setEditingCapacity] = useState<string | null>(null);
  const [capacityInput, setCapacityInput] = useState('');
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await fetch('/api/admin/groups');
    const data = await res.json();
    setShards(data.shards ?? []);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function addShard(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const res = await fetch('/api/admin/groups', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    });
    const data = await res.json();
    if (!res.ok) {
      setError(data.error);
      return;
    }
    setForm({ shardKey: '', telegramChatId: '', inviteLink: '' });
    load();
  }

  async function patchShard(shardId: string, body: Record<string, unknown>) {
    await fetch('/api/admin/groups', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ shardId, ...body }),
    });
    load();
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Group Shards</h1>

      <form onSubmit={addShard} className="card mb-6 flex flex-wrap gap-2 items-end">
        <div>
          <label className="text-xs text-gray-500 block mb-1">Shard key</label>
          <input
            className="input"
            placeholder="group-01"
            value={form.shardKey}
            onChange={(e) => setForm({ ...form, shardKey: e.target.value })}
            required
          />
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Telegram chat ID</label>
          <input
            className="input"
            placeholder="-1009876543210"
            value={form.telegramChatId}
            onChange={(e) => setForm({ ...form, telegramChatId: e.target.value })}
            required
          />
        </div>
        <div className="flex-1 min-w-[200px]">
          <label className="text-xs text-gray-500 block mb-1">Invite link</label>
          <input
            className="input"
            placeholder="https://t.me/+wxyz9876"
            value={form.inviteLink}
            onChange={(e) => setForm({ ...form, inviteLink: e.target.value })}
            required
          />
        </div>
        <button className="btn-primary">Add Group Shard</button>
      </form>
      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500">
              <th className="pb-2">Key</th>
              <th className="pb-2">Members</th>
              <th className="pb-2">Status</th>
              <th className="pb-2"></th>
            </tr>
          </thead>
          <tbody>
            {shards.map((s) => (
              <tr key={s.id} className="border-t border-gray-100">
                <td className="py-2">{s.shardKey}</td>
                <td className="py-2">
                  {editingCapacity === s.id ? (
                    <div className="flex gap-1 items-center">
                      <input
                        className="input text-xs w-24"
                        value={capacityInput}
                        onChange={(e) => setCapacityInput(e.target.value)}
                      />
                      <button
                        className="text-xs px-2 py-1 rounded bg-brand text-white"
                        onClick={async () => {
                          await patchShard(s.id, { action: 'SET_CAPACITY', capacityLimit: Number(capacityInput) });
                          setEditingCapacity(null);
                        }}
                      >
                        Save
                      </button>
                    </div>
                  ) : (
                    <span>
                      {s.memberCount.toLocaleString()} / {s.capacityLimit.toLocaleString()}
                    </span>
                  )}
                </td>
                <td className="py-2">{s.status}</td>
                <td className="py-2 text-right whitespace-nowrap space-x-2">
                  <button
                    className="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-50"
                    onClick={() => {
                      setEditingCapacity(s.id);
                      setCapacityInput(String(s.capacityLimit));
                    }}
                  >
                    Set Capacity
                  </button>
                  <button
                    className="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-50"
                    onClick={() => patchShard(s.id, { action: s.status === 'DISABLED' ? 'ENABLE' : 'DISABLE' })}
                  >
                    {s.status === 'DISABLED' ? 'Enable' : 'Disable'}
                  </button>
                </td>
              </tr>
            ))}
            {shards.length === 0 && (
              <tr>
                <td colSpan={4} className="py-6 text-center text-gray-400">
                  No group shards yet — add your first one above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
