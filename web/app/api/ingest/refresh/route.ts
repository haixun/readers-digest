import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { fetchChannelVideos, extractChannelId, extractVideoId } from '@/lib/youtube';
import { fetchTranscript } from '@/lib/transcript';

export async function POST(request: Request) {
  const header = request.headers.get('x-cron-secret');
  if (process.env.CRON_SECRET && header !== process.env.CRON_SECRET) {
    return NextResponse.json({ error: 'forbidden' }, { status: 403 });
  }

  const sources = await prisma.source.findMany();
  let created = 0;

  for (const source of sources) {
    if (source.type === 'youtube_video') {
      const videoId = extractVideoId(source.url);
      if (!videoId) continue;
      await prisma.video.upsert({
        where: { videoId },
        update: { canonicalUrl: source.url },
        create: { videoId, canonicalUrl: source.url }
      });
      await prisma.contentItem.upsert({
        where: {
          userId_sourceId_videoId: {
            userId: source.userId,
            sourceId: source.id,
            videoId
          }
        },
        update: {},
        create: {
          userId: source.userId,
          sourceId: source.id,
          videoId,
          title: source.title || source.url
        }
      });
      created += 1;
      const existing = await prisma.transcript.findUnique({ where: { videoId } });
      if (!existing) {
        try {
          const { text, hash } = await fetchTranscript(videoId);
          await prisma.transcript.create({
            data: { videoId, blobKey: `inline:${videoId}`, text, hash }
          });
        } catch {
          // ignore transcript failures for now
        }
      }
    }

    if (source.type === 'youtube_channel') {
      const channelId = extractChannelId(source.url);
      if (!channelId) continue;
      let videos = [];
      try {
        videos = await fetchChannelVideos(channelId, 30);
      } catch {
        continue;
      }
      for (const video of videos) {
        await prisma.video.upsert({
          where: { videoId: video.videoId },
          update: {
            canonicalUrl: video.url,
            title: video.title,
            channelId: video.channelId,
            channelName: video.channelName,
            publishedAt: video.publishedAt ? new Date(video.publishedAt) : undefined
          },
          create: {
            videoId: video.videoId,
            canonicalUrl: video.url,
            title: video.title,
            channelId: video.channelId,
            channelName: video.channelName,
            publishedAt: video.publishedAt ? new Date(video.publishedAt) : undefined
          }
        });

        await prisma.contentItem.upsert({
          where: {
            userId_sourceId_videoId: {
              userId: source.userId,
              sourceId: source.id,
              videoId: video.videoId
            }
          },
          update: {},
          create: {
            userId: source.userId,
            sourceId: source.id,
            videoId: video.videoId,
            title: video.title,
            publishedAt: video.publishedAt ? new Date(video.publishedAt) : undefined
          }
        });
        created += 1;

        const existing = await prisma.transcript.findUnique({ where: { videoId: video.videoId } });
        if (!existing) {
          try {
            const { text, hash } = await fetchTranscript(video.videoId);
            await prisma.transcript.create({
              data: { videoId: video.videoId, blobKey: `inline:${video.videoId}`, text, hash }
            });
          } catch {
            // ignore transcript failures for now
          }
        }
      }
    }

    if (source.type === 'blog') {
      await prisma.contentItem.upsert({
        where: {
          userId_sourceId_blogUrl: {
            userId: source.userId,
            sourceId: source.id,
            blogUrl: source.url
          }
        },
        update: {},
        create: {
          userId: source.userId,
          sourceId: source.id,
          blogUrl: source.url,
          title: source.title || source.url
        }
      });
      created += 1;
    }
  }

  return NextResponse.json({ ok: true, created });
}
