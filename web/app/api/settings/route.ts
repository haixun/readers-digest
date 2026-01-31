import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { createSupabaseServerClient } from '@/lib/supabase/server';

export async function GET() {
  const supabase = createSupabaseServerClient();
  const { data } = await supabase.auth.getUser();
  if (!data.user) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const settings = await prisma.userSettings.findUnique({
    where: { userId: data.user.id },
  });

  return NextResponse.json({
    defaultModel: settings?.defaultModel ?? process.env.DEFAULT_MODEL ?? 'gpt-4.1-mini',
    hasApiKey: Boolean(settings?.openaiApiKeyEncrypted),
  });
}

export async function POST(request: Request) {
  const supabase = createSupabaseServerClient();
  const { data } = await supabase.auth.getUser();
  if (!data.user) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const payload = await request.json();
  const defaultModel = String(payload.defaultModel || '').trim();
  if (!defaultModel) {
    return NextResponse.json({ error: 'defaultModel required' }, { status: 400 });
  }

  await prisma.userSettings.upsert({
    where: { userId: data.user.id },
    update: {
      defaultModel,
      openaiApiKeyEncrypted: payload.openaiApiKeyEncrypted ?? undefined,
    },
    create: {
      userId: data.user.id,
      defaultModel,
      openaiApiKeyEncrypted: payload.openaiApiKeyEncrypted ?? undefined,
    },
  });

  return NextResponse.json({ ok: true });
}
