import { Controller, Get, UseGuards } from '@nestjs/common';
import { Throttle } from '@nestjs/throttler';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { SelectionService } from './selection.service';
import { User } from '@prisma/client';

@Controller('selection')
@UseGuards(JwtAuthGuard)
export class SelectionController {
  constructor(private readonly selection: SelectionService) {}

  @Get('status')
  async status(@CurrentUser() user: User) {
    return this.selection.getStatus(user.id);
  }

  @Get('group-invite')
  @Throttle({ default: { limit: 10, ttl: 60_000 } })
  async groupInvite(@CurrentUser() user: User) {
    return this.selection.getGroupInvite(user.id);
  }
}
