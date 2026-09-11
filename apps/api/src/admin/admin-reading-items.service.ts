import { BadRequestException, ConflictException, Injectable, Logger, NotFoundException } from '@nestjs/common';
import { Prisma } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuditLogService } from '../audit/audit-log.service';
import { SystemConfigService } from '../system-config/system-config.service';
import { CreateReadingItemDto } from './dto/create-reading-item.dto';
import { UpdateReadingItemDto } from './dto/update-reading-item.dto';
import { formatGrouped, isTwelveDigits, normaliseNumber } from '../kyc-training/number-reading.util';

/**
 * The bank of practice numbers.
 *
 * An admin writes each entry: the number, the question asked about it, and the
 * answer that question has. Candidates are served from this bank, so it is the
 * entire content supply for the challenge.
 *
 * Entries repeat — least recently seen first — so the bank does not need to be
 * as large as the target. A target of 200 against 20 numbers means each comes
 * round about ten times.
 */
@Injectable()
export class AdminReadingItemsService {
  private readonly logger = new Logger(AdminReadingItemsService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly systemConfig: SystemConfigService,
    private readonly audit: AuditLogService,
  ) {}

  async list() {
    const [items, threshold] = await Promise.all([
      this.prisma.numberReadingItem.findMany({
        orderBy: { createdAt: 'desc' },
        select: {
          id: true,
          number: true,
          question: true,
          expectedAnswer: true,
          answerHint: true,
          isActive: true,
          createdAt: true,
          _count: { select: { attempts: true } },
        },
      }),
      this.systemConfig.getKycChallengeThreshold(),
    ]);

    // Pass rate per item. An answer keyed in wrong is invisible at authoring
    // time but obvious here: an item everyone fails is almost always a typo in
    // the answer, not 200 candidates misreading the same number.
    const graded = await this.prisma.challengeAttempt.groupBy({
      by: ['itemId', 'isCorrect'],
      where: { itemId: { in: items.map((i) => i.id) }, isCorrect: { not: null } },
      _count: { _all: true },
    });
    const tally = new Map<string, { correct: number; total: number }>();
    for (const row of graded) {
      if (!row.itemId) continue;
      const entry = tally.get(row.itemId) ?? { correct: 0, total: 0 };
      entry.total += row._count._all;
      if (row.isCorrect) entry.correct += row._count._all;
      tally.set(row.itemId, entry);
    }

    const active = items.filter((i) => i.isActive).length;
    return {
      items: items.map((item) => {
        const t = tally.get(item.id);
        return {
          ...item,
          numberDisplay: formatGrouped(item.number),
          graded: t?.total ?? 0,
          // Null until somebody has actually answered it — 0% with no
          // attempts would read as a broken item rather than an unused one.
          passRate: t && t.total > 0 ? Math.round((t.correct / t.total) * 100) : null,
        };
      }),
      summary: {
        total: items.length,
        active,
        currentTarget: threshold,
        // What an admin actually wants to know when sizing the bank: how often
        // a candidate will see the same number come round again.
        averageRepeatsPerItem: active > 0 ? Math.round((threshold / active) * 10) / 10 : null,
      },
    };
  }

  async create(dto: CreateReadingItemDto, actorUserId: string) {
    const number = normaliseNumber(dto.number);
    if (!isTwelveDigits(number)) {
      throw new BadRequestException('The number must be 12 digits.');
    }

    try {
      const created = await this.prisma.numberReadingItem.create({
        data: {
          number,
          question: dto.question.trim(),
          expectedAnswer: dto.expectedAnswer.trim(),
          answerHint: dto.answerHint?.trim() || null,
          isActive: dto.isActive ?? true,
        },
      });

      await this.audit.record({
        actorUserId,
        action: 'READING_ITEM_CREATED',
        entityType: 'NumberReadingItem',
        entityId: created.id,
        // The answer is deliberately not recorded here: the audit log is read
        // far more widely than the bank itself.
        metadata: { question: created.question },
      });

      this.logger.log(`reading item created: ${created.id}`);
      return { ...created, numberDisplay: formatGrouped(created.number) };
    } catch (e) {
      if (e instanceof Prisma.PrismaClientKnownRequestError && e.code === 'P2002') {
        throw new ConflictException('That question already exists for this number.');
      }
      throw e;
    }
  }

  async update(id: string, dto: UpdateReadingItemDto, actorUserId: string) {
    const existing = await this.prisma.numberReadingItem.findUnique({ where: { id } });
    if (!existing) throw new NotFoundException('Practice number not found.');

    const number = dto.number === undefined ? undefined : normaliseNumber(dto.number);
    if (number !== undefined && !isTwelveDigits(number)) {
      throw new BadRequestException('The number must be 12 digits.');
    }

    // Retiring the last active entry would leave every candidate with nothing
    // to answer, so it is refused rather than silently stranding them.
    if (dto.isActive === false && existing.isActive) {
      await this.assertNotLastActive(id);
    }

    try {
      const updated = await this.prisma.numberReadingItem.update({
        where: { id },
        data: {
          number,
          question: dto.question?.trim(),
          expectedAnswer: dto.expectedAnswer?.trim(),
          answerHint: dto.answerHint === undefined ? undefined : dto.answerHint.trim() || null,
          isActive: dto.isActive,
        },
      });

      await this.audit.record({
        actorUserId,
        action: 'READING_ITEM_UPDATED',
        entityType: 'NumberReadingItem',
        entityId: id,
        metadata: {
          // Which fields moved, not what they moved to — enough to trace a
          // change without copying answers into the audit log.
          changed: Object.keys(dto).filter((k) => (dto as Record<string, unknown>)[k] !== undefined),
        },
      });

      return { ...updated, numberDisplay: formatGrouped(updated.number) };
    } catch (e) {
      if (e instanceof Prisma.PrismaClientKnownRequestError && e.code === 'P2002') {
        throw new ConflictException('That question already exists for this number.');
      }
      throw e;
    }
  }

  async setActive(id: string, isActive: boolean, actorUserId: string) {
    const item = await this.prisma.numberReadingItem.findUnique({ where: { id } });
    if (!item) throw new NotFoundException('Practice number not found.');

    if (!isActive && item.isActive) await this.assertNotLastActive(id);

    const updated = await this.prisma.numberReadingItem.update({
      where: { id },
      data: { isActive },
    });

    await this.audit.record({
      actorUserId,
      action: isActive ? 'READING_ITEM_ACTIVATED' : 'READING_ITEM_RETIRED',
      entityType: 'NumberReadingItem',
      entityId: id,
    });

    return updated;
  }

  private async assertNotLastActive(id: string) {
    const remaining = await this.prisma.numberReadingItem.count({
      where: { isActive: true, id: { not: id } },
    });
    if (remaining === 0) {
      throw new BadRequestException(
        'This is the last active practice number. Retiring it would leave candidates with nothing to answer. Add another first.',
      );
    }
  }
}
