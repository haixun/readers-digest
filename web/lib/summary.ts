import crypto from 'crypto';

export function hashPrompt(system: string, user: string, model: string) {
  const payload = JSON.stringify({ system, user, model });
  return crypto.createHash('sha256').update(payload).digest('hex');
}

export function hashSummaryCache(input: {
  videoId?: string | null;
  transcriptHash?: string | null;
  promptHash: string;
  model: string;
  tags?: string[];
}) {
  const payload = JSON.stringify({
    videoId: input.videoId || null,
    transcriptHash: input.transcriptHash || null,
    promptHash: input.promptHash,
    model: input.model,
    tags: input.tags || []
  });
  return crypto.createHash('sha256').update(payload).digest('hex');
}
