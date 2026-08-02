import { prisma } from '@platform/database';

async function getStats() {
  const dayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);
  const [totalUsers, activeUsers, pendingUsers, joiningUsers, suspendedUsers, flaggedUsers, dau] = await Promise.all([
    prisma.user.count(),
    prisma.user.count({ where: { status: 'ACTIVE' } }),
    prisma.user.count({ where: { status: 'PENDING' } }),
    prisma.user.count({ where: { status: 'JOINING' } }),
    prisma.user.count({ where: { status: 'SUSPENDED' } }),
    prisma.user.count({ where: { fraudScore: { gte: 40, lt: 70 } } }),
    prisma.user.count({ where: { OR: [{ channelLastSeenAt: { gte: dayAgo } }, { groupLastSeenAt: { gte: dayAgo } }] } }),
  ]);
  const activationRate = totalUsers > 0 ? Math.round((activeUsers / totalUsers) * 1000) / 10 : 0;

  const [channelShards, groupShards] = await Promise.all([
    prisma.channelShard.findMany(),
    prisma.groupShard.findMany(),
  ]);

  const pendingPayouts = await prisma.monthlyPayout.count({ where: { status: 'PENDING' } });
  const pendingPayoutTotal = await prisma.monthlyPayout.aggregate({
    where: { status: 'PENDING' },
    _sum: { totalAmountInr: true },
  });

  return {
    totalUsers,
    activeUsers,
    pendingUsers,
    joiningUsers,
    suspendedUsers,
    flaggedUsers,
    dau,
    activationRate,
    channelShards,
    groupShards,
    pendingPayouts,
    pendingPayoutTotalInr: Number(pendingPayoutTotal._sum.totalAmountInr ?? 0),
  };
}

export default async function AdminDashboardPage() {
  const stats = await getStats();

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
        <Stat label="Total Users" value={stats.totalUsers} />
        <Stat label="Active" value={stats.activeUsers} />
        <Stat label="DAU" value={stats.dau} />
        <Stat label="Activation Rate" value={`${stats.activationRate}%`} />
        <Stat label="Pending" value={stats.pendingUsers} />
        <Stat label="Joining" value={stats.joiningUsers} />
        <Stat label="Suspended" value={stats.suspendedUsers} />
        <Stat label="Flagged (40-69)" value={stats.flaggedUsers} />
      </div>

      <div className="card mb-6">
        <h2 className="font-semibold mb-3">Pending Payouts</h2>
        <p className="text-sm text-gray-600">
          {stats.pendingPayouts} rows pending, totaling ₹{stats.pendingPayoutTotalInr}.
        </p>
      </div>

      <div className="grid sm:grid-cols-2 gap-6">
        <div className="card">
          <h2 className="font-semibold mb-3">Channel Shards</h2>
          <ShardTable shards={stats.channelShards} capacityField="capacityLimit" />
        </div>
        <div className="card">
          <h2 className="font-semibold mb-3">Group Shards</h2>
          <ShardTable shards={stats.groupShards} capacityField="capacityLimit" />
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card text-center">
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-xs text-gray-500 mt-1">{label}</div>
    </div>
  );
}

function ShardTable({
  shards,
  capacityField,
}: {
  shards: { shardKey: string; memberCount: number; status: string; capacityLimit: number }[];
  capacityField: 'capacityLimit';
}) {
  if (shards.length === 0) return <p className="text-sm text-gray-400">No shards yet.</p>;
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-gray-500">
          <th className="pb-2">Key</th>
          <th className="pb-2">Members</th>
          <th className="pb-2">Status</th>
        </tr>
      </thead>
      <tbody>
        {shards.map((s) => (
          <tr key={s.shardKey} className="border-t border-gray-100">
            <td className="py-2">{s.shardKey}</td>
            <td className="py-2">
              {s.memberCount.toLocaleString()} / {s[capacityField].toLocaleString()}
            </td>
            <td className="py-2">{s.status}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
