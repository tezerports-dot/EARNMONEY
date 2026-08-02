import { NextResponse } from 'next/server';
import { prisma } from '@platform/database';

export async function GET() {
  const logs = await prisma.auditLog.findMany({
    orderBy: { createdAt: 'desc' },
    take: 200,
    include: { admin: { select: { username: true } } },
  });

  return NextResponse.json({
    logs: logs.map((l) => ({
      id: l.id,
      admin: l.admin?.username ?? 'system',
      action: l.action,
      targetType: l.targetType,
      targetId: l.targetId,
      metadata: l.metadata,
      createdAt: l.createdAt,
    })),
  });
}
