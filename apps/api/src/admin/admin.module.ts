import { Module } from '@nestjs/common';
import { AuthModule } from '../auth/auth.module';
import { SystemConfigModule } from '../system-config/system-config.module';
import { AdminController } from './admin.controller';
import { AdminConfigService } from './admin-config.service';
import { AdminReadingItemsService } from './admin-reading-items.service';

@Module({
  imports: [AuthModule, SystemConfigModule],
  controllers: [AdminController],
  providers: [AdminConfigService, AdminReadingItemsService],
})
export class AdminModule {}
