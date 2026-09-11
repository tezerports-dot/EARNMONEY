import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import configuration from './config/configuration';
import { PrismaModule } from './prisma/prisma.module';
import { AuditModule } from './audit/audit.module';
import { CacheModule } from './cache/cache.module';
import { QueueModule } from './queue/queue.module';
import { ContentCoreModule } from './content/content-core.module';

/**
 * What a worker process loads — deliberately much less than the API.
 *
 * No controllers, no guards, no throttler, no HTTP stack. It cannot serve a
 * request even if something tried to send it one, and it uses the smaller
 * `DB_POOL_WORKER` pool rather than the API's.
 *
 * Note the absence of SchedulerModule: dispatching is separate from
 * processing, so worker containers can be scaled without multiplying
 * dispatchers.
 */
@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true, load: [configuration] }),
    PrismaModule,
    CacheModule,
    QueueModule,
    AuditModule,
    ContentCoreModule,
  ],
})
export class WorkerModule {}
