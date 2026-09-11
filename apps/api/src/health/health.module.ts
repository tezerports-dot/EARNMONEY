import { Module } from '@nestjs/common';
import { AuthModule } from '../auth/auth.module';
import { SchedulerModule } from '../scheduler/scheduler.module';
import { HealthController } from './health.controller';
import { OpsController } from './ops.controller';

@Module({
  imports: [AuthModule, SchedulerModule],
  controllers: [HealthController, OpsController],
})
export class HealthModule {}
