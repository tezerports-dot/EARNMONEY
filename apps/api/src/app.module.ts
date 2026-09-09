import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { ThrottlerModule, ThrottlerGuard } from '@nestjs/throttler';
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

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true, load: [configuration] }),
    ThrottlerModule.forRootAsync({
      useFactory: () => ({
        throttlers: [{ ttl: 60_000, limit: 60 }], // sane global default; tighter limits set per-route
      }),
    }),
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
  ],
  providers: [
    {
      provide: APP_GUARD,
      useClass: ThrottlerGuard, // global rate limiting (TRD §2)
    },
  ],
})
export class AppModule {}
