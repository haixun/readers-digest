import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { createSupabaseServerClient } from '@/lib/supabase/server';

export async function GET() {
  const supabase = createSupabaseServerClient();
  const { data } = await supabase.auth.getUser();
  if (!data.user) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const sources = await prisma.source.findMany({
    where: { userId: data.user.id },
    orderBy: { createdAt: 'desc' },
  });

  return NextResponse.json({ sources });
}

export async function POST(request: Request) {
  const supabase = createSupabaseServerClient();
  const { data } = await supabase.auth.getUser();
  if (!data.user) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const payload = await request.json();
  const type = String(payload.type || '').trim();
  const url = String(payload.url || '').trim();
  const title = payload.title ? String(payload.title).trim() : undefined;
  const category = payload.category ? String(payload.category).trim() : undefined;
  const tags = Array.isArray(payload.tags) ? payload.tags.map((t: string) => String(t).trim()).filter(Boolean) : [];

  if (!type || !url) {
    return NextResponse.json({ error: 'type and url are required' }, { status: 400 });
  }

  const source = await prisma.source.create({
    data: {
      userId: data.user.id,
      type,
      url,
      title,
      category,
      tags,
    },
  });

  return NextResponse.json({ source });
}
