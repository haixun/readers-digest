'use client';

import { useEffect, useState } from 'react';

type Source = {
  id: string;
  type: string;
  url: string;
  title?: string | null;
  category?: string | null;
  tags: string[];
};

export default function SourcesClient() {
  const [sources, setSources] = useState<Source[]>([]);
  const [type, setType] = useState('youtube_channel');
  const [url, setUrl] = useState('');
  const [status, setStatus] = useState('');

  const loadSources = async () => {
    const res = await fetch('/api/sources');
    if (!res.ok) {
      setStatus('Failed to load sources');
      return;
    }
    const payload = await res.json();
    setSources(payload.sources || []);
  };

  useEffect(() => {
    loadSources();
  }, []);

  const addSource = async () => {
    setStatus('');
    if (!url) {
      setStatus('URL required');
      return;
    }
    const res = await fetch('/api/sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, url })
    });
    if (!res.ok) {
      const payload = await res.json();
      setStatus(payload.error || 'Failed to add source');
      return;
    }
    setUrl('');
    await loadSources();
  };

  return (
    <section>
      <div style={{ margin: '16px 0', display: 'flex', gap: 8 }}>
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="youtube_channel">YouTube Channel</option>
          <option value="youtube_video">YouTube Video</option>
          <option value="blog">Blog</option>
        </select>
        <input
          type="url"
          placeholder="https://"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          style={{ flex: 1 }}
        />
        <button onClick={addSource}>Add</button>
      </div>
      {status && <p>{status}</p>}
      <ul>
        {sources.map((source) => (
          <li key={source.id}>
            <strong>{source.type}</strong> — {source.url}
          </li>
        ))}
      </ul>
    </section>
  );
}
