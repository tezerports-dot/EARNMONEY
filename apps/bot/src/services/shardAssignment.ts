import { prisma } from '@platform/database';
import {
  CHANNEL_SHARD_NEAR_CAPACITY_AT,
  GROUP_SHARD_NEAR_CAPACITY_AT,
} from '@platform/shared';
import type { ShardAssignmentResult } from '@platform/shared';

export class NoAvailableChannelError extends Error {
  constructor() {
    super('NO_AVAILABLE_CHANNEL');
  }
}
export class NoAvailableGroupError extends Error {
  constructor() {
    super('NO_AVAILABLE_GROUP');
  }
}

/**
 * Assigns exactly one channel shard and one group shard to a user.
 * Each is chosen independently using "first-fill" order: the oldest
 * still-ACTIVE shard of that type (i.e. the one you created first that
 * isn't full yet) is used until it crosses its near-capacity threshold,
 * at which point it's automatically marked NEAR_CAPACITY and the next
 * oldest shard takes over. Add new shards from the admin panel whenever
 * you need more room — they'll only start receiving users once every
 * earlier shard is full.
 */
export async function assignShards(userId: string): Promise<ShardAssignmentResult> {
  const channel = await prisma.channelShard.findFirst({
    where: { status: 'ACTIVE', memberCount: { lt: CHANNEL_SHARD_NEAR_CAPACITY_AT } },
    orderBy: { createdAt: 'asc' },
  });
  if (!channel) throw new NoAvailableChannelError();

  const group = await prisma.groupShard.findFirst({
    where: { status: 'ACTIVE', memberCount: { lt: GROUP_SHARD_NEAR_CAPACITY_AT } },
    orderBy: { createdAt: 'asc' },
  });
  if (!group) throw new NoAvailableGroupError();

  await prisma.$transaction([
    prisma.user.update({
      where: { id: userId },
      data: { assignedChannelId: channel.id, assignedGroupId: group.id, status: 'JOINING' },
    }),
    prisma.channelShard.update({ where: { id: channel.id }, data: { memberCount: { increment: 1 } } }),
    prisma.groupShard.update({ where: { id: group.id }, data: { memberCount: { increment: 1 } } }),
  ]);

  await flagNearCapacityIfNeeded();

  return {
    channelId: channel.id,
    channelInviteLink: channel.inviteLink,
    groupId: group.id,
    groupInviteLink: group.inviteLink,
  };
}

/** Marks shards NEAR_CAPACITY once they cross their threshold, so future lookups skip them cheaply. */
export async function flagNearCapacityIfNeeded(): Promise<void> {
  await prisma.channelShard.updateMany({
    where: { status: 'ACTIVE', memberCount: { gte: CHANNEL_SHARD_NEAR_CAPACITY_AT } },
    data: { status: 'NEAR_CAPACITY' },
  });
  await prisma.groupShard.updateMany({
    where: { status: 'ACTIVE', memberCount: { gte: GROUP_SHARD_NEAR_CAPACITY_AT } },
    data: { status: 'NEAR_CAPACITY' },
  });
}
