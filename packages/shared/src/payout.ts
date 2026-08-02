// ---- Payout eligibility rule ----
// A referral counts toward a given month's payout ONLY if the referred user
// became ACTIVE (i.e. finished their 24h dual-membership requirement) on or
// before the 15th of that month, Indian Standard Time. This gives every
// counted referral at least ~15 days of standing before the payout run
// (traditionally done around the 30th).
//
// Example: referred user joins and activates on the 23rd -> NOT counted in
// that month's payout (activated after the 15th cutoff). A user who
// activated on the 15th or earlier IS counted, even though the payout run
// itself happens on the 30th.

export const PAYOUT_ELIGIBILITY_CUTOFF_DAY_IST = 15;
export const IST_OFFSET_MINUTES = 330; // India Standard Time = UTC+5:30, no DST

/**
 * Returns the exact UTC instant corresponding to 23:59:59.999 IST on the
 * 15th of the given "YYYY-MM" month. Compare a user's `activatedAt` against
 * this with `<=` to determine payout eligibility for that month.
 */
export function getPayoutEligibilityCutoffUtc(month: string): Date {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  if (!match) throw new Error(`Invalid month "${month}", expected "YYYY-MM"`);
  const year = Number(match[1]);
  const monthIndex = Number(match[2]) - 1; // JS Date months are 0-based

  // Midnight-anchored UTC timestamp for 15th 23:59:59.999 IST, computed by
  // building the IST wall-clock time in UTC fields and then subtracting the
  // IST offset — avoids any local-timezone dependence on the host machine.
  const istWallClockAsUtcMs = Date.UTC(
    year,
    monthIndex,
    PAYOUT_ELIGIBILITY_CUTOFF_DAY_IST,
    23,
    59,
    59,
    999,
  );
  return new Date(istWallClockAsUtcMs - IST_OFFSET_MINUTES * 60 * 1000);
}

/** True if activatedAt qualifies this referral for the given month's payout. */
export function isEligibleForPayoutMonth(activatedAt: Date | null, month: string): boolean {
  if (!activatedAt) return false;
  return activatedAt.getTime() <= getPayoutEligibilityCutoffUtc(month).getTime();
}

function currentIstDate(): Date {
  return new Date(Date.now() + IST_OFFSET_MINUTES * 60 * 1000);
}

/** Current month as "YYYY-MM", computed in IST (matters near month boundaries). */
export function currentMonthIst(): string {
  const d = currentIstDate();
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
}
