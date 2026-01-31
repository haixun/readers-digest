import crypto from 'crypto';
import { YoutubeTranscript } from 'youtube-transcript';

export async function fetchTranscript(videoId: string) {
  const transcript = await YoutubeTranscript.fetchTranscript(videoId, { lang: 'en' });
  const text = transcript.map((item) => item.text).join(' ');
  const hash = crypto.createHash('sha256').update(text).digest('hex');
  return { text, hash };
}
