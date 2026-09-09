import { Module } from '@nestjs/common';
import { ReferralsService } from './referrals.service';
import { ReferralsController } from './referrals.controller';
import { EligibilityModule } from '../eligibility/eligibility.module';
import { AuthModule } from '../auth/auth.module';

@Module({
  imports: [EligibilityModule, AuthModule],
  providers: [ReferralsService],
  controllers: [ReferralsController],
  exports: [ReferralsService],
})
export class ReferralsModule {}
