# Reading Digest

A consolidated pipeline for tracking YouTube channels, individual videos, and blogs, generating
OpenAI-powered summaries, and serving them via a local web interface organised by category and
publication date.

## Quick Start

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt  # create if needed; at minimum flask, requests, beautifulsoup4, openai, pyyaml
   ```

2. **Set OpenAI credentials**
   ```bash
   cat <<'EOF' > .env.local
   OPENAI_API_KEY=sk-...
   OPENAI_MODEL=gpt-4.1-mini
   EOF
   ```

3. **Refresh the cache and summaries**
   ```bash
   python manage.py refresh
   ```
   This command parses `readinglist.md`, downloads any new source material, stores it under
   `cache/raw`, generates summaries under `cache/summaries`, and writes metadata to
   `data/content_index.json`. Use `--skip-summaries` if you only want to refresh raw content.
   YouTube transcripts are fetched on-demand, one at a time, from the web UI.

4. **Start the web UI**
   ```bash
   ./start_web_interface.sh
   ```
   Visit <http://localhost:5001> to browse summaries by category, see the latest updates, and
   regenerate summaries on demand.

   Keyboard shortcuts (selected item in the list):
   - `t` fetch transcript
   - `s` summarize / re-summarize

## Fetch a single transcript

If a YouTube item shows “Transcript unavailable” in the UI, fetch it on demand:

```bash
python manage.py fetch-transcript https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

This downloads one transcript and refreshes the index (no bulk fetching).

## Reading List Format

`readinglist.md` is the single source of truth for monitored content. Supported patterns:

```markdown
# Youtube Videos
- [Finance] https://www.youtube.com/watch?v=dQw4w9WgXcQ

# Youtube Channels
- [Technology] AI Explained: https://www.youtube.com/@aiexplained | tags: ai, research

# Blogs
- [Productivity] Writer Name: https://example.com/blog (tags: habits, systems)
```

- The section heading controls the default source type.
- The optional `[Category]` prefix overrides the category shown on the website.
- Append `tags:` or `author:` metadata using either `|` or parentheses.

## Prompts & Summaries

Prompt templates live in `prompts/summaries.yaml`. Edit them to fine-tune the summarisation style
without touching code. Each prompt has a `prompt_version`; bumping it forces the cache to refresh on
next summarisation run.

Summaries are cached under `cache/summaries/<content_id>.json` with the original prompt version and
content hash so reruns are only triggered when the source material or prompt changes. Usage stats per
summary are appended to `data/openai_usage.jsonl`.

## Caching Layout

```
cache/
  raw/
    blogs/<content_id>.json        # raw article bodies + metadata
    youtube/<content_id>.json      # raw YouTube transcripts + metadata
  summaries/<content_id>.json      # cached summary payloads

data/content_index.json            # master index consumed by the web UI
```

## Tests

Run the lightweight unit tests with:

```bash
pytest
```

These currently cover the reading list parser and cache manager. Extend them as the pipeline evolves.

## Troubleshooting

- **Missing dependencies** – install `requests`, `beautifulsoup4`, `flask`, `openai`, and `pyyaml`.
- **OpenAI errors** – ensure `OPENAI_API_KEY` is set and the selected model is available to your
  account.
- **Network issues** – the refresh command fetches live content; rerun once connectivity is restored.
