import { Global, Module, OnApplicationShutdown } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Queue } from 'bullmq';
import type Redis from 'ioredis';
import { createQueueRedis, REDIS_QUEUE } from '../cache/redis.provider';
import { QUEUES } from './queue.constants';
import { QueueProducer } from './queue.producer';

/**
 * Provides the queue PRODUCER side — used by API processes to enqueue work.
 * Consumers (workers) live in worker.ts and are never loaded by an API
 * process, which is what keeps update processing off API CPU entirely.
 */
@Global()
@Module({
  providers: [
    {
      provide: REDIS_QUEUE,
      inject: [ConfigService],
      useFactory: (config: ConfigService) => createQueueRedis(config.get<string>('redis.url')!),
    },
    {
      provide: QUEUES.CONTENT_UPDATES,
      inject: [REDIS_QUEUE],
      useFactory: (connection: Redis) =>
        new Queue(QUEUES.CONTENT_UPDATES, {
          connection,
          defaultJobOptions: {
            // Keep the queue small: completed jobs are trimmed aggressively
            // because `UserUpdateState` already records what was delivered.
            removeOnComplete: { count: 1_000 },
            // Keep failures long enough to diagnose them.
            removeOnFail: { count: 10_000 },
          },
        }),
    },
    {
      provide: QUEUES.BACKGROUND,
      inject: [REDIS_QUEUE],
      useFactory: (connection: Redis) =>
        new Queue(QUEUES.BACKGROUND, {
          connection,
          defaultJobOptions: { removeOnComplete: { count: 500 }, removeOnFail: { count: 2_000 } },
        }),
    },
    {
      provide: QUEUES.DEAD_LETTER,
      inject: [REDIS_QUEUE],
      useFactory: (connection: Redis) =>
        // Never auto-trimmed: a silently discarded dead letter is a lost user.
        new Queue(QUEUES.DEAD_LETTER, { connection }),
    },
    QueueProducer,
  ],
  exports: [QueueProducer, QUEUES.CONTENT_UPDATES, QUEUES.BACKGROUND, QUEUES.DEAD_LETTER],
})
export class QueueModule implements OnApplicationShutdown {
  async onApplicationShutdown() {
    // Connections are closed by the Redis provider's own lifecycle.
  }
}
