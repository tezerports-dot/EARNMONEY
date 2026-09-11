import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Cron, CronExpression } from '@nestjs/schedule';
import { PrismaService } from '../prisma/prisma.service';
import { ContentService } from '../content/content.service';
import { QueueProducer } from '../queue/queue.producer';
import { DeliverUpdateJob } from '../queue/queue.constants';
import { recentSlots, slotDateFor, slotForDate } from './slot.util';

/**
 * Dispatches one slot's accounts per tick.
 *
 * The design goal is that the queue never holds more than one slot's work.
 * With 1,440 slots and 2.9M accounts that is ~2,000 jobs at a time instead of
 * 2.9M delayed jobs, which is the difference between a few MB of Redis and
 * tens of GB.
 *
 * Two scheduler instances can run safely: claiming a slot is an INSERT against
 * a unique (slot_date, slot) constraint, so exactly one wins and the other
 * skips. That also means the record of what has been dispatched survives a
 * restart, which is what recovery reads.
 */
@Injectable()
export class SchedulerService implements OnModuleInit {
  private readonly logger = new Logger(SchedulerService.name);
  private running = false;

  constructor(
    private readonly prisma: PrismaService,
    private readonly content: ContentService,
    private readonly producer: QueueProducer,
    private readonly config: ConfigService,
  ) {}

  private get slotsPerDay(): number {
    return this.config.get<number>('scheduler.slotsPerDay')!;
  }

  async onModuleInit() {
    if (!this.config.get<boolean>('scheduler.enabled')) {
      this.logger.log('Scheduler disabled on this process (SCHEDULER_ENABLED=false).');
      return;
    }
    // Catch up on anything missed while this process was down, before the
    // first normal tick.
    await this.recoverMissedSlots().catch((e) =>
      this.logger.error(`startup recovery failed: ${e}`),
    );
  }

  /**
   * Fires every minute. Overlap is prevented by the `running` flag locally and
   * by the unique slot claim globally, so a slow tick can never stack up.
   */
  @Cron(CronExpression.EVERY_MINUTE, { name: 'dispatch-slot' })
  async tick(): Promise<void> {
    if (!this.config.get<boolean>('scheduler.enabled')) return;
    if (this.running) {
      this.logger.warn('previous tick still running, skipping this one');
      return;
    }
    this.running = true;
    try {
      const now = new Date();
      await this.dispatchSlot(slotDateFor(now), slotForDate(now, this.slotsPerDay));
      await this.recoverMissedSlots();
    } catch (err) {
      this.logger.error(`tick failed: ${err}`);
    } finally {
      this.running = false;
    }
  }

  /**
   * Replays slots in the lookback window that were never completed — the
   * "server went down mid-cycle" case. Safe to run every tick because
   * dispatching an already-dispatched slot produces no duplicate work:
   * job ids are deterministic and delivery is conditional.
   */
  async recoverMissedSlots(): Promise<number> {
    const lookback = this.config.get<number>('scheduler.recoveryLookbackSlots')!;
    const candidates = recentSlots(new Date(), lookback, this.slotsPerDay).slice(1); // skip current
    if (candidates.length === 0) return 0;

    const existing = await this.prisma.scheduleTick.findMany({
      where: {
        OR: candidates.map((c) => ({ slotDate: c.slotDate, slot: c.slot })),
      },
      select: { slotDate: true, slot: true, status: true },
    });

    const done = new Set(
      existing
        .filter((t) => t.status === 'COMPLETED')
        .map((t) => `${t.slotDate.toISOString()}:${t.slot}`),
    );

    const missed = candidates.filter((c) => !done.has(`${c.slotDate.toISOString()}:${c.slot}`));
    if (missed.length === 0) return 0;

    this.logger.warn(`recovering ${missed.length} missed slot(s)`);
    let recovered = 0;
    for (const c of missed) {
      const n = await this.dispatchSlot(c.slotDate, c.slot, true);
      if (n >= 0) recovered++;
    }
    return recovered;
  }

  /**
   * Claims and dispatches one slot. Returns the number of jobs enqueued, or
   * -1 if another instance already owns it.
   */
  async dispatchSlot(slotDate: Date, slot: number, isRecovery = false): Promise<number> {
    const content = await this.content.getCurrent();
    if (!content) {
      this.logger.debug(`slot ${slot}: no published content, nothing to dispatch`);
      return 0;
    }

    // Claim. On a recovery pass the row may already exist in a non-completed
    // state, which we are allowed to take over.
    const claimed = await this.claimSlot(slotDate, slot, isRecovery);
    if (!claimed) return -1;

    const pageSize = this.config.get<number>('scheduler.dispatchPageSize')!;
    let cursor: string | undefined;
    let enqueued = 0;

    try {
      for (;;) {
        // Keyset pagination, not OFFSET: at 2.9M rows OFFSET degrades into a
        // full scan for later pages.
        const users = await this.prisma.user.findMany({
          where: {
            updateSlot: slot,
            // Only accounts that can actually use an update.
            status: { notIn: ['SUSPENDED', 'KYC_REJECTED', 'REGISTERED'] },
            ...(cursor ? { id: { gt: cursor } } : {}),
          },
          select: { id: true },
          orderBy: { id: 'asc' },
          take: pageSize,
        });

        if (users.length === 0) break;

        const jobs: DeliverUpdateJob[] = users.map((u) => ({
          userId: u.id,
          version: content.version,
          slot,
        }));
        enqueued += await this.producer.enqueueUpdates(jobs);

        cursor = users[users.length - 1].id;
        if (users.length < pageSize) break;
      }

      await this.prisma.scheduleTick.updateMany({
        where: { slotDate, slot },
        data: { status: 'COMPLETED', completedAt: new Date(), enqueuedCount: enqueued },
      });

      if (enqueued > 0) {
        this.logger.log(
          `slot ${slot}${isRecovery ? ' (recovery)' : ''}: enqueued ${enqueued} update(s) for v${content.version}`,
        );
      }
      return enqueued;
    } catch (err) {
      await this.prisma.scheduleTick
        .updateMany({
          where: { slotDate, slot },
          data: { status: 'FAILED', lastError: String(err).slice(0, 500) },
        })
        .catch(() => undefined);
      // Left FAILED so the next recovery sweep picks it up again.
      this.logger.error(`slot ${slot} dispatch failed after ${enqueued} job(s): ${err}`);
      throw err;
    }
  }

  /**
   * Atomically claims a slot. The unique (slot_date, slot) constraint is the
   * lock — no Redis lock needed, and it survives a restart.
   */
  private async claimSlot(slotDate: Date, slot: number, allowRetake: boolean): Promise<boolean> {
    try {
      await this.prisma.scheduleTick.create({
        data: { slotDate, slot, status: 'IN_PROGRESS' },
      });
      return true;
    } catch {
      // Row exists. Take it over only if it never completed.
      if (!allowRetake) return false;
      const retaken = await this.prisma.scheduleTick.updateMany({
        where: { slotDate, slot, status: { in: ['FAILED', 'IN_PROGRESS'] } },
        data: { status: 'IN_PROGRESS', startedAt: new Date() },
      });
      return retaken.count > 0;
    }
  }

  /** Dispatcher health, for the ops endpoint. */
  async status() {
    const now = new Date();
    const [lastCompleted, failed] = await Promise.all([
      this.prisma.scheduleTick.findFirst({
        where: { status: 'COMPLETED' },
        orderBy: [{ slotDate: 'desc' }, { slot: 'desc' }],
      }),
      this.prisma.scheduleTick.count({ where: { status: 'FAILED' } }),
    ]);
    return {
      enabled: this.config.get<boolean>('scheduler.enabled'),
      slotsPerDay: this.slotsPerDay,
      currentSlot: slotForDate(now, this.slotsPerDay),
      lastCompletedSlot: lastCompleted
        ? { slot: lastCompleted.slot, at: lastCompleted.completedAt, enqueued: lastCompleted.enqueuedCount }
        : null,
      failedTicks: failed,
    };
  }
}
