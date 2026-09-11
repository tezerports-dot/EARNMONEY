import { Module } from '@nestjs/common';
import { ContentService } from './content.service';
import { ContentDeliveryService } from './content-delivery.service';

/**
 * Content domain logic with no HTTP surface — no controller, no guards, no
 * auth dependency. This is what worker processes load, so a worker never
 * instantiates the JWT stack or anything else it has no use for.
 */
@Module({
  providers: [ContentService, ContentDeliveryService],
  exports: [ContentService, ContentDeliveryService],
})
export class ContentCoreModule {}
