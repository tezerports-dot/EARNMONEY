# Migration Guide — Moving to a New Host Safely

This works for **any** move: Railway → Oracle, Railway → another VPS,
Oracle → Railway, etc. The only thing that changes between scenarios is
*where* you get the new `DATABASE_URL` from — the procedure is identical.

The core idea: **freeze writes, snapshot, restore, verify counts match,
then cut over.** Nothing is deleted from the old side until you've confirmed
the new side is correct.

---

## Step 0 — Set up the new host, but don't go live yet
Deploy the app on the new host (`RAILWAY_DEPLOY_GUIDE.md` or
`ORACLE_MIGRATION_PLAN.md`) with:
- `MAINTENANCE_MODE=true`
- A **fresh, empty** database (don't point it at real traffic yet)

Confirm it builds and starts cleanly before touching any real data.

## Step 1 — Freeze the OLD deployment
On the **old** host, set `MAINTENANCE_MODE=true` and redeploy/restart.
From this point on:
- Every bot message gets an instant "we're upgrading, try again shortly"
  reply — **no database writes happen**.
- The worker's cron jobs skip themselves instead of running (you'll see
  `skipping ... — maintenance mode is on` in the logs).

## Step 2 — Confirm nothing is still in-flight
Check the old host's logs. You should NOT see any `[worker] ... started`
lines after the maintenance flip — only `skipping`. If a job was already
mid-run when you flipped the flag, wait for it to finish (check logs) before
continuing. This is usually seconds, not minutes.

## Step 3 — Run the migration script
From your own computer (needs `pg_dump`/`pg_restore`/`psql` installed —
these come with Postgres, or `brew install postgresql` / `apt install
postgresql-client`):

```bash
./scripts/migrate-db.sh "OLD_DATABASE_URL" "NEW_DATABASE_URL"
```

This does three things automatically:
1. **Dumps** the old database (a perfectly consistent snapshot — safe
   because writes are frozen, so nothing can change mid-dump).
2. **Restores** it into the new database.
3. **Verifies row counts** for every table (`User`, `MonthlyPayout`,
   `ChannelShard`, `GroupShard`, `AdminUser`, `AuditLog`) match exactly
   between old and new. It refuses to tell you it's safe unless every table
   matches.

If it reports a mismatch, **stop** — don't cut over. Re-run it (safe to
re-run — it always restores fresh) or investigate the error output first.

## Step 4 — Point traffic at the new host
Only after Step 3 shows all ✅:
1. Update `BOT_WEBHOOK_URL` and `NEXT_PUBLIC_SITE_URL` on the **new** host to
   its real public domain.
2. If using your own domain (not a Railway-generated one), update your DNS
   **A record** now — allow a few minutes for propagation.
3. Set `MAINTENANCE_MODE=false` on the **new** host and redeploy.

## Step 5 — Leave the old host as a cold backup for a day
- Keep `MAINTENANCE_MODE=true` on the old host — it stays reachable but
  inert, so if anything briefly hits it during DNS propagation, it still
  can't write bad data.
- Watch the new host for a day: check `/status` works, test `/bankdetails`,
  confirm the admin panel shows the same numbers you saw on the old host
  right before migrating.
- Only **then** delete/decommission the old host and the dump file.

---

## "Nothing is left behind" — what this guarantees
- **Data:** the dump is taken while writes are frozen, so it's a true
  snapshot — no user can join/activate/get paid mid-dump, so there's no
  window where something could be lost or duplicated.
- **Verification:** the script checks actual row counts on both sides
  before declaring success — it doesn't just trust that `pg_restore`
  "probably worked."
- **Rollback:** the old host isn't deleted until you've personally confirmed
  the new one is stable — if something's wrong, you can flip
  `MAINTENANCE_MODE` back and point the domain back at the old host.

## What you do NOT need to migrate
- **Redis** — nothing in the codebase actually uses it yet (bot sessions are
  in-memory, cron doesn't need it), so there's no state to move.
- **Environment secrets** — these aren't "data," just re-enter them on the
  new host (`BOT_TOKEN`, `JWT_SECRET`, etc.) — see the `.env.example`
  comments for what each one does.

## Typical time budget
- Steps 1–2 (freeze + confirm idle): a few minutes.
- Step 3 (dump/restore/verify): a few minutes at your current data size —
  scales with row count, but even at 1000 joins/day for a year that's well
  under a minute of actual transfer time; most of the "a few minutes" is
  you watching the script run.
- Step 4 (DNS/webhook cutover): a few minutes, plus DNS propagation if using
  a custom domain (Railway-generated domains are instant).
- **Total realistic window: 15–30 minutes**, not 5 — but also not the full
  hour you might fear, because the freeze means there's no rush and no risk
  of corruption while you work through it calmly.
