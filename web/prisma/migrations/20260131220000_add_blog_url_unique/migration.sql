-- Add unique constraint for blogUrl entries per user/source
CREATE UNIQUE INDEX IF NOT EXISTS "ContentItem_userId_sourceId_blogUrl_key"
ON "ContentItem"("userId", "sourceId", "blogUrl");
