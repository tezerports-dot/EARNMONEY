import { BadRequestException, Injectable, Logger, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { AuditLogService } from '../audit/audit-log.service';
import { SystemConfigService } from '../system-config/system-config.service';
import { CreateScenarioDto } from './dto/create-scenario.dto';

/**
 * The KYC practice-document bank.
 *
 * This is the supply side of the challenge target: the target can only be
 * raised as far as there are scenarios to meet it, so adding scenarios here is
 * what unlocks a higher number in admin config.
 *
 * Every document stored here is fictitious and authored by the institute. The
 * skill being tested — spotting a mismatch or a tampered field on a customer's
 * KYC document — is ordinary regulated work; practising it on invented
 * documents is what keeps that legitimate.
 */
@Injectable()
export class AdminScenariosService {
  private readonly logger = new Logger(AdminScenariosService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly systemConfig: SystemConfigService,
    private readonly audit: AuditLogService,
  ) {}

  async list() {
    const [scenarios, threshold] = await Promise.all([
      this.prisma.kycTrainingScenario.findMany({
        orderBy: { createdAt: 'desc' },
        select: {
          id: true,
          title: true,
          difficulty: true,
          isActive: true,
          createdAt: true,
          expectedOutcome: true,
          _count: { select: { attempts: true } },
        },
      }),
      this.systemConfig.getKycChallengeThreshold(),
    ]);

    const active = scenarios.filter((s) => s.isActive).length;
    return {
      scenarios,
      summary: {
        total: scenarios.length,
        active,
        currentTarget: threshold,
        // Scenarios repeat, so the target is always reachable. What this tells
        // an admin is how much repetition candidates will see: a target of 200
        // against 5 scenarios means each document comes round about 40 times.
        averageRepeatsPerScenario: active > 0 ? Math.round((threshold / active) * 10) / 10 : null,
      },
    };
  }

  async create(dto: CreateScenarioDto, actorUserId: string) {
    if (Object.keys(dto.syntheticDocument).length === 0) {
      throw new BadRequestException('syntheticDocument must contain at least one field.');
    }
    // A fault scenario with no named issue cannot be graded: the candidate's
    // answer would be compared against `undefined` and could never match.
    if (dto.expectedOutcome.valid === false && !dto.expectedOutcome.issue) {
      throw new BadRequestException(
        'An invalid-document scenario must name the issue, so the answer can be graded.',
      );
    }

    const created = await this.prisma.kycTrainingScenario.create({
      data: {
        title: dto.title,
        syntheticDocument: dto.syntheticDocument,
        expectedOutcome: { valid: dto.expectedOutcome.valid, issue: dto.expectedOutcome.issue },
        difficulty: dto.difficulty ?? 'standard',
        isActive: true,
      },
    });

    await this.audit.record({
      actorUserId,
      action: 'KYC_SCENARIO_CREATED',
      entityType: 'KycTrainingScenario',
      entityId: created.id,
      metadata: { title: created.title },
    });

    this.logger.log(`scenario created: ${created.title}`);
    return created;
  }

  /**
   * Retiring a scenario can make the current target unreachable, so this
   * refuses rather than letting an admin strand every candidate with one
   * click. Raising the supply is safe; lowering it below demand is not.
   */
  async setActive(id: string, isActive: boolean, actorUserId: string) {
    const scenario = await this.prisma.kycTrainingScenario.findUnique({ where: { id } });
    if (!scenario) throw new NotFoundException('Scenario not found.');

    if (!isActive && scenario.isActive) {
      // Scenarios repeat, so the bank does not have to be as large as the
      // target — but it cannot be empty, or no challenge can be issued at all.
      const activeCount = await this.prisma.kycTrainingScenario.count({
        where: { isActive: true },
      });
      if (activeCount <= 1) {
        throw new BadRequestException(
          'This is the last active scenario. Retiring it would leave candidates with nothing to review. Add another first.',
        );
      }
    }

    const updated = await this.prisma.kycTrainingScenario.update({
      where: { id },
      data: { isActive },
    });

    await this.audit.record({
      actorUserId,
      action: isActive ? 'KYC_SCENARIO_ACTIVATED' : 'KYC_SCENARIO_RETIRED',
      entityType: 'KycTrainingScenario',
      entityId: id,
    });

    return updated;
  }
}
