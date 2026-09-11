import { Injectable, Logger, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { PrismaClient } from '@prisma/client';

/**
 * Prisma client with an explicit, role-aware connection pool.
 *
 * Why this matters more than it looks: Prisma's default pool is
 * `num_cpus * 2 + 1` per process. Run four containers on an 8-core box and you
 * have silently asked Postgres for 68 connections — past the default
 * `max_connections` of 100 once autovacuum and psql sessions are counted, at
 * which point signup starts failing with "too many connections" during a
 * routine update cycle.
 *
 * So the pool is set explicitly and differs by role:
 *   API    — DB_POOL_API    (default 10). Protects interactive traffic.
 *   WORKER — DB_POOL_WORKER (default 5).  Background work gets less, on purpose.
 *
 * The invariant to hold when scaling:
 *   (api_replicas x DB_POOL_API) + (worker_replicas x DB_POOL_WORKER)
 *     + headroom(~10) <= postgres max_connections
 */
@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  private static readonly logger = new Logger(PrismaService.name);

  constructor() {
    super({ datasources: { db: { url: PrismaService.buildUrl() } } });
  }

  /**
   * Appends pool parameters to DATABASE_URL. Prisma takes them from the
   * connection string, so this is the only place they can be set.
   */
  private static buildUrl(): string {
    const base = process.env.DATABASE_URL;
    if (!base) throw new Error('DATABASE_URL is not set.');

    // PROCESS_ROLE is set by the container command: "api" or "worker".
    const role = process.env.PROCESS_ROLE === 'worker' ? 'worker' : 'api';
    const limit =
      role === 'worker'
        ? parseInt(process.env.DB_POOL_WORKER || '5', 10)
        : parseInt(process.env.DB_POOL_API || '10', 10);
    const timeout = parseInt(process.env.DB_POOL_TIMEOUT_SECONDS || '10', 10);

    try {
      const url = new URL(base);
      // Respect an explicit connection_limit already in the URL.
      if (!url.searchParams.has('connection_limit')) {
        url.searchParams.set('connection_limit', String(limit));
      }
      if (!url.searchParams.has('pool_timeout')) {
        url.searchParams.set('pool_timeout', String(timeout));
      }
      PrismaService.logger.log(
        `role=${role} connection_limit=${url.searchParams.get('connection_limit')} pool_timeout=${url.searchParams.get('pool_timeout')}s`,
      );
      return url.toString();
    } catch {
      // A malformed URL is Prisma's problem to report, not ours to mangle.
      return base;
    }
  }

  async onModuleInit() {
    await this.$connect();
  }

  async onModuleDestroy() {
    await this.$disconnect();
  }
}
