import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { prisma } from '@platform/database';
import { verifyPassword, signAdminToken, ADMIN_COOKIE_NAME } from '@/lib/auth';

const bodySchema = z.object({
  username: z.string().min(1),
  password: z.string().min(1),
});

export async function POST(req: NextRequest) {
  const parsed = bodySchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: 'Username and password are required.' }, { status: 400 });
  }

  const admin = await prisma.adminUser.findUnique({ where: { username: parsed.data.username } });
  if (!admin) {
    return NextResponse.json({ error: 'Invalid username or password.' }, { status: 401 });
  }

  const ok = await verifyPassword(parsed.data.password, admin.passwordHash);
  if (!ok) {
    return NextResponse.json({ error: 'Invalid username or password.' }, { status: 401 });
  }

  await prisma.adminUser.update({ where: { id: admin.id }, data: { lastLoginAt: new Date() } });
  await prisma.auditLog.create({
    data: { adminId: admin.id, action: 'ADMIN_LOGIN', targetType: 'AdminUser', targetId: admin.id },
  });

  const token = signAdminToken({ sub: admin.id, username: admin.username, role: admin.role });

  const res = NextResponse.json({ ok: true });
  res.cookies.set(ADMIN_COOKIE_NAME, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/',
    maxAge: 60 * 60 * 12,
  });
  return res;
}
