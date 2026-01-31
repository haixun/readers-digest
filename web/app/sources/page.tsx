import { redirect } from 'next/navigation';
import { createSupabaseServerClient } from '@/lib/supabase/server';
import SignOutButton from '@/components/SignOutButton';

export default async function SourcesPage() {
  const supabase = createSupabaseServerClient();
  const { data } = await supabase.auth.getUser();
  if (!data.user) {
    redirect('/login');
  }

  return (
    <section>
      <h1>Sources</h1>
      <p>Signed in as {data.user.email}</p>
      <SignOutButton />
      <p>Manage your channels, blogs, and individual videos here.</p>
    </section>
  );
}
