-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "public";

-- CreateEnum
CREATE TYPE "ListingKind" AS ENUM ('DONATION_TIER', 'SERVICE_OFFER', 'NFT_GIFT_SALE');

-- CreateEnum
CREATE TYPE "ListingStatus" AS ENUM ('ACTIVE', 'RESERVED', 'SOLD', 'HIDDEN', 'EXPIRED');

-- CreateEnum
CREATE TYPE "PaymentMethod" AS ENUM ('TELEGRAM_STARS', 'TON', 'NFT_GIFT');

-- CreateEnum
CREATE TYPE "TransactionStatus" AS ENUM ('PENDING', 'AWAITING_PAYMENT', 'PAID', 'SETTLED', 'REFUNDED', 'FAILED', 'EXPIRED');

-- CreateEnum
CREATE TYPE "DonationTier" AS ENUM ('MICRO', 'MAJOR', 'WHALE');

-- CreateEnum
CREATE TYPE "GiftRarity" AS ENUM ('COMMON', 'RARE', 'EPIC', 'LEGENDARY');

-- CreateEnum
CREATE TYPE "ThemeRarity" AS ENUM ('FREE', 'PREMIUM', 'LEGENDARY');

-- CreateEnum
CREATE TYPE "ThemeEffect" AS ENUM ('NONE', 'LOW_POLY', 'CYBERPUNK_GRID', 'GOLD_ROYALTY', 'CRT_SCANLINES', 'AURORA');

-- CreateEnum
CREATE TYPE "BannerStyle" AS ENUM ('SOLID', 'GRADIENT', 'HOLOGRAM', 'MARQUEE', 'PIXEL');

-- CreateEnum
CREATE TYPE "LeaderboardScope" AS ENUM ('DAILY', 'WEEKLY', 'ALL_TIME');

-- CreateEnum
CREATE TYPE "GiftTransferState" AS ENUM ('HELD_BY_OWNER', 'IN_ESCROW', 'TRANSFERRED', 'RECLAIMED');

-- CreateTable
CREATE TABLE "users" (
    "id" TEXT NOT NULL,
    "telegramId" BIGINT NOT NULL,
    "username" TEXT,
    "displayName" TEXT NOT NULL,
    "photoUrl" TEXT,
    "languageCode" VARCHAR(8),
    "isPremium" BOOLEAN NOT NULL DEFAULT false,
    "isBanned" BOOLEAN NOT NULL DEFAULT false,
    "tonWalletRaw" TEXT,
    "tonProofAt" TIMESTAMP(3),
    "starsDonated" INTEGER NOT NULL DEFAULT 0,
    "starsReceived" INTEGER NOT NULL DEFAULT 0,
    "giftsDonated" INTEGER NOT NULL DEFAULT 0,
    "giftsReceived" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "lastSeenAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "users_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "rooms" (
    "id" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT NOT NULL DEFAULT '',
    "emoji" TEXT NOT NULL DEFAULT '🏛',
    "accent" TEXT NOT NULL DEFAULT '#49df64',
    "capacity" INTEGER NOT NULL DEFAULT 50,
    "isHidden" BOOLEAN NOT NULL DEFAULT false,
    "sortOrder" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "rooms_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "stand_themes" (
    "id" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT NOT NULL DEFAULT '',
    "rarity" "ThemeRarity" NOT NULL DEFAULT 'FREE',
    "priceStars" INTEGER NOT NULL DEFAULT 0,
    "effect" "ThemeEffect" NOT NULL DEFAULT 'NONE',
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "palette" JSONB NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "stand_themes_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "user_themes" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "themeId" TEXT NOT NULL,
    "transactionId" TEXT,
    "unlockedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "user_themes_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "stands" (
    "id" TEXT NOT NULL,
    "ownerId" TEXT NOT NULL,
    "roomId" TEXT,
    "title" TEXT NOT NULL DEFAULT 'My Stand',
    "goal" TEXT,
    "goalTargetStars" INTEGER,
    "themeId" TEXT NOT NULL,
    "bannerStyle" "BannerStyle" NOT NULL DEFAULT 'GRADIENT',
    "totalStarsReceived" INTEGER NOT NULL DEFAULT 0,
    "totalGiftsReceived" INTEGER NOT NULL DEFAULT 0,
    "supporterCount" INTEGER NOT NULL DEFAULT 0,
    "isPublished" BOOLEAN NOT NULL DEFAULT true,
    "version" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "stands_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "listings" (
    "id" TEXT NOT NULL,
    "standId" TEXT NOT NULL,
    "kind" "ListingKind" NOT NULL,
    "status" "ListingStatus" NOT NULL DEFAULT 'ACTIVE',
    "title" TEXT NOT NULL,
    "description" TEXT,
    "priceStars" INTEGER,
    "priceNanoton" DECIMAL(38,0),
    "position" INTEGER NOT NULL DEFAULT 0,
    "soldCount" INTEGER NOT NULL DEFAULT 0,
    "supply" INTEGER,
    "giftId" TEXT,
    "expiresAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "listings_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "gifts" (
    "id" TEXT NOT NULL,
    "telegramGiftId" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "rarity" "GiftRarity" NOT NULL DEFAULT 'COMMON',
    "previewUrl" TEXT,
    "attributes" JSONB NOT NULL DEFAULT '[]',
    "ownerId" TEXT NOT NULL,
    "state" "GiftTransferState" NOT NULL DEFAULT 'HELD_BY_OWNER',
    "escrowedForTxId" TEXT,
    "escrowedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "gifts_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "donation_transactions" (
    "id" TEXT NOT NULL,
    "donorId" TEXT,
    "receiverId" TEXT NOT NULL,
    "standId" TEXT NOT NULL,
    "roomId" TEXT,
    "listingId" TEXT,
    "giftId" TEXT,
    "method" "PaymentMethod" NOT NULL,
    "status" "TransactionStatus" NOT NULL DEFAULT 'PENDING',
    "tier" "DonationTier" NOT NULL DEFAULT 'MICRO',
    "amountStars" INTEGER NOT NULL DEFAULT 0,
    "feeStars" INTEGER NOT NULL DEFAULT 0,
    "netStars" INTEGER NOT NULL DEFAULT 0,
    "feeBps" INTEGER NOT NULL DEFAULT 500,
    "amountNanoton" DECIMAL(38,0),
    "feeNanoton" DECIMAL(38,0),
    "valuationStars" INTEGER NOT NULL DEFAULT 0,
    "isAnonymous" BOOLEAN NOT NULL DEFAULT false,
    "message" VARCHAR(280),
    "invoicePayload" TEXT,
    "telegramChargeId" TEXT,
    "tonTxHash" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,
    "settledAt" TIMESTAMP(3),
    "refundedAt" TIMESTAMP(3),

    CONSTRAINT "donation_transactions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "room_sessions" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "roomId" TEXT NOT NULL,
    "nodeId" TEXT NOT NULL,
    "socketId" TEXT NOT NULL,
    "joinedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "lastHeartbeat" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "leftAt" TIMESTAMP(3),

    CONSTRAINT "room_sessions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "leaderboard_entries" (
    "id" TEXT NOT NULL,
    "scope" "LeaderboardScope" NOT NULL,
    "bucket" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "starsDonated" INTEGER NOT NULL DEFAULT 0,
    "giftsDonated" INTEGER NOT NULL DEFAULT 0,
    "rank" INTEGER NOT NULL DEFAULT 0,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "leaderboard_entries_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "processed_events" (
    "id" TEXT NOT NULL,
    "source" VARCHAR(32) NOT NULL,
    "externalId" TEXT NOT NULL,
    "processedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "processed_events_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "users_telegramId_key" ON "users"("telegramId");

-- CreateIndex
CREATE UNIQUE INDEX "users_tonWalletRaw_key" ON "users"("tonWalletRaw");

-- CreateIndex
CREATE INDEX "users_tonWalletRaw_idx" ON "users"("tonWalletRaw");

-- CreateIndex
CREATE INDEX "users_starsDonated_idx" ON "users"("starsDonated" DESC);

-- CreateIndex
CREATE INDEX "users_lastSeenAt_idx" ON "users"("lastSeenAt");

-- CreateIndex
CREATE UNIQUE INDEX "rooms_slug_key" ON "rooms"("slug");

-- CreateIndex
CREATE INDEX "rooms_isHidden_sortOrder_idx" ON "rooms"("isHidden", "sortOrder");

-- CreateIndex
CREATE UNIQUE INDEX "stand_themes_slug_key" ON "stand_themes"("slug");

-- CreateIndex
CREATE INDEX "stand_themes_isActive_rarity_idx" ON "stand_themes"("isActive", "rarity");

-- CreateIndex
CREATE UNIQUE INDEX "user_themes_transactionId_key" ON "user_themes"("transactionId");

-- CreateIndex
CREATE INDEX "user_themes_userId_idx" ON "user_themes"("userId");

-- CreateIndex
CREATE UNIQUE INDEX "user_themes_userId_themeId_key" ON "user_themes"("userId", "themeId");

-- CreateIndex
CREATE UNIQUE INDEX "stands_ownerId_key" ON "stands"("ownerId");

-- CreateIndex
CREATE INDEX "stands_roomId_isPublished_idx" ON "stands"("roomId", "isPublished");

-- CreateIndex
CREATE INDEX "stands_totalStarsReceived_idx" ON "stands"("totalStarsReceived" DESC);

-- CreateIndex
CREATE INDEX "stands_updatedAt_idx" ON "stands"("updatedAt" DESC);

-- CreateIndex
CREATE UNIQUE INDEX "listings_giftId_key" ON "listings"("giftId");

-- CreateIndex
CREATE INDEX "listings_standId_status_position_idx" ON "listings"("standId", "status", "position");

-- CreateIndex
CREATE INDEX "listings_status_kind_idx" ON "listings"("status", "kind");

-- CreateIndex
CREATE UNIQUE INDEX "gifts_telegramGiftId_key" ON "gifts"("telegramGiftId");

-- CreateIndex
CREATE UNIQUE INDEX "gifts_escrowedForTxId_key" ON "gifts"("escrowedForTxId");

-- CreateIndex
CREATE INDEX "gifts_ownerId_state_idx" ON "gifts"("ownerId", "state");

-- CreateIndex
CREATE INDEX "gifts_rarity_idx" ON "gifts"("rarity");

-- CreateIndex
CREATE UNIQUE INDEX "donation_transactions_invoicePayload_key" ON "donation_transactions"("invoicePayload");

-- CreateIndex
CREATE UNIQUE INDEX "donation_transactions_telegramChargeId_key" ON "donation_transactions"("telegramChargeId");

-- CreateIndex
CREATE UNIQUE INDEX "donation_transactions_tonTxHash_key" ON "donation_transactions"("tonTxHash");

-- CreateIndex
CREATE INDEX "donation_transactions_receiverId_status_createdAt_idx" ON "donation_transactions"("receiverId", "status", "createdAt" DESC);

-- CreateIndex
CREATE INDEX "donation_transactions_donorId_status_createdAt_idx" ON "donation_transactions"("donorId", "status", "createdAt" DESC);

-- CreateIndex
CREATE INDEX "donation_transactions_standId_createdAt_idx" ON "donation_transactions"("standId", "createdAt" DESC);

-- CreateIndex
CREATE INDEX "donation_transactions_roomId_createdAt_idx" ON "donation_transactions"("roomId", "createdAt" DESC);

-- CreateIndex
CREATE INDEX "donation_transactions_status_createdAt_idx" ON "donation_transactions"("status", "createdAt");

-- CreateIndex
CREATE INDEX "donation_transactions_tier_createdAt_idx" ON "donation_transactions"("tier", "createdAt" DESC);

-- CreateIndex
CREATE UNIQUE INDEX "room_sessions_socketId_key" ON "room_sessions"("socketId");

-- CreateIndex
CREATE INDEX "room_sessions_roomId_leftAt_idx" ON "room_sessions"("roomId", "leftAt");

-- CreateIndex
CREATE INDEX "room_sessions_userId_leftAt_idx" ON "room_sessions"("userId", "leftAt");

-- CreateIndex
CREATE INDEX "room_sessions_lastHeartbeat_idx" ON "room_sessions"("lastHeartbeat");

-- CreateIndex
CREATE INDEX "leaderboard_entries_scope_bucket_starsDonated_idx" ON "leaderboard_entries"("scope", "bucket", "starsDonated" DESC);

-- CreateIndex
CREATE UNIQUE INDEX "leaderboard_entries_scope_bucket_userId_key" ON "leaderboard_entries"("scope", "bucket", "userId");

-- CreateIndex
CREATE INDEX "processed_events_processedAt_idx" ON "processed_events"("processedAt");

-- CreateIndex
CREATE UNIQUE INDEX "processed_events_source_externalId_key" ON "processed_events"("source", "externalId");

-- AddForeignKey
ALTER TABLE "user_themes" ADD CONSTRAINT "user_themes_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "user_themes" ADD CONSTRAINT "user_themes_themeId_fkey" FOREIGN KEY ("themeId") REFERENCES "stand_themes"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "stands" ADD CONSTRAINT "stands_ownerId_fkey" FOREIGN KEY ("ownerId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "stands" ADD CONSTRAINT "stands_roomId_fkey" FOREIGN KEY ("roomId") REFERENCES "rooms"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "stands" ADD CONSTRAINT "stands_themeId_fkey" FOREIGN KEY ("themeId") REFERENCES "stand_themes"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "listings" ADD CONSTRAINT "listings_standId_fkey" FOREIGN KEY ("standId") REFERENCES "stands"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "listings" ADD CONSTRAINT "listings_giftId_fkey" FOREIGN KEY ("giftId") REFERENCES "gifts"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "gifts" ADD CONSTRAINT "gifts_ownerId_fkey" FOREIGN KEY ("ownerId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "donation_transactions" ADD CONSTRAINT "donation_transactions_donorId_fkey" FOREIGN KEY ("donorId") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "donation_transactions" ADD CONSTRAINT "donation_transactions_receiverId_fkey" FOREIGN KEY ("receiverId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "donation_transactions" ADD CONSTRAINT "donation_transactions_standId_fkey" FOREIGN KEY ("standId") REFERENCES "stands"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "donation_transactions" ADD CONSTRAINT "donation_transactions_roomId_fkey" FOREIGN KEY ("roomId") REFERENCES "rooms"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "donation_transactions" ADD CONSTRAINT "donation_transactions_listingId_fkey" FOREIGN KEY ("listingId") REFERENCES "listings"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "donation_transactions" ADD CONSTRAINT "donation_transactions_giftId_fkey" FOREIGN KEY ("giftId") REFERENCES "gifts"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "room_sessions" ADD CONSTRAINT "room_sessions_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "room_sessions" ADD CONSTRAINT "room_sessions_roomId_fkey" FOREIGN KEY ("roomId") REFERENCES "rooms"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "leaderboard_entries" ADD CONSTRAINT "leaderboard_entries_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

