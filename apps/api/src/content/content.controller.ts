import { Body, Controller, Get, Post, UseGuards } from '@nestjs/common';
import { Throttle } from '@nestjs/throttler';
import { IsOptional, IsString, MaxLength, MinLength } from 'class-validator';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { RolesGuard } from '../common/guards/roles.guard';
import { Roles } from '../common/decorators/roles.decorator';
import { CsrfGuard } from '../common/guards/csrf.guard';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { ContentService } from './content.service';
import { User } from '@prisma/client';

class PublishContentDto {
  @IsString() @MinLength(1) @MaxLength(200) title: string;
  @IsString() @MinLength(1) @MaxLength(4000) body: string;
  @IsOptional() @IsString() @MaxLength(2000) linkUrl?: string;
}

@Controller('content')
export class ContentController {
  constructor(private readonly content: ContentService) {}

  /**
   * The candidate's own feed. Served from cache, so this stays cheap even
   * when every account polls it.
   */
  @Get('me')
  @UseGuards(JwtAuthGuard)
  async mine(@CurrentUser() user: User) {
    return this.content.getForUser(user.id);
  }

  /** Publishing a new version is what starts the next day's fan-out. */
  @Post('publish')
  @UseGuards(JwtAuthGuard, CsrfGuard, RolesGuard)
  @Roles('ADMIN_SUPERADMIN')
  @Throttle({ default: { limit: 10, ttl: 60_000 } })
  async publish(@Body() dto: PublishContentDto) {
    return this.content.publish(dto);
  }
}
