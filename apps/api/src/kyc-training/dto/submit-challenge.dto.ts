import { IsString, MaxLength, MinLength } from 'class-validator';

export class SubmitChallengeDto {
  /** What the candidate typed after reading the number. */
  @IsString()
  @MinLength(1, { message: 'Enter your answer.' })
  @MaxLength(20, { message: 'That answer is too long.' })
  answer: string;
}
