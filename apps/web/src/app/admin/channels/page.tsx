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

export default function AdminChannelsPage() {
  const [shards, setShards] = useState<Shard[]>([]);
  const [form, setForm] = useState({ shardKey: '', telegramChatId: '', inviteLink: '' });
  const [rotating, setRotating] = useState<string | null>(null);
  const [newLink, setNewLink] = useState('');
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await fetch('/api/admin/channels');
    const data = await res.json();
    setShards(data.shards ?? []);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function addShard(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const res = await fetch('/api/admin/channels', {
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
    await fetch('/api/admin/channels', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ shardId, ...body }),
    });
    load();
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Channel Shards</h1>

      <form onSubmit={addShard} className="card mb-6 flex flex-wrap gap-2 items-end">
        <div>
          <label className="text-xs text-gray-500 block mb-1">Shard key</label>
          <input
            className="input"
            placeholder="channel-01"
            value={form.shardKey}
            onChange={(e) => setForm({ ...form, shardKey: e.target.value })}
            required
          />
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Telegram chat ID</label>
          <input
            className="input"
            placeholder="-1001234567890"
            value={form.telegramChatId}
            onChange={(e) => setForm({ ...form, telegramChatId: e.target.value })}
            required
          />
        </div>
        <div className="flex-1 min-w-[200px]">
          <label className="text-xs text-gray-500 block mb-1">Invite link</label>
          <input
            className="input"
            placeholder="https://t.me/+abcd1234"
            value={form.inviteLink}
            onChange={(e) => setForm({ ...form, inviteLink: e.target.value })}
            required
          />
        </div>
        <button className="btn-primary">Add Channel Shard</button>
      </form>
      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500">
              <th className="pb-2">Key</th>
              <th className="pb-2">Members</th>
              <th className="pb-2">Status</th>
              <th className="pb-2">Invite Link</th>
              <th className="pb-2"></th>
            </tr>
          </thead>
          <tbody>
            {shards.map((s) => (
              <tr key={s.id} className="border-t border-gray-100 align-top">
                <td className="py-2">{s.shardKey}</td>
                <td className="py-2">
                  {s.memberCount.toLocaleString()} / {s.capacityLimit.toLocaleString()}
                </td>
                <td className="py-2">{s.status}</td>
                <td className="py-2 max-w-[220px] truncate">
                  {rotating === s.id ? (
                    <div className="flex gap-1">
                      <input
                        className="input text-xs"
                        placeholder="New invite link"
                        value={newLink}
                        onChange={(e) => setNewLink(e.target.value)}
                      />
                      <button
                        className="text-xs px-2 py-1 rounded bg-brand text-white"
                        onClick={async () => {
                          await patchShard(s.id, { action: 'ROTATE_INVITE', newInviteLink: newLink });
                          setRotating(null);
                          setNewLink('');
                        }}
                      >
                        Save
                      </button>
                    </div>
                  ) : (
                    s.inviteLink
                  )}
                </td>
                <td className="py-2 text-right whitespace-nowrap space-x-2">
                  <button
                    className="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-50"
                    onClick={() => setRotating(s.id)}
                  >
                    Rotate Link
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
                <td colSpan={5} className="py-6 text-center text-gray-400">
                  No channel shards yet — add your first one above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
