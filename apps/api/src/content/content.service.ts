import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { PrismaService } from '../prisma/prisma.service';
import { CacheService, cacheKeys } from '../cache/cache.service';

export type CurrentContent = {
  version: number;
  title: string;
  body: string;
  linkUrl: string | null;
  publishedAt: string;
};

/**
 * The text/link payload every account receives once a day.
 *
 * Why this is cached rather than read per update: at 2.9M accounts the daily
 * fan-out would otherwise issue 2.9M identical `SELECT ... WHERE is_current`
 * queries against Postgres purely to read one unchanging row. Cached, it is
 * roughly 288 reads a day (one per TTL expiry) regardless of user count — the
 * single highest-leverage cache in the system.
 *
 * Postgres remains the source of truth: every miss falls through to it, and a
 * total Redis outage only costs latency.
 */
@Injectable()
export class ContentService {
  private readonly logger = new Logger(ContentService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly cache: CacheService,
    private readonly config: ConfigService,
  ) {}

  async getCurrent(): Promise<CurrentContent | null> {
    const ttl = this.config.get<number>('cache.contentTtlSeconds')!;
    if (!this.config.get<boolean>('cache.enabled')) return this.loadCurrentFromDb();

    return this.cache.getOrSet<CurrentContent | null>(cacheKeys.currentContent(), ttl, () =>
      this.loadCurrentFromDb(),
    );
  }

  private async loadCurrentFromDb(): Promise<CurrentContent | null> {
    const row = await this.prisma.contentVersion.findFirst({
      where: { isCurrent: true },
      orderBy: { version: 'desc' },
    });
    if (!row) return null;
    return {
      version: row.version,
      title: row.title,
      body: row.body,
      linkUrl: row.linkUrl,
      publishedAt: row.publishedAt.toISOString(),
    };
  }

  /**
   * Publishes a new version and invalidates the cache.
   *
   * Invalidation is explicit rather than TTL-only so a newly published update
   * goes out on the next slot instead of up to one TTL later.
   */
  async publish(input: { title: string; body: string; linkUrl?: string }): Promise<CurrentContent> {
    const latest = await this.prisma.contentVersion.findFirst({ orderBy: { version: 'desc' } });
    const nextVersion = (latest?.version ?? 0) + 1;

    const created = await this.prisma.$transaction(async (tx: any) => {
      await tx.contentVersion.updateMany({ where: { isCurrent: true }, data: { isCurrent: false } });
      return tx.contentVersion.create({
        data: {
          version: nextVersion,
          title: input.title,
          body: input.body,
          linkUrl: input.linkUrl ?? null,
          isCurrent: true,
        },
      });
    });

    await this.cache.del(cacheKeys.currentContent());
    this.logger.log(`Published content version ${nextVersion}.`);

    return {
      version: created.version,
      title: created.title,
      body: created.body,
      linkUrl: created.linkUrl,
      publishedAt: created.publishedAt.toISOString(),
    };
  }

  /** What a candidate's app shows — their own delivery state plus the content. */
  async getForUser(userId: string) {
    const [content, state] = await Promise.all([
      this.getCurrent(),
      this.prisma.userUpdateState.findUnique({ where: { userId } }),
    ]);
    return {
      content,
      deliveredVersion: state?.deliveredVersion ?? 0,
      deliveredAt: state?.deliveredAt?.toISOString() ?? null,
      /** True when this account's daily update has landed for the current version. */
      upToDate: !!content && (state?.deliveredVersion ?? 0) >= content.version,
    };
  }
}
