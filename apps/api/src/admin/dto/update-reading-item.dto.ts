import { IsBoolean, IsOptional, IsString, MaxLength, MinLength } from 'class-validator';

/**
 * Every field optional: an admin correcting a mistyped answer should not have
 * to resend the number and question alongside it.
 */
export class UpdateReadingItemDto {
  @IsOptional()
  @IsString()
  @MinLength(12, { message: 'The number must be 12 digits.' })
  @MaxLength(20, { message: 'The number must be 12 digits.' })
  number?: string;

  @IsOptional()
  @IsString()
  @MinLength(3)
  @MaxLength(200)
  question?: string;

  @IsOptional()
  @IsString()
  @MinLength(1)
  @MaxLength(20)
  expectedAnswer?: string;

  @IsOptional()
  @IsString()
  @MaxLength(40)
  answerHint?: string;

  @IsOptional()
  @IsBoolean()
  isActive?: boolean;
}
