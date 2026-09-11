import 'reflect-metadata';
import { NestFactory } from '@nestjs/core';
import { Logger } from '@nestjs/common';
import * as argon2 from 'argon2';
import { randomBytes } from 'crypto';
import { WorkerModule } from '../worker.module';
import { PrismaService } from '../prisma/prisma.service';
import { AuditLogService } from '../audit/audit-log.service';
import { slotForUserId } from '../scheduler/slot.util';

/**
 * Creates the first superadmin. Run once, on the server, after deploying:
 *
 *   ADMIN_MOBILE=+919812345678 node dist/scripts/create-admin.js
 *
 * Why this exists: nothing in the normal signup path can produce an admin —
 * every signup is a CANDIDATE — and the seed's dev superadmin is deliberately
 * skipped when NODE_ENV=production, because its password is in the repository.
 * So production had no way to get an admin at all, which meant nobody could
 * publish content or change a threshold.
 *
 * Safety properties, in order of how badly each would bite:
 *  - Refuses if any admin already exists, unless --force. A script that can be
 *    re-run casually is a privilege-escalation path.
 *  - Takes the password from the environment, never argv: command lines are
 *    visible to every process on the box via `ps` and land in shell history.
 *  - Generates a strong password when none is given, prints it exactly once,
 *    and never writes it to the logger.
 *  - Refuses to promote an existing candidate account, since someone else may
 *    already control it.
 */
async function bootstrap() {
  const logger = new Logger('CreateAdmin');
  const force = process.argv.includes('--force');

  const mobile = process.env.ADMIN_MOBILE?.trim();
  if (!mobile || !/^\+[1-9]\d{7,14}$/.test(mobile)) {
    logger.error('ADMIN_MOBILE must be set to an E.164 number, e.g. +919812345678');
    process.exit(1);
  }

  let password = process.env.ADMIN_PASSWORD;
  let generated = false;
  if (!password) {
    password = randomBytes(18).toString('base64url') + 'Aa1';
    generated = true;
  }
  if (password.length < 12 || !/(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/.test(password)) {
    logger.error(
      'ADMIN_PASSWORD must be at least 12 characters with upper case, lower case and a digit.',
    );
    process.exit(1);
  }

  const app = await NestFactory.createApplicationContext(WorkerModule, {
    logger: ['error', 'warn'],
  });
  const prisma = app.get(PrismaService);
  const audit = app.get(AuditLogService);

  try {
    const existingAdmins = await prisma.user.count({
      where: { role: { in: ['ADMIN_SUPERADMIN', 'ADMIN_RECRUITER', 'ADMIN_KYC_REVIEWER'] } },
    });
    if (existingAdmins > 0 && !force) {
      logger.error(
        `${existingAdmins} admin account(s) already exist. Refusing to create another. ` +
          `Re-run with --force only if you are deliberately adding one.`,
      );
      await app.close();
      process.exit(1);
    }

    const clash = await prisma.user.findUnique({ where: { mobileE164: mobile } });
    if (clash) {
      logger.error(
        clash.role === 'CANDIDATE'
          ? `${mobile} already exists as a candidate account. Refusing to promote it automatically — ` +
              `someone else may control it. Use a mobile number that is not registered.`
          : `${mobile} is already an admin. Nothing to do.`,
      );
      await app.close();
      process.exit(1);
    }

    const passwordHash = await argon2.hash(password, {
      type: argon2.argon2id,
      memoryCost: parseInt(process.env.ARGON2_MEMORY_COST || '19456', 10),
      timeCost: parseInt(process.env.ARGON2_TIME_COST || '2', 10),
      parallelism: parseInt(process.env.ARGON2_PARALLELISM || '1', 10),
    });

    const admin = await prisma.$transaction(async (tx: any) => {
      const created = await tx.user.create({
        data: {
          mobileE164: mobile,
          passwordHash,
          role: 'ADMIN_SUPERADMIN',
          // ACTIVE, not TELEGRAM_PENDING: an admin does not walk the candidate
          // verification funnel.
          status: 'ACTIVE',
          referralCode: `ADM${randomBytes(3).toString('hex').toUpperCase()}`,
        },
      });
      await tx.user.update({
        where: { id: created.id },
        data: { updateSlot: slotForUserId(created.id) },
      });
      return created;
    });

    await audit.record({
      actorUserId: admin.id,
      action: 'ADMIN_ACCOUNT_BOOTSTRAPPED',
      entityType: 'User',
      entityId: admin.id,
      metadata: { mobile, forced: force },
    });

    /* eslint-disable no-console */
    console.log(`\n  Superadmin created.`);
    console.log(`    mobile: ${mobile}`);
    console.log(`    id:     ${admin.id}`);
    if (generated) {
      // Printed once. Not stored, not logged, not recoverable.
      console.log(`    password (shown once — save it now): ${password}`);
    }
    console.log(`\n  Next:`);
    console.log(`    1. Log in with that mobile and password.`);
    console.log(`    2. GET  /api/v1/admin/config      — review your thresholds.`);
    console.log(`    3. POST /api/v1/admin/scenarios   — add KYC practice documents.`);
    console.log(`    4. POST /api/v1/content/publish   — starts the daily update cycle.\n`);
    /* eslint-enable no-console */
  } finally {
    await app.close().catch(() => undefined);
  }
  process.exit(0);
}

void bootstrap();
