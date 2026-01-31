import { XMLParser } from 'fast-xml-parser';

export type YouTubeVideo = {
  videoId: string;
  title: string;
  publishedAt?: string;
  channelId?: string;
  channelName?: string;
  url: string;
};

const parser = new XMLParser({ ignoreAttributes: false });

export async function fetchChannelVideos(channelId: string, limit = 30): Promise<YouTubeVideo[]> {
  const rssUrl = `https://www.youtube.com/feeds/videos.xml?channel_id=${channelId}`;
  const res = await fetch(rssUrl, { cache: 'no-store' });
  if (!res.ok) {
    throw new Error(`Failed to fetch RSS for channel ${channelId}`);
  }
  const xml = await res.text();
  const json = parser.parse(xml) as any;
  const entries = json?.feed?.entry ? (Array.isArray(json.feed.entry) ? json.feed.entry : [json.feed.entry]) : [];
  const items: YouTubeVideo[] = [];
  for (const entry of entries.slice(0, limit)) {
    const videoId = entry['yt:videoId'];
    const title = entry.title;
    const publishedAt = entry.published;
    const channelName = entry.author?.name;
    if (!videoId || !title) continue;
    items.push({
      videoId,
      title,
      publishedAt,
      channelId,
      channelName,
      url: `https://www.youtube.com/watch?v=${videoId}`
    });
  }
  return items;
}

export function extractVideoId(url: string): string | null {
  const match = url.match(/(?:v=|be\/|embed\/)([a-zA-Z0-9_-]{11})/);
  return match?.[1] || null;
}

export function extractChannelId(url: string): string | null {
  if (url.includes('/channel/')) {
    const parts = url.split('/channel/')[1].split(/[/?#]/);
    return parts[0] || null;
  }
  return null;
}
