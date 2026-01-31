from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional


@dataclasses.dataclass
class ReadingListEntry:
    source_type: str  # youtube_video, youtube_channel, blog
    url: str
    category: str
    title: Optional[str] = None
    tags: List[str] = dataclasses.field(default_factory=list)
    metadata: Dict[str, str] = dataclasses.field(default_factory=dict)

    @property
    def content_id_hint(self) -> str:
        """Return a stable hint for downstream cache ids."""
        if self.source_type == "youtube_video":
            return self.metadata.get("video_id", "") or self.url
        return self.url


class ReadingListParser:
    """Parse readinglist.md and return structured entries.

    Supported syntax examples:
        https://youtube.com/watch?v=abc123
        - [Finance] YouTube Channel: https://youtube.com/@channel
        - [Technology] Cool Blog: https://example.com (tags: ai, research)
        - Blog Name: https://example.com | tags: productivity, habits
    """

    SECTION_TYPE_MAP = {
        "youtube videos": "youtube_video",
        "youtube channels": "youtube_channel",
        "blogs": "blog",
    }

    DEFAULT_CATEGORY_MAP = {
        "youtube videos": "Individual YouTube",
        "youtube channels": "YouTube Channels",
        "blogs": "Blogs",
    }

    URL_PATTERN = re.compile(r"https?://[^\s)]+", re.IGNORECASE)
    CATEGORY_PREFIX_PATTERN = re.compile(r"^\-?\s*\[([^\]]+)\]\s*:?")
    KV_PATTERN = re.compile(r"(?P<key>tags?|category|author)\s*:\s*(?P<value>[^|]+)", re.IGNORECASE)

    def __init__(self, markdown_path: Path):
        self.markdown_path = Path(markdown_path)
        if not self.markdown_path.exists():
            raise FileNotFoundError(f"Reading list not found: {self.markdown_path}")

    def parse(self) -> List[ReadingListEntry]:
        entries: List[ReadingListEntry] = []
        current_section: Optional[str] = None

        for raw_line in self._iter_lines():
            line = raw_line.strip()
            if not line:
                continue

            section = self._extract_section(line)
            if section:
                current_section = section
                continue

            if not current_section:
                continue

            entry = self._parse_line(line, current_section)
            if entry:
                entries.append(entry)

        return entries

    def _iter_lines(self) -> Iterable[str]:
        with self.markdown_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                yield line

    def _extract_section(self, line: str) -> Optional[str]:
        if line.startswith("#"):
            header = line.lstrip("#").strip().lower()
            return header
        return None

    def _parse_line(self, line: str, section: str) -> Optional[ReadingListEntry]:
        url_match = self.URL_PATTERN.search(line)
        if not url_match:
            return None

        url = url_match.group(0).rstrip('.,)')
        pre_text = line[: url_match.start()].strip()
        post_text = line[url_match.end():].strip()

        category = self._extract_category_from_prefix(pre_text) or self.DEFAULT_CATEGORY_MAP.get(section, section.title())
        cleaned_pre_text = self._remove_category_prefix(pre_text)
        title = cleaned_pre_text.rstrip(":-").strip() or None

        metadata = self._extract_key_values(post_text)

        # tags may be inline or provided via metadata
        tags_text = metadata.pop("tags", "")
        tags = self._split_tags(tags_text)

        if "category" in metadata and metadata["category"]:
            category = metadata.pop("category")

        author = metadata.get("author")
        if author and author not in tags:
            metadata["author"] = author.strip()

        source_type = self._detect_source_type(section, url)

        if source_type == "youtube_video":
            metadata.setdefault("video_id", self._extract_video_id(url))

        return ReadingListEntry(
            source_type=source_type,
            url=url,
            category=category or "General",
            title=title,
            tags=tags,
            metadata={k: v.strip() for k, v in metadata.items() if isinstance(v, str)},
        )

    def _extract_category_from_prefix(self, text: str) -> Optional[str]:
        match = self.CATEGORY_PREFIX_PATTERN.search(text)
        if match:
            return match.group(1).strip()
        return None

    def _remove_category_prefix(self, text: str) -> str:
        return self.CATEGORY_PREFIX_PATTERN.sub("", text, count=1).strip()

    def _extract_key_values(self, text: str) -> Dict[str, str]:
        values: Dict[str, str] = {}
        for match in self.KV_PATTERN.finditer(text or ""):
            key = match.group("key").lower()
            value = match.group("value").strip()
            values[key] = value
        return values

    def _split_tags(self, tag_text: str) -> List[str]:
        if not tag_text:
            return []
        parts = re.split(r"[,;]\s*", tag_text)
        cleaned = []
        for part in parts:
            token = part.strip().strip("()[]{} ")
            if token:
                cleaned.append(token)
        return cleaned

    def _detect_source_type(self, section: str, url: str) -> str:
        section_key = section.lower()
        if section_key in self.SECTION_TYPE_MAP:
            return self.SECTION_TYPE_MAP[section_key]

        if "youtube" in url:
            if any(token in url for token in ("/watch", "youtu.be")):
                return "youtube_video"
            return "youtube_channel"
        return "blog"

    def _extract_video_id(self, url: str) -> str:
        match = re.search(r"(?:v=|be/|embed/)([a-zA-Z0-9_-]{11})", url)
        return match.group(1) if match else ""
