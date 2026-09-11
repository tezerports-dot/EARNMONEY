import { BadRequestException, Injectable, Logger, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { AuditLogService } from '../audit/audit-log.service';
import { CONFIG_KEYS, SystemConfigService } from '../system-config/system-config.service';

/**
 * Admin-editable operating thresholds.
 *
 * These were always stored in `system_config` rather than hardcoded, but there
 * was no way to change them without direct database access. This is that way.
 *
 * The important part is `assertReachable()`. The KYC challenge target is the
 * number of DISTINCT scenarios a candidate must pass, and
 * `issueNextChallenge()` never re-issues one they have already passed. So if
 * the target is ever higher than the number of active scenarios, every
 * candidate runs out of material partway and can never finish — the funnel
 * dead-ends silently, and nobody finds out until users complain.
 *
 * This service refuses to store such a value. The constraint is enforced here
 * rather than documented, because a target of 200 against 5 scenarios looks
 * perfectly reasonable in a form field.
 */
@Injectable()
export class AdminConfigService {
  private readonly logger = new Logger(AdminConfigService.name);

  /** Keys an admin may change, with the context needed to change them safely. */
  private static readonly EDITABLE = {
    [CONFIG_KEYS.REFERRAL_THRESHOLD]: {
      label: 'Verified referrals required',
      description:
        'Credited referrals a candidate needs before they may apply. A referral counts only once that person completes their own verification.',
      fallback: 200,
    },
    [CONFIG_KEYS.KYC_CHALLENGE_THRESHOLD]: {
      label: 'KYC training challenges required',
      description:
        'Distinct practice documents a candidate must review correctly. Cannot exceed the number of active scenarios, or candidates run out of material and can never finish.',
      fallback: 200,
    },
    [CONFIG_KEYS.FRAUD_STRIKE_LIMIT]: {
      label: 'Fake referrals before suspension',
      description:
        'Confirmed fake referrals a candidate may accumulate before the account is suspended.',
      fallback: 8,
    },
    [CONFIG_KEYS.KYC_REJECTION_ATTEMPTS]: {
      label: 'Rejections before a referral is confirmed fake',
      description:
        'Independent verification rejections needed before a referred account counts as fraud against its referrer.',
      fallback: 3,
    },
    [CONFIG_KEYS.REFERRAL_ATTRIBUTION_WINDOW_DAYS]: {
      label: 'Referral attribution window (days)',
      description: 'How long after signup a referral can still be credited.',
      fallback: 30,
    },
  } as const;

  constructor(
    private readonly prisma: PrismaService,
    private readonly systemConfig: SystemConfigService,
    private readonly audit: AuditLogService,
  ) {}

  /** Current values plus the limits that constrain them. */
  async listSettings() {
    const [rows, activeScenarios] = await Promise.all([
      this.prisma.systemConfig.findMany(),
      this.prisma.kycTrainingScenario.count({ where: { isActive: true } }),
    ]);
    const byKey = new Map(rows.map((r: { key: string; value: unknown }) => [r.key, r.value]));

    return {
      settings: Object.entries(AdminConfigService.EDITABLE).map(([key, meta]) => ({
        key,
        label: meta.label,
        description: meta.description,
        value: (byKey.get(key) as number) ?? meta.fallback,
        // Surfaced so an admin can see WHY a value is capped before they try it.
        max:
          key === CONFIG_KEYS.KYC_CHALLENGE_THRESHOLD ? activeScenarios : undefined,
      })),
      context: {
        activeScenarios,
        note:
          'The KYC challenge target cannot exceed the number of active scenarios. Add scenarios first, then raise the target.',
      },
    };
  }

  async update(key: string, value: number, actorUserId: string) {
    const meta = (AdminConfigService.EDITABLE as Record<string, { label: string } | undefined>)[key];
    if (!meta) {
      // Allow-list, not deny-list: an unknown key must not silently create a
      // config row that nothing reads.
      throw new NotFoundException(`'${key}' is not an editable setting.`);
    }

    await this.assertReachable(key, value);

    const previous = await this.systemConfig.get<number | null>(key, null);
    await this.systemConfig.set(key, value, actorUserId);

    await this.audit.record({
      actorUserId,
      action: 'SYSTEM_CONFIG_UPDATED',
      entityType: 'SystemConfig',
      entityId: key,
      metadata: { key, previous, value },
    });

    this.logger.log(`${key}: ${previous} -> ${value} (by ${actorUserId})`);
    return { key, previous, value };
  }

  /**
   * Blocks values that would strand candidates. Currently only the KYC target
   * has a hard ceiling, because it is the only one bounded by content the
   * institute has to author.
   */
  private async assertReachable(key: string, value: number): Promise<void> {
    if (key !== CONFIG_KEYS.KYC_CHALLENGE_THRESHOLD) return;

    const activeScenarios = await this.prisma.kycTrainingScenario.count({
      where: { isActive: true },
    });

    if (value > activeScenarios) {
      throw new BadRequestException(
        `Cannot require ${value} challenges: only ${activeScenarios} active scenario(s) exist. ` +
          `A candidate is never shown a scenario twice, so they would run out after ${activeScenarios} ` +
          `and could never become eligible. Add more scenarios first, or set the target to ${activeScenarios} or fewer.`,
      );
    }
  }
}
