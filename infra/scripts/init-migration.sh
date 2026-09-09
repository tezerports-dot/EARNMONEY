#!/usr/bin/env bash
set -euo pipefail

# Run this ONCE, before the first deployment anywhere, from a machine that
# has normal internet access (your laptop, Claude Code's environment, or the
# VPS itself) — NOT from a network-restricted sandbox. It needs to reach
# binaries.prisma.sh, which the build/dev sandbox this repo was scaffolded in
# could not do.
#
# What it does: generates prisma/migrations/<timestamp>_init/ from the
# current schema.prisma, and applies it to whatever DATABASE_URL points at.
# Commit the generated prisma/migrations/ folder afterwards — from then on,
# `prisma migrate deploy` (used in docker-compose.prod.yml) will work
# normally in any environment, restricted or not, because it only reads the
# already-generated SQL rather than computing a new diff.
#
# Usage:
#   docker compose up -d postgres          # make sure a DB is reachable
#   cp .env.example .env && edit DATABASE_URL if needed
#   ./infra/scripts/init-migration.sh

cd "$(dirname "$0")/../../apps/api"

if [ ! -f .env ] && [ ! -f ../../.env ]; then
  echo "No .env found. Copy .env.example to .env first (see README)." >&2
  exit 1
fi

npm install
npx prisma migrate dev --name init
npx prisma generate

echo ""
echo "Done. prisma/migrations/ now contains real migration SQL — commit it."
echo "From now on, 'npx prisma migrate deploy' will work anywhere, including"
echo "network-restricted environments, since it just applies existing SQL."
