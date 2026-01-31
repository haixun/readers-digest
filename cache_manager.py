from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from config import RAW_CACHE_DIR, SUMMARY_CACHE_DIR


class CacheManager:
    def __init__(self, *, raw_dir: Path = RAW_CACHE_DIR, summary_dir: Path = SUMMARY_CACHE_DIR):
        self.raw_dir = raw_dir
        self.summary_dir = summary_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.summary_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sha256(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def raw_path(self, source_type: str, content_id: str) -> Path:
        return self.raw_dir / source_type / f"{content_id}.json"

    def load_raw(self, source_type: str, content_id: str) -> Optional[Dict[str, Any]]:
        path = self.raw_path(source_type, content_id)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save_raw(self, source_type: str, content_id: str, payload: Dict[str, Any]) -> None:
        path = self.raw_path(source_type, content_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {**payload}
        payload.setdefault("cached_at", self._utc_now())
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)

    def raw_is_current(self, source_type: str, content_id: str, content_hash: str) -> bool:
        cached = self.load_raw(source_type, content_id)
        if not cached:
            return False
        return cached.get("content_hash") == content_hash

    def save_summary(self, content_id: str, summary: Dict[str, Any]) -> None:
        path = self.summary_dir / f"{content_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        summary = {**summary}
        summary.setdefault("cached_at", self._utc_now())
        with path.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, ensure_ascii=False)

    def load_summary(self, content_id: str) -> Optional[Dict[str, Any]]:
        path = self.summary_dir / f"{content_id}.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()
