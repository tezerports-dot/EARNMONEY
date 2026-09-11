import { Test } from '@nestjs/testing';
import { BadRequestException, ConflictException, NotFoundException } from '@nestjs/common';
import { Prisma } from '@prisma/client';
import { AdminReadingItemsService } from './admin-reading-items.service';
import { PrismaService } from '../prisma/prisma.service';
import { AuditLogService } from '../audit/audit-log.service';
import { SystemConfigService } from '../system-config/system-config.service';

const duplicate = () =>
  new Prisma.PrismaClientKnownRequestError('dup', {
    code: 'P2002',
    clientVersion: '5.22.0',
  });

describe('AdminReadingItemsService', () => {
  let service: AdminReadingItemsService;
  let prisma: any;
  let audit: any;

  beforeEach(async () => {
    prisma = {
      numberReadingItem: {
        findMany: jest.fn().mockResolvedValue([]),
        findUnique: jest.fn(),
        create: jest.fn(),
        update: jest.fn(),
        count: jest.fn().mockResolvedValue(5),
      },
      challengeAttempt: { groupBy: jest.fn().mockResolvedValue([]) },
    };
    audit = { record: jest.fn() };

    const moduleRef = await Test.createTestingModule({
      providers: [
        AdminReadingItemsService,
        { provide: PrismaService, useValue: prisma },
        { provide: AuditLogService, useValue: audit },
        {
          provide: SystemConfigService,
          useValue: { getKycChallengeThreshold: jest.fn().mockResolvedValue(200) },
        },
      ],
    }).compile();

    service = moduleRef.get(AdminReadingItemsService);
  });

  describe('create', () => {
    const valid = {
      number: '284713905612',
      question: 'Enter the LAST 4 digits of the number above.',
      expectedAnswer: '5612',
    };

    it('stores the number, question and the answer the admin set', async () => {
      prisma.numberReadingItem.create.mockImplementation(async ({ data }: any) => ({
        id: 'item-1',
        ...data,
      }));

      const created = await service.create(valid, 'admin-1');

      expect(prisma.numberReadingItem.create).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({
            number: '284713905612',
            question: 'Enter the LAST 4 digits of the number above.',
            expectedAnswer: '5612',
            isActive: true,
          }),
        }),
      );
      expect(created.numberDisplay).toBe('2847 1390 5612');
    });

    it('accepts a number pasted with spaces and stores it as digits', async () => {
      prisma.numberReadingItem.create.mockImplementation(async ({ data }: any) => ({
        id: 'item-1',
        ...data,
      }));

      // An admin copying a grouped number off a card should not have to strip
      // the spacing by hand.
      await service.create({ ...valid, number: '2847 1390 5612' }, 'admin-1');

      expect(prisma.numberReadingItem.create.mock.calls[0][0].data.number).toBe('284713905612');
    });

    it('rejects a number that is not 12 digits', async () => {
      await expect(service.create({ ...valid, number: '28471390' }, 'admin-1')).rejects.toBeInstanceOf(
        BadRequestException,
      );
      expect(prisma.numberReadingItem.create).not.toHaveBeenCalled();
    });

    it('rejects a number containing letters', async () => {
      await expect(
        service.create({ ...valid, number: '28471390561X' }, 'admin-1'),
      ).rejects.toBeInstanceOf(BadRequestException);
    });

    it('reports a duplicate question on the same number as a conflict', async () => {
      prisma.numberReadingItem.create.mockRejectedValueOnce(duplicate());

      await expect(service.create(valid, 'admin-1')).rejects.toBeInstanceOf(ConflictException);
    });

    it('keeps the answer out of the audit log', async () => {
      prisma.numberReadingItem.create.mockImplementation(async ({ data }: any) => ({
        id: 'item-1',
        ...data,
      }));

      await service.create(valid, 'admin-1');

      // The audit log is read far more widely than the bank itself, so copying
      // answers into it would leak the whole answer key.
      const recorded = audit.record.mock.calls[0][0];
      expect(recorded).toMatchObject({ actorUserId: 'admin-1', action: 'READING_ITEM_CREATED' });
      expect(JSON.stringify(recorded)).not.toContain('5612');
    });
  });

  describe('update', () => {
    beforeEach(() => {
      prisma.numberReadingItem.findUnique.mockResolvedValue({ id: 'item-1', isActive: true });
      // Like Prisma: an undefined field means "leave it alone", so it must not
      // overwrite the stored value with undefined.
      prisma.numberReadingItem.update.mockImplementation(async ({ data }: any) => {
        const row: Record<string, unknown> = { id: 'item-1', number: '284713905612' };
        for (const [k, v] of Object.entries(data)) if (v !== undefined) row[k] = v;
        return row;
      });
    });

    it('corrects just the answer without resending the number or question', async () => {
      await service.update('item-1', { expectedAnswer: '5612' }, 'admin-1');

      const data = prisma.numberReadingItem.update.mock.calls[0][0].data;
      expect(data.expectedAnswer).toBe('5612');
      // Undefined fields must stay undefined, or Prisma would blank them.
      expect(data.number).toBeUndefined();
      expect(data.question).toBeUndefined();
    });

    it('404s on an item that does not exist', async () => {
      prisma.numberReadingItem.findUnique.mockResolvedValueOnce(null);

      await expect(service.update('nope', { expectedAnswer: '1' }, 'admin-1')).rejects.toBeInstanceOf(
        NotFoundException,
      );
    });

    it('rejects a replacement number that is not 12 digits', async () => {
      await expect(service.update('item-1', { number: '123' }, 'admin-1')).rejects.toBeInstanceOf(
        BadRequestException,
      );
      expect(prisma.numberReadingItem.update).not.toHaveBeenCalled();
    });

    it('refuses to retire the last active item', async () => {
      prisma.numberReadingItem.count.mockResolvedValueOnce(0);

      await expect(service.update('item-1', { isActive: false }, 'admin-1')).rejects.toBeInstanceOf(
        BadRequestException,
      );
    });

    it('clears the hint when given an empty string', async () => {
      await service.update('item-1', { answerHint: '  ' }, 'admin-1');

      expect(prisma.numberReadingItem.update.mock.calls[0][0].data.answerHint).toBeNull();
    });
  });

  describe('setActive', () => {
    it('refuses to retire the last active item, rather than stranding candidates', async () => {
      prisma.numberReadingItem.findUnique.mockResolvedValueOnce({ id: 'item-1', isActive: true });
      prisma.numberReadingItem.count.mockResolvedValueOnce(0);

      await expect(service.setActive('item-1', false, 'admin-1')).rejects.toBeInstanceOf(
        BadRequestException,
      );
      expect(prisma.numberReadingItem.update).not.toHaveBeenCalled();
    });

    it('retires an item when others remain active', async () => {
      prisma.numberReadingItem.findUnique.mockResolvedValueOnce({ id: 'item-1', isActive: true });
      prisma.numberReadingItem.count.mockResolvedValueOnce(3);
      prisma.numberReadingItem.update.mockResolvedValueOnce({ id: 'item-1', isActive: false });

      await service.setActive('item-1', false, 'admin-1');

      expect(audit.record).toHaveBeenCalledWith(
        expect.objectContaining({ action: 'READING_ITEM_RETIRED' }),
      );
    });

    it('does not run the last-active check when activating', async () => {
      prisma.numberReadingItem.findUnique.mockResolvedValueOnce({ id: 'item-1', isActive: false });
      prisma.numberReadingItem.update.mockResolvedValueOnce({ id: 'item-1', isActive: true });

      await service.setActive('item-1', true, 'admin-1');

      expect(prisma.numberReadingItem.count).not.toHaveBeenCalled();
    });
  });

  describe('list', () => {
    beforeEach(() => {
      prisma.numberReadingItem.findMany.mockResolvedValue([
        {
          id: 'item-1',
          number: '284713905612',
          question: 'Q1',
          expectedAnswer: '5612',
          answerHint: null,
          isActive: true,
          createdAt: new Date(),
          _count: { attempts: 10 },
        },
        {
          id: 'item-2',
          number: '739024681537',
          question: 'Q2',
          expectedAnswer: '7390',
          answerHint: null,
          isActive: true,
          createdAt: new Date(),
          _count: { attempts: 0 },
        },
      ]);
    });

    it('reports a pass rate per item, so a mistyped answer is visible', async () => {
      prisma.challengeAttempt.groupBy.mockResolvedValueOnce([
        { itemId: 'item-1', isCorrect: true, _count: { _all: 2 } },
        { itemId: 'item-1', isCorrect: false, _count: { _all: 8 } },
      ]);

      const result = await service.list();
      const item = result.items.find((i) => i.id === 'item-1');

      // 20% is the signal an admin needs: ten candidates did not all misread
      // the same number, the stored answer is wrong.
      expect(item?.passRate).toBe(20);
      expect(item?.graded).toBe(10);
    });

    it('leaves the pass rate null for an item nobody has answered', async () => {
      const result = await service.list();

      // 0% on an unused item would read as broken rather than untouched.
      expect(result.items.find((i) => i.id === 'item-2')?.passRate).toBeNull();
    });

    it('shows how often each item repeats at the current target', async () => {
      const result = await service.list();

      // 200 target, 2 active items.
      expect(result.summary.averageRepeatsPerItem).toBe(100);
      expect(result.summary.currentTarget).toBe(200);
      expect(result.summary.active).toBe(2);
    });

    it('groups the number for display', async () => {
      const result = await service.list();

      expect(result.items[0].numberDisplay).toBe('2847 1390 5612');
    });
  });
});
