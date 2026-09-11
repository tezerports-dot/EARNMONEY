/**
 * Contract every identity/KYC provider integration must satisfy.
 *
 * IMPORTANT: this platform does NOT implement Aadhaar or any other
 * government ID authentication itself, and should not — that requires
 * UIDAI (or equivalent) authorization that only a licensed provider holds.
 * This interface exists so a real, contracted vendor (e.g. DigiLocker-based
 * providers, Signzy, IDfy, HyperVerge, etc. — whoever you sign with) can be
 * wired in behind it. Do not build direct government-ID verification.
 */
export interface StartVerificationResult {
  providerReference: string;
  /** URL/deep-link the candidate is sent to at the provider, if applicable. */
  redirectUrl?: string;
}

export interface VerificationStatusResult {
  status: 'PENDING' | 'IN_REVIEW' | 'VERIFIED' | 'REJECTED' | 'EXPIRED';
  failureReasonCode?: string;
  /** A masked identifier safe to store/display, e.g. "XXXX-XXXX-1234". Never a full ID number. */
  maskedIdentifier?: string;
}

export interface IdentityProvider {
  startVerification(userId: string): Promise<StartVerificationResult>;
  getVerificationStatus(providerReference: string): Promise<VerificationStatusResult>;
  /**
   * Validates and parses an inbound webhook payload from the provider.
   * Must verify the provider's signature/secret — never trust an
   * unauthenticated webhook body.
   */
  handleWebhook(payload: unknown, signatureHeader: string | undefined): Promise<{
    providerReference: string;
    result: VerificationStatusResult;
  }>;
  cancelVerification(providerReference: string): Promise<void>;
}
