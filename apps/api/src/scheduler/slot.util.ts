import { createHash } from 'crypto';

/**
 * Deterministic slot assignment — the reason this system never holds millions
 * of pending jobs.
 *
 * The naive design is "schedule a delayed job per user per day". At 2.9M
 * accounts that is 2.9M live job records, tens of GB of Redis, and a thundering
 * herd whenever the queue is drained. Instead each account is permanently
 * assigned one of `slotsPerDay` slots by hashing its id. The dispatcher wakes
 * once per slot and enqueues only that slot's accounts, so the queue never
 * holds more than one slot's worth of work — about 2,000 jobs at 2.9M users on
 * a 1,440-slot day.
 *
 * Properties that matter:
 *  - Deterministic: the same id always lands in the same slot, so a restart,
 *    a replay, or a second dispatcher all agree without coordination.
 *  - Uniform: SHA-256 spreads sequential UUIDs evenly, so no slot becomes hot.
 *  - Stable: assigned once at signup and stored, so changing `slotsPerDay`
 *    later does not silently reshuffle everyone (see `reassignAllSlots`).
 */

/** One slot per minute. Divides evenly into 24h and keeps batches small. */
export const DEFAULT_SLOTS_PER_DAY = 1440;

/**
 * Maps a user id into `[0, slotsPerDay)`.
 *
 * Uses the first 4 bytes of SHA-256 rather than a cheap arithmetic hash:
 * sequential or time-ordered ids (UUIDv7, snowflakes) cluster badly under
 * modulo, which would leave most slots empty and a few overloaded.
 */
export function slotForUserId(userId: string, slotsPerDay = DEFAULT_SLOTS_PER_DAY): number {
  if (slotsPerDay <= 0) throw new Error('slotsPerDay must be positive');
  const digest = createHash('sha256').update(userId).digest();
  return digest.readUInt32BE(0) % slotsPerDay;
}

/** Slot a given instant falls into, in UTC. */
export function slotForDate(date: Date, slotsPerDay = DEFAULT_SLOTS_PER_DAY): number {
  const minutesIntoDay = date.getUTCHours() * 60 + date.getUTCMinutes();
  const secondsIntoDay = minutesIntoDay * 60 + date.getUTCSeconds();
  return Math.floor((secondsIntoDay / 86400) * slotsPerDay) % slotsPerDay;
}

/** Midnight UTC for the given instant — the `slotDate` half of a tick's key. */
export function slotDateFor(date: Date): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
}

/**
 * The (date, slot) pairs that should have been dispatched in the last
 * `lookbackSlots`, most recent first. This is what turns recovery from
 * guesswork into a query: compare against `schedule_ticks` and replay whatever
 * is missing or incomplete.
 */
export function recentSlots(
  now: Date,
  lookbackSlots: number,
  slotsPerDay = DEFAULT_SLOTS_PER_DAY,
): Array<{ slotDate: Date; slot: number }> {
  const out: Array<{ slotDate: Date; slot: number }> = [];
  const msPerSlot = 86_400_000 / slotsPerDay;
  for (let i = 0; i < lookbackSlots; i++) {
    const at = new Date(now.getTime() - i * msPerSlot);
    out.push({ slotDate: slotDateFor(at), slot: slotForDate(at, slotsPerDay) });
  }
  return out;
}

/**
 * How many accounts a slot holds on average, and the per-second rate that
 * implies. Used by the docs and by the capacity endpoint so the numbers in
 * the runbook can never drift from the ones the code actually uses.
 */
export function slotLoad(totalAccounts: number, slotsPerDay = DEFAULT_SLOTS_PER_DAY) {
  const perSlot = totalAccounts / slotsPerDay;
  const secondsPerSlot = 86400 / slotsPerDay;
  return {
    accountsPerSlot: Math.ceil(perSlot),
    secondsPerSlot,
    updatesPerSecond: Number((perSlot / secondsPerSlot).toFixed(2)),
  };
}
