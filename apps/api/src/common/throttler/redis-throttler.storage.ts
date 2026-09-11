import { Inject, Injectable, Logger } from '@nestjs/common';
import type { ThrottlerStorage } from '@nestjs/throttler';
import type { ThrottlerStorageRecord } from '@nestjs/throttler/dist/throttler-storage-record.interface';
import type Redis from 'ioredis';
import { REDIS_RATELIMIT } from '../../cache/redis.provider';

/**
 * Rate-limit counters in Redis instead of process memory.
 *
 * The default in-memory storage counts per process, which silently breaks the
 * moment there is more than one API container: two replicas means an attacker
 * gets double the allowance, and every deploy resets everyone's counters. Since
 * these limits are brute-force protection on login, that is a security
 * property, not just a tidiness one.
 *
 * The increment is a Lua script so INCR and the conditional EXPIRE happen in
 * one atomic round trip — as two separate commands there is a window where a
 * crash in between leaves a key with no TTL, blocking that user forever.
 */
@Injectable()
export class RedisThrottlerStorage implements ThrottlerStorage {
  private readonly logger = new Logger(RedisThrottlerStorage.name);

  /**
   * KEYS[1] = counter key. ARGV = [ttlSeconds, blockSeconds, limit].
   * Returns [totalHits, timeToExpire, isBlocked, timeToBlockExpire].
   */
  private static readonly SCRIPT = `
    local hits = redis.call('INCR', KEYS[1])
    if hits == 1 then
      redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
    local ttl = redis.call('TTL', KEYS[1])
    if ttl < 0 then
      redis.call('EXPIRE', KEYS[1], ARGV[1])
      ttl = tonumber(ARGV[1])
    end
    local blocked = 0
    local blockTtl = 0
    if hits > tonumber(ARGV[3]) then
      blocked = 1
      local blockKey = KEYS[1] .. ':blocked'
      if redis.call('EXISTS', blockKey) == 0 then
        redis.call('SET', blockKey, 1, 'EX', ARGV[2])
      end
      blockTtl = redis.call('TTL', blockKey)
    end
    return { hits, ttl, blocked, blockTtl }
  `;

  constructor(@Inject(REDIS_RATELIMIT) private readonly redis: Redis) {}

  async increment(
    key: string,
    ttl: number,
    limit: number,
    blockDuration: number,
    throttlerName: string,
  ): Promise<ThrottlerStorageRecord> {
    const redisKey = `throttle:${throttlerName}:${key}`;
    const ttlSeconds = Math.max(1, Math.ceil(ttl / 1000));
    const blockSeconds = Math.max(1, Math.ceil((blockDuration || ttl) / 1000));

    try {
      const [totalHits, timeToExpire, isBlocked, timeToBlockExpire] = (await this.redis.eval(
        RedisThrottlerStorage.SCRIPT,
        1,
        redisKey,
        String(ttlSeconds),
        String(blockSeconds),
        String(limit),
      )) as [number, number, number, number];

      return { totalHits, timeToExpire, isBlocked: isBlocked === 1, timeToBlockExpire };
    } catch (err) {
      // Fail OPEN, deliberately. If Redis is unreachable, blocking every login
      // would turn a cache outage into a total outage. The tradeoff is
      // explicit: availability over rate limiting, with the incident logged.
      // The other protections (argon2id cost, SUSPENDED checks, CAPTCHA) all
      // still apply, so this is not an unauthenticated bypass.
      this.logger.error(`rate-limit storage unavailable, allowing request: ${err}`);
      return { totalHits: 0, timeToExpire: ttlSeconds, isBlocked: false, timeToBlockExpire: 0 };
    }
  }
}
