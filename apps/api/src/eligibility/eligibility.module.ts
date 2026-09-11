import { Module } from '@nestjs/common';
import { SystemConfigModule } from '../system-config/system-config.module';
import { EligibilityService } from './eligibility.service';

@Module({
  imports: [SystemConfigModule],
  providers: [EligibilityService],
  exports: [EligibilityService],
})
export class EligibilityModule {}
