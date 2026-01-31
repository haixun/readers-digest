#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import threading
from contextlib import redirect_stdout
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, List, Optional

from flask import Flask, jsonify, render_template, request

from cache_manager import CacheManager
from pipeline.content_index import ContentIndex, ContentRecord
from config import DATA_DIR, PROMPTS_DIR, USER_SETTINGS_FILE, get_user_settings
import yaml
from summarizer import Summarizer, SummarizationError
from manage import run_refresh
from youtube_transcript import extract_video_id, get_youtube_transcript
from pipeline.readinglist_parser import ReadingListParser

app = Flask(__name__)
app.secret_key = "reading_portal_secret"  # Replace for production

cache = CacheManager()
summary_status: Dict[str, Dict[str, str]] = {}
summary_status_lock = threading.Lock()
READING_LIST_PATH = Path(__file__).resolve().parent / "readinglist.md"
TRANSCRIPT_METADATA_PATH = Path(__file__).resolve().parent / "transcript_metadata.json"
USER_TAGS_PATH = DATA_DIR / "user_tags.json"
PROMPT_OVERRIDES_PATH = DATA_DIR / "prompt_overrides.json"

SECTION_CONFIG = {
    "youtube_video": {"header": "# Youtube Videos", "format": "{url}"},
    "youtube_channel": {"header": "# Youtube Channels", "format": "{url}"},
    "blog": {"header": "# Blogs", "format": "- {url}"},
}


def add_url_to_reading_list(url: str, origin: str) -> None:
    config = SECTION_CONFIG.get(origin)
    if not config:
        raise ValueError(f"Unsupported origin: {origin}")

    url = url.strip()
    if not url.startswith("http"):
        raise ValueError("URL must start with http or https")

    lines = READING_LIST_PATH.read_text(encoding="utf-8").splitlines()
    if any(url in line for line in lines):
        raise ValueError("URL already exists in reading list")

    header = config["header"]
    new_entry = config["format"].format(url=url)

    if header not in lines:
        lines.append("")
        lines.append(header)
        lines.append("")
        lines.append(new_entry)
    else:
        header_index = lines.index(header)
        insert_index = header_index + 1
        while insert_index < len(lines) and not lines[insert_index].startswith("# "):
            insert_index += 1
        if insert_index > header_index + 1 and lines[insert_index - 1].strip():
            lines.insert(insert_index, new_entry)
        else:
            lines.insert(insert_index, new_entry)

    READING_LIST_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_json_file(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def _save_json_file(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def load_user_tags() -> Dict[str, List[str]]:
    raw = _load_json_file(USER_TAGS_PATH)
    return {key: list(value) for key, value in raw.items() if isinstance(value, list)}


def save_user_tags(tags: Dict[str, List[str]]) -> None:
    _save_json_file(USER_TAGS_PATH, tags)


def load_prompt_overrides() -> Dict[str, Dict[str, object]]:
    raw = _load_json_file(PROMPT_OVERRIDES_PATH)
    return {key: dict(value) for key, value in raw.items() if isinstance(value, dict)}


def save_prompt_overrides(overrides: Dict[str, Dict[str, object]]) -> None:
    _save_json_file(PROMPT_OVERRIDES_PATH, overrides)


def _extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    return parsed.netloc or url


@lru_cache(maxsize=1)
def load_transcript_metadata() -> Dict[str, Dict[str, object]]:
    if TRANSCRIPT_METADATA_PATH.exists():
        try:
            with TRANSCRIPT_METADATA_PATH.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return {}
    return {}


def resolve_channel_url(record: ContentRecord, raw: Optional[Dict[str, object]] = None) -> Optional[str]:
    if record.source_type != "youtube_video":
        return None

    if raw is None:
        raw = cache.load_raw("youtube", record.content_id)
    channel_id = (raw or {}).get("channel_id")
    if channel_id:
        return f"https://www.youtube.com/channel/{channel_id}"

    metadata = load_transcript_metadata()
    video_id = record.content_id
    if video_id not in metadata:
        video_id = extract_video_id(record.original_url) or video_id
    data = metadata.get(video_id)
    if data:
        channel_id = data.get("channel_id")
        if channel_id:
            return f"https://www.youtube.com/channel/{channel_id}"
    return None


def parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def serialize_record(record: ContentRecord) -> Dict[str, object]:
    summary = cache.load_summary(record.content_id)
    summary_text = summary.get("summary") if summary else None

    raw_data = cache.load_raw("youtube" if record.source_type == "youtube_video" else "blogs", record.content_id)
    channel_url = resolve_channel_url(record, raw_data)

    effective_published_at = record.published_at or (raw_data.get("published_at") if raw_data else None)
    published_at_dt = parse_date(effective_published_at)
    published_sort_key = published_at_dt or datetime.min

    transcript_available = True
    transcript_error = None
    if record.source_type == "youtube_video":
        if raw_data:
            transcript_available = bool(raw_data.get("transcript_available", bool(raw_data.get("transcript"))))
            transcript_error = raw_data.get("transcript_error")
        else:
            transcript_available = False

    user_tags = load_user_tags().get(record.content_id, [])
    tags = list(dict.fromkeys([*(record.tags or []), *user_tags]))
    site_key = _extract_domain(record.original_url) if record.source_type == "blog_article" else None
    site_name = site_key

    return {
        "content_id": record.content_id,
        "source_type": record.source_type,
        "origin": record.origin or record.source_type,
        "title": record.title,
        "author": record.author,
        "original_url": record.original_url,
        "channel_url": channel_url,
        "published_at": effective_published_at,
        "published_display": published_at_dt.strftime("%Y-%m-%d") if published_at_dt else "Unknown",
        "categories": record.categories,
        "tags": tags,
        "site_key": site_key,
        "site_name": site_name,
        "summary": summary_text,
        "has_summary": summary_text is not None,
        "raw_path": record.raw_path,
        "summary_path": record.summary_path,
        "last_updated": record.last_updated,
        "published_sort_key": published_sort_key.isoformat(),
        "transcript_available": transcript_available,
        "transcript_error": transcript_error,
    }


@lru_cache(maxsize=1)
def load_index() -> ContentIndex:
    return ContentIndex()


@app.route("/")
def home() -> str:
    return render_template("index.html")


@app.route("/api/items")
def api_items() -> object:
    category_filter = request.args.get("category")
    index = ContentIndex()
    items = [serialize_record(record) for record in index.all()]

    if category_filter:
        items = [item for item in items if category_filter in item["categories"]]

    items.sort(key=lambda item: item["published_sort_key"], reverse=True)

    grouped_categories: Dict[str, List[Dict[str, object]]] = {}
    grouped_origin: Dict[str, List[Dict[str, object]]] = {}
    for item in items:
        for category in item["categories"]:
            grouped_categories.setdefault(category, []).append(item)
        origin = item.get("origin") or item["source_type"]
        grouped_origin.setdefault(origin, []).append(item)

    stats = {
        "total_items": len(items),
        "by_source": {},
        "by_origin": {key: len(value) for key, value in grouped_origin.items()},
        "latest_published_at": items[0]["published_display"] if items else None,
    }
    for item in items:
        stats["by_source"].setdefault(item["source_type"], 0)
        stats["by_source"][item["source_type"]] += 1

    return jsonify({"items": items, "grouped": grouped_categories, "grouped_origin": grouped_origin, "stats": stats})


@app.route("/api/refresh", methods=["POST"])
def api_refresh() -> object:
    log_stream = io.StringIO()
    try:
        with redirect_stdout(log_stream):
            run_refresh(READING_LIST_PATH, skip_summaries=True)
    except Exception as exc:
        return jsonify({"status": "error", "message": f"Refresh failed: {exc}"}), 500
    return jsonify({"status": "ok", "logs": log_stream.getvalue()})


@app.route("/api/channels")
def api_channels() -> object:
    try:
        parser = ReadingListParser(READING_LIST_PATH)
        entries = [entry for entry in parser.parse() if entry.source_type == "youtube_channel"]
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

    index = ContentIndex()
    counts: Dict[str, int] = {}
    for record in index.all():
        if record.origin != "youtube_channel":
            continue
        if record.author:
            counts[record.author] = counts.get(record.author, 0) + 1

    def _display_name(entry: ReadingListEntry) -> str:
        if entry.title:
            return entry.title
        url = entry.url.rstrip("/")
        if "@" in url:
            return url.split("@", 1)[1]
        for token in ("/c/", "/channel/", "/user/"):
            if token in url:
                return url.split(token, 1)[1].split("/", 1)[0]
        return url.split("/")[-1]

    channels = []
    for entry in entries:
        name = _display_name(entry)
        channels.append(
            {
                "name": name,
                "url": entry.url,
                "category": entry.category,
                "tags": entry.tags,
                "video_count": counts.get(entry.title or "", 0),
            }
        )

    return jsonify({"status": "ok", "channels": channels})


@app.route("/api/blogs")
def api_blogs() -> object:
    try:
        parser = ReadingListParser(READING_LIST_PATH)
        entries = [entry for entry in parser.parse() if entry.source_type == "blog"]
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

    index = ContentIndex()
    counts: Dict[str, int] = {}
    for record in index.all():
        if record.origin != "blog":
            continue
        site_key = _extract_domain(record.original_url)
        counts[site_key] = counts.get(site_key, 0) + 1

    def _display_name(entry: ReadingListEntry) -> str:
        if entry.title:
            return entry.title
        return _extract_domain(entry.url)

    blogs = []
    for entry in entries:
        site_key = _extract_domain(entry.url)
        blogs.append(
            {
                "name": _display_name(entry),
                "url": entry.url,
                "site_key": site_key,
                "category": entry.category,
                "tags": entry.tags,
                "post_count": counts.get(site_key, 0),
            }
        )

    return jsonify({"status": "ok", "blogs": blogs})


@app.route("/api/items/<content_id>")
def api_item_detail(content_id: str) -> object:
    index = ContentIndex()
    record = index.get(content_id)
    if not record:
        return jsonify({"error": "Content not found"}), 404
    data = serialize_record(record)
    raw = cache.load_raw("youtube" if record.source_type == "youtube_video" else "blogs", content_id)
    data["raw_excerpt"] = (raw.get("transcript") or raw.get("text") or "")[:1000] if raw else ""
    if record.source_type == "youtube_video":
        channel_url = resolve_channel_url(record, raw)
        if channel_url:
            data["channel_url"] = channel_url
        data["transcript_available"] = bool(raw.get("transcript_available", bool(raw.get("transcript")))) if raw else False
        data["transcript_error"] = raw.get("transcript_error") if raw else None
    return jsonify(data)


@app.route("/api/items/<content_id>/transcripts", methods=["POST"])
def api_fetch_transcript(content_id: str) -> object:
    index = ContentIndex()
    record = index.get(content_id)
    if not record:
        return jsonify({"status": "error", "message": "Content not found"}), 404
    if record.source_type != "youtube_video":
        return jsonify({"status": "error", "message": "Transcripts are only available for YouTube videos."}), 400

    raw = cache.load_raw("youtube", content_id)
    if not raw:
        return jsonify({"status": "error", "message": "Missing cached metadata for this video."}), 400

    video_url = record.original_url or raw.get("original_url")
    if not video_url:
        return jsonify({"status": "error", "message": "Missing video URL."}), 400

    result = get_youtube_transcript(video_url)
    if not result.get("success"):
        message = result.get("error") or "Unable to fetch transcript."
        raw["transcript_available"] = False
        raw["transcript_error"] = message
        cache.save_raw("youtube", content_id, raw)
        return jsonify({"status": "error", "message": message}), 400

    transcript = result.get("transcript") or ""
    transcript_hash = cache.sha256(transcript)
    raw.update(
        {
            "content_hash": transcript_hash,
            "transcript": transcript,
            "transcript_available": bool(transcript),
            "transcript_error": None,
        }
    )
    cache.save_raw("youtube", content_id, raw)

    video_id = extract_video_id(video_url) or content_id
    transcripts_dir = Path(__file__).resolve().parent / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    try:
        (transcripts_dir / f"{video_id}.txt").write_text(transcript, encoding="utf-8")
    except OSError:
        pass

    return jsonify({"status": "ok"})


@app.route("/api/items/<content_id>/summaries", methods=["POST"])
def api_regenerate_summary(content_id: str) -> object:
    try:
        summarizer = Summarizer(cache)
    except SummarizationError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    index = ContentIndex()
    record = index.get(content_id)
    if not record:
        return jsonify({"status": "error", "message": "Content not found"}), 404

    with summary_status_lock:
        status = summary_status.get(content_id)
        if status and status.get("status") == "running":
            return jsonify({"status": "running"})
        summary_status[content_id] = {"status": "queued", "progress": "0"}

    thread = threading.Thread(target=_run_summary, args=(record, summarizer), daemon=True)
    thread.start()
    return jsonify({"status": "queued"})


@app.route("/api/items/<content_id>/status")
def api_summary_status(content_id: str) -> object:
    with summary_status_lock:
        status = summary_status.get(content_id)
    if not status:
        summary = cache.load_summary(content_id)
        if summary:
            return jsonify({"status": "complete", "progress": "100"})
        return jsonify({"status": "idle", "progress": "0"})
    return jsonify(status)


@app.route("/api/stats")
def api_stats() -> object:
    index = ContentIndex()
    items = [serialize_record(record) for record in index.all()]
    items.sort(key=lambda item: item["published_sort_key"], reverse=True)

    by_category: Dict[str, int] = {}
    for item in items:
        for category in item["categories"]:
            by_category[category] = by_category.get(category, 0) + 1

    by_origin: Dict[str, int] = {}
    for item in items:
        origin = item.get("origin") or item["source_type"]
        by_origin[origin] = by_origin.get(origin, 0) + 1

    return jsonify(
        {
            "total_items": len(items),
            "categories": by_category,
            "origins": by_origin,
            "latest": items[0] if items else None,
        }
    )


@app.route("/api/items/add", methods=["POST"])
def api_add_item() -> object:
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    origin = data.get("origin")

    if origin not in SECTION_CONFIG:
        return jsonify({"status": "error", "message": "Unsupported source"}), 400
    if not url:
        return jsonify({"status": "error", "message": "URL is required"}), 400

    try:
        add_url_to_reading_list(url, origin)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    log_stream = io.StringIO()
    try:
        with redirect_stdout(log_stream):
            run_refresh(READING_LIST_PATH, skip_summaries=True)
    except Exception as exc:
        return jsonify({"status": "error", "message": f"Refresh failed: {exc}"}), 500

    logs = log_stream.getvalue()
    index = ContentIndex()
    record = next((item for item in index.all() if item.original_url == url), None)
    if not record:
        video_id = extract_video_id(url)
        if video_id:
            record = index.get(video_id)

    if not record:
        message = "Content could not be fetched. See logs for details."
        return jsonify({"status": "error", "message": message, "logs": logs}), 400

    return jsonify({"status": "ok", "item": serialize_record(record), "logs": logs})


@app.route("/api/items/<content_id>/tags", methods=["POST"])
def api_item_tags(content_id: str) -> object:
    data = request.get_json(silent=True) or {}
    tags = data.get("tags")
    if not isinstance(tags, list):
        return jsonify({"status": "error", "message": "Tags must be a list."}), 400

    cleaned = []
    for tag in tags:
        if isinstance(tag, str):
            value = tag.strip()
            if value:
                cleaned.append(value)

    user_tags = load_user_tags()
    user_tags[content_id] = cleaned
    save_user_tags(user_tags)
    return jsonify({"status": "ok", "tags": cleaned})


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings() -> object:
    if request.method == "GET":
        settings = get_user_settings()
        return jsonify(
            {
                "status": "ok",
                "openai_model": settings.get("openai_model"),
                "has_api_key": bool(settings.get("openai_api_key")),
            }
        )

    data = request.get_json(silent=True) or {}
    model = (data.get("openai_model") or "").strip()
    api_key = data.get("openai_api_key")
    settings = get_user_settings()

    if model:
        settings["openai_model"] = model

    if isinstance(api_key, str):
        api_key = api_key.strip()
        if api_key:
            settings["openai_api_key"] = api_key
        else:
            settings.pop("openai_api_key", None)

    _save_json_file(USER_SETTINGS_FILE, settings)
    return jsonify({"status": "ok"})


@app.route("/api/prompts")
def api_prompt_keys() -> object:
    prompt_file = PROMPTS_DIR / "summaries.yaml"
    if not prompt_file.exists():
        return jsonify({"status": "error", "message": "Prompt file not found."}), 404
    with prompt_file.open("r", encoding="utf-8") as handle:
        default_prompts = yaml.safe_load(handle) or {}
    return jsonify({"status": "ok", "keys": list(default_prompts.keys())})


@app.route("/api/prompts/<prompt_key>", methods=["GET", "POST"])
def api_prompts(prompt_key: str) -> object:
    prompt_file = PROMPTS_DIR / "summaries.yaml"
    if not prompt_file.exists():
        return jsonify({"status": "error", "message": "Prompt file not found."}), 404

    with prompt_file.open("r", encoding="utf-8") as handle:
        default_prompts = yaml.safe_load(handle) or {}

    if prompt_key not in default_prompts:
        return jsonify({"status": "error", "message": "Unknown prompt key."}), 404

    overrides = load_prompt_overrides()

    if request.method == "GET":
        return jsonify(
            {
                "status": "ok",
                "default": default_prompts.get(prompt_key, {}),
                "override": overrides.get(prompt_key),
            }
        )

    data = request.get_json(silent=True) or {}
    system = (data.get("system") or "").strip()
    user = (data.get("user") or "").strip()
    if not system or not user:
        return jsonify({"status": "error", "message": "System and user prompts are required."}), 400

    current = overrides.get(prompt_key, {})
    next_version = int(current.get("prompt_version") or default_prompts[prompt_key].get("prompt_version", 1)) + 1
    overrides[prompt_key] = {
        "prompt_version": next_version,
        "system": system,
        "user": user,
    }
    save_prompt_overrides(overrides)
    return jsonify({"status": "ok", "override": overrides[prompt_key]})


def _run_summary(record: ContentRecord, summarizer: Summarizer) -> None:
    with summary_status_lock:
        summary_status[record.content_id] = {"status": "running", "progress": "5"}
    try:
        result = summarizer.summarize(record, force=True)
        index = ContentIndex()
        updated = ContentRecord(
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
            last_updated=datetime.utcnow().isoformat() + "Z",
        )
        index.upsert(updated)
        index.save()
        with summary_status_lock:
            summary_status[record.content_id] = {"status": "complete", "progress": "100"}
    except Exception as exc:  # pragma: no cover - runtime path
        with summary_status_lock:
            summary_status[record.content_id] = {"status": "error", "message": str(exc)}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
