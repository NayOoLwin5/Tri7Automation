-- CreateTable
CREATE TABLE "user" (
    "id" TEXT NOT NULL,
    "user_email" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "user_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "user_user_email_key" ON "user"("user_email");
