import { Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';

@Injectable()
export class VacanciesService {
  constructor(private readonly prisma: PrismaService) {}

  /**
   * Open vacancies for the home screen. Public — this is the advertisement
   * that brings candidates in, so it must render before anyone logs in.
   * `salaryMonthlyPaise` is a BigInt in the database; JSON has no BigInt, so
   * it is converted to a number of rupees here rather than blowing up the
   * serializer.
   */
  async listOpen() {
    const vacancies = await this.prisma.vacancy.findMany({
      where: { status: 'OPEN' },
      orderBy: [{ state: 'asc' }, { tier: 'asc' }],
    });

    return vacancies.map((v: any) => ({
      id: v.id,
      title: v.title,
      state: v.state,
      tier: v.tier,
      postCount: v.postCount,
      salaryMonthlyRupees: Number(v.salaryMonthlyPaise) / 100,
      status: v.status,
    }));
  }
}
