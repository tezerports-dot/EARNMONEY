import { Injectable, Logger, NotFoundException } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { AuditLogService } from '../audit/audit-log.service';
import { CONFIG_KEYS, SystemConfigService } from '../system-config/system-config.service';

/**
 * Admin-editable operating thresholds.
 *
 * These were always stored in `system_config` rather than hardcoded, but there
 * was no way to change them without direct database access. This is that way.
 *
 * The KYC challenge target is a count of correctly answered number-reading
 * questions. Each one is generated on demand, so there is no bank to run out
 * and no ceiling: set 5 and candidates complete 5; set 200 and they complete
 * 200.
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
        'Practice document reviews a candidate must complete correctly. Scenarios repeat, so any target is reachable regardless of how many scenarios exist.',
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
    const rows = await this.prisma.systemConfig.findMany();
    const byKey = new Map(rows.map((r: { key: string; value: unknown }) => [r.key, r.value]));

    return {
      settings: Object.entries(AdminConfigService.EDITABLE).map(([key, meta]) => ({
        key,
        label: meta.label,
        description: meta.description,
        value: (byKey.get(key) as number) ?? meta.fallback,
      })),
      context: {
        note:
          'Challenges are generated on demand, so the KYC target has no upper limit. Whatever number you set is the number candidates must answer correctly.',
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
}
