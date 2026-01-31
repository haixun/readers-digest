import { redirect } from 'next/navigation';
import { createSupabaseServerClient } from '@/lib/supabase/server';
import SignOutButton from '@/components/SignOutButton';
import SettingsClient from './SettingsClient';

export default async function SettingsPage() {
  const supabase = createSupabaseServerClient();
  const { data } = await supabase.auth.getUser();
  if (!data.user) {
    redirect('/login');
  }

  return (
    <section>
      <h1>Settings</h1>
      <p>Signed in as {data.user.email}</p>
      <SignOutButton />
      <SettingsClient />
    </section>
  );
}
