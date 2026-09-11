import { IsInt, Max, Min } from 'class-validator';

export class UpdateConfigDto {
  /**
   * Every tunable in this system is a positive integer count. Bounded at both
   * ends: 0 would make a target meaningless, and an absurd ceiling protects
   * against a fat-fingered value stranding the whole user base.
   */
  @IsInt({ message: 'value must be a whole number' })
  @Min(1, { message: 'value must be at least 1' })
  @Max(1_000_000, { message: 'value is implausibly large' })
  value: number;
}
