#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from cache_manager import CacheManager
from pipeline.content_index import ContentIndex
from pipeline.blog_ingestor import BlogIngestor
from pipeline.youtube_ingestor import YouTubeIngestor
from pipeline.readinglist_parser import ReadingListParser, ReadingListEntry
from summarizer import summarize_all, SummarizationError
from youtube_channel_tracker import YouTubeChannelTracker


def run_refresh(reading_list_path: Path, *, skip_summaries: bool = False) -> None:
    parser = ReadingListParser(reading_list_path)
    entries = parser.parse()

    cache = CacheManager()
    index = ContentIndex()

    blog_entries: List[ReadingListEntry] = [entry for entry in entries if entry.source_type == "blog"]
    youtube_entries: List[ReadingListEntry] = [
        entry for entry in entries if entry.source_type in {"youtube", "youtube_video", "youtube_channel"}
    ]

    blog_ingestor = BlogIngestor(cache)
    yt_ingestor = YouTubeIngestor(cache)

    if blog_entries:
        print(f"📚 Fetching content from {len(blog_entries)} blog sources...")
        blog_ingestor.ingest(blog_entries, index)

    if youtube_entries:
        print(f"🎬 Fetching content from {len(youtube_entries)} YouTube sources...")
        yt_ingestor.ingest(youtube_entries, index)

    if skip_summaries:
        index.dedupe_by_url()
        index.save()
        print("✅ Content index updated (summaries skipped)")
        return

    try:
        summarize_all(index, cache)
        index.dedupe_by_url()
        print("✅ Content index updated with summaries")
    except SummarizationError as exc:
        print(f"⚠️  Summarization skipped: {exc}")
        index.dedupe_by_url()
        index.save()


def main() -> None:
    argument_parser = argparse.ArgumentParser(description="Manage reading list ingestion pipeline")
    subparsers = argument_parser.add_subparsers(dest="command")

    refresh_parser = subparsers.add_parser("refresh", help="Refresh cached content and content index")
    refresh_parser.add_argument(
        "--reading-list",
        dest="reading_list",
        type=Path,
        default=Path("readinglist.md"),
        help="Path to readinglist.md",
    )
    refresh_parser.add_argument(
        "--skip-summaries",
        action="store_true",
        help="Only refresh raw content and metadata without generating summaries",
    )

    transcript_parser = subparsers.add_parser(
        "fetch-transcript", help="Fetch a single YouTube transcript and refresh the index"
    )
    transcript_parser.add_argument("video", help="YouTube URL or video ID")
    transcript_parser.add_argument(
        "--reading-list",
        dest="reading_list",
        type=Path,
        default=Path("readinglist.md"),
        help="Path to readinglist.md",
    )

    args = argument_parser.parse_args()

    if args.command == "refresh":
        run_refresh(args.reading_list, skip_summaries=args.skip_summaries)
    elif args.command == "fetch-transcript":
        tracker = YouTubeChannelTracker()
        tracker.download_transcript_by_url(args.video)
        run_refresh(args.reading_list, skip_summaries=True)
    else:
        argument_parser.print_help()


if __name__ == "__main__":
    main()
