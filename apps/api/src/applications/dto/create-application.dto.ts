import { IsIn, IsOptional, IsString } from 'class-validator';

// Keep this list in sync with the states/tiers your vacancies actually use.
const STATES = ['Rajasthan', 'Uttar Pradesh', 'Gujarat', 'Madhya Pradesh', 'Maharashtra'] as const;
const TIERS = ['tier1', 'tier2', 'tier3'] as const;

export class CreateApplicationDto {
  @IsIn(STATES)
  statePreference: (typeof STATES)[number];

  @IsIn(TIERS)
  tierPreference: (typeof TIERS)[number];

  @IsOptional()
  @IsString()
  districtPreference?: string;
}
