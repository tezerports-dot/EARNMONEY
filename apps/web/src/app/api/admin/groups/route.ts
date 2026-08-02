import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { prisma } from '@platform/database';
import { getAdminFromRequest } from '@/lib/auth';
import { GROUP_SHARD_CAPACITY, GROUP_SHARD_NEAR_CAPACITY_AT } from '@platform/shared';

export async function GET() {
  const shards = await prisma.groupShard.findMany({ orderBy: { createdAt: 'asc' } });
  return NextResponse.json({
    shards: shards.map((s) => ({ ...s, telegramChatId: s.telegramChatId.toString() })),
  });
}

const createSchema = z.object({
  shardKey: z.string().min(1),
  telegramChatId: z.string().min(1),
  inviteLink: z.string().url(),
  capacityLimit: z.number().int().positive().optional(),
  nearCapacityAt: z.number().int().positive().optional(),
});

export async function POST(req: NextRequest) {
  const admin = getAdminFromRequest(req);
  const parsed = createSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.issues[0]?.message ?? 'Invalid input.' }, { status: 400 });
  }
  const { shardKey, telegramChatId, inviteLink, capacityLimit, nearCapacityAt } = parsed.data;

  const shard = await prisma.groupShard.create({
    data: {
      shardKey,
      telegramChatId: BigInt(telegramChatId),
      inviteLink,
      capacityLimit: capacityLimit ?? GROUP_SHARD_CAPACITY,
      nearCapacityAt: nearCapacityAt ?? GROUP_SHARD_NEAR_CAPACITY_AT,
    },
  });

  await prisma.auditLog.create({
    data: { adminId: admin?.sub, action: 'GROUP_SHARD_CREATED', targetType: 'GroupShard', targetId: shard.id },
  });

  return NextResponse.json({ ok: true, shard: { ...shard, telegramChatId: shard.telegramChatId.toString() } });
}

const updateSchema = z.object({
  shardId: z.string().min(1),
  action: z.enum(['DISABLE', 'ENABLE', 'SET_CAPACITY']),
  capacityLimit: z.number().int().positive().optional(),
  nearCapacityAt: z.number().int().positive().optional(),
});

export async function PATCH(req: NextRequest) {
  const admin = getAdminFromRequest(req);
  const parsed = updateSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: 'Invalid input.' }, { status: 400 });
  }
  const { shardId, action, capacityLimit, nearCapacityAt } = parsed.data;

  let data: Record<string, unknown> = {};
  if (action === 'DISABLE') data = { status: 'DISABLED' };
  if (action === 'ENABLE') data = { status: 'ACTIVE' };
  if (action === 'SET_CAPACITY') {
    if (!capacityLimit) {
      return NextResponse.json({ error: 'capacityLimit is required.' }, { status: 400 });
    }
    data = { capacityLimit, nearCapacityAt: nearCapacityAt ?? Math.round(capacityLimit * 0.9) };
  }

  const shard = await prisma.groupShard.update({ where: { id: shardId }, data });

  await prisma.auditLog.create({
    data: { adminId: admin?.sub, action: `GROUP_SHARD_${action}`, targetType: 'GroupShard', targetId: shard.id },
  });

  return NextResponse.json({ ok: true, shard: { ...shard, telegramChatId: shard.telegramChatId.toString() } });
}
