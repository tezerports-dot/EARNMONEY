import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { createHmac, timingSafeEqual } from 'crypto';
import {
  IdentityProvider,
  StartVerificationResult,
  VerificationStatusResult,
} from '../identity-provider.interface';

/**
 * Generic HTTP adapter for a contracted KYC vendor.
 *
 * This platform does not, and must not, verify Aadhaar itself — that requires
 * UIDAI authorisation only a licensed provider holds. This class calls out to
 * whichever provider you sign with (Signzy, IDfy, Karza, Digio, HyperVerge…).
 *
 * ⚠️ READ BEFORE GOING LIVE — the request and response SHAPES below are a
 * reasonable default, not a verified integration. Every vendor differs. You
 * must confirm three things against your vendor's actual documentation and
 * adjust `toStatus()` / the request bodies if they differ:
 *
 *   1. The field their API expects for your reference id, and what they return
 *      as their own reference.
 *   2. Their status vocabulary — `toStatus()` maps a common set, and anything
 *      unrecognised is treated as PENDING rather than guessed at.
 *   3. Their webhook signature scheme. `verifySignature()` implements
 *      HMAC-SHA256 over the raw body, which is the most common, but some use a
 *      timestamped payload or a different digest.
 *
 * Getting (3) wrong is the dangerous one: an unverified webhook means anyone
 * who learns the endpoint can mark any candidate as verified. That is why
 * `handleWebhook` refuses outright when no secret is configured, rather than
 * accepting the payload.
 */
@Injectable()
export class HttpIdentityProvider implements IdentityProvider {
  private readonly logger = new Logger(HttpIdentityProvider.name);
  private static readonly TIMEOUT_MS = 10_000;

  constructor(private readonly config: ConfigService) {}

  private get baseUrl(): string {
    const url = this.config.get<string>('identityProvider.baseUrl');
    if (!url) throw new Error('IDENTITY_PROVIDER_BASE_URL is not set.');
    return url.replace(/\/$/, '');
  }

  private get apiKey(): string {
    const key = this.config.get<string>('identityProvider.apiKey');
    if (!key) throw new Error('IDENTITY_PROVIDER_API_KEY is not set.');
    return key;
  }

  private async request<T>(path: string, init: RequestInit): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), HttpIdentityProvider.TIMEOUT_MS);
    try {
      const res = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${this.apiKey}`,
          ...(init.headers ?? {}),
        },
      });
      if (!res.ok) {
        const text = await res.text().catch(() => '');
        // Never log the body wholesale — a KYC provider's error payload can
        // echo back identity data.
        throw new Error(`provider returned HTTP ${res.status}${text ? ` (${text.slice(0, 120)})` : ''}`);
      }
      return (await res.json()) as T;
    } finally {
      clearTimeout(timer);
    }
  }

  async startVerification(userId: string): Promise<StartVerificationResult> {
    // `userId` only — never the Aadhaar number. The provider collects the
    // identity data directly from the candidate, which is what keeps it out of
    // this system entirely.
    const data = await this.request<{ reference?: string; id?: string; redirect_url?: string; url?: string }>(
      '/verifications',
      { method: 'POST', body: JSON.stringify({ reference_id: userId }) },
    );

    const providerReference = data.reference ?? data.id;
    if (!providerReference) {
      throw new Error('provider did not return a reference for the verification.');
    }
    return { providerReference, redirectUrl: data.redirect_url ?? data.url };
  }

  async getVerificationStatus(providerReference: string): Promise<VerificationStatusResult> {
    const data = await this.request<{ status?: string; reason?: string; masked_id?: string }>(
      `/verifications/${encodeURIComponent(providerReference)}`,
      { method: 'GET' },
    );
    return {
      status: this.toStatus(data.status),
      failureReasonCode: data.reason,
      maskedIdentifier: data.masked_id,
    };
  }

  async handleWebhook(
    payload: unknown,
    signatureHeader: string | undefined,
  ): Promise<{ providerReference: string; result: VerificationStatusResult }> {
    // IdentityService verifies the signature over the RAW body before calling
    // this; re-checking here would need the raw bytes again. What this does
    // guarantee is that a missing secret is fatal rather than permissive.
    const secret = this.config.get<string>('identityProvider.webhookSecret');
    if (!secret) {
      throw new Error(
        'IDENTITY_PROVIDER_WEBHOOK_SECRET is not set. Refusing to process an unauthenticated identity webhook — ' +
          'anyone able to reach the endpoint could otherwise mark any candidate as verified.',
      );
    }
    void signatureHeader;

    const body = payload as { reference?: string; id?: string; status?: string; reason?: string; masked_id?: string };
    const providerReference = body.reference ?? body.id;
    if (!providerReference) {
      throw new Error('identity webhook contained no provider reference.');
    }

    return {
      providerReference,
      result: {
        status: this.toStatus(body.status),
        failureReasonCode: body.reason,
        maskedIdentifier: body.masked_id,
      },
    };
  }

  async cancelVerification(providerReference: string): Promise<void> {
    await this.request(`/verifications/${encodeURIComponent(providerReference)}/cancel`, {
      method: 'POST',
    }).catch((err) => {
      // Cancellation is best-effort; a failure here must not break the caller.
      this.logger.warn(`could not cancel ${providerReference}: ${err}`);
    });
  }

  /**
   * Maps a vendor's status vocabulary onto ours.
   *
   * Anything unrecognised becomes PENDING, never VERIFIED. Guessing in the
   * permissive direction would let an unexpected status silently pass someone
   * through identity verification.
   */
  private toStatus(raw: string | undefined): VerificationStatusResult['status'] {
    switch ((raw ?? '').toLowerCase()) {
      case 'verified':
      case 'approved':
      case 'success':
      case 'completed':
        return 'VERIFIED';
      case 'rejected':
      case 'failed':
      case 'declined':
        return 'REJECTED';
      case 'expired':
        return 'EXPIRED';
      case 'in_review':
      case 'manual_review':
      case 'review':
        return 'IN_REVIEW';
      case 'pending':
      case 'processing':
      case 'created':
        return 'PENDING';
      default:
        if (raw) this.logger.warn(`unrecognised provider status '${raw}', treating as PENDING`);
        return 'PENDING';
    }
  }

  /** HMAC-SHA256 over the raw body. Exposed for IdentityService to reuse. */
  static verifySignature(rawBody: string, signature: string | undefined, secret: string): boolean {
    if (!signature) return false;
    const expected = createHmac('sha256', secret).update(rawBody).digest('hex');
    const a = Buffer.from(expected, 'utf8');
    const b = Buffer.from(signature, 'utf8');
    if (a.length !== b.length) return false;
    return timingSafeEqual(a, b);
  }
}
