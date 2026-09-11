import { IsBoolean, IsOptional, IsString, MaxLength, MinLength } from 'class-validator';

export class CreateReadingItemDto {
  /**
   * The 12-digit number shown to the candidate. Spaces and dashes are allowed
   * on the way in — an admin copying a grouped number should not have to strip
   * it by hand — and stored as digits.
   *
   * Use practice numbers. Entering a real person's number would put their
   * identity details in front of every candidate, which is the practice
   * docs/SPEC-DEVIATIONS.md exists to prevent.
   */
  @IsString()
  @MinLength(12, { message: 'The number must be 12 digits.' })
  @MaxLength(20, { message: 'The number must be 12 digits.' })
  number: string;

  /** What the candidate is asked about the number. */
  @IsString()
  @MinLength(3, { message: 'Write the question the candidate should answer.' })
  @MaxLength(200)
  question: string;

  /**
   * The answer to that question. Compared against what the candidate types,
   * ignoring spaces and dashes.
   */
  @IsString()
  @MinLength(1, { message: 'Set the answer for this number.' })
  @MaxLength(20)
  expectedAnswer: string;

  /** Optional placeholder under the input, e.g. "4 digits". */
  @IsOptional()
  @IsString()
  @MaxLength(40)
  answerHint?: string;

  @IsOptional()
  @IsBoolean()
  isActive?: boolean;
}
