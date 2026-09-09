import { Injectable, Logger, ConflictException } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { ReferralsService } from '../referrals/referrals.service';
import { AuditLogService } from '../audit/audit-log.service';

@Injectable()
export class UsersService {
  private readonly logger = new Logger(UsersService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly referrals: ReferralsService,
    private readonly audit: AuditLogService,
  ) {}

  /**
   * Called by the identity-verification and Telegram modules (stage 3) once
   * a user has completed: identity verification -> Telegram connected ->
   * required group(s) joined. This is the ONLY place a user becomes ACTIVE —
   * do not set that status anywhere else, so this stays the single source of
   * truth for "this account is real and reachable."
   */
  async activateUser(userId: string): Promise<void> {
    const user = await this.prisma.user.findUnique({ where: { id: userId } });
    if (!user) {
      throw new ConflictException('User not found.');
    }
    if (user.status === 'ACTIVE' || user.status === 'REFERRAL_IN_PROGRESS' || user.status === 'APPLICATION_ELIGIBLE') {
      return; // already activated — idempotent
    }
    if (user.status !== 'GROUP_PENDING') {
      this.logger.warn(`activateUser called for ${userId} from unexpected status ${user.status}`);
    }

    await this.prisma.user.update({ where: { id: userId }, data: { status: 'ACTIVE' } });

    await this.audit.record({
      actorUserId: userId,
      action: 'USER_ACTIVATED',
      entityType: 'User',
      entityId: userId,
    });

    // If someone referred this user, this is the moment that referral
    // becomes real (not just a signup) — credit it and re-check the
    // referrer's own eligibility.
    await this.referrals.creditReferralIfEligible(userId);
  }

  /**
   * Called by the identity module once a provider confirms verification.
   * Moves the candidate on to the Telegram-binding step.
   */
  async markIdentityVerified(userId: string): Promise<void> {
    const user = await this.prisma.user.findUnique({ where: { id: userId } });
    if (!user) return;
    if (!['REGISTERED', 'IDENTITY_PENDING'].includes(user.status)) {
      return; // already past this step, or in a state this shouldn't touch — idempotent no-op
    }

    await this.prisma.user.update({ where: { id: userId }, data: { status: 'TELEGRAM_PENDING' } });
    await this.audit.record({
      actorUserId: userId,
      action: 'IDENTITY_VERIFIED',
      entityType: 'User',
      entityId: userId,
    });
  }

  /** Called by the identity module if a provider rejects verification. */
  async markIdentityRejected(userId: string, reasonCode?: string): Promise<void> {
    await this.prisma.user.update({ where: { id: userId }, data: { status: 'KYC_REJECTED' } });
    await this.audit.record({
      actorUserId: userId,
      action: 'IDENTITY_REJECTED',
      entityType: 'User',
      entityId: userId,
      metadata: { reasonCode },
    });
  }

  /**
   * Called by the Telegram module once account binding + required group
   * membership are both confirmed.
   */
  async markTelegramVerified(userId: string): Promise<void> {
    const user = await this.prisma.user.findUnique({ where: { id: userId } });
    if (!user || user.status !== 'GROUP_PENDING') return;
    await this.activateUser(userId);
  }
}
