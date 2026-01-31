from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List

import requests
from bs4 import BeautifulSoup

from cache_manager import CacheManager
from pipeline.content_index import ContentIndex
from pipeline.readinglist_parser import ReadingListEntry


@dataclass
class BlogContent:
    content_id: str
    title: str
    author: str | None
    published_at: str | None
    url: str
    text: str
    categories: List[str]
    tags: List[str]
    raw_path: str


class BlogIngestor:
    def __init__(self, cache: CacheManager, *, session: requests.Session | None = None):
        self.cache = cache
        self.session = session or self._build_session()

    def ingest(self, entries: Iterable[ReadingListEntry], index: ContentIndex) -> List[BlogContent]:
        collected: List[BlogContent] = []
        for entry in entries:
            posts = self._fetch_recent_posts(entry.url)
            for post in posts:
                article_data = self._download_article(post["url"])
                if not article_data["text"]:
                    continue

                combined_hash = self.cache.sha256(article_data["text"])
                content_id = hashlib.sha1(post["url"].encode("utf-8")).hexdigest()

                if not self.cache.raw_is_current("blogs", content_id, combined_hash):
                    payload = {
                        "content_hash": combined_hash,
                        "title": post["title"],
                        "author": article_data["author"],
                        "published_at": article_data["published_at"],
                        "original_url": post["url"],
                        "text": article_data["text"],
                        "categories": [entry.category],
                        "tags": entry.tags,
                    }
                    self.cache.save_raw("blogs", content_id, payload)

                raw_path = str(self.cache.raw_path("blogs", content_id))
                collected.append(
                    BlogContent(
                        content_id=content_id,
                        title=post["title"],
                        author=article_data["author"],
                        published_at=article_data["published_at"],
                        url=post["url"],
                        text=article_data["text"],
                        categories=[entry.category],
                        tags=entry.tags,
                        raw_path=raw_path,
                    )
                )

                record = ContentIndex.build_record(
                    content_id=content_id,
                    source_type="blog_article",
                    origin=entry.source_type,
                    original_url=post["url"],
                    title=post["title"],
                    raw_path=self.cache.raw_path("blogs", content_id),
                    summary_path=None,
                    published_at=article_data["published_at"],
                    author=article_data["author"],
                    categories=[entry.category],
                    tags=entry.tags,
                )
                index.upsert(record)

            time.sleep(0.5)

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

    def _fetch_recent_posts(self, base_url: str, limit: int = 5) -> List[dict]:
        try:
            response = self.session.get(base_url, timeout=15)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"  ⚠️ Unable to fetch posts from {base_url}: {exc}")
            return []
        soup = BeautifulSoup(response.text, "html.parser")

        selectors = [
            "article h1 a",
            "article h2 a",
            "article .title a",
            ".post-title a",
            ".entry-title a",
            "main h2 a",
            "main h3 a",
            ".content h2 a",
        ]

        articles: List[dict] = []
        seen = set()
        for selector in selectors:
            for link in soup.select(selector):
                href = link.get("href")
                title = link.get_text(strip=True)
                if not href or not title:
                    continue
                if href.startswith("#"):
                    continue
                full_url = requests.compat.urljoin(base_url, href)
                if full_url in seen:
                    continue
                seen.add(full_url)
                if self._looks_like_article(href, title, base_url):
                    articles.append({"title": title, "url": full_url})
                if len(articles) >= limit:
                    break
            if len(articles) >= limit:
                break

        return articles

    def _looks_like_article(self, href: str, title: str, base_url: str) -> bool:
        href_lower = href.lower()
        title_lower = title.lower()
        non_content_tokens = [
            "privacy",
            "terms",
            "about",
            "contact",
            "login",
            "search",
            "tag",
            "category",
            "rss",
            "feed",
            "subscribe",
            "share",
            "comment",
            "?",
        ]
        if any(token in href_lower for token in non_content_tokens):
            return False
        if len(title_lower.split()) < 3:
            return False
        if href_lower.startswith("http") and requests.compat.urlparse(href).netloc != requests.compat.urlparse(base_url).netloc:
            return False
        return True

    def _download_article(self, url: str) -> dict:
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
        except requests.RequestException as exc:
            return {"text": None, "published_at": None, "author": None, "error": str(exc)}
        soup = BeautifulSoup(response.text, "html.parser")

        for element in soup(["script", "style", "nav", "header", "footer", "aside", ".sidebar"]):
            element.decompose()

        paragraphs = [
            p.get_text(strip=True)
            for p in soup.find_all("p")
            if len(p.get_text(strip=True)) > 40
        ]
        text = "\n\n".join(paragraphs[:80])

        published_at = self._extract_date(soup)
        author = self._extract_author(soup)

        return {
            "text": text,
            "published_at": published_at,
            "author": author,
        }

    def _extract_date(self, soup: BeautifulSoup) -> str | None:
        selectors = [
            "time[datetime]",
            "meta[property='article:published_time']",
            "meta[name='date']",
            "meta[name='pubdate']",
        ]
        for selector in selectors:
            element = soup.select_one(selector)
            if not element:
                continue
            if element.has_attr("datetime"):
                return element["datetime"]
            if element.has_attr("content"):
                return element["content"]
            text = element.get_text(strip=True)
            if text:
                return text
        return None

    def _extract_author(self, soup: BeautifulSoup) -> str | None:
        selectors = [
            "meta[name='author']",
            "meta[property='article:author']",
            ".author",
            ".post-author",
        ]
        for selector in selectors:
            element = soup.select_one(selector)
            if not element:
                continue
            if element.has_attr("content"):
                return element["content"].strip()
            text = element.get_text(strip=True)
            if text:
                return text
        return None


__all__ = ["BlogIngestor", "BlogContent"]
