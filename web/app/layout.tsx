import type { ReactNode } from 'react';

export const metadata = {
  title: 'Readers Digest',
  description: 'Shared transcript research with per-user sources'
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: 'system-ui, sans-serif', margin: 0 }}>
        <div style={{ display: 'flex', minHeight: '100vh' }}>
          <aside style={{ width: 240, borderRight: '1px solid #e2e8f0', padding: 16 }}>
            <h2 style={{ marginTop: 0 }}>Readers Digest</h2>
            <nav style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <a href="/sources">Sources</a>
              <a href="/settings">Settings</a>
            </nav>
          </aside>
          <main style={{ flex: 1, padding: 24 }}>{children}</main>
        </div>
      </body>
    </html>
  );
}
