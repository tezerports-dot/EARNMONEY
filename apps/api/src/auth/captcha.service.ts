import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

export interface CaptchaService {
  verify(token: string, remoteIp?: string): Promise<boolean>;
}

/**
 * STUB — always passes in non-production environments so local development
 * and tests aren't blocked. This MUST be replaced with a real provider
 * (Cloudflare Turnstile or hCaptcha are the common choices) before this goes
 * live, per TRD section 2 ("CAPTCHA on signup and abuse-prone endpoints").
 *
 * We are not guessing which provider/account to wire in (Agent Rule 1) —
 * that needs a real account and site/secret keys you create yourself.
 */
@Injectable()
export class NoopCaptchaService implements CaptchaService {
  private readonly logger = new Logger(NoopCaptchaService.name);

  async verify(token: string): Promise<boolean> {
    if (!token) return false;
    this.logger.warn(
      'NoopCaptchaService is active — CAPTCHA is NOT actually being verified. Do not deploy to production like this.',
    );
    return true;
  }
}

/**
 * Example of how a real provider will plug in later (Cloudflare Turnstile
 * shown). Left unregistered until TURNSTILE_SECRET_KEY is configured.
 */
@Injectable()
export class TurnstileCaptchaService implements CaptchaService {
  constructor(private readonly config: ConfigService) {}

  async verify(token: string, remoteIp?: string): Promise<boolean> {
    const secret = this.config.get<string>('captcha.turnstileSecret');
    if (!secret) return false;

    const res = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ secret, response: token, remoteip: remoteIp }),
    });
    const data = (await res.json()) as { success: boolean };
    return !!data.success;
  }
}
