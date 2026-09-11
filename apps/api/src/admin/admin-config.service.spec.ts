import { Test } from '@nestjs/testing';
import { NotFoundException } from '@nestjs/common';
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

  describe('any target is settable, because scenarios repeat', () => {
    it('allows the small target an operator actually wants', async () => {
      prisma.kycTrainingScenario.count.mockResolvedValue(5);
      await expect(service.update('kyc_challenge_threshold', 2, 'admin-1')).resolves.toMatchObject({
        key: 'kyc_challenge_threshold',
        value: 2,
      });
      expect(systemConfig.set).toHaveBeenCalledWith('kyc_challenge_threshold', 2, 'admin-1');
    });

    it('allows a target far larger than the scenario bank', async () => {
      // The bank size no longer caps the target: issueNextChallenge cycles
      // scenarios, so 200 reviews against 5 scenarios is 40 passes each.
      prisma.kycTrainingScenario.count.mockResolvedValue(5);
      await expect(
        service.update('kyc_challenge_threshold', 200, 'admin-1'),
      ).resolves.toMatchObject({ value: 200 });
      expect(systemConfig.set).toHaveBeenCalledWith('kyc_challenge_threshold', 200, 'admin-1');
    });

    it('allows the referral target, which has no content dependency', async () => {
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
    it('reports how many scenarios exist, for context on repetition', async () => {
      prisma.kycTrainingScenario.count.mockResolvedValue(5);
      const result = await service.listSettings();
      expect(result.context.activeScenarios).toBe(5);
    });

    it('falls back to defaults for settings never written to the database', async () => {
      prisma.systemConfig.findMany.mockResolvedValue([]);
      const result = await service.listSettings();
      expect(result.settings.find((s) => s.key === 'referral_threshold')?.value).toBe(200);
    });
  });
});
