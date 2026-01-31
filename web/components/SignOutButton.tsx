'use client';

import { createSupabaseBrowserClient } from '@/lib/supabase/client';

export default function SignOutButton() {
  const supabase = createSupabaseBrowserClient();

  const signOut = async () => {
    await supabase.auth.signOut();
    window.location.href = '/login';
  };

  return (
    <button onClick={signOut} style={{ padding: 8 }}>
      Sign out
    </button>
  );
}
