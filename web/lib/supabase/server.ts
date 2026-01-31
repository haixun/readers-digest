import { cookies } from 'next/headers';
import { createServerClient } from '@supabase/auth-helpers-nextjs';

type CookieStore = ReturnType<typeof cookies>;

export function createSupabaseServerClient(cookieStore?: CookieStore) {
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL || '',
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || process.env.SUPABASE_ANON_KEY || '',
    { cookies: () => cookieStore ?? cookies() }
  );
}
