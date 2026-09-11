/**
 * Queue topology.
 *
 * Three queues, kept separate so one class of work can never block another:
 *
 *  - CONTENT_UPDATES  — the daily fan-out. High volume, rate-limited, and the
 *                       only one allowed to be slow.
 *  - BACKGROUND       — non-critical work shed from the signup/login path
 *                       (audit writes, welcome messages). Small and quick, so
 *                       it must not sit behind a 2,000-job update batch.
 *  - DEAD_LETTER      — terminal failures, parked for inspection. Nothing
 *                       consumes this automatically; draining it is a human
 *                       decision after the cause is understood.
 */
export const QUEUES = {
  CONTENT_UPDATES: 'content-updates',
  BACKGROUND: 'background',
  DEAD_LETTER: 'dead-letter',
} as const;

export const JOBS = {
  DELIVER_UPDATE: 'deliver-update',
  POST_SIGNUP: 'post-signup',
  POST_LOGIN: 'post-login',
} as const;

export type DeliverUpdateJob = {
  userId: string;
  /** Target content version. Combined with the user id this makes the job id. */
  version: number;
  /** The slot this was dispatched for — carried for tracing only. */
  slot: number;
};

export type PostSignupJob = { userId: string; ip?: string };
export type PostLoginJob = { userId: string; ip?: string };

/**
 * Deterministic job id. BullMQ refuses to enqueue a second job with an id it
 * already knows, so a replayed slot produces no duplicates while the original
 * job is still in the queue or its completed set.
 *
 * This is only the FIRST line of defence — once BullMQ trims completed jobs
 * the id is forgotten, so `UserUpdateState.deliveredVersion` in the processor
 * is what actually guarantees at-most-once delivery.
 */
export function deliverUpdateJobId(userId: string, version: number): string {
  // Underscores, not colons: BullMQ rejects ':' in a custom job id because it
  // is the delimiter in its own Redis key structure. UUIDs contain hyphens but
  // never underscores, so this stays unambiguous.
  return `u_${userId}_v_${version}`;
}
