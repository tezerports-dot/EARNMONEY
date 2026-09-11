import { Inject, Injectable, Logger, OnModuleDestroy } from '@nestjs/common';
import type Redis from 'ioredis';
import { REDIS_CACHE } from './redis.provider';

/**
 * Read-through cache in front of Postgres.
 *
 * Two rules this service enforces by construction:
 *
 *  1. **Redis is never the source of truth.** Every read falls back to the
 *     loader (Postgres) on a miss, and every failure of Redis degrades to a
 *     direct Postgres read rather than an error. Losing Redis costs latency,
 *     never data.
 *  2. **A cache failure never fails a request.** Every Redis call here is
 *     wrapped; if Redis is down the caller still gets its answer.
 */
@Injectable()
export class CacheService implements OnModuleDestroy {
  private readonly logger = new Logger(CacheService.name);
  private hits = 0;
  private misses = 0;
  private errors = 0;

  constructor(@Inject(REDIS_CACHE) private readonly redis: Redis) {}

  async onModuleDestroy() {
    await this.redis.quit().catch(() => undefined);
  }

  /**
   * Read-through with a loader. The loader runs on a miss and its result is
   * written back with `ttlSeconds`.
   *
   * Note there is deliberately no distributed lock around the loader. For the
   * content this caches — one small row read by many workers — a brief
   * stampede of a few duplicate reads after expiry is far cheaper than the
   * coordination, and Postgres serves it from shared buffers anyway.
   */
  async getOrSet<T>(key: string, ttlSeconds: number, loader: () => Promise<T>): Promise<T> {
    const cached = await this.get<T>(key);
    if (cached !== null) return cached;

    const fresh = await loader();
    if (fresh !== null && fresh !== undefined) {
      await this.set(key, fresh, ttlSeconds);
    }
    return fresh;
  }

  async get<T>(key: string): Promise<T | null> {
    try {
      const raw = await this.redis.get(key);
      if (raw === null) {
        this.misses++;
        return null;
      }
      this.hits++;
      return JSON.parse(raw) as T;
    } catch (err) {
      // Degrade to a miss: the caller will hit Postgres and still succeed.
      this.errors++;
      this.logger.warn(`cache get failed for ${key}, falling through to source: ${err}`);
      return null;
    }
  }

  async set(key: string, value: unknown, ttlSeconds: number): Promise<void> {
    try {
      await this.redis.set(key, JSON.stringify(value), 'EX', ttlSeconds);
    } catch (err) {
      this.errors++;
      this.logger.warn(`cache set failed for ${key}: ${err}`);
    }
  }

  async del(...keys: string[]): Promise<void> {
    if (keys.length === 0) return;
    try {
      await this.redis.del(...keys);
    } catch (err) {
      this.errors++;
      this.logger.warn(`cache del failed: ${err}`);
    }
  }

  /** Exposed on the health endpoint so hit ratio is observable in production. */
  stats() {
    const total = this.hits + this.misses;
    return {
      hits: this.hits,
      misses: this.misses,
      errors: this.errors,
      hitRatio: total === 0 ? null : Number((this.hits / total).toFixed(4)),
    };
  }
}

/** Namespaced key builders, so key formats live in one place. */
export const cacheKeys = {
  currentContent: () => 'content:current',
  contentByVersion: (version: number) => `content:v:${version}`,
} as const;
