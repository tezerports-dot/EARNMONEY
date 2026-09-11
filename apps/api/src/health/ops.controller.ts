import { Controller, Get, UseGuards } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { RolesGuard } from '../common/guards/roles.guard';
import { Roles } from '../common/decorators/roles.decorator';
import { PrismaService } from '../prisma/prisma.service';
import { CacheService } from '../cache/cache.service';
import { QueueProducer } from '../queue/queue.producer';
import { SchedulerService } from '../scheduler/scheduler.service';
import { slotLoad } from '../scheduler/slot.util';

/**
 * The numbers you alert on, in one place.
 *
 * Admin-only rather than public: queue depth and account totals are useful to
 * an attacker sizing the system. The plain `/health` endpoint stays public and
 * unauthenticated for the load balancer.
 */
@Controller('ops')
@UseGuards(JwtAuthGuard, RolesGuard)
@Roles('ADMIN_SUPERADMIN')
export class OpsController {
  constructor(
    private readonly prisma: PrismaService,
    private readonly cache: CacheService,
    private readonly queue: QueueProducer,
    private readonly scheduler: SchedulerService,
    private readonly config: ConfigService,
  ) {}

  @Get('metrics')
  async metrics() {
    const [accounts, delivered, failedStates, queueDepths, schedulerStatus] = await Promise.all([
      this.prisma.user.count(),
      this.prisma.userUpdateState.count({ where: { deliveredAt: { not: null } } }),
      this.prisma.userUpdateState.count({ where: { failureCount: { gt: 0 } } }),
      this.queue.depths().catch(() => null),
      this.scheduler.status(),
    ]);

    const slotsPerDay = this.config.get<number>('scheduler.slotsPerDay')!;
    const load = slotLoad(accounts, slotsPerDay);

    return {
      accounts,
      // Derived from the SAME function the dispatcher uses, so the projected
      // rate here can never drift from what actually runs.
      projected: {
        accountsPerSlot: load.accountsPerSlot,
        updatesPerSecond: load.updatesPerSecond,
        configuredCeilingPerSecond:
          (this.config.get<number>('queue.rateLimitMax')! * 1000) /
          this.config.get<number>('queue.rateLimitDurationMs')!,
      },
      delivery: { delivered, withFailures: failedStates },
      queues: queueDepths,
      scheduler: schedulerStatus,
      cache: this.cache.stats(),
      pools: {
        role: process.env.PROCESS_ROLE ?? 'api',
        apiPoolSize: this.config.get<number>('database.apiPoolSize'),
        workerPoolSize: this.config.get<number>('database.workerPoolSize'),
      },
    };
  }
}
