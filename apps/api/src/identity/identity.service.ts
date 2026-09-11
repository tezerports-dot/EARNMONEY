import { BadRequestException, Inject, Injectable, NotFoundException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { createHmac, timingSafeEqual } from 'crypto';
import { PrismaService } from '../prisma/prisma.service';
import { UsersService } from '../users/users.service';
import { AuditLogService } from '../audit/audit-log.service';
import { IdentityProvider } from './identity-provider.interface';
import { FraudService } from '../fraud/fraud.service';

@Injectable()
export class IdentityService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly users: UsersService,
    private readonly audit: AuditLogService,
    private readonly config: ConfigService,
    @Inject('IdentityProvider') private readonly provider: IdentityProvider,
    private readonly fraud: FraudService,
  ) {}

  async startVerification(userId: string) {
    const user = await this.prisma.user.findUnique({ where: { id: userId } });
    if (!user) throw new NotFoundException();
    if (!['REGISTERED', 'IDENTITY_PENDING'].includes(user.status)) {
      throw new BadRequestException('Identity verification is not applicable at this stage.');
    }

    const result = await this.provider.startVerification(userId);

    await this.prisma.identityVerification.upsert({
      where: { userId },
      update: { provider: 'default', providerReference: result.providerReference, status: 'PENDING' },
      create: {
        userId,
        provider: 'default',
        providerReference: result.providerReference,
        status: 'PENDING',
      },
    });

    if (user.status === 'REGISTERED') {
      await this.prisma.user.update({ where: { id: userId }, data: { status: 'IDENTITY_PENDING' } });
    }

    await this.audit.record({
      actorUserId: userId,
      action: 'IDENTITY_VERIFICATION_STARTED',
      entityType: 'IdentityVerification',
    });

    return { redirectUrl: result.redirectUrl, status: 'PENDING' as const };
  }

  async getMyStatus(userId: string) {
    const record = await this.prisma.identityVerification.findUnique({ where: { userId } });
    return record
      ? { status: record.status, failureReasonCode: record.failureReasonCode }
      : { status: 'NOT_STARTED' as const };
  }

  /**
   * Verifies the webhook came from the real provider before trusting
   * anything in the body. Real providers each have their own signature
   * scheme — this HMAC check is a reasonable default; adjust it to match
   * whichever vendor you actually contract with.
   */
  verifyWebhookSignature(rawBody: string, signatureHeader: string | undefined): boolean {
    const secret = this.config.get<string>('identityProvider.webhookSecret');
    if (!secret || !signatureHeader) return false;

    const expected = createHmac('sha256', secret).update(rawBody).digest('hex');
    const expectedBuf = Buffer.from(expected, 'utf8');
    const gotBuf = Buffer.from(signatureHeader, 'utf8');
    if (expectedBuf.length !== gotBuf.length) return false;
    return timingSafeEqual(expectedBuf, gotBuf);
  }

  async handleWebhook(payload: unknown, signatureHeader: string | undefined) {
    const { providerReference, result } = await this.provider.handleWebhook(payload, signatureHeader);

    const verification = await this.prisma.identityVerification.findFirst({
      where: { providerReference },
    });
    if (!verification) {
      throw new NotFoundException('Unknown verification reference.');
    }

    await this.prisma.identityVerification.update({
      where: { id: verification.id },
      data: {
        status: result.status,
        failureReasonCode: result.failureReasonCode,
        verifiedAt: result.status === 'VERIFIED' ? new Date() : undefined,
      },
    });

    if (result.status === 'VERIFIED') {
      if (result.maskedIdentifier) {
        await this.prisma.protectedIdentity.upsert({
          where: { userId: verification.userId },
          update: { maskedIdentifier: result.maskedIdentifier },
          create: {
            userId: verification.userId,
            identityToken: `idt_${verification.id}`,
            maskedIdentifier: result.maskedIdentifier,
            dataClassification: 'restricted',
          },
        });
      }
      await this.users.markIdentityVerified(verification.userId);
    } else if (result.status === 'REJECTED') {
      // Counts the rejection; only flags the account and strikes the referrer
      // once it has failed `kyc_rejection_attempts` times independently.
      await this.fraud.recordVerificationRejection(verification.userId, result.failureReasonCode);
    }

    await this.audit.record({
      actorUserId: verification.userId,
      action: `IDENTITY_WEBHOOK_${result.status}`,
      entityType: 'IdentityVerification',
      entityId: verification.id,
    });

    return { ok: true };
  }
}
