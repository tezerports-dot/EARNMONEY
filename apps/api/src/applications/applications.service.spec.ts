import { Test } from '@nestjs/testing';
import { ConflictException, ForbiddenException } from '@nestjs/common';
import { ApplicationsService } from './applications.service';
import { PrismaService } from '../prisma/prisma.service';
import { AuditLogService } from '../audit/audit-log.service';

describe('ApplicationsService', () => {
  let service: ApplicationsService;
  let prisma: any;

  const dto = { statePreference: 'Rajasthan' as const, tierPreference: 'tier3' as const };

  beforeEach(async () => {
    prisma = {
      user: { findUnique: jest.fn(), update: jest.fn() },
      application: { findFirst: jest.fn(), create: jest.fn() },
      $transaction: jest.fn(async (fn: any) => fn(prisma)),
    };

    const moduleRef = await Test.createTestingModule({
      providers: [
        ApplicationsService,
        { provide: PrismaService, useValue: prisma },
        { provide: AuditLogService, useValue: { record: jest.fn() } },
      ],
    }).compile();

    service = moduleRef.get(ApplicationsService);
  });

  it('rejects application when the user has not reached APPLICATION_ELIGIBLE — even if the client claims otherwise', async () => {
    prisma.user.findUnique.mockResolvedValueOnce({ id: 'u1', status: 'REFERRAL_IN_PROGRESS' });

    await expect(service.apply('u1', dto)).rejects.toBeInstanceOf(ForbiddenException);
    expect(prisma.application.create).not.toHaveBeenCalled();
  });

  it('rejects a second application from the same user', async () => {
    prisma.user.findUnique.mockResolvedValueOnce({ id: 'u1', status: 'APPLICATION_ELIGIBLE' });
    prisma.application.findFirst.mockResolvedValueOnce({ id: 'existing-app' });

    await expect(service.apply('u1', dto)).rejects.toBeInstanceOf(ConflictException);
  });

  it('creates the application and transitions status to APPLIED when eligible', async () => {
    prisma.user.findUnique.mockResolvedValueOnce({ id: 'u1', status: 'APPLICATION_ELIGIBLE' });
    prisma.application.findFirst.mockResolvedValueOnce(null);
    prisma.application.create.mockResolvedValueOnce({ id: 'app-1', userId: 'u1', ...dto });

    const result = await service.apply('u1', dto);

    expect(result.id).toBe('app-1');
    expect(prisma.user.update).toHaveBeenCalledWith({ where: { id: 'u1' }, data: { status: 'APPLIED' } });
  });
});
