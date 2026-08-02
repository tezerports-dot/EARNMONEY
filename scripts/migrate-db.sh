#!/usr/bin/env bash
# Moves the Postgres database from an old host to a new one, and verifies
# nothing was left behind. See MIGRATION_GUIDE.md for the full checklist
# (maintenance mode, DNS, webhook) — this script only handles the DB.
#
# Usage:
#   ./scripts/migrate-db.sh "OLD_DATABASE_URL" "NEW_DATABASE_URL"
#
# Before running this:
#   1. Set MAINTENANCE_MODE=true on the OLD deployment and redeploy it.
#   2. Confirm no worker job is mid-run (check its logs — it should be idle).
# Only then run this script.

set -euo pipefail

OLD_URL="${1:?Usage: migrate-db.sh OLD_DATABASE_URL NEW_DATABASE_URL}"
NEW_URL="${2:?Usage: migrate-db.sh OLD_DATABASE_URL NEW_DATABASE_URL}"
DUMP_FILE="referral_platform_$(date +%Y%m%d_%H%M%S).dump"

echo "== 1/4: Dumping OLD database (consistent snapshot) =="
pg_dump "$OLD_URL" --format=custom --no-owner --no-acl --file="$DUMP_FILE"
echo "Saved: $DUMP_FILE ($(du -h "$DUMP_FILE" | cut -f1))"

echo "== 2/4: Restoring into NEW database =="
pg_restore --clean --if-exists --no-owner --no-acl --dbname="$NEW_URL" "$DUMP_FILE"

echo "== 3/4: Verifying row counts match, table by table =="
TABLES=(User ChannelShard GroupShard MonthlyPayout AdminUser AuditLog)
MISMATCH=0
for T in "${TABLES[@]}"; do
  OLD_COUNT=$(psql "$OLD_URL" -t -A -c "SELECT COUNT(*) FROM \"$T\";")
  NEW_COUNT=$(psql "$NEW_URL" -t -A -c "SELECT COUNT(*) FROM \"$T\";")
  if [ "$OLD_COUNT" != "$NEW_COUNT" ]; then
    echo "  ❌ $T: old=$OLD_COUNT new=$NEW_COUNT — MISMATCH"
    MISMATCH=1
  else
    echo "  ✅ $T: $OLD_COUNT rows on both"
  fi
done

echo "== 4/4: Result =="
if [ "$MISMATCH" -eq 1 ]; then
  echo "❌ Row counts do NOT match. Do not switch the webhook/DNS over yet."
  echo "   Keep MAINTENANCE_MODE=true on the old host and investigate before retrying."
  exit 1
fi

echo "✅ All tables match. Safe to:"
echo "   1. Point BOT_WEBHOOK_URL / NEXT_PUBLIC_SITE_URL / DNS at the new host."
echo "   2. Set MAINTENANCE_MODE=false on the NEW host only."
echo "   3. Keep MAINTENANCE_MODE=true on the OLD host and leave it running"
echo "      for a day as a cold rollback, then decommission it."
echo ""
echo "Keeping $DUMP_FILE — safe to delete once you've confirmed the new host"
echo "is stable (it's your rollback copy in the meantime)."
