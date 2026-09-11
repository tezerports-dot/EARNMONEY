import {
  BadRequestException,
  Body,
  Controller,
  Get,
  Headers,
  HttpCode,
  Post,
  UseGuards,
} from '@nestjs/common';
import { Throttle } from '@nestjs/throttler';
import { ConfigService } from '@nestjs/config';
import { timingSafeEqual } from 'crypto';
import { JwtAuthGuard } from '../auth/guards/jwt-auth.guard';
import { CsrfGuard } from '../common/guards/csrf.guard';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { TelegramService } from './telegram.service';
import { User } from '@prisma/client';

@Controller('telegram')
export class TelegramController {
  constructor(
    private readonly telegram: TelegramService,
    private readonly config: ConfigService,
  ) {}

  /** Bot deep link plus both channel invite links, for the verify screen. */
  @Get('link')
  @UseGuards(JwtAuthGuard)
  async link(@CurrentUser() user: User) {
    return this.telegram.getLinkInfo(user.id);
  }

  /** Live checklist the app polls while the candidate works through the bot. */
  @Get('state')
  @UseGuards(JwtAuthGuard)
  async state(@CurrentUser() user: User) {
    return this.telegram.getVerificationState(user.id);
  }

  /** "I've joined both — check again" button. */
  @Post('recheck')
  @UseGuards(JwtAuthGuard, CsrfGuard)
  @Throttle({ default: { limit: 6, ttl: 60_000 } })
  async recheck(@CurrentUser() user: User) {
    return this.telegram.recheckForUser(user.id);
  }

  /**
   * Telegram's servers post here — no JWT, no CSRF, since the caller is not a
   * logged-in candidate. Trust comes from the secret token Telegram echoes in
   * a header, which we set when registering the webhook.
   *
   * Always answers 200: a non-2xx makes Telegram retry and then disable the
   * webhook, which would strand every candidate mid-verification.
   */
  @Post('webhook')
  @HttpCode(200)
  @Throttle({ default: { limit: 300, ttl: 60_000 } })
  async webhook(
    @Headers('x-telegram-bot-api-secret-token') secretToken: string | undefined,
    @Body() update: unknown,
  ) {
    const expected = this.config.get<string>('telegram.webhookSecret');
    if (!expected) {
      throw new BadRequestException('Telegram webhook secret is not configured.');
    }
    if (!secretToken || !safeEqual(secretToken, expected)) {
      // Wrong or missing token: refuse, and do it without leaking timing.
      throw new BadRequestException('Invalid webhook token.');
    }

    await this.telegram.handleUpdate(update);
    return { ok: true };
  }
}

function safeEqual(a: string, b: string): boolean {
  const ab = Buffer.from(a, 'utf8');
  const bb = Buffer.from(b, 'utf8');
  if (ab.length !== bb.length) return false;
  return timingSafeEqual(ab, bb);
}
