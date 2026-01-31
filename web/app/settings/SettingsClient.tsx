'use client';

import { useEffect, useState } from 'react';

type PromptPayload = {
  key: string;
  default: { system: string; user: string };
  global?: { system: string; user: string; promptVersion: number } | null;
};

export default function SettingsClient() {
  const [defaultModel, setDefaultModel] = useState('gpt-4.1-mini');
  const [apiKey, setApiKey] = useState('');
  const [promptKey, setPromptKey] = useState('youtube_video');
  const [promptSystem, setPromptSystem] = useState('');
  const [promptUser, setPromptUser] = useState('');
  const [status, setStatus] = useState('');

  const loadSettings = async () => {
    const res = await fetch('/api/settings');
    if (!res.ok) return;
    const payload = await res.json();
    setDefaultModel(payload.defaultModel || 'gpt-4.1-mini');
  };

  const loadPrompt = async (key: string) => {
    const res = await fetch(`/api/prompts/${key}`);
    if (!res.ok) return;
    const payload: PromptPayload = await res.json();
    setPromptSystem(payload.global?.system || payload.default.system);
    setPromptUser(payload.global?.user || payload.default.user);
  };

  useEffect(() => {
    loadSettings();
    loadPrompt(promptKey);
  }, []);

  const saveSettings = async () => {
    setStatus('Saving settings...');
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ defaultModel, openaiApiKeyEncrypted: apiKey })
    });
    setStatus(res.ok ? 'Settings saved.' : 'Failed to save settings.');
    setApiKey('');
  };

  const savePrompt = async () => {
    setStatus('Saving prompt...');
    const res = await fetch(`/api/prompts/${promptKey}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ system: promptSystem, user: promptUser })
    });
    setStatus(res.ok ? 'Prompt saved.' : 'Failed to save prompt.');
  };

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div>
        <h2>OpenAI Settings</h2>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <label>Default model</label>
          <input value={defaultModel} onChange={(e) => setDefaultModel(e.target.value)} />
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 8 }}>
          <label>API key</label>
          <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        </div>
        <button onClick={saveSettings} style={{ marginTop: 12 }}>Save settings</button>
      </div>

      <div>
        <h2>Global prompt</h2>
        <div style={{ marginBottom: 12 }}>
          <select value={promptKey} onChange={(e) => { setPromptKey(e.target.value); loadPrompt(e.target.value); }}>
            <option value="youtube_video">YouTube Video</option>
            <option value="blog_post">Blog Post</option>
          </select>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <label>System</label>
          <textarea rows={4} value={promptSystem} onChange={(e) => setPromptSystem(e.target.value)} />
          <label>User</label>
          <textarea rows={6} value={promptUser} onChange={(e) => setPromptUser(e.target.value)} />
        </div>
        <button onClick={savePrompt} style={{ marginTop: 12 }}>Save prompt</button>
      </div>

      {status && <p>{status}</p>}
    </section>
  );
}
