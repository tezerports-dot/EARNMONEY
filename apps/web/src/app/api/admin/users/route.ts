import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { prisma } from '@platform/database';
import { getAdminFromRequest } from '@/lib/auth';

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get('q')?.trim();
  const statusFilter = req.nextUrl.searchParams.get('status');

  const users = await prisma.user.findMany({
    where: {
      AND: [
        q
          ? {
              OR: [
                { referralCode: { contains: q, mode: 'insensitive' } },
                { telegramUsername: { contains: q, mode: 'insensitive' } },
                { phoneNumber: { contains: q } },
              ],
            }
          : {},
        statusFilter ? { status: statusFilter as never } : {},
      ],
    },
    orderBy: { createdAt: 'desc' },
    take: 100,
    select: {
      id: true,
      telegramId: true,
      telegramUsername: true,
      referralCode: true,
      status: true,
      fraudScore: true,
      createdAt: true,
      activatedAt: true,
    },
  });

  return NextResponse.json({
    users: users.map((u) => ({ ...u, telegramId: u.telegramId.toString() })),
  });
}

const actionSchema = z.object({
  userId: z.string().min(1),
  action: z.enum(['SUSPEND', 'UNSUSPEND']),
});

export async function POST(req: NextRequest) {
  const admin = getAdminFromRequest(req);
  const parsed = actionSchema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: 'Invalid request.' }, { status: 400 });
  }

  const { userId, action } = parsed.data;
  const newStatus = action === 'SUSPEND' ? 'SUSPENDED' : 'ACTIVE';

  const user = await prisma.user.update({ where: { id: userId }, data: { status: newStatus } });

  await prisma.auditLog.create({
    data: {
      adminId: admin?.sub,
      action: `USER_${action}`,
      targetType: 'User',
      targetId: user.id,
    },
  });

  return NextResponse.json({ ok: true, user: { ...user, telegramId: user.telegramId.toString() } });
}
