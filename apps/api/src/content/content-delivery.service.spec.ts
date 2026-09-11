import { Test } from '@nestjs/testing';
import { ContentDeliveryService } from './content-delivery.service';
import { ContentService } from './content.service';
import { PrismaService } from '../prisma/prisma.service';

describe('ContentDeliveryService', () => {
  let service: ContentDeliveryService;
  let prisma: any;
  let content: any;

  const CONTENT = {
    version: 7,
    title: 'Daily update',
    body: 'text',
    linkUrl: null,
    publishedAt: new Date().toISOString(),
  };

  beforeEach(async () => {
    prisma = {
      userUpdateState: { findUnique: jest.fn(), create: jest.fn(), updateMany: jest.fn() },
      user: { findUnique: jest.fn() },
    };
    content = { getCurrent: jest.fn().mockResolvedValue(CONTENT) };

    const moduleRef = await Test.createTestingModule({
      providers: [
        ContentDeliveryService,
        { provide: PrismaService, useValue: prisma },
        { provide: ContentService, useValue: content },
      ],
    }).compile();

    service = moduleRef.get(ContentDeliveryService);
  });

  it('delivers to an account that has not received this version', async () => {
    prisma.userUpdateState.findUnique.mockResolvedValue({ userId: 'u1', deliveredVersion: 6 });
    prisma.userUpdateState.updateMany.mockResolvedValue({ count: 1 });

    await expect(service.deliver('u1', 7)).resolves.toBe('delivered');
  });

  it('is idempotent: a redelivered job reports already-delivered and writes nothing new', async () => {
    prisma.userUpdateState.findUnique.mockResolvedValue({ userId: 'u1', deliveredVersion: 7 });
    // The conditional WHERE no longer matches, so Postgres updates 0 rows.
    prisma.userUpdateState.updateMany.mockResolvedValue({ count: 0 });

    await expect(service.deliver('u1', 7)).resolves.toBe('already-delivered');
  });

  it('guards idempotency inside the UPDATE, not with a read-then-write', async () => {
    prisma.userUpdateState.findUnique.mockResolvedValue({ userId: 'u1', deliveredVersion: 6 });
    prisma.userUpdateState.updateMany.mockResolvedValue({ count: 1 });

    await service.deliver('u1', 7);

    // This is what makes two racing workers safe: the version check is part of
    // the same statement that writes, so there is no window between them.
    const where = prisma.userUpdateState.updateMany.mock.calls[0][0].where;
    expect(where).toEqual({ userId: 'u1', deliveredVersion: { lt: 7 } });
  });

  it('delivers the newer version when content moved on after the job was queued', async () => {
    content.getCurrent.mockResolvedValue({ ...CONTENT, version: 9 });
    prisma.userUpdateState.findUnique.mockResolvedValue({ userId: 'u1', deliveredVersion: 6 });
    prisma.userUpdateState.updateMany.mockResolvedValue({ count: 1 });

    await service.deliver('u1', 7);

    expect(prisma.userUpdateState.updateMany.mock.calls[0][0].data.deliveredVersion).toBe(9);
  });

  it('creates the state row on first ever delivery', async () => {
    prisma.userUpdateState.findUnique.mockResolvedValue(null);
    prisma.user.findUnique.mockResolvedValue({ id: 'u1' });
    prisma.userUpdateState.create.mockResolvedValue({});

    await expect(service.deliver('u1', 7)).resolves.toBe('delivered');
    expect(prisma.userUpdateState.create).toHaveBeenCalled();
  });

  it('falls back to the conditional update when two workers race to create the row', async () => {
    prisma.userUpdateState.findUnique.mockResolvedValue(null);
    prisma.user.findUnique.mockResolvedValue({ id: 'u1' });
    // The unique constraint rejects the loser of the race...
    prisma.userUpdateState.create.mockRejectedValue(new Error('unique violation'));
    // ...which then resolves correctly via the conditional update.
    prisma.userUpdateState.updateMany.mockResolvedValue({ count: 0 });

    await expect(service.deliver('u1', 7)).resolves.toBe('already-delivered');
  });

  it('reports user-gone rather than throwing when the account was deleted', async () => {
    prisma.userUpdateState.findUnique.mockResolvedValue(null);
    prisma.user.findUnique.mockResolvedValue(null);

    await expect(service.deliver('u1', 7)).resolves.toBe('user-gone');
  });

  it('reports no-content instead of retrying forever when nothing is published', async () => {
    content.getCurrent.mockResolvedValue(null);
    await expect(service.deliver('u1', 7)).resolves.toBe('no-content');
    expect(prisma.userUpdateState.updateMany).not.toHaveBeenCalled();
  });

  it('reads content from the cache layer, not Postgres, on the hot path', async () => {
    prisma.userUpdateState.findUnique.mockResolvedValue({ userId: 'u1', deliveredVersion: 6 });
    prisma.userUpdateState.updateMany.mockResolvedValue({ count: 1 });

    await service.deliver('u1', 7);

    // 2.9M deliveries must not become 2.9M content queries.
    expect(content.getCurrent).toHaveBeenCalledTimes(1);
  });

  it('recordFailure never throws, so a logging failure cannot fail a job twice', async () => {
    prisma.userUpdateState.updateMany.mockRejectedValue(new Error('db down'));
    await expect(service.recordFailure('u1', 'boom')).resolves.toBeUndefined();
  });
});
