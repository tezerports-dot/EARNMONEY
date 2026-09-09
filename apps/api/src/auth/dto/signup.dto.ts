import { IsBoolean, IsOptional, IsString, Matches, MinLength, Equals } from 'class-validator';

export class SignupDto {
  // E.164 format, e.g. +919812345678 — validated more strictly in the service
  // with libphonenumber-js, this regex just rejects obviously malformed input.
  @Matches(/^\+[1-9]\d{7,14}$/, { message: 'mobile must be a valid E.164 number, e.g. +919812345678' })
  mobile: string;

  @MinLength(10, { message: 'password must be at least 10 characters' })
  @Matches(/(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/, {
    message: 'password must contain upper, lower case letters and a number',
  })
  password: string;

  @IsOptional()
  @IsString()
  referralCode?: string;

  // Must be explicitly true — signup fails otherwise. This is the consent
  // checkbox required by 01-PRD.md step 4 ("required consent").
  @IsBoolean()
  @Equals(true, { message: 'consent to the privacy notice is required to sign up' })
  consentAccepted: boolean;

  // CAPTCHA token from the provider widget (see CaptchaService).
  @IsString()
  captchaToken: string;
}
