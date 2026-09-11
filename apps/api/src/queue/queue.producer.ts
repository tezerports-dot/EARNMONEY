import { Inject, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Queue } from 'bullmq';
import {
  DeliverUpdateJob,
  deliverUpdateJobId,
  JOBS,
  PostLoginJob,
  PostSignupJob,
  QUEUES,
} from './queue.constants';

/**
 * The only way work gets onto a queue.
 *
 * Every method here is failure-tolerant on purpose: enqueueing background work
 * must never be able to fail a signup or a login. If Redis is unavailable the
 * user still gets their account; the audit row is simply written inline.
 */
@Injectable()
export class QueueProducer {
  private readonly logger = new Logger(QueueProducer.name);

  constructor(
    @Inject(QUEUES.CONTENT_UPDATES) private readonly updates: Queue,
    @Inject(QUEUES.BACKGROUND) private readonly background: Queue,
    @Inject(QUEUES.DEAD_LETTER) private readonly deadLetter: Queue,
    private readonly config: ConfigService,
  ) {}

  /**
   * Enqueues one slot's worth of daily updates in a single pipelined call.
   * `addBulk` matters at this size: 2,000 individual `add` calls is 2,000
   * round trips, which would make the dispatch itself the bottleneck.
   */
  async enqueueUpdates(jobs: DeliverUpdateJob[]): Promise<number> {
    if (jobs.length === 0) return 0;

    const attempts = this.config.get<number>('queue.maxAttempts')!;
    const backoffBase = this.config.get<number>('queue.backoffBaseMs')!;

    const added = await this.updates.addBulk(
      jobs.map((data) => ({
        name: JOBS.DELIVER_UPDATE,
        data,
        opts: {
          // Deterministic id — a replayed slot re-enqueues nothing.
          jobId: deliverUpdateJobId(data.userId, data.version),
          attempts,
          backoff: { type: 'exponential' as const, delay: backoffBase },
        },
      })),
    );
    return added.length;
  }

  /**
   * Non-critical work shed from the signup path. Returns false when the work
   * could not be queued, so the caller can fall back to doing it inline.
   */
  async enqueuePostSignup(data: PostSignupJob): Promise<boolean> {
    return this.tryEnqueueBackground(JOBS.POST_SIGNUP, data);
  }

  async enqueuePostLogin(data: PostLoginJob): Promise<boolean> {
    return this.tryEnqueueBackground(JOBS.POST_LOGIN, data);
  }

  private async tryEnqueueBackground(name: string, data: unknown): Promise<boolean> {
    try {
      await this.background.add(name, data, {
        attempts: 3,
        backoff: { type: 'exponential', delay: 2_000 },
      });
      return true;
    } catch (err) {
      // Deliberately swallowed. A failed audit enqueue must not cost a user
      // their signup; the caller writes it inline instead.
      this.logger.warn(`could not enqueue ${name}, caller will handle inline: ${err}`);
      return false;
    }
  }

  /** Parks a terminally failed job for human inspection. */
  async sendToDeadLetter(queue: string, jobName: string, data: unknown, reason: string) {
    try {
      await this.deadLetter.add(`${queue}:${jobName}`, {
        originalQueue: queue,
        originalJob: jobName,
        data,
        reason,
        failedAt: new Date().toISOString(),
      });
    } catch (err) {
      // Last resort: at least the log records it.
      this.logger.error(`FAILED TO DEAD-LETTER ${queue}:${jobName} (${reason}): ${err}`);
    }
  }

  /** Queue depths, for the health endpoint and alerting. */
  async depths() {
    const [updates, background, deadLetter] = await Promise.all([
      this.updates.getJobCounts('waiting', 'active', 'delayed', 'failed'),
      this.background.getJobCounts('waiting', 'active', 'failed'),
      this.deadLetter.getJobCounts('waiting'),
    ]);
    return { updates, background, deadLetter };
  }
}
