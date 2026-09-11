import {
  DEFAULT_SLOTS_PER_DAY,
  recentSlots,
  slotDateFor,
  slotForDate,
  slotForUserId,
  slotLoad,
} from './slot.util';
import { randomUUID } from 'crypto';

describe('slot.util', () => {
  describe('slotForUserId', () => {
    it('is deterministic — the same id always lands in the same slot', () => {
      const id = randomUUID();
      expect(slotForUserId(id)).toBe(slotForUserId(id));
    });

    it('stays inside the slot range', () => {
      for (let i = 0; i < 500; i++) {
        const slot = slotForUserId(randomUUID());
        expect(slot).toBeGreaterThanOrEqual(0);
        expect(slot).toBeLessThan(DEFAULT_SLOTS_PER_DAY);
      }
    });

    it('spreads 144k accounts evenly enough that no slot becomes a hotspot', () => {
      // The whole design rests on this: if the hash clustered, a few slots
      // would carry the entire user base and the rate limiter would be useless.
      const counts = new Array(DEFAULT_SLOTS_PER_DAY).fill(0);
      const total = DEFAULT_SLOTS_PER_DAY * 100; // 100 per slot on average
      for (let i = 0; i < total; i++) counts[slotForUserId(randomUUID())]++;

      const max = Math.max(...counts);
      const min = Math.min(...counts);
      // Poisson(100) has sd 10, so ~±5 sd is a generous but still meaningful bound.
      expect(max).toBeLessThan(160);
      expect(min).toBeGreaterThan(45);
    });

    it('does not cluster for sequential ids, which modulo-on-integer would', () => {
      const counts = new Map<number, number>();
      for (let i = 0; i < 10_000; i++) {
        const slot = slotForUserId(`user-${i}`);
        counts.set(slot, (counts.get(slot) ?? 0) + 1);
      }
      // With 10k sequential ids over 1440 slots we expect nearly every slot hit.
      expect(counts.size).toBeGreaterThan(1300);
    });

    it('respects a custom slot count', () => {
      for (let i = 0; i < 100; i++) {
        expect(slotForUserId(randomUUID(), 24)).toBeLessThan(24);
      }
    });

    it('rejects a nonsensical slot count rather than dividing by zero', () => {
      expect(() => slotForUserId('x', 0)).toThrow();
    });
  });

  describe('slotForDate', () => {
    it('maps midnight UTC to slot 0 and the last minute to the last slot', () => {
      expect(slotForDate(new Date('2026-01-01T00:00:00Z'))).toBe(0);
      expect(slotForDate(new Date('2026-01-01T23:59:59Z'))).toBe(1439);
    });

    it('advances one slot per minute on a 1440-slot day', () => {
      expect(slotForDate(new Date('2026-01-01T00:01:00Z'))).toBe(1);
      expect(slotForDate(new Date('2026-01-01T12:00:00Z'))).toBe(720);
    });

    it('scales to a coarser slot count', () => {
      expect(slotForDate(new Date('2026-01-01T12:00:00Z'), 24)).toBe(12);
    });
  });

  it('slotDateFor normalises to midnight UTC', () => {
    expect(slotDateFor(new Date('2026-03-04T17:45:12Z')).toISOString()).toBe(
      '2026-03-04T00:00:00.000Z',
    );
  });

  describe('recentSlots', () => {
    it('walks backwards and crosses midnight correctly', () => {
      const slots = recentSlots(new Date('2026-03-04T00:01:00Z'), 3);
      expect(slots[0]).toEqual({ slotDate: new Date('2026-03-04T00:00:00Z'), slot: 1 });
      expect(slots[1]).toEqual({ slotDate: new Date('2026-03-04T00:00:00Z'), slot: 0 });
      // One more minute back is yesterday's final slot.
      expect(slots[2]).toEqual({ slotDate: new Date('2026-03-03T00:00:00Z'), slot: 1439 });
    });
  });

  describe('slotLoad', () => {
    it('computes the documented rate for 2.9M accounts', () => {
      const load = slotLoad(2_900_000);
      expect(load.accountsPerSlot).toBe(2014); // 2_900_000 / 1440 = 2013.89
      expect(load.secondsPerSlot).toBe(60);
      expect(load.updatesPerSecond).toBeCloseTo(33.56, 1);
    });

    it('scales down for a smaller user base', () => {
      expect(slotLoad(100_000).updatesPerSecond).toBeCloseTo(1.16, 1);
    });
  });
});
