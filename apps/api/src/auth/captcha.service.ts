import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

export interface CaptchaService {
  verify(token: string, remoteIp?: string): Promise<boolean>;
}

/**
 * Development stub. Accepts any non-empty token.
 *
 * This is never selected when NODE_ENV=production — `captchaProvider()` in
 * auth.module.ts throws at boot rather than allowing it, because a CAPTCHA
 * that silently passes is indistinguishable from a working one until you are
 * being flooded with bot signups.
 */
@Injectable()
export class NoopCaptchaService implements CaptchaService {
  private readonly logger = new Logger(NoopCaptchaService.name);

  async verify(token: string): Promise<boolean> {
    if (!token) return false;
    this.logger.warn(
      'NoopCaptchaService active — CAPTCHA is NOT being verified. Development only.',
    );
    return true;
  }
}

/**
 * Cloudflare Turnstile.
 *
 * Notes on the failure behaviour, which is the part that matters:
 *
 *  - Fails CLOSED. If Turnstile is unreachable or returns something
 *    unexpected, verification fails and the signup is rejected. This is the
 *    opposite of the rate limiter's fail-open choice, and deliberately so:
 *    rate limiting degrades an existing user's experience, whereas a CAPTCHA
 *    failing open invites exactly the automated abuse it exists to stop.
 *  - Has an explicit timeout. Without one, a hanging Turnstile request holds
 *    the signup request open for as long as the socket lives, which is a cheap
 *    way to exhaust the API's capacity.
 *  - Logs the provider's error codes, since "invalid-input-secret" versus
 *    "timeout-or-duplicate" are very different problems.
 */
@Injectable()
export class TurnstileCaptchaService implements CaptchaService {
  private readonly logger = new Logger(TurnstileCaptchaService.name);
  private static readonly VERIFY_URL =
    'https://challenges.cloudflare.com/turnstile/v0/siteverify';
  private static readonly TIMEOUT_MS = 5_000;

  constructor(private readonly config: ConfigService) {}

  async verify(token: string, remoteIp?: string): Promise<boolean> {
    if (!token) return false;

    const secret = this.config.get<string>('captcha.turnstileSecret');
    if (!secret) {
      // Only reachable via misconfiguration; the module refuses to select this
      // provider without a secret.
      this.logger.error('TURNSTILE_SECRET_KEY missing at verification time.');
      return false;
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TurnstileCaptchaService.TIMEOUT_MS);

    try {
      // Turnstile's endpoint expects form encoding, not JSON.
      const body = new URLSearchParams({ secret, response: token });
      if (remoteIp) body.set('remoteip', remoteIp);

      const res = await fetch(TurnstileCaptchaService.VERIFY_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
        signal: controller.signal,
      });

      if (!res.ok) {
        this.logger.error(`Turnstile returned HTTP ${res.status}; rejecting.`);
        return false;
      }

      const data = (await res.json()) as { success?: boolean; 'error-codes'?: string[] };
      if (!data.success) {
        this.logger.warn(`Turnstile rejected a token: ${(data['error-codes'] ?? []).join(', ')}`);
        return false;
      }
      return true;
    } catch (err) {
      const aborted = err instanceof Error && err.name === 'AbortError';
      this.logger.error(
        aborted
          ? `Turnstile timed out after ${TurnstileCaptchaService.TIMEOUT_MS}ms; rejecting.`
          : `Turnstile verification failed: ${err}`,
      );
      return false;
    } finally {
      clearTimeout(timer);
    }
  }
}
