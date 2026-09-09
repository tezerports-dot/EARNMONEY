import { ConflictException, ForbiddenException, Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { AuditLogService } from '../audit/audit-log.service';
import { CreateApplicationDto } from './dto/create-application.dto';

@Injectable()
export class ApplicationsService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly audit: AuditLogService,
  ) {}

  async apply(userId: string, dto: CreateApplicationDto) {
    const user = await this.prisma.user.findUnique({ where: { id: userId } });
    if (!user) {
      throw new ForbiddenException();
    }

    // This is the actual gate. It is re-checked here, server-side, at the
    // moment of application — never inferred from anything the client sends.
    if (user.status !== 'APPLICATION_ELIGIBLE') {
      throw new ForbiddenException(
        'You need to complete the referral and KYC training requirements before applying.',
      );
    }

    const existing = await this.prisma.application.findFirst({ where: { userId } });
    if (existing) {
      throw new ConflictException('You have already submitted an application.');
    }

    const application = await this.prisma.$transaction(async (tx: any) => {
      const created = await tx.application.create({
        data: {
          userId,
          statePreference: dto.statePreference,
          tierPreference: dto.tierPreference,
          districtPreference: dto.districtPreference,
        },
      });
      await tx.user.update({ where: { id: userId }, data: { status: 'APPLIED' } });
      return created;
    });

    await this.audit.record({
      actorUserId: userId,
      action: 'APPLICATION_SUBMITTED',
      entityType: 'Application',
      entityId: application.id,
      metadata: { statePreference: dto.statePreference, tierPreference: dto.tierPreference },
    });

    return application;
  }

  async myApplication(userId: string) {
    return this.prisma.application.findFirst({ where: { userId } });
  }
}
