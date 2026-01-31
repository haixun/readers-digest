import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { createSupabaseServerClient } from '@/lib/supabase/server';
import { isAdminEmail } from '@/lib/auth';

const DEFAULT_PROMPTS: Record<string, { system: string; user: string }> = {
  youtube_video: {
    system: 'You are an assistant that writes crisp, well-structured executive summaries of YouTube transcripts.',
    user: 'Summarize the following YouTube video transcript. Include **Key Points:** with 3-5 bullets.\n\nVideo Title: {title}\nChannel: {channel}\nPublished At: {published_at}\nTags: {tags}\nTranscript:\n"""\n{transcript}\n"""'
  },
  blog_post: {
    system: 'You craft precise executive summaries of long-form blog posts and newsletters for busy readers.',
    user: 'Summarize the following article and add **Key Points:**.\n\nArticle Title: {title}\nAuthor: {author}\nPublished At: {published_at}\nURL: {url}\nTags: {tags}\nContent:\n"""\n{content}\n"""'
  }
};

export async function GET(_: Request, { params }: { params: { key: string } }) {
  const supabase = createSupabaseServerClient();
  const { data } = await supabase.auth.getUser();
  if (!data.user) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const key = params.key;
  const defaultPrompt = DEFAULT_PROMPTS[key];
  if (!defaultPrompt) {
    return NextResponse.json({ error: 'unknown prompt key' }, { status: 404 });
  }

  const globalPrompt = await prisma.prompt.findUnique({
    where: { key_scope_userId: { key, scope: 'global', userId: null } }
  }).catch(() => null);
  const userPrompt = await prisma.prompt.findUnique({
    where: { key_scope_userId: { key, scope: 'user', userId: data.user.id } }
  }).catch(() => null);

  return NextResponse.json({
    key,
    default: defaultPrompt,
    global: globalPrompt,
    user: userPrompt,
    isAdmin: isAdminEmail(data.user.email),
  });
}

export async function POST(request: Request, { params }: { params: { key: string } }) {
  const supabase = createSupabaseServerClient();
  const { data } = await supabase.auth.getUser();
  if (!data.user) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const key = params.key;
  const defaultPrompt = DEFAULT_PROMPTS[key];
  if (!defaultPrompt) {
    return NextResponse.json({ error: 'unknown prompt key' }, { status: 404 });
  }

  const payload = await request.json();
  const system = String(payload.system || '').trim();
  const user = String(payload.user || '').trim();
  if (!system || !user) {
    return NextResponse.json({ error: 'system and user required' }, { status: 400 });
  }

  const scope = payload.scope === 'user' ? 'user' : 'global';
  if (scope === 'global' && !isAdminEmail(data.user.email)) {
    return NextResponse.json({ error: 'forbidden' }, { status: 403 });
  }

  const prompt = await prisma.prompt.upsert({
    where: { key_scope_userId: { key, scope, userId: scope === 'user' ? data.user.id : null } },
    update: { system, user, promptVersion: { increment: 1 } },
    create: { key, scope, userId: scope === 'user' ? data.user.id : null, system, user, promptVersion: 1 }
  });

  return NextResponse.json({ prompt });
}

export async function DELETE(_: Request, { params }: { params: { key: string } }) {
  const supabase = createSupabaseServerClient();
  const { data } = await supabase.auth.getUser();
  if (!data.user) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const key = params.key;
  await prisma.prompt.deleteMany({
    where: { key, scope: 'user', userId: data.user.id }
  });
  return NextResponse.json({ ok: true });
}
