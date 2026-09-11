-- AlterTable
ALTER TABLE "identity_verifications" ADD COLUMN     "rejection_count" INTEGER NOT NULL DEFAULT 0;

-- AlterTable
ALTER TABLE "users" ADD COLUMN     "aadhaar_hash" TEXT,
ADD COLUMN     "aadhaar_last4" TEXT,
ADD COLUMN     "fake_referral_count" INTEGER NOT NULL DEFAULT 0;

-- CreateIndex
CREATE UNIQUE INDEX "users_aadhaar_hash_key" ON "users"("aadhaar_hash");

