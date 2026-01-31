'use client';

import { useState } from 'react';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';

export default function LoginPage() {
  const supabase = createSupabaseBrowserClient();
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(false);

  const signIn = async () => {
    setLoading(true);
    setStatus('');
    const { error } = await supabase.auth.signInWithOtp({ email });
    if (error) {
      setStatus(error.message);
    } else {
      setStatus('Check your email for the login link.');
    }
    setLoading(false);
  };

  return (
    <section style={{ maxWidth: 420 }}>
      <h1>Login</h1>
      <p>Use your email to sign in.</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <input
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          style={{ padding: 10, borderRadius: 8, border: '1px solid #cbd5f5' }}
        />
        <button onClick={signIn} disabled={!email || loading} style={{ padding: 10 }}>
          {loading ? 'Sending…' : 'Send login link'}
        </button>
        {status && <p>{status}</p>}
      </div>
    </section>
  );
}
