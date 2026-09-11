import { Module } from '@nestjs/common';
import { ScheduleModule } from '@nestjs/schedule';
import { ContentCoreModule } from '../content/content-core.module';
import { SchedulerService } from './scheduler.service';

@Module({
  imports: [ScheduleModule.forRoot(), ContentCoreModule],
  providers: [SchedulerService],
  exports: [SchedulerService],
})
export class SchedulerModule {}
