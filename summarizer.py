from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from cache_manager import CacheManager
from config import OPENAI_API_KEY, OPENAI_MODEL, PROMPTS_DIR, SUMMARY_CACHE_DIR, DATA_DIR, get_user_settings
from pipeline.content_index import ContentIndex, ContentRecord

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - surface clear error at runtime
    OpenAI = None  # type: ignore


USAGE_LOG = DATA_DIR / "openai_usage.jsonl"


@dataclass
class SummaryResult:
    content_id: str
    text: str
    model: str
    prompt_version: int
    usage: Dict[str, Any] | None
    summary_path: Path


class SummarizationError(RuntimeError):
    pass


class Summarizer:
    PROMPT_FILES = {"default": PROMPTS_DIR / "summaries.yaml"}

    def __init__(self, cache: CacheManager, *, model: str | None = None, prompts_key: str = "default"):
        if OpenAI is None:
            raise SummarizationError("openai package is not installed. Install with `pip install openai`." )
        settings = get_user_settings()
        api_key = settings.get("openai_api_key") or OPENAI_API_KEY
        model_name = model or settings.get("openai_model") or OPENAI_MODEL
        if not api_key:
            raise SummarizationError("OPENAI_API_KEY is not set. Put it in .env.local or export it before running.")

        self.cache = cache
        self.model = model_name
        self.client = OpenAI(api_key=api_key)
        self.prompts = self._load_prompts(self.PROMPT_FILES[prompts_key])

    def summarize(self, record: ContentRecord, *, force: bool = False) -> SummaryResult:
        raw_data = self.cache.load_raw(self._raw_source(record.source_type), record.content_id)
        if not raw_data:
            raise SummarizationError(f"Raw content not found for {record.content_id}")

        prompt_key = self._prompt_key(record.source_type)
        prompt_template = self.prompts[prompt_key]
        prompt_version = prompt_template.get("prompt_version", 1)
        existing = self.cache.load_summary(record.content_id)

        if (
            not force
            and existing
            and existing.get("content_hash") == raw_data.get("content_hash")
            and existing.get("prompt_version") == prompt_version
        ):
            summary_path = SUMMARY_CACHE_DIR / f"{record.content_id}.json"
            return SummaryResult(
                content_id=record.content_id,
                text=existing["summary"],
                model=existing.get("model", self.model),
                prompt_version=existing.get("prompt_version", prompt_version),
                usage=existing.get("usage"),
                summary_path=summary_path,
            )

        payload = self._build_payload(prompt_key, record, raw_data)
        messages = [
            {"role": "system", "content": prompt_template["system"].strip()},
            {"role": "user", "content": prompt_template["user"].format(**payload).strip()},
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3,
        )

        summary_text = response.choices[0].message.content.strip()
        usage = getattr(response, "usage", None)
        summary_payload = {
            "summary": summary_text,
            "model": self.model,
            "prompt_version": prompt_version,
            "content_hash": raw_data.get("content_hash"),
            "usage": usage.to_dict() if hasattr(usage, "to_dict") else usage,
        }
        self.cache.save_summary(record.content_id, summary_payload)
        summary_path = SUMMARY_CACHE_DIR / f"{record.content_id}.json"

        self._log_usage(record, summary_payload)

        return SummaryResult(
            content_id=record.content_id,
            text=summary_text,
            model=self.model,
            prompt_version=prompt_version,
            usage=summary_payload.get("usage"),
            summary_path=summary_path,
        )

    def _load_prompts(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            raise SummarizationError(f"Prompt file not found: {path}")
        with path.open("r", encoding="utf-8") as handle:
            prompts = yaml.safe_load(handle)
        return self._apply_prompt_overrides(prompts or {})

    def _apply_prompt_overrides(self, prompts: Dict[str, Any]) -> Dict[str, Any]:
        overrides_path = DATA_DIR / "prompt_overrides.json"
        if not overrides_path.exists():
            return prompts
        try:
            overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
        except Exception:
            return prompts
        for key, override in overrides.items():
            if key not in prompts or not isinstance(override, dict):
                continue
            merged = dict(prompts[key])
            for field in ("system", "user", "prompt_version"):
                if field in override:
                    merged[field] = override[field]
            prompts[key] = merged
        return prompts

    def _prompt_key(self, source_type: str) -> str:
        if source_type == "youtube_video":
            return "youtube_video"
        if source_type == "blog_article":
            return "blog_post"
        raise SummarizationError(f"Unsupported source type for summarization: {source_type}")

    def _raw_source(self, source_type: str) -> str:
        if source_type == "youtube_video":
            return "youtube"
        if source_type == "blog_article":
            return "blogs"
        raise SummarizationError(f"Unsupported source type for raw mapping: {source_type}")

    def _build_payload(self, prompt_key: str, record: ContentRecord, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        tags = self._merge_tags(record.content_id, record.tags or [])
        if prompt_key == "youtube_video":
            return {
                "title": record.title,
                "channel": raw_data.get("channel_name") or record.author or "Unknown Channel",
                "published_at": record.published_at or "Unknown",
                "transcript": (raw_data.get("transcript") or "")[:12000],
                "tags": tags,
            }
        return {
            "title": record.title,
            "author": raw_data.get("author") or record.author or "Unknown",
            "published_at": record.published_at or "Unknown",
            "url": record.original_url,
            "content": (raw_data.get("text") or "")[:12000],
            "tags": tags,
        }

    def _merge_tags(self, content_id: str, base_tags: list[str]) -> str:
        user_tags = []
        user_tags_path = DATA_DIR / "user_tags.json"
        if user_tags_path.exists():
            try:
                raw = json.loads(user_tags_path.read_text(encoding="utf-8"))
                if isinstance(raw.get(content_id), list):
                    user_tags = [tag for tag in raw.get(content_id) if isinstance(tag, str)]
            except Exception:
                user_tags = []
        merged = list(dict.fromkeys([*base_tags, *user_tags]))
        return ", ".join(merged) if merged else "None"

    def _log_usage(self, record: ContentRecord, summary_payload: Dict[str, Any]) -> None:
        usage = summary_payload.get("usage")
        log_entry = {
            "content_id": record.content_id,
            "source_type": record.source_type,
            "model": summary_payload.get("model"),
            "prompt_version": summary_payload.get("prompt_version"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "usage": usage,
        }
        USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with USAGE_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(log_entry) + "\n")


def summarize_all(index: ContentIndex, cache: CacheManager, *, force: bool = False) -> None:
    summarizer = Summarizer(cache)
    for record in index.all():
        try:
            result = summarizer.summarize(record, force=force)
            updated_record = ContentRecord(
                content_id=record.content_id,
                source_type=record.source_type,
                origin=record.origin,
                original_url=record.original_url,
                title=record.title,
                summary_path=str(result.summary_path),
                published_at=record.published_at,
                author=record.author,
                categories=record.categories,
                tags=record.tags,
                raw_path=record.raw_path,
                last_updated=datetime.now(timezone.utc).isoformat(),
            )
            index.upsert(updated_record)
        except SummarizationError as exc:  # pragma: no cover - runtime path
            print(f"⚠️  Skipping {record.content_id}: {exc}")
        except Exception as exc:  # pragma: no cover - runtime path
            print(f"⚠️  Error summarizing {record.content_id}: {exc}")
    index.save()


__all__ = ["Summarizer", "summarize_all", "SummarizationError", "SummaryResult"]
