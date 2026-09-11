import { ConfigService } from '@nestjs/config';
import { selectIdentityProvider } from './identity.module';
import { HttpIdentityProvider } from './providers/http-identity-provider.service';
import { MockIdentityProvider } from './providers/mock-identity-provider.service';

describe('selectIdentityProvider', () => {
  const http = {} as HttpIdentityProvider;
  const mock = {} as MockIdentityProvider;
  const cfg = (values: Record<string, unknown>) =>
    ({ get: (k: string) => values[k] }) as unknown as ConfigService;

  it('uses the real vendor adapter when a base URL is configured', () => {
    expect(
      selectIdentityProvider(
        cfg({ 'identityProvider.baseUrl': 'https://vendor.example/api', nodeEnv: 'production' }),
        http,
        mock,
      ),
    ).toBe(http);
  });

  it('falls back to the mock in development', () => {
    expect(selectIdentityProvider(cfg({ nodeEnv: 'development' }), http, mock)).toBe(mock);
  });

  it('REFUSES TO BOOT in production without a configured vendor', () => {
    // The mock auto-approves everyone, so shipping it would not look broken —
    // it would look like every candidate passing KYC, with the fraud rules
    // never firing once.
    expect(() => selectIdentityProvider(cfg({ nodeEnv: 'production' }), http, mock)).toThrow(
      /IDENTITY_PROVIDER_BASE_URL/,
    );
  });

  it('names the consequence in the error, not just the missing variable', () => {
    expect(() => selectIdentityProvider(cfg({ nodeEnv: 'production' }), http, mock)).toThrow(
      /auto-approves every candidate/,
    );
  });
});
