#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE_DIR))

from cache_manager import CacheManager
from config import SUMMARY_CACHE_DIR
from pipeline.content_index import ContentIndex, ContentRecord
from pipeline.youtube_ingestor import YouTubeIngestor
from youtube_transcript import extract_video_id
TRANSCRIPT_METADATA_PATH = BASE_DIR / "transcript_metadata.json"


def parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_transcript_metadata() -> Dict[str, Dict[str, object]]:
    if not TRANSCRIPT_METADATA_PATH.exists():
        return {}
    try:
        return json.loads(TRANSCRIPT_METADATA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def choose_best_record(records: List[ContentRecord]) -> ContentRecord:
    def score(record: ContentRecord) -> Tuple[int, datetime, str]:
        published = parse_date(record.published_at)
        has_date = 1 if published else 0
        return (has_date, published or datetime.min.replace(tzinfo=timezone.utc), record.last_updated)

    return sorted(records, key=score, reverse=True)[0]


def dedupe_records(records: Dict[str, ContentRecord]) -> Tuple[Dict[str, ContentRecord], List[str]]:
    by_url: Dict[str, List[ContentRecord]] = {}
    for record in records.values():
        by_url.setdefault(record.original_url, []).append(record)

    cleaned: Dict[str, ContentRecord] = dict(records)
    removed: List[str] = []
    for url, grouped in by_url.items():
        if len(grouped) <= 1:
            continue
        keep = choose_best_record(grouped)
        for record in grouped:
            if record.content_id == keep.content_id:
                continue
            cleaned.pop(record.content_id, None)
            removed.append(record.content_id)
    return cleaned, removed


def main() -> None:
    cache = CacheManager()
    index = ContentIndex()
    ingestor = YouTubeIngestor(cache)
    transcript_metadata = load_transcript_metadata()

    records = {record.content_id: record for record in index.all()}
    channel_name_map: Dict[str, str] = {}
    for record in records.values():
        if record.source_type != "youtube_video" or record.origin != "youtube_channel":
            continue
        raw = cache.load_raw("youtube", record.content_id) or {}
        channel_id = raw.get("channel_id")
        channel_name = raw.get("channel_name")
        if channel_id and channel_name:
            channel_name_map.setdefault(channel_id, channel_name)

    updated = 0
    for record in list(records.values()):
        if record.source_type != "youtube_video" or record.origin != "youtube_channel":
            continue
        raw = cache.load_raw("youtube", record.content_id) or {}
        video_id = extract_video_id(record.original_url) or raw.get("video_id") or record.content_id
        channel_id = raw.get("channel_id")

        if not record.author:
            record.author = raw.get("channel_name") or record.author
            if not record.author:
                metadata = transcript_metadata.get(video_id)
                if metadata and metadata.get("channel_name"):
                    record.author = metadata.get("channel_name")
            if not record.author and channel_id and channel_id in channel_name_map:
                record.author = channel_name_map[channel_id]

        if not record.published_at:
            record.published_at = raw.get("published_at") or record.published_at

        if (not record.published_at or not record.author) and video_id:
            metadata = ingestor._fetch_single_video_metadata(video_id)
            if metadata:
                record.published_at = record.published_at or metadata.get("published_at")
                record.author = record.author or metadata.get("channel_name")
                if raw:
                    raw.setdefault("published_at", metadata.get("published_at"))
                    raw.setdefault("channel_name", metadata.get("channel_name"))
                    raw.setdefault("channel_id", metadata.get("channel_id"))
                    cache.save_raw("youtube", record.content_id, raw)
        if raw and channel_id and channel_id in channel_name_map and not raw.get("channel_name"):
            raw["channel_name"] = channel_name_map[channel_id]
            cache.save_raw("youtube", record.content_id, raw)

        records[record.content_id] = record
        updated += 1

    cleaned, removed = dedupe_records(records)
    index._records = cleaned  # intentional: maintenance pass
    index.save()

    for content_id in removed:
        raw_path = cache.raw_path("youtube", content_id)
        summary_path = SUMMARY_CACHE_DIR / f"{content_id}.json"
        if raw_path.exists():
            raw_path.unlink()
        if summary_path.exists():
            summary_path.unlink()

    print(f"Updated {updated} channel video records.")
    print(f"Removed {len(removed)} duplicate records.")


if __name__ == "__main__":
    main()
