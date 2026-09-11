import { Module } from '@nestjs/common';
import { SystemConfigModule } from '../system-config/system-config.module';
import { ReferralsService } from './referrals.service';
import { ReferralsController } from './referrals.controller';
import { EligibilityModule } from '../eligibility/eligibility.module';
import { AuthModule } from '../auth/auth.module';

@Module({
  imports: [EligibilityModule, AuthModule, SystemConfigModule],
  providers: [ReferralsService],
  controllers: [ReferralsController],
  exports: [ReferralsService],
})
export class ReferralsModule {}
