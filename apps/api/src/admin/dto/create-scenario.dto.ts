import { Type } from 'class-transformer';
import {
  IsBoolean,
  IsIn,
  IsObject,
  IsOptional,
  IsString,
  MaxLength,
  MinLength,
  ValidateNested,
} from 'class-validator';

class ExpectedOutcomeDto {
  /** True when the document is clean and the candidate should accept it. */
  @IsBoolean()
  valid: boolean;

  /**
   * The specific fault, when `valid` is false. Graded against the candidate's
   * answer, so it must match the vocabulary the app offers.
   */
  @IsOptional()
  @IsString()
  @MaxLength(100)
  issue?: string;
}

export class CreateScenarioDto {
  @IsString()
  @MinLength(3)
  @MaxLength(200)
  title: string;

  /**
   * The fictitious document the candidate reviews. Free-form key/value so new
   * document types need no schema change.
   *
   * MUST be synthetic. Putting a real person's details here would recreate
   * exactly the practice docs/SPEC-DEVIATIONS.md exists to prevent.
   */
  @IsObject()
  syntheticDocument: Record<string, string>;

  @ValidateNested()
  @Type(() => ExpectedOutcomeDto)
  expectedOutcome: ExpectedOutcomeDto;

  @IsOptional()
  @IsIn(['easy', 'standard', 'hard'])
  difficulty?: string;
}
