-- AlterTable
ALTER TABLE "challenge_attempts" ADD COLUMN     "item_id" TEXT;

-- CreateTable
CREATE TABLE "number_reading_items" (
    "id" TEXT NOT NULL,
    "number" TEXT NOT NULL,
    "question" TEXT NOT NULL,
    "expected_answer" TEXT NOT NULL,
    "answer_hint" TEXT,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "number_reading_items_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "number_reading_items_is_active_idx" ON "number_reading_items"("is_active");

-- CreateIndex
CREATE UNIQUE INDEX "number_reading_items_number_question_key" ON "number_reading_items"("number", "question");

-- CreateIndex
CREATE INDEX "challenge_attempts_candidate_user_id_item_id_idx" ON "challenge_attempts"("candidate_user_id", "item_id");

-- AddForeignKey
ALTER TABLE "challenge_attempts" ADD CONSTRAINT "challenge_attempts_item_id_fkey" FOREIGN KEY ("item_id") REFERENCES "number_reading_items"("id") ON DELETE SET NULL ON UPDATE CASCADE;
