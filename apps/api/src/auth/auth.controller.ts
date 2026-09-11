import {
  Body,
  Controller,
  HttpCode,
  HttpStatus,
  Ip,
  Post,
  Req,
  Res,
  UseGuards,
} from '@nestjs/common';
import { Throttle } from '@nestjs/throttler';
import { ConfigService } from '@nestjs/config';
import { Request, Response } from 'express';
import { randomBytes } from 'crypto';
import { AuthService } from './auth.service';
import { SignupDto } from './dto/signup.dto';
import { LoginDto } from './dto/login.dto';
import { JwtAuthGuard } from './guards/jwt-auth.guard';
import { CurrentUser } from '../common/decorators/current-user.decorator';

@Controller('auth')
export class AuthController {
  constructor(
    private readonly authService: AuthService,
    private readonly config: ConfigService,
  ) {}

  @Post('signup')
  @HttpCode(HttpStatus.CREATED)
  @Throttle({ default: { limit: 5, ttl: 60_000 } }) // signup is abuse-prone (TRD §2)
  async signup(@Body() dto: SignupDto, @Ip() ip: string) {
    return this.authService.signup(dto, ip);
  }

  @Post('login')
  @HttpCode(HttpStatus.OK)
  @Throttle({ default: { limit: 8, ttl: 60_000 } })
  async login(@Body() dto: LoginDto, @Ip() ip: string, @Res({ passthrough: true }) res: Response) {
    const { user, tokens } = await this.authService.login(dto, ip);
    const csrfToken = this.setSessionCookies(
      res,
      tokens.accessToken,
      tokens.refreshToken,
      tokens.refreshTokenExpiresAt,
    );
    // Returned in the body as well as the cookie, because a native app has no
    // document.cookie to read it from. This is not a secret from the
    // legitimate client — a CSRF token defends against *cross-site* requests,
    // which a native app does not make. The cookie stays for web clients.
    return { user, csrfToken };
  }

  @Post('refresh')
  @HttpCode(HttpStatus.OK)
  @Throttle({ default: { limit: 20, ttl: 60_000 } })
  async refresh(@Req() req: Request, @Res({ passthrough: true }) res: Response) {
    const raw = req.cookies?.['refresh_token'];
    if (!raw) {
      res.status(HttpStatus.UNAUTHORIZED);
      return { message: 'No active session.' };
    }
    const tokens = await this.authService.refresh(raw);
    const csrfToken = this.setSessionCookies(
      res,
      tokens.accessToken,
      tokens.refreshToken,
      tokens.refreshTokenExpiresAt,
    );
    return { ok: true, csrfToken };
  }

  @Post('logout')
  @HttpCode(HttpStatus.OK)
  @UseGuards(JwtAuthGuard)
  async logout(
    @Req() req: Request,
    @CurrentUser() user: { id: string },
    @Ip() ip: string,
    @Res({ passthrough: true }) res: Response,
  ) {
    const raw = req.cookies?.['refresh_token'];
    await this.authService.logout(raw, user.id, ip);
    this.clearSessionCookies(res);
    return { ok: true };
  }

  // -------------------------------------------------------------------

  /** Sets the session cookies and returns the CSRF token it issued. */
  private setSessionCookies(
    res: Response,
    accessToken: string,
    refreshToken: string,
    refreshExpiresAt: Date,
  ): string {
    const secure = this.config.get<boolean>('cookies.secure');
    const domain = this.config.get<string>('cookies.domain');

    res.cookie('access_token', accessToken, {
      httpOnly: true,
      secure,
      sameSite: 'lax',
      domain,
      maxAge: 15 * 60 * 1000,
      path: '/',
    });

    res.cookie('refresh_token', refreshToken, {
      httpOnly: true,
      secure,
      sameSite: 'strict',
      domain,
      expires: refreshExpiresAt,
      path: '/api/v1/auth',
    });

    // CSRF token: intentionally NOT httpOnly, so a web frontend can read it
    // and echo it back in a header (double-submit pattern — see CsrfGuard).
    const csrfToken = randomBytes(24).toString('hex');
    res.cookie('csrf_token', csrfToken, {
      httpOnly: false,
      secure,
      sameSite: 'lax',
      domain,
      expires: refreshExpiresAt,
      path: '/',
    });
    return csrfToken;
  }

  private clearSessionCookies(res: Response) {
    res.clearCookie('access_token', { path: '/' });
    res.clearCookie('refresh_token', { path: '/api/v1/auth' });
    res.clearCookie('csrf_token', { path: '/' });
  }
}
