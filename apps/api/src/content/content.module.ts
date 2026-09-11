import { Module } from '@nestjs/common';
import { AuthModule } from '../auth/auth.module';
import { ContentCoreModule } from './content-core.module';
import { ContentController } from './content.controller';

/** The HTTP-facing half. API processes load this; workers load the core only. */
@Module({
  imports: [ContentCoreModule, AuthModule],
  controllers: [ContentController],
  exports: [ContentCoreModule],
})
export class ContentModule {}
