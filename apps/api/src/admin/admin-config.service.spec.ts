import { Test } from '@nestjs/testing';
import { BadRequestException, NotFoundException } from '@nestjs/common';
import { AdminConfigService } from './admin-config.service';
import { PrismaService } from '../prisma/prisma.service';
import { AuditLogService } from '../audit/audit-log.service';
import { SystemConfigService } from '../system-config/system-config.service';

describe('AdminConfigService', () => {
  let service: AdminConfigService;
  let prisma: any;
  let systemConfig: any;
  let audit: any;

  beforeEach(async () => {
    prisma = {
      systemConfig: { findMany: jest.fn().mockResolvedValue([]) },
      kycTrainingScenario: { count: jest.fn().mockResolvedValue(5) },
    };
    systemConfig = { get: jest.fn().mockResolvedValue(200), set: jest.fn() };
    audit = { record: jest.fn() };

    const moduleRef = await Test.createTestingModule({
      providers: [
        AdminConfigService,
        { provide: PrismaService, useValue: prisma },
        { provide: SystemConfigService, useValue: systemConfig },
        { provide: AuditLogService, useValue: audit },
      ],
    }).compile();

    service = moduleRef.get(AdminConfigService);
  });

  describe('the unreachable-target guard', () => {
    it('refuses a KYC target higher than the number of active scenarios', async () => {
      // This is the exact bug that shipped: target 200, 5 scenarios, and every
      // candidate dead-ends at the sixth challenge forever.
      prisma.kycTrainingScenario.count.mockResolvedValue(5);

      await expect(service.update('kyc_challenge_threshold', 200, 'admin-1')).rejects.toBeInstanceOf(
        BadRequestException,
      );
      expect(systemConfig.set).not.toHaveBeenCalled();
    });

    it('explains why, and names the value that would work', async () => {
      prisma.kycTrainingScenario.count.mockResolvedValue(5);

      await expect(
        service.update('kyc_challenge_threshold', 200, 'admin-1'),
      ).rejects.toThrow(/only 5 active scenario/);
      await expect(
        service.update('kyc_challenge_threshold', 200, 'admin-1'),
      ).rejects.toThrow(/5 or fewer/);
    });

    it('allows a target equal to the scenario count', async () => {
      prisma.kycTrainingScenario.count.mockResolvedValue(5);
      await expect(service.update('kyc_challenge_threshold', 5, 'admin-1')).resolves.toMatchObject({
        value: 5,
      });
    });

    it('allows the small target the operator actually wants', async () => {
      prisma.kycTrainingScenario.count.mockResolvedValue(5);
      await expect(service.update('kyc_challenge_threshold', 2, 'admin-1')).resolves.toMatchObject({
        key: 'kyc_challenge_threshold',
        value: 2,
      });
      expect(systemConfig.set).toHaveBeenCalledWith('kyc_challenge_threshold', 2, 'admin-1');
    });

    it('allows a high target once enough scenarios exist', async () => {
      prisma.kycTrainingScenario.count.mockResolvedValue(250);
      await expect(service.update('kyc_challenge_threshold', 200, 'admin-1')).resolves.toMatchObject(
        { value: 200 },
      );
    });

    it('does not cap the referral threshold, which has no content dependency', async () => {
      prisma.kycTrainingScenario.count.mockResolvedValue(5);
      await expect(service.update('referral_threshold', 200, 'admin-1')).resolves.toMatchObject({
        value: 200,
      });
    });
  });

  describe('key allow-list', () => {
    it('rejects an unknown key rather than creating a config row nothing reads', async () => {
      await expect(service.update('made_up_key', 5, 'admin-1')).rejects.toBeInstanceOf(
        NotFoundException,
      );
      expect(systemConfig.set).not.toHaveBeenCalled();
    });
  });

  describe('auditing', () => {
    it('records who changed what, including the previous value', async () => {
      systemConfig.get.mockResolvedValue(8);
      await service.update('fraud_strike_limit', 4, 'admin-7');

      expect(audit.record).toHaveBeenCalledWith(
        expect.objectContaining({
          actorUserId: 'admin-7',
          action: 'SYSTEM_CONFIG_UPDATED',
          metadata: expect.objectContaining({ key: 'fraud_strike_limit', previous: 8, value: 4 }),
        }),
      );
    });
  });

  describe('listSettings', () => {
    it('reports the scenario ceiling so an admin sees the limit before hitting it', async () => {
      prisma.kycTrainingScenario.count.mockResolvedValue(5);
      const result = await service.listSettings();

      const kyc = result.settings.find((s) => s.key === 'kyc_challenge_threshold');
      expect(kyc?.max).toBe(5);
      expect(result.context.activeScenarios).toBe(5);
    });

    it('falls back to defaults for settings never written to the database', async () => {
      prisma.systemConfig.findMany.mockResolvedValue([]);
      const result = await service.listSettings();
      expect(result.settings.find((s) => s.key === 'referral_threshold')?.value).toBe(200);
    });
  });
});
