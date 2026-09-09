import {
  BadRequestException,
  Body,
  Controller,
  Get,
  Headers,
  Post,
  Req,
  UseGuards,
} from '@nestjs/common';
import { Throttle } from '@nestjs/throttler';
import { Request } from 'express';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { CsrfGuard } from '../common/guards/csrf.guard';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { IdentityService } from './identity.service';
import { User } from '@prisma/client';

@Controller('identity')
export class IdentityController {
  constructor(private readonly identityService: IdentityService) {}

  @Post('start')
  @UseGuards(JwtAuthGuard, CsrfGuard)
  @Throttle({ default: { limit: 5, ttl: 60_000 } })
  async start(@CurrentUser() user: User) {
    return this.identityService.startVerification(user.id);
  }

  @Get('status')
  @UseGuards(JwtAuthGuard)
  async status(@CurrentUser() user: User) {
    return this.identityService.getMyStatus(user.id);
  }

  // No JWT here — the caller is the identity provider's server, not a
  // logged-in candidate. Trust is established via HMAC signature instead.
  @Post('webhook')
  @Throttle({ default: { limit: 100, ttl: 60_000 } })
  async webhook(@Req() req: Request, @Headers('x-signature') signature: string | undefined, @Body() body: unknown) {
    const rawBody = (req as any).rawBody as Buffer | undefined;
    if (!rawBody) {
      throw new BadRequestException('Missing raw body for signature verification.');
    }

    const valid = this.identityService.verifyWebhookSignature(rawBody.toString('utf8'), signature);
    if (!valid) {
      throw new BadRequestException('Invalid webhook signature.');
    }

    return this.identityService.handleWebhook(body, signature);
  }
}
