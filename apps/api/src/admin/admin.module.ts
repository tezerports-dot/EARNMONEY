import { Module } from '@nestjs/common';
import { AuthModule } from '../auth/auth.module';
import { SystemConfigModule } from '../system-config/system-config.module';
import { AdminController } from './admin.controller';
import { AdminConfigService } from './admin-config.service';
import { AdminScenariosService } from './admin-scenarios.service';

@Module({
  imports: [AuthModule, SystemConfigModule],
  controllers: [AdminController],
  providers: [AdminConfigService, AdminScenariosService],
})
export class AdminModule {}
