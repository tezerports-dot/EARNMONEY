import { Injectable } from '@nestjs/common';
import { Prisma } from '@prisma/client';
import { createHash } from 'crypto';
import { PrismaService } from '../prisma/prisma.service';

export interface RecordAuditEventInput {
  actorUserId?: string | null;
  action: string;
  entityType: string;
  entityId?: string | null;
  metadata?: Record<string, unknown>;
  ip?: string | null;
}

@Injectable()
export class AuditLogService {
  constructor(private readonly prisma: PrismaService) {}

  /**
   * Records an audit event. IP addresses are hashed, never stored raw.
   * Never pass secrets, passwords, OTPs, or full identity values in metadata —
   * this is not enforced automatically here, so callers are responsible
   * (see Agent Rule 15 in 07-AGENT-RULES.md).
   */
  async record(input: RecordAuditEventInput): Promise<void> {
    await this.prisma.auditLog.create({
      data: {
        actorUserId: input.actorUserId ?? null,
        action: input.action,
        entityType: input.entityType,
        entityId: input.entityId ?? null,
        metadata: (input.metadata ?? {}) as Prisma.InputJsonObject,
        ipHash: input.ip ? this.hashIp(input.ip) : null,
      },
    });
  }

  private hashIp(ip: string): string {
    return createHash('sha256').update(ip).digest('hex');
  }
}
