import { Module } from '@nestjs/common';
import { SystemConfigModule } from '../system-config/system-config.module';
import { FraudService } from './fraud.service';

@Module({
  imports: [SystemConfigModule],
  providers: [FraudService],
  exports: [FraudService],
})
export class FraudModule {}
