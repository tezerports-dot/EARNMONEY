import { IsBoolean, IsOptional, IsString, Matches, MinLength, Equals } from 'class-validator';

export class SignupDto {
  // Aadhaar number the candidate is registering with. Validated for shape and
  // Verhoeff checksum in the service, hashed immediately, and never stored or
  // echoed back in full. See common/identity/aadhaar.util.ts.
  @IsString()
  @Matches(/^[0-9\s-]{12,14}$/, { message: 'Aadhaar number must be 12 digits' })
  aadhaarNumber: string;

  // Must be the mobile number linked to that Aadhaar — this is what the
  // Telegram "share contact" step later proves the candidate controls.
  @Matches(/^\+[1-9]\d{7,14}$/, { message: 'mobile must be a valid E.164 number, e.g. +919812345678' })
  mobile: string;

  @MinLength(10, { message: 'password must be at least 10 characters' })
  @Matches(/(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/, {
    message: 'password must contain upper, lower case letters and a number',
  })
  password: string;

  @IsString()
  confirmPassword: string;

  // Pre-filled and locked by the app when the user arrived via a referral
  // link. The server re-resolves it regardless of what the client sends.
  @IsOptional()
  @IsString()
  referralCode?: string;

  @IsBoolean()
  @Equals(true, { message: 'consent to the privacy notice is required to sign up' })
  consentAccepted: boolean;

  @IsString()
  captchaToken: string;
}
