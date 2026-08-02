import 'dotenv/config';
import { prisma } from '@platform/database';
import { hashPassword } from '../src/lib/auth';

async function main() {
  const username = process.env.ADMIN_USERNAME;
  const password = process.env.ADMIN_PASSWORD;
  if (!username || !password) {
    throw new Error('Set ADMIN_USERNAME and ADMIN_PASSWORD in your .env file before seeding.');
  }

  const existing = await prisma.adminUser.findUnique({ where: { username } });
  if (existing) {
    console.log(`Admin "${username}" already exists — skipping.`);
    return;
  }

  const passwordHash = await hashPassword(password);
  await prisma.adminUser.create({
    data: { username, passwordHash, role: 'SUPER_ADMIN' },
  });
  console.log(`Created admin user "${username}". You can now log in at /admin/login.`);
}

main()
  .catch((err) => {
    console.error(err);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
