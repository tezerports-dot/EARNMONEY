import { Injectable, Logger } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { ContentService } from './content.service';

export type DeliveryOutcome = 'delivered' | 'already-delivered' | 'no-content' | 'user-gone';

/**
 * Applies one account's daily update.
 *
 * This is the idempotency boundary for the whole scheduled system. The write
 * is a single conditional UPDATE:
 *
 *     UPDATE user_update_states
 *        SET delivered_version = $version ...
 *      WHERE user_id = $user AND delivered_version < $version
 *
 * Because the guard is inside the same statement that writes, two workers
 * racing on the same account cannot both deliver: Postgres serialises the row
 * and the loser's `WHERE` no longer matches, so it reports 0 rows updated and
 * returns `already-delivered`. There is no read-then-write window to lose.
 *
 * That is also why redelivery after a crash is safe — replaying a slot that
 * was half-processed re-runs this statement, and the already-done accounts
 * simply no-op.
 */
@Injectable()
export class ContentDeliveryService {
  private readonly logger = new Logger(ContentDeliveryService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly content: ContentService,
  ) {}

  async deliver(userId: string, version: number): Promise<DeliveryOutcome> {
    // Served from Redis; Postgres is not touched for content on this path.
    const content = await this.content.getCurrent();
    if (!content) return 'no-content';

    // Deliver the version the job was created for, unless content has moved on
    // — then deliver the newer one, since it supersedes it anyway.
    const targetVersion = Math.max(version, content.version);

    // Ensure a state row exists without clobbering an existing one. The unique
    // constraint on user_id makes the concurrent case safe.
    const existing = await this.prisma.userUpdateState.findUnique({ where: { userId } });
    if (!existing) {
      const user = await this.prisma.user.findUnique({ where: { id: userId }, select: { id: true } });
      if (!user) return 'user-gone';
      try {
        await this.prisma.userUpdateState.create({
          data: { userId, deliveredVersion: targetVersion, deliveredAt: new Date() },
        });
        return 'delivered';
      } catch {
        // Another worker created it first; fall through to the conditional
        // update, which resolves the race correctly.
      }
    }

    const result = await this.prisma.userUpdateState.updateMany({
      where: { userId, deliveredVersion: { lt: targetVersion } },
      data: {
        deliveredVersion: targetVersion,
        deliveredAt: new Date(),
        failureCount: 0,
        lastError: null,
      },
    });

    return result.count > 0 ? 'delivered' : 'already-delivered';
  }

  /** Records a failed attempt for observability; never throws. */
  async recordFailure(userId: string, error: string): Promise<void> {
    try {
      await this.prisma.userUpdateState.updateMany({
        where: { userId },
        data: { failureCount: { increment: 1 }, lastError: error.slice(0, 500) },
      });
    } catch (err) {
      this.logger.warn(`could not record failure for ${userId}: ${err}`);
    }
  }
}
