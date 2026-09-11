import { Logger } from '@nestjs/common';
import Redis, { RedisOptions } from 'ioredis';

/**
 * Redis connection factory.
 *
 * Three separate connections exist on purpose, because they have
 * incompatible requirements:
 *
 *  - CACHE      — normal request/response. Retries are good here.
 *  - QUEUE      — BullMQ blocks on BRPOPLPUSH, which needs
 *                 `maxRetriesPerRequest: null` or ioredis aborts the blocking
 *                 read mid-wait and BullMQ throws.
 *  - RATE LIMIT — small, hot, and must never be starved behind queue traffic.
 *
 * Sharing one connection across all three is the usual way this design goes
 * wrong: a blocked queue read stalls rate-limit lookups, which stalls login.
 */
export const REDIS_CACHE = Symbol('REDIS_CACHE');
export const REDIS_QUEUE = Symbol('REDIS_QUEUE');
export const REDIS_RATELIMIT = Symbol('REDIS_RATELIMIT');

const logger = new Logger('Redis');

function baseOptions(name: string): RedisOptions {
  return {
    connectionName: `bbazaar:${name}`,
    // Fail fast rather than hanging a request behind a dead Redis.
    connectTimeout: 5_000,
    enableOfflineQueue: true,
    retryStrategy: (attempt) => Math.min(attempt * 200, 3_000),
    reconnectOnError: (err) => {
      // READONLY means we followed a failover to a replica; reconnecting
      // picks up the new primary.
      if (err.message.includes('READONLY')) return 2;
      return false;
    },
  };
}

export function createCacheRedis(url: string): Redis {
  const client = new Redis(url, baseOptions('cache'));
  client.on('error', (e) => logger.error(`cache redis: ${e.message}`));
  return client;
}

export function createRateLimitRedis(url: string): Redis {
  const client = new Redis(url, baseOptions('ratelimit'));
  client.on('error', (e) => logger.error(`ratelimit redis: ${e.message}`));
  return client;
}

export function createQueueRedis(url: string): Redis {
  const client = new Redis(url, {
    ...baseOptions('queue'),
    // Required by BullMQ's blocking commands. Without this, long polls abort.
    maxRetriesPerRequest: null,
  });
  client.on('error', (e) => logger.error(`queue redis: ${e.message}`));
  return client;
}
