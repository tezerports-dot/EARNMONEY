import { Module } from '@nestjs/common';
import { JwtModule } from '@nestjs/jwt';
import { AuthController } from './auth.controller';
import { AuthService } from './auth.service';
import { JwtAuthGuard } from './guards/jwt-auth.guard';
import { NoopCaptchaService } from './captcha.service';

@Module({
  imports: [JwtModule.register({})],
  controllers: [AuthController],
  providers: [
    AuthService,
    JwtAuthGuard,
    // Swap this provider for TurnstileCaptchaService once TURNSTILE_SECRET_KEY
    // is configured for production. See captcha.service.ts.
    { provide: 'CaptchaService', useClass: NoopCaptchaService },
  ],
  // JwtModule is re-exported so that JwtAuthGuard can be constructed inside
  // importing modules' contexts — @UseGuards(JwtAuthGuard) instantiates the
  // guard in the host module, which needs JwtService resolvable there.
  exports: [AuthService, JwtAuthGuard, JwtModule],
})
export class AuthModule {}
