from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from config import CONTENT_INDEX_FILE


@dataclass
class ContentRecord:
    content_id: str
    source_type: str
    origin: Optional[str]
    original_url: str
    title: str
    summary_path: Optional[str]
    published_at: Optional[str]
    author: Optional[str]
    categories: List[str]
    tags: List[str]
    raw_path: Optional[str]
    last_updated: str


class ContentIndex:
    def __init__(self, path: Path = CONTENT_INDEX_FILE):
        self.path = Path(path)
        self._records: Dict[str, ContentRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            return
        with self.path.open("r", encoding="utf-8") as handle:
            raw_records = json.load(handle)
        for item in raw_records:
            if "origin" not in item:
                item["origin"] = None
            record = ContentRecord(**item)
            self._records[record.content_id] = record

    def upsert(self, record: ContentRecord) -> None:
        self._records[record.content_id] = record

    def get(self, content_id: str) -> Optional[ContentRecord]:
        return self._records.get(content_id)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump([asdict(record) for record in self._records.values()], handle, indent=2, ensure_ascii=False)

    def all(self) -> Iterable[ContentRecord]:
        return self._records.values()

    def dedupe_by_url(self) -> None:
        by_url: Dict[str, List[ContentRecord]] = {}
        for record in self._records.values():
            by_url.setdefault(record.original_url, []).append(record)

        def _parse_date(value: Optional[str]) -> Optional[datetime]:
            if not value:
                return None
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None

        for url, records in by_url.items():
            if len(records) <= 1:
                continue
            records.sort(
                key=lambda item: (
                    _parse_date(item.published_at) is None,
                    _parse_date(item.published_at) or datetime.min.replace(tzinfo=timezone.utc),
                    item.last_updated,
                ),
                reverse=True,
            )
            keep = records[0].content_id
            for record in records[1:]:
                if record.content_id != keep and record.content_id in self._records:
                    del self._records[record.content_id]

    @staticmethod
    def build_record(
        *,
        content_id: str,
        source_type: str,
        origin: str | None,
        original_url: str,
        title: str,
        raw_path: Optional[Path],
        summary_path: Optional[Path],
        published_at: Optional[str],
        author: Optional[str],
        categories: List[str],
        tags: List[str],
    ) -> ContentRecord:
        return ContentRecord(
            content_id=content_id,
            source_type=source_type,
            origin=origin,
            original_url=original_url,
            title=title,
            summary_path=str(summary_path) if summary_path else None,
            raw_path=str(raw_path) if raw_path else None,
            published_at=published_at,
            author=author,
            categories=categories,
            tags=tags,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )
