import { Module } from '@nestjs/common';
import { AuthModule } from '../auth/auth.module';
import { EligibilityModule } from '../eligibility/eligibility.module';
import { SelectionController } from './selection.controller';
import { SelectionService } from './selection.service';

@Module({
  imports: [AuthModule, EligibilityModule],
  controllers: [SelectionController],
  providers: [SelectionService],
})
export class SelectionModule {}
