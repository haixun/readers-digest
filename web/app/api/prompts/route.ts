import { NextResponse } from 'next/server';

const DEFAULT_KEYS = ['youtube_video', 'blog_post'];

export async function GET() {
  return NextResponse.json({ keys: DEFAULT_KEYS });
}
