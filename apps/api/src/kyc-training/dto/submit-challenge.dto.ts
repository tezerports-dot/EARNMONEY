import { IsBoolean, IsOptional, IsString } from 'class-validator';

export class SubmitChallengeDto {
  @IsBoolean()
  valid: boolean;

  // Required when valid=false — which problem did you spot?
  @IsOptional()
  @IsString()
  issue?: string;
}
