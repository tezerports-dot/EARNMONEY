import { Module } from '@nestjs/common';
import { JwtModule } from '@nestjs/jwt';
import { AuthController } from './auth.controller';
import { AuthService } from './auth.service';
import { JwtAuthGuard } from './guards/jwt-auth.guard';
import { NoopCaptchaService, TurnstileCaptchaService } from './captcha.service';
import { ConfigService } from '@nestjs/config';

/**
 * Chooses the CAPTCHA implementation.
 *
 * Real Turnstile whenever TURNSTILE_SECRET_KEY is set; the dev stub only
 * otherwise — and never in production, where a missing key is a boot failure
 * rather than a silently disabled defence. A CAPTCHA that always passes looks
 * exactly like one that works, right up until the bot flood.
 *
 * Exported so the rule can be tested directly rather than by booting the
 * module graph.
 */
export function selectCaptchaProvider(
  config: ConfigService,
  turnstile: TurnstileCaptchaService,
  noop: NoopCaptchaService,
): TurnstileCaptchaService | NoopCaptchaService {
  const secret = config.get<string>('captcha.turnstileSecret');
  const isProduction = config.get<string>('nodeEnv') === 'production';

  if (secret) return turnstile;

  if (isProduction) {
    throw new Error(
      'TURNSTILE_SECRET_KEY is not set. Refusing to start in production with CAPTCHA disabled — ' +
        'signup and login would accept unlimited automated requests. Set the key, or run with NODE_ENV != production.',
    );
  }
  return noop;
}

@Module({
  imports: [JwtModule.register({})],
  controllers: [AuthController],
  providers: [
    AuthService,
    JwtAuthGuard,
    TurnstileCaptchaService,
    NoopCaptchaService,
    {
      provide: 'CaptchaService',
      inject: [ConfigService, TurnstileCaptchaService, NoopCaptchaService],
      useFactory: selectCaptchaProvider,
    },
  ],
  // JwtModule is re-exported so that JwtAuthGuard can be constructed inside
  // importing modules' contexts — @UseGuards(JwtAuthGuard) instantiates the
  // guard in the host module, which needs JwtService resolvable there.
  exports: [AuthService, JwtAuthGuard, JwtModule],
})
export class AuthModule {}
