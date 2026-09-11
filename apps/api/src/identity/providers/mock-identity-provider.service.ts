import { Injectable, Logger } from '@nestjs/common';
import { randomBytes } from 'crypto';
import {
  IdentityProvider,
  StartVerificationResult,
  VerificationStatusResult,
} from '../identity-provider.interface';

/**
 * DEV/TEST ONLY. Auto-verifies after a short delay so the rest of the
 * pipeline (status transitions, referral crediting, eligibility) can be
 * built and tested without a real vendor contract in place. Swap for a real
 * provider implementation before launch — see identity.module.ts.
 */
@Injectable()
export class MockIdentityProvider implements IdentityProvider {
  private readonly logger = new Logger(MockIdentityProvider.name);
  // In-memory only — fine for a mock; a real provider's state of record
  // lives with the vendor, not in this process.
  private store = new Map<string, VerificationStatusResult>();

  async startVerification(userId: string): Promise<StartVerificationResult> {
    const providerReference = `mock_${randomBytes(8).toString('hex')}`;
    this.store.set(providerReference, { status: 'PENDING' });

    this.logger.warn(
      `MockIdentityProvider used for user ${userId} — this is NOT real identity verification. Do not deploy to production like this.`,
    );

    // Simulate the vendor verifying asynchronously.
    setTimeout(() => {
      this.store.set(providerReference, {
        status: 'VERIFIED',
        maskedIdentifier: 'MOCK-XXXX-0000',
      });
    }, 5000);

    return { providerReference, redirectUrl: undefined };
  }

  async getVerificationStatus(providerReference: string): Promise<VerificationStatusResult> {
    return this.store.get(providerReference) ?? { status: 'EXPIRED' };
  }

  async handleWebhook(payload: unknown): Promise<{ providerReference: string; result: VerificationStatusResult }> {
    const body = payload as { providerReference: string; status: VerificationStatusResult['status'] };
    const result: VerificationStatusResult = { status: body.status, maskedIdentifier: 'MOCK-XXXX-0000' };
    this.store.set(body.providerReference, result);
    return { providerReference: body.providerReference, result };
  }

  async cancelVerification(providerReference: string): Promise<void> {
    this.store.delete(providerReference);
  }
}
