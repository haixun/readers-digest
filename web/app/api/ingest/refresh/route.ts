import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

export async function POST(request: Request) {
  const header = request.headers.get('x-cron-secret');
  if (process.env.CRON_SECRET && header !== process.env.CRON_SECRET) {
    return NextResponse.json({ error: 'forbidden' }, { status: 403 });
  }

  const sources = await prisma.source.findMany();
  let created = 0;

  for (const source of sources) {
    if (source.type === 'youtube_video') {
      // TODO: extract videoId and fetch metadata.
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
    if (source.type === 'youtube_channel') {
      // TODO: fetch channel feed and insert per-video content items.
    }
  }

  return NextResponse.json({ ok: true, created });
}
