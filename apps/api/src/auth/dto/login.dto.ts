import { IsString, Matches } from 'class-validator';

export class LoginDto {
  @Matches(/^\+[1-9]\d{7,14}$/, { message: 'mobile must be a valid E.164 number' })
  mobile: string;

  @IsString()
  password: string;

  @IsString()
  captchaToken: string;
}
