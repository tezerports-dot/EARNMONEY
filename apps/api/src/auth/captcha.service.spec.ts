import { ConfigService } from '@nestjs/config';
import { NoopCaptchaService, TurnstileCaptchaService } from './captcha.service';

/**
 * The provider-selection rules are the security-carrying part here: a CAPTCHA
 * that silently passes looks exactly like one that works.
 */
import { selectCaptchaProvider } from './auth.module';

/**
 * The selection rule is the security-carrying part: a CAPTCHA that silently
 * passes is indistinguishable from one that works.
 */
describe('selectCaptchaProvider', () => {
  const turnstile = {} as TurnstileCaptchaService;
  const noop = {} as NoopCaptchaService;
  const cfg = (values: Record<string, unknown>) =>
    ({ get: (k: string) => values[k] }) as unknown as ConfigService;

  it('uses Turnstile when a secret is configured', () => {
    expect(
      selectCaptchaProvider(
        cfg({ 'captcha.turnstileSecret': 'a-real-secret', nodeEnv: 'production' }),
        turnstile,
        noop,
      ),
    ).toBe(turnstile);
  });

  it('falls back to the stub in development', () => {
    expect(selectCaptchaProvider(cfg({ nodeEnv: 'development' }), turnstile, noop)).toBe(noop);
  });

  it('REFUSES TO BOOT in production without a Turnstile secret', () => {
    // A missing key must be a loud startup failure, not a quietly disabled
    // defence discovered during a bot flood.
    expect(() => selectCaptchaProvider(cfg({ nodeEnv: 'production' }), turnstile, noop)).toThrow(
      /TURNSTILE_SECRET_KEY/,
    );
  });
});

describe('TurnstileCaptchaService', () => {
  let service: TurnstileCaptchaService;
  const originalFetch = global.fetch;

  beforeEach(() => {
    service = new TurnstileCaptchaService({
      get: () => 'secret',
    } as unknown as ConfigService);
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('accepts a token Cloudflare reports as successful', async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ success: true }) });
    await expect(service.verify('tok')).resolves.toBe(true);
  });

  it('rejects a token Cloudflare refuses', async () => {
    global.fetch = jest
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ success: false, 'error-codes': ['invalid-input-response'] }) });
    await expect(service.verify('tok')).resolves.toBe(false);
  });

  it('rejects an empty token without calling out at all', async () => {
    global.fetch = jest.fn();
    await expect(service.verify('')).resolves.toBe(false);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('fails CLOSED when Cloudflare is unreachable', async () => {
    // Opposite of the rate limiter's fail-open choice, deliberately: a CAPTCHA
    // failing open invites exactly the abuse it exists to prevent.
    global.fetch = jest.fn().mockRejectedValue(new Error('network down'));
    await expect(service.verify('tok')).resolves.toBe(false);
  });

  it('fails closed on a non-200 from Cloudflare', async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 500 });
    await expect(service.verify('tok')).resolves.toBe(false);
  });

  it('sends form encoding, which is what the endpoint expects', async () => {
    const fetchMock = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ success: true }) });
    global.fetch = fetchMock;

    await service.verify('tok', '1.2.3.4');

    const init = fetchMock.mock.calls[0][1];
    expect(init.headers['Content-Type']).toBe('application/x-www-form-urlencoded');
    expect(init.body.toString()).toContain('remoteip=1.2.3.4');
  });
});
