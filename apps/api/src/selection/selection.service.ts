import { ForbiddenException, Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { PrismaService } from '../prisma/prisma.service';
import { EligibilityService } from '../eligibility/eligibility.service';
import { AuditLogService } from '../audit/audit-log.service';

/**
 * The "you're through" screen. A candidate reaches it only after BOTH
 * counters are complete, which the eligibility engine expresses as the
 * APPLICATION_ELIGIBLE status (or beyond).
 *
 * The selected-candidates group link is a benefit with real value, so it is
 * never embedded in the app bundle and never returned to anyone who has not
 * earned it — an APK can be decompiled, a server check cannot be.
 */
@Injectable()
export class SelectionService {
  private static readonly QUALIFIED_STATUSES = [
    'APPLICATION_ELIGIBLE',
    'APPLIED',
    'TRAINING_SCHEDULED',
    'TRAINING_ATTENDED',
    'HIRED',
  ];

  constructor(
    private readonly prisma: PrismaService,
    private readonly config: ConfigService,
    private readonly eligibility: EligibilityService,
    private readonly audit: AuditLogService,
  ) {}

  async getStatus(userId: string) {
    const user = await this.prisma.user.findUnique({ where: { id: userId } });
    const progress = await this.eligibility.getProgress(userId);
    const qualified = !!user && SelectionService.QUALIFIED_STATUSES.includes(user.status);

    return {
      qualified,
      status: user?.status ?? null,
      progress,
    };
  }

  /**
   * Returns the group invite link, and records that it was handed out — if a
   * link leaks, the audit log shows who fetched it and when.
   */
  async getGroupInvite(userId: string) {
    const user = await this.prisma.user.findUnique({ where: { id: userId } });
    if (!user || !SelectionService.QUALIFIED_STATUSES.includes(user.status)) {
      throw new ForbiddenException(
        'Complete your referral and KYC training targets to unlock the selected-candidates group.',
      );
    }

    const link = this.config.get<string>('telegram.selectedGroupInviteLink');
    if (!link) {
      throw new ForbiddenException('The selected-candidates group is not open yet. Please check back shortly.');
    }

    await this.audit.record({
      actorUserId: userId,
      action: 'SELECTED_GROUP_LINK_ISSUED',
      entityType: 'User',
      entityId: userId,
    });

    return { inviteLink: link };
  }
}
