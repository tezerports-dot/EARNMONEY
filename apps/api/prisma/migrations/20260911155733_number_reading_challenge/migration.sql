-- CreateEnum
CREATE TYPE "ChallengeKind" AS ENUM ('NUMBER_READING', 'DOCUMENT_REVIEW');

-- DropForeignKey
ALTER TABLE "challenge_attempts" DROP CONSTRAINT "challenge_attempts_scenario_id_fkey";

-- AlterTable
ALTER TABLE "challenge_attempts" ADD COLUMN     "expected_answer" TEXT,
ADD COLUMN     "kind" "ChallengeKind" NOT NULL DEFAULT 'NUMBER_READING',
ADD COLUMN     "prompt" JSONB,
ALTER COLUMN "scenario_id" DROP NOT NULL;

-- AddForeignKey
ALTER TABLE "challenge_attempts" ADD CONSTRAINT "challenge_attempts_scenario_id_fkey" FOREIGN KEY ("scenario_id") REFERENCES "kyc_training_scenarios"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- Backfill: every attempt that already exists was a document review, so the
-- NUMBER_READING default above would relabel history as a challenge type that
-- did not exist when those rows were written.
UPDATE "challenge_attempts" SET "kind" = 'DOCUMENT_REVIEW' WHERE "scenario_id" IS NOT NULL;
