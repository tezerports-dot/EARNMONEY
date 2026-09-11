import { Controller, Get } from '@nestjs/common';
import { Throttle } from '@nestjs/throttler';
import { VacanciesService } from './vacancies.service';

@Controller('vacancies')
export class VacanciesController {
  constructor(private readonly vacancies: VacanciesService) {}

  /** Public: the home screen must work for a visitor who has not signed up. */
  @Get()
  @Throttle({ default: { limit: 60, ttl: 60_000 } })
  async list() {
    return { vacancies: await this.vacancies.listOpen() };
  }
}
