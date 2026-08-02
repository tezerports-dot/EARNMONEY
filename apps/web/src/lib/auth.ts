import jwt from 'jsonwebtoken';
import bcrypt from 'bcryptjs';
import { NextRequest } from 'next/server';
import type { JwtAdminPayload } from '@platform/shared';

const JWT_SECRET = process.env.JWT_SECRET;
if (!JWT_SECRET) {
  throw new Error('JWT_SECRET is required. Set it in your .env file.');
}

export const ADMIN_COOKIE_NAME = 'admin_session';

export function hashPassword(plain: string): Promise<string> {
  return bcrypt.hash(plain, 12);
}

export function verifyPassword(plain: string, hash: string): Promise<boolean> {
  return bcrypt.compare(plain, hash);
}

export function signAdminToken(payload: JwtAdminPayload): string {
  return jwt.sign(payload, JWT_SECRET!, { expiresIn: '12h' });
}

export function verifyAdminToken(token: string): JwtAdminPayload | null {
  try {
    return jwt.verify(token, JWT_SECRET!) as JwtAdminPayload;
  } catch {
    return null;
  }
}

export function getAdminFromRequest(req: NextRequest): JwtAdminPayload | null {
  const token = req.cookies.get(ADMIN_COOKIE_NAME)?.value;
  if (!token) return null;
  return verifyAdminToken(token);
}
