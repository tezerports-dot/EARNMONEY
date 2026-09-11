import { Module } from '@nestjs/common';
import { KycTrainingService } from './kyc-training.service';
import { KycTrainingController } from './kyc-training.controller';
import { EligibilityModule } from '../eligibility/eligibility.module';
import { AuthModule } from '../auth/auth.module';

@Module({
  imports: [EligibilityModule, AuthModule],
  providers: [KycTrainingService],
  controllers: [KycTrainingController],
})
export class KycTrainingModule {}
