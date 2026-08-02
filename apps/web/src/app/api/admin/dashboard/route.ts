import { NextResponse } from 'next/server';
import { prisma } from '@platform/database';

export async function GET() {
  const [totalUsers, activeUsers, pendingUsers, joiningUsers, suspendedUsers, flaggedUsers] = await Promise.all([
    prisma.user.count(),
    prisma.user.count({ where: { status: 'ACTIVE' } }),
    prisma.user.count({ where: { status: 'PENDING' } }),
    prisma.user.count({ where: { status: 'JOINING' } }),
    prisma.user.count({ where: { status: 'SUSPENDED' } }),
    prisma.user.count({ where: { fraudScore: { gte: 40, lt: 70 } } }),
  ]);

  const dayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);
  const dau = await prisma.user.count({
    where: {
      OR: [{ channelLastSeenAt: { gte: dayAgo } }, { groupLastSeenAt: { gte: dayAgo } }],
    },
  });

  const activationRate = totalUsers > 0 ? Math.round((activeUsers / totalUsers) * 1000) / 10 : 0;

  const [channelShards, groupShards] = await Promise.all([
    prisma.channelShard.findMany({ select: { memberCount: true, capacityLimit: true, status: true } }),
    prisma.groupShard.findMany({ select: { memberCount: true, capacityLimit: true, status: true } }),
  ]);

  const channelUtilization = channelShards.map((s) => ({
    ...s,
    utilizationPct: s.capacityLimit > 0 ? Math.round((s.memberCount / s.capacityLimit) * 1000) / 10 : 0,
  }));
  const groupUtilization = groupShards.map((s) => ({
    ...s,
    utilizationPct: s.capacityLimit > 0 ? Math.round((s.memberCount / s.capacityLimit) * 1000) / 10 : 0,
  }));

  const pendingPayouts = await prisma.monthlyPayout.count({ where: { status: 'PENDING' } });
  const pendingPayoutTotal = await prisma.monthlyPayout.aggregate({
    where: { status: 'PENDING' },
    _sum: { totalAmountInr: true },
  });

  return NextResponse.json({
    totalUsers,
    activeUsers,
    pendingUsers,
    joiningUsers,
    suspendedUsers,
    flaggedUsers,
    dau,
    activationRate,
    channelUtilization,
    groupUtilization,
    pendingPayouts,
    pendingPayoutTotalInr: Number(pendingPayoutTotal._sum.totalAmountInr ?? 0),
  });
}
