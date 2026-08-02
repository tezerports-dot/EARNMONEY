'use client';

import { useEffect, useState } from 'react';

interface LogRow {
  id: string;
  admin: string;
  action: string;
  targetType: string;
  targetId: string | null;
  metadata: unknown;
  createdAt: string;
}

export default function AdminAuditLogsPage() {
  const [logs, setLogs] = useState<LogRow[]>([]);

  useEffect(() => {
    fetch('/api/admin/audit-logs')
      .then((r) => r.json())
      .then((d) => setLogs(d.logs ?? []));
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Audit Logs</h1>
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500">
              <th className="pb-2">When</th>
              <th className="pb-2">Admin</th>
              <th className="pb-2">Action</th>
              <th className="pb-2">Target</th>
              <th className="pb-2">Details</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((l) => (
              <tr key={l.id} className="border-t border-gray-100">
                <td className="py-2 whitespace-nowrap">{new Date(l.createdAt).toLocaleString()}</td>
                <td className="py-2">{l.admin}</td>
                <td className="py-2">{l.action}</td>
                <td className="py-2">
                  {l.targetType}
                  {l.targetId ? ` #${l.targetId.slice(0, 8)}` : ''}
                </td>
                <td className="py-2 text-xs text-gray-500 max-w-xs truncate">
                  {l.metadata ? JSON.stringify(l.metadata) : ''}
                </td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr>
                <td colSpan={5} className="py-6 text-center text-gray-400">
                  No activity yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
