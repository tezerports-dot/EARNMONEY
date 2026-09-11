-- CreateEnum
CREATE TYPE "TickStatus" AS ENUM ('IN_PROGRESS', 'COMPLETED', 'FAILED');

-- AlterTable
ALTER TABLE "users" ADD COLUMN     "update_slot" INTEGER NOT NULL DEFAULT 0;

-- CreateTable
CREATE TABLE "content_versions" (
    "id" TEXT NOT NULL,
    "version" INTEGER NOT NULL,
    "title" TEXT NOT NULL,
    "body" TEXT NOT NULL,
    "link_url" TEXT,
    "published_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "is_current" BOOLEAN NOT NULL DEFAULT false,

    CONSTRAINT "content_versions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "user_update_states" (
    "id" TEXT NOT NULL,
    "user_id" TEXT NOT NULL,
    "delivered_version" INTEGER NOT NULL DEFAULT 0,
    "delivered_at" TIMESTAMP(3),
    "failure_count" INTEGER NOT NULL DEFAULT 0,
    "last_error" TEXT,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "user_update_states_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "schedule_ticks" (
    "id" TEXT NOT NULL,
    "slot_date" DATE NOT NULL,
    "slot" INTEGER NOT NULL,
    "status" "TickStatus" NOT NULL DEFAULT 'IN_PROGRESS',
    "enqueued_count" INTEGER NOT NULL DEFAULT 0,
    "started_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "completed_at" TIMESTAMP(3),
    "last_error" TEXT,

    CONSTRAINT "schedule_ticks_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "content_versions_version_key" ON "content_versions"("version");

-- CreateIndex
CREATE INDEX "content_versions_is_current_idx" ON "content_versions"("is_current");

-- CreateIndex
CREATE UNIQUE INDEX "user_update_states_user_id_key" ON "user_update_states"("user_id");

-- CreateIndex
CREATE INDEX "user_update_states_delivered_version_idx" ON "user_update_states"("delivered_version");

-- CreateIndex
CREATE INDEX "schedule_ticks_status_slot_date_idx" ON "schedule_ticks"("status", "slot_date");

-- CreateIndex
CREATE UNIQUE INDEX "schedule_ticks_slot_date_slot_key" ON "schedule_ticks"("slot_date", "slot");

-- CreateIndex
CREATE INDEX "users_update_slot_id_idx" ON "users"("update_slot", "id");

-- AddForeignKey
ALTER TABLE "user_update_states" ADD CONSTRAINT "user_update_states_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;


-- Backfill update_slot for accounts that existed before this column.
--
-- Without this every existing account keeps the DEFAULT 0 and the entire
-- pre-migration user base lands in a single slot — exactly the thundering
-- herd the slot design exists to prevent.
--
-- This must produce the SAME value as slotForUserId() in
-- src/scheduler/slot.util.ts, which is the first 4 bytes of SHA-256(id) read
-- big-endian, modulo the slot count. Postgres's sha256() takes bytea, and
-- get_byte() lets us reassemble the same uint32.
UPDATE "users"
SET "update_slot" = (
  (get_byte(sha256("id"::bytea), 0)::bigint << 24) |
  (get_byte(sha256("id"::bytea), 1)::bigint << 16) |
  (get_byte(sha256("id"::bytea), 2)::bigint << 8)  |
  (get_byte(sha256("id"::bytea), 3)::bigint)
) % 1440;
