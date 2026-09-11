import { Global, Module } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { CacheService } from './cache.service';
import { RedisThrottlerStorage } from '../common/throttler/redis-throttler.storage';
import { createCacheRedis, createRateLimitRedis, REDIS_CACHE, REDIS_RATELIMIT } from './redis.provider';

/**
 * Global so any module can cache without re-importing plumbing. The queue's
 * Redis connection is deliberately NOT here — it belongs to the queue module,
 * which only worker processes load.
 */
@Global()
@Module({
  providers: [
    {
      provide: REDIS_CACHE,
      inject: [ConfigService],
      useFactory: (config: ConfigService) => createCacheRedis(config.get<string>('redis.url')!),
    },
    {
      provide: REDIS_RATELIMIT,
      inject: [ConfigService],
      useFactory: (config: ConfigService) => createRateLimitRedis(config.get<string>('redis.url')!),
    },
    CacheService,
    RedisThrottlerStorage,
  ],
  exports: [CacheService, RedisThrottlerStorage, REDIS_CACHE, REDIS_RATELIMIT],
})
export class CacheModule {}
