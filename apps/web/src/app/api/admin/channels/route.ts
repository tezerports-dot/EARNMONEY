import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { prisma } from '@platform/database';
import { getAdminFromRequest } from '@/lib/auth';
import { CHANNEL_SHARD_CAPACITY, CHANNEL_SHARD_NEAR_CAPACITY_AT } from '@platform/shared';

export async function GET() {
  const shards = await prisma.channelShard.findMany({ orderBy: { createdAt: 'asc' } });
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

  const shard = await prisma.channelShard.create({
    data: {
      shardKey,
      telegramChatId: BigInt(telegramChatId),
      inviteLink,
      capacityLimit: capacityLimit ?? CHANNEL_SHARD_CAPACITY,
      nearCapacityAt: nearCapacityAt ?? CHANNEL_SHARD_NEAR_CAPACITY_AT,
    },
  });

  await prisma.auditLog.create({
    data: { adminId: admin?.sub, action: 'CHANNEL_SHARD_CREATED', targetType: 'ChannelShard', targetId: shard.id },
  });

  return NextResponse.json({ ok: true, shard: { ...shard, telegramChatId: shard.telegramChatId.toString() } });
}

const updateSchema = z.object({
  shardId: z.string().min(1),
  action: z.enum(['DISABLE', 'ENABLE', 'ROTATE_INVITE']),
  newInviteLink: z.string().url().optional(),
});

export async function PATCH(req: NextRequest) {
  const admin = getAdminFromRequest(req);
  const parsed = updateSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: 'Invalid input.' }, { status: 400 });
  }
  const { shardId, action, newInviteLink } = parsed.data;

  let data: Record<string, unknown> = {};
  if (action === 'DISABLE') data = { status: 'DISABLED' };
  if (action === 'ENABLE') data = { status: 'ACTIVE' };
  if (action === 'ROTATE_INVITE') {
    if (!newInviteLink) {
      return NextResponse.json({ error: 'newInviteLink is required to rotate.' }, { status: 400 });
    }
    data = { inviteLink: newInviteLink };
  }

  const shard = await prisma.channelShard.update({ where: { id: shardId }, data });

  await prisma.auditLog.create({
    data: { adminId: admin?.sub, action: `CHANNEL_SHARD_${action}`, targetType: 'ChannelShard', targetId: shard.id },
  });

  return NextResponse.json({ ok: true, shard: { ...shard, telegramChatId: shard.telegramChatId.toString() } });
}
