import { BotContext } from '../context';

/**
 * When MAINTENANCE_MODE=true, every incoming update gets a short "please
 * wait" reply and nothing downstream runs — no DB reads/writes happen.
 *
 * Use this window (env var flip + redeploy) whenever you're migrating hosts:
 * flip it on, wait for in-flight worker jobs to finish, snapshot/restore the
 * DB, then flip it off on the NEW deployment only. See MIGRATION_GUIDE.md.
 */
export function isMaintenanceMode(): boolean {
  return process.env.MAINTENANCE_MODE === 'true';
}

export async function maintenanceMiddleware(
  ctx: BotContext,
  next: () => Promise<void>,
): Promise<void> {
  if (!isMaintenanceMode()) {
    return next();
  }

  try {
    await ctx.reply(
      "We're doing a quick upgrade right now. Please try again in a few minutes — " +
        'nothing you do right now will be lost, we just need a moment. 🙏',
    );
  } catch (err) {
    console.error('[maintenance] failed to send maintenance reply:', err);
  }
  // Deliberately does NOT call next() — no handler below this runs, so no
  // DB writes happen while we're mid-migration.
}
