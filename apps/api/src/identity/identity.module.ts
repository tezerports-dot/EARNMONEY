import { Module } from '@nestjs/common';
import { IdentityService } from './identity.service';
import { IdentityController } from './identity.controller';
import { MockIdentityProvider } from './providers/mock-identity-provider.service';
import { HttpIdentityProvider } from './providers/http-identity-provider.service';
import { ConfigService } from '@nestjs/config';
import { UsersModule } from '../users/users.module';
import { FraudModule } from '../fraud/fraud.module';
import { AuthModule } from '../auth/auth.module';

/**
 * Chooses the identity provider.
 *
 * The mock auto-approves every candidate, which makes "KYC-verified referrals"
 * verify nothing and stops the fraud rules from ever firing. Shipping it would
 * not look broken — it would look like everyone passing. So production refuses
 * to boot without a configured vendor.
 */
export function selectIdentityProvider(
  config: ConfigService,
  http: HttpIdentityProvider,
  mock: MockIdentityProvider,
): HttpIdentityProvider | MockIdentityProvider {
  const baseUrl = config.get<string>('identityProvider.baseUrl');
  const isProduction = config.get<string>('nodeEnv') === 'production';

  if (baseUrl) return http;

  if (isProduction) {
    throw new Error(
      'IDENTITY_PROVIDER_BASE_URL is not set. Refusing to start in production with the mock identity ' +
        'provider — it auto-approves every candidate, so referral verification and the fraud rules ' +
        'would be meaningless. Contract a licensed KYC vendor and configure it first.',
    );
  }
  return mock;
}

@Module({
  imports: [UsersModule, AuthModule, FraudModule],
  controllers: [IdentityController],
  providers: [
    IdentityService,
    MockIdentityProvider,
    HttpIdentityProvider,
    {
      provide: 'IdentityProvider',
      inject: [ConfigService, HttpIdentityProvider, MockIdentityProvider],
      useFactory: selectIdentityProvider,
    },
  ],
})
export class IdentityModule {}
