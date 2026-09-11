import { Module } from '@nestjs/common';
import { IdentityService } from './identity.service';
import { IdentityController } from './identity.controller';
import { MockIdentityProvider } from './providers/mock-identity-provider.service';
import { UsersModule } from '../users/users.module';
import { FraudModule } from '../fraud/fraud.module';
import { AuthModule } from '../auth/auth.module';

@Module({
  imports: [UsersModule, AuthModule, FraudModule],
  controllers: [IdentityController],
  providers: [
    IdentityService,
    // Swap this for your real vendor's implementation of IdentityProvider
    // once contracted — nothing else in the app needs to change. See
    // identity-provider.interface.ts and providers/mock-identity-provider.service.ts.
    { provide: 'IdentityProvider', useClass: MockIdentityProvider },
  ],
})
export class IdentityModule {}
