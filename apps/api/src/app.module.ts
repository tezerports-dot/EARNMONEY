import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { ThrottlerModule, ThrottlerGuard } from '@nestjs/throttler';
import { CacheModule } from './cache/cache.module';
import { QueueModule } from './queue/queue.module';
import { SchedulerModule } from './scheduler/scheduler.module';
import { ContentModule } from './content/content.module';
import { AdminModule } from './admin/admin.module';
import { RedisThrottlerStorage } from './common/throttler/redis-throttler.storage';
import { APP_GUARD } from '@nestjs/core';
import configuration from './config/configuration';
import { PrismaModule } from './prisma/prisma.module';
import { AuditModule } from './audit/audit.module';
import { SystemConfigModule } from './system-config/system-config.module';
import { AuthModule } from './auth/auth.module';
import { UsersModule } from './users/users.module';
import { HealthModule } from './health/health.module';
import { EligibilityModule } from './eligibility/eligibility.module';
import { ReferralsModule } from './referrals/referrals.module';
import { KycTrainingModule } from './kyc-training/kyc-training.module';
import { ApplicationsModule } from './applications/applications.module';
import { IdentityModule } from './identity/identity.module';
import { TelegramModule } from './telegram/telegram.module';
import { FraudModule } from './fraud/fraud.module';
import { VacanciesModule } from './vacancies/vacancies.module';
import { SelectionModule } from './selection/selection.module';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true, load: [configuration] }),
    // Counters live in Redis, so limits hold across every API replica rather
    // than resetting per process (see RedisThrottlerStorage).
    ThrottlerModule.forRootAsync({
      imports: [CacheModule],
      inject: [RedisThrottlerStorage],
      useFactory: (storage: RedisThrottlerStorage) => ({
        // Generous global ceiling: this exists to stop abuse, NOT to shape
        // normal traffic. Interactive routes are never queued or deferred.
        throttlers: [{ name: 'default', ttl: 60_000, limit: 120 }],
        storage,
      }),
    }),
    CacheModule,
    QueueModule,
    PrismaModule,
    AuditModule,
    SystemConfigModule,
    AuthModule,
    UsersModule,
    HealthModule,
    EligibilityModule,
    ReferralsModule,
    KycTrainingModule,
    ApplicationsModule,
    IdentityModule,
    TelegramModule,
    FraudModule,
    VacanciesModule,
    SelectionModule,
    ContentModule,
    AdminModule,
    // Dispatching runs on API processes by default so a single small VPS needs
    // only two containers. Set SCHEDULER_ENABLED=false here and run a
    // dedicated dispatcher once you have more than one API replica.
    SchedulerModule,
  ],
  providers: [
    {
      provide: APP_GUARD,
      useClass: ThrottlerGuard, // global rate limiting (TRD §2)
    },
  ],
})
export class AppModule {}
