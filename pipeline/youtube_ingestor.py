from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

import requests
from bs4 import BeautifulSoup
from xml.etree import ElementTree

from cache_manager import CacheManager
from pipeline.content_index import ContentIndex
from pipeline.readinglist_parser import ReadingListEntry
from youtube_channel_tracker import YouTubeChannelTracker
from youtube_transcript import extract_video_id


@dataclass
class YouTubeContent:
    content_id: str
    title: str
    channel_name: str | None
    published_at: str | None
    url: str
    transcript: str
    categories: List[str]
    tags: List[str]
    raw_path: str


class YouTubeIngestor:
    CHANNEL_VIDEO_LIMIT = 30

    def __init__(self, cache: CacheManager, *, session: requests.Session | None = None):
        self.cache = cache
        self.session = session or self._build_session()
        self.tracker = YouTubeChannelTracker()
        self._channel_cache: dict[str, List[dict]] = {}

    def ingest(self, entries: Iterable[ReadingListEntry], index: ContentIndex) -> List[YouTubeContent]:
        collected: List[YouTubeContent] = []
        for entry in entries:
            if entry.source_type == "youtube_channel":
                channel_id = self._extract_channel_id_local(entry.url)
                if not channel_id:
                    channel_id = self._resolve_channel_id(entry.url)
                    if channel_id:
                        print(f"  ℹ️ Resolved channel ID {channel_id} for {entry.url}")
                local_videos = self._videos_from_store(entry, channel_id)
                remote_videos: List[dict] = []
                if channel_id:
                    remote_videos = self._fetch_channel_videos(channel_id, limit=self.CHANNEL_VIDEO_LIMIT)
                videos = self._merge_videos(local_videos, remote_videos, limit=self.CHANNEL_VIDEO_LIMIT)
                if not videos:
                    print(f"  ⚠️ No videos available for {entry.url}")
                    continue
            else:
                video_id = extract_video_id(entry.url)
                if not video_id:
                    print(f"  ⚠️ Unable to extract video ID for {entry.url}")
                    continue
                video_data = self._video_from_store(video_id)
                if not video_data:
                    video_data = self._fetch_single_video_metadata(video_id)
                if not video_data:
                    print(f"  ⚠️ No metadata available for video {entry.url}")
                    continue
                videos = [video_data]

            for video in videos:
                if not video:
                    continue
                if not self._is_iso_date(video.get("published_at")):
                    self._hydrate_published_at(video)
                if not self._is_iso_date(video.get("published_at")):
                    video_id = video.get("video_id") or extract_video_id(video.get("url", ""))
                    if video_id:
                        metadata = self._fetch_single_video_metadata(video_id)
                        if metadata and metadata.get("published_at"):
                            video["published_at"] = metadata.get("published_at")
                            if not video.get("channel_name"):
                                video["channel_name"] = metadata.get("channel_name")
                            if not video.get("channel_id"):
                                video["channel_id"] = metadata.get("channel_id")
                transcript_text, transcript_error = self._load_transcript(video)
                video_id = video.get("video_id") or extract_video_id(video.get("url", ""))
                content_id = video_id or hashlib.sha1(video["url"].encode()).hexdigest()
                if video_id:
                    video["video_id"] = video_id
                if transcript_text:
                    content_hash = self.cache.sha256(transcript_text)
                else:
                    fallback_basis = (video.get("title") or "") + (video.get("published_at") or "")
                    content_hash = self.cache.sha256(fallback_basis or video.get("url") or content_id)

                canonical_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else video["url"]
                if not self.cache.raw_is_current("youtube", content_id, content_hash):
                    payload = {
                        "content_hash": content_hash,
                        "title": video["title"],
                        "channel_name": video.get("channel_name"),
                        "channel_id": video.get("channel_id"),
                        "published_at": video.get("published_at"),
                        "original_url": canonical_url,
                        "transcript": transcript_text or "",
                        "transcript_available": bool(transcript_text),
                        "transcript_error": transcript_error,
                        "categories": [entry.category],
                        "tags": entry.tags,
                    }
                    self.cache.save_raw("youtube", content_id, payload)

                raw_path = str(self.cache.raw_path("youtube", content_id))
                record = ContentIndex.build_record(
                    content_id=content_id,
                    source_type="youtube_video",
                    origin=entry.source_type,
                    original_url=canonical_url,
                    title=video["title"],
                    raw_path=self.cache.raw_path("youtube", content_id),
                    summary_path=None,
                    published_at=video.get("published_at"),
                    author=video.get("channel_name"),
                    categories=[entry.category],
                    tags=entry.tags,
                )
                index.upsert(record)

                if transcript_text:
                    collected.append(
                        YouTubeContent(
                            content_id=content_id,
                            title=video["title"],
                            channel_name=video.get("channel_name"),
                            published_at=video.get("published_at"),
                            url=video["url"],
                            transcript=transcript_text,
                            categories=[entry.category],
                            tags=entry.tags,
                            raw_path=raw_path,
                        )
                    )
                else:
                    print(
                        f"  ⚠️ Transcript unavailable for {video.get('title', video.get('url'))}: {transcript_error or 'no transcript'}"
                    )

        return collected

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        return session

    def _resolve_channel_id(self, channel_url: str) -> str | None:
        if "channel/" in channel_url:
            parts = channel_url.rstrip("/").split("/")
            return parts[-1]

        if channel_url.startswith("UC") and len(channel_url) == 24:
            return channel_url

        response = self.session.get(channel_url, timeout=15)
        response.raise_for_status()
        patterns = [
            r'"channelId":"([A-Za-z0-9_-]{24})"',
            r'channel/([A-Za-z0-9_-]{24})',
        ]
        for pattern in patterns:
            match = re.search(pattern, response.text)
            if match:
                return match.group(1)
        return None

    def _fetch_channel_videos(self, channel_id: str, limit: int = 30) -> List[dict]:
        if not channel_id or len(channel_id) < 6:
            return []
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        print(f"  ⏳ Fetching RSS feed for channel {channel_id}")
        rss_response = None
        try:
            rss_response = self.session.get(rss_url, timeout=15)
            rss_response.raise_for_status()
        except requests.RequestException as exc:
            print(f"  ⚠️ Unable to fetch RSS for channel {channel_id}: {exc}")

        videos: List[dict] = []
        if rss_response is not None:
            try:
                root = ElementTree.fromstring(rss_response.content)
            except ElementTree.ParseError:
                print(f"  ⚠️ Unable to parse RSS feed for channel {channel_id}")
                root = None

            if root is not None:
                ns = {
                    "atom": "http://www.w3.org/2005/Atom",
                    "yt": "http://www.youtube.com/xml/schemas/2015",
                }

                for entry in root.findall("atom:entry", ns)[:limit]:
                    video_id_elem = entry.find("yt:videoId", ns)
                    title_elem = entry.find("atom:title", ns)
                    published_elem = entry.find("atom:published", ns)
                    author_elem = entry.find("atom:author/atom:name", ns)

                    if not video_id_elem or not title_elem:
                        continue

                    video_id = video_id_elem.text
                    title = title_elem.text
                    published = published_elem.text if published_elem is not None else None
                    channel_title = author_elem.text if author_elem is not None else None

                    videos.append(
                        {
                            "video_id": video_id,
                            "title": title,
                            "published_at": published,
                            "channel_name": channel_title,
                            "channel_id": channel_id,
                            "url": f"https://www.youtube.com/watch?v={video_id}",
                        }
                    )

        if videos:
            print(f"  ✅ Retrieved {len(videos)} videos from RSS for channel {channel_id}")
            return videos

        print(f"  ⚠️ RSS feed empty for channel {channel_id}; attempting HTML fallback")
        page_videos = self._fetch_channel_videos_from_page(channel_id, limit)
        print(f"  ✅ Retrieved {len(page_videos)} videos from HTML fallback for channel {channel_id}")
        return page_videos

    def _fetch_channel_videos_from_page(self, channel_id: str, limit: int) -> List[dict]:
        page_url = f"https://www.youtube.com/channel/{channel_id}/videos?view=0&sort=dd&flow=grid"
        try:
            response = self.session.get(page_url, timeout=15)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"  ⚠️ Unable to fetch channel page for {channel_id}: {exc}")
            return []

        match = re.search(r"ytInitialData\s*=\s*(\{.*?\})\s*;", response.text, re.DOTALL)
        if not match:
            print(f"  ⚠️ Could not locate ytInitialData for channel {channel_id}")
            return []

        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            print(f"  ⚠️ Failed to parse ytInitialData for channel {channel_id}: {exc}")
            return []

        videos: List[dict] = []

        tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
        for tab in tabs:
            tab_renderer = tab.get("tabRenderer")
            if not tab_renderer or not tab_renderer.get("selected"):
                continue
            content = tab_renderer.get("content", {})
            rich_grid = content.get("richGridRenderer")
            if rich_grid:
                for order_index, item in enumerate(rich_grid.get("contents", [])):
                    video_renderer = (
                        item.get("richItemRenderer", {})
                        .get("content", {})
                        .get("videoRenderer")
                    )
                    if not video_renderer:
                        continue
                    video_data = self._video_renderer_to_dict(video_renderer, channel_id, order_index)
                    if video_data:
                        videos.append(video_data)
                    if len(videos) >= limit:
                        return videos

        # Legacy layout fallback
        tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
        section_list = {}
        if tabs:
            tab_renderer = tabs[0].get("tabRenderer", {})
            section_list = tab_renderer.get("content", {}).get("sectionListRenderer", {})
        for section in section_list.get("contents", []):
            item_section = section.get("itemSectionRenderer")
            if not item_section:
                continue
            for item in item_section.get("contents", []):
                grid = item.get("gridRenderer")
                if not grid:
                    continue
                for order_index, video in enumerate(grid.get("items", [])):
                    video_renderer = video.get("gridVideoRenderer")
                    if not video_renderer:
                        continue
                    video_data = self._video_renderer_to_dict(video_renderer, channel_id, order_index)
                    if video_data:
                        videos.append(video_data)
                    if len(videos) >= limit:
                        return videos

        return videos

    def _video_renderer_to_dict(self, renderer: dict, channel_id: str, order_index: int) -> Optional[dict]:
        video_id = renderer.get("videoId")
        if not video_id:
            return None
        title_runs = renderer.get("title", {}).get("runs") or []
        title = title_runs[0]["text"] if title_runs else renderer.get("title", {}).get("simpleText")
        owner_runs = renderer.get("ownerText", {}).get("runs") or []
        channel_name = owner_runs[0]["text"] if owner_runs else None
        published_text = renderer.get("publishedTimeText", {}).get("simpleText")
        # Some renderers expose exact dates under "publishedTimeText" -> runs
        if published_text is None:
            runs = renderer.get("publishedTimeText", {}).get("runs") or []
            if runs:
                published_text = runs[0].get("text")

        return {
            "video_id": video_id,
            "title": title,
            "published_at": published_text,
            "channel_name": channel_name,
            "channel_id": channel_id,
            "order_index": order_index,
            "url": f"https://www.youtube.com/watch?v={video_id}",
        }

    def _fetch_single_video_metadata(self, video_id: str) -> dict:
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            response = self.session.get(video_url, timeout=15)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"  ⚠️ Unable to fetch metadata for {video_url}: {exc}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.select_one("meta[name='title']")
        title_text = title["content"] if title and title.has_attr("content") else soup.title.string if soup.title else video_id
        channel = soup.select_one("link[itemprop='name']")
        channel_name = channel["content"] if channel and channel.has_attr("content") else None
        date_meta = soup.select_one("meta[itemprop='datePublished']")
        published_at = date_meta["content"] if date_meta and date_meta.has_attr("content") else None
        channel_id = None
        channel_meta = soup.select_one("meta[itemprop='channelId']")
        if channel_meta and channel_meta.has_attr("content"):
            channel_id = channel_meta["content"]
        else:
            match = re.search(r'"channelId":"([A-Za-z0-9_-]{24})"', response.text)
            if match:
                channel_id = match.group(1)
        return {
            "video_id": video_id,
            "title": title_text,
            "channel_name": channel_name,
            "channel_id": channel_id,
            "published_at": published_at,
            "url": video_url,
        }

    def _is_iso_date(self, value: Optional[str]) -> bool:
        if not value or not isinstance(value, str):
            return False
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False

    def _hydrate_published_at(self, video: dict) -> None:
        published_at = video.get("published_at")
        if not published_at or not isinstance(published_at, str):
            return
        relative = self._parse_relative_published_at(published_at)
        if relative:
            video["published_at"] = relative

    def _parse_relative_published_at(self, value: str) -> Optional[str]:
        text = value.strip().lower()
        now = datetime.now(timezone.utc)

        if text in {"just now", "moments ago"}:
            return now.isoformat()
        if text in {"today"}:
            return now.isoformat()
        if text in {"yesterday"}:
            return (now - timedelta(days=1)).isoformat()

        match = re.match(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", text)
        if not match:
            return None
        amount = int(match.group(1))
        unit = match.group(2)

        if unit == "second":
            delta = timedelta(seconds=amount)
        elif unit == "minute":
            delta = timedelta(minutes=amount)
        elif unit == "hour":
            delta = timedelta(hours=amount)
        elif unit == "day":
            delta = timedelta(days=amount)
        elif unit == "week":
            delta = timedelta(weeks=amount)
        elif unit == "month":
            delta = timedelta(days=amount * 30)
        else:  # year
            delta = timedelta(days=amount * 365)

        return (now - delta).isoformat()

    def _extract_channel_id_local(self, url: str) -> Optional[str]:
        if "channel/" in url:
            parts = url.rstrip("/").split("/")
            if parts:
                last = parts[-1]
                if last.startswith("UC") and len(last) == 24:
                    return last
        if url.startswith("UC") and len(url) == 24:
            return url
        return None

    def _slugify(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    def _videos_from_store(self, entry: ReadingListEntry, channel_id: Optional[str], limit: int = 30) -> List[dict]:
        handle = ""
        if "@" in entry.url:
            handle = entry.url.split("@", 1)[1].strip("/")
        handle_slug = self._slugify(handle)
        handle_base = re.sub(r"\d+$", "", handle_slug)
        title_slug = self._slugify(entry.title or "")

        candidates: List[dict] = []
        for video in self.tracker.metadata.values():
            vid_channel_id = video.get("channel_id")
            if channel_id and vid_channel_id == channel_id:
                candidates.append(video)
                continue
            if handle_slug:
                name = video.get("channel_name", "")
                if name:
                    name_slug = self._slugify(name)
                    if (
                        handle_slug in name_slug
                        or name_slug in handle_slug
                        or (handle_base and handle_base in name_slug)
                        or (title_slug and title_slug in name_slug)
                    ):
                        candidates.append(video)
                        continue
            if title_slug:
                name = video.get("channel_name", "")
                if name and title_slug in self._slugify(name):
                    candidates.append(video)

        seen = set()
        unique = []
        for video in candidates:
            vid = video.get("video_id")
            if vid and vid in seen:
                continue
            seen.add(vid)
            unique.append(video)

        unique.sort(key=lambda item: item.get("published_date", ""), reverse=True)
        result = []
        for video in unique[:limit]:
            result.append(
                {
                    "video_id": video.get("video_id"),
                    "title": video.get("title"),
                    "published_at": video.get("published_date"),
                    "channel_name": video.get("channel_name"),
                    "channel_id": video.get("channel_id"),
                    "url": video.get("url"),
                    "transcript_file": video.get("transcript_file"),
                    "duration_seconds": video.get("duration_seconds"),
                }
            )
        return result

    def _merge_videos(self, local: List[dict], remote: List[dict], limit: int = 30) -> List[dict]:
        combined: Dict[str, dict] = {}
        for collection in (local or []):
            vid = collection.get("video_id")
            if not vid:
                continue
            combined[vid] = collection
        for idx, collection in enumerate(remote or []):
            vid = collection.get("video_id")
            if not vid:
                continue
            if vid not in combined:
                # ensure remote order is available if date missing
                collection.setdefault("order_index", idx)
                combined[vid] = collection
        def sort_key(item: dict) -> tuple:
            published = item.get("published_at") or item.get("published_date")
            iso_value = None
            if isinstance(published, str):
                try:
                    iso_value = datetime.fromisoformat(published.replace("Z", "+00:00"))
                except ValueError:
                    iso_value = None
            order_index = item.get("order_index", 0)
            if iso_value is not None:
                return (0, iso_value, -order_index)
            return (1, -order_index)

        videos = list(combined.values())
        videos.sort(key=sort_key)
        return videos[:limit]

    def _video_from_store(self, video_id: str) -> Optional[dict]:
        video = self.tracker.metadata.get(video_id)
        if not video:
            return None
        return {
            "video_id": video.get("video_id"),
            "title": video.get("title"),
            "published_at": video.get("published_date"),
            "channel_name": video.get("channel_name"),
            "channel_id": video.get("channel_id"),
            "url": video.get("url"),
            "transcript_file": video.get("transcript_file"),
            "duration_seconds": video.get("duration_seconds"),
        }

    def _load_transcript(self, video: dict) -> tuple[Optional[str], Optional[str]]:
        transcript_paths = []
        explicit = video.get("transcript_file")
        if explicit:
            transcript_paths.append(explicit)
        video_id = video.get("video_id")
        if video_id:
            transcript_paths.append(self.tracker.transcripts_dir + f"/{video_id}.txt")

        for path in transcript_paths:
            if path and os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as handle:
                        return handle.read(), None
                except OSError:
                    continue

        return None, "Transcript not downloaded. Fetch one at a time before summarizing."


__all__ = ["YouTubeIngestor", "YouTubeContent"]
