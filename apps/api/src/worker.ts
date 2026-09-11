import 'reflect-metadata';
import { NestFactory } from '@nestjs/core';
import { Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Job, Worker } from 'bullmq';
import { WorkerModule } from './worker.module';
import { ContentDeliveryService } from './content/content-delivery.service';
import { AuditLogService } from './audit/audit-log.service';
import { createQueueRedis } from './cache/redis.provider';
import {
  DeliverUpdateJob,
  JOBS,
  PostLoginJob,
  PostSignupJob,
  QUEUES,
} from './queue/queue.constants';
import { QueueProducer } from './queue/queue.producer';

/**
 * Worker entrypoint — a SEPARATE process from the API.
 *
 * This separation is the core of the whole design. Because update processing
 * runs in its own process with its own Postgres pool and its own Redis
 * connection, a 2,000-job fan-out cannot:
 *   - consume the event loop that serves login,
 *   - exhaust the connection pool signup needs,
 *   - or be slowed down by user traffic.
 *
 * Scale the two independently: more API containers for user load, more worker
 * containers for update throughput. Neither forces the other.
 *
 * Run with:  node dist/worker.js
 */
async function bootstrap() {
  const logger = new Logger('Worker');

  // `createApplicationContext`, not `create`: a worker must never open an HTTP
  // port. It has no routes and nothing should be able to reach it.
  const app = await NestFactory.createApplicationContext(WorkerModule, {
    logger: ['error', 'warn', 'log'],
  });

  const config = app.get(ConfigService);
  const delivery = app.get(ContentDeliveryService);
  const audit = app.get(AuditLogService);
  const producer = app.get(QueueProducer);

  const connection = createQueueRedis(config.get<string>('redis.url')!);
  const concurrency = config.get<number>('queue.updateConcurrency')!;
  const rateMax = config.get<number>('queue.rateLimitMax')!;
  const rateDuration = config.get<number>('queue.rateLimitDurationMs')!;
  const maxAttempts = config.get<number>('queue.maxAttempts')!;

  logger.log(
    `starting: concurrency=${concurrency}, rate=${rateMax}/${rateDuration}ms, attempts=${maxAttempts}`,
  );

  const updateWorker = new Worker<DeliverUpdateJob>(
    QUEUES.CONTENT_UPDATES,
    async (job: Job<DeliverUpdateJob>) => {
      const { userId, version } = job.data;
      const outcome = await delivery.deliver(userId, version);

      if (outcome === 'no-content') {
        // Nothing published yet. Not an error, and retrying will not help.
        return { outcome };
      }
      return { outcome };
    },
    {
      connection,
      concurrency,
      // Shared across every worker process on this Redis, so total throughput
      // is bounded regardless of how many containers are running. Raise this
      // once the database shows headroom — the architecture does not change.
      limiter: { max: rateMax, duration: rateDuration },
    },
  );

  /**
   * Terminal failures are parked, never dropped. `attemptsMade` reaching
   * `maxAttempts` means exponential backoff has already been exhausted.
   */
  updateWorker.on('failed', async (job, err) => {
    if (!job) return;
    await delivery.recordFailure(job.data.userId, err.message).catch(() => undefined);

    if (job.attemptsMade >= maxAttempts) {
      logger.error(
        `job ${job.id} exhausted ${maxAttempts} attempts, dead-lettering: ${err.message}`,
      );
      await producer.sendToDeadLetter(QUEUES.CONTENT_UPDATES, job.name, job.data, err.message);
    }
  });

  updateWorker.on('error', (err) => logger.error(`update worker error: ${err.message}`));

  // Background work shed from signup/login. Separate worker so a large update
  // batch never delays it.
  const backgroundWorker = new Worker(
    QUEUES.BACKGROUND,
    async (job: Job<PostSignupJob | PostLoginJob>) => {
      switch (job.name) {
        case JOBS.POST_SIGNUP:
          await audit.record({
            actorUserId: job.data.userId,
            action: 'USER_SIGNUP_BACKGROUND',
            entityType: 'User',
            entityId: job.data.userId,
            ip: job.data.ip,
          });
          return;
        case JOBS.POST_LOGIN:
          await audit.record({
            actorUserId: job.data.userId,
            action: 'USER_LOGIN_BACKGROUND',
            entityType: 'User',
            entityId: job.data.userId,
            ip: job.data.ip,
          });
          return;
        default:
          logger.warn(`unknown background job ${job.name}`);
      }
    },
    { connection, concurrency: config.get<number>('queue.backgroundConcurrency')! },
  );

  backgroundWorker.on('error', (err) => logger.error(`background worker error: ${err.message}`));

  /**
   * Graceful shutdown. `worker.close()` waits for in-flight jobs to finish
   * rather than killing them mid-write — without it a redeploy would leave
   * jobs stalled until BullMQ's stall timeout reclaimed them.
   */
  const shutdown = async (signal: string) => {
    logger.log(`${signal} received, finishing in-flight jobs…`);
    await Promise.allSettled([updateWorker.close(), backgroundWorker.close()]);
    await connection.quit().catch(() => undefined);
    await app.close();
    process.exit(0);
  };

  process.on('SIGTERM', () => void shutdown('SIGTERM'));
  process.on('SIGINT', () => void shutdown('SIGINT'));

  logger.log('worker ready');
}

void bootstrap();
