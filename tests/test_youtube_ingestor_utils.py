import json
from types import SimpleNamespace

import pytest

from cache_manager import CacheManager
from pipeline.youtube_ingestor import YouTubeIngestor


class DummyResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def build_ingestor(tmp_path):
    cache = CacheManager(raw_dir=tmp_path / "raw", summary_dir=tmp_path / "summary")
    ingestor = YouTubeIngestor(cache)
    return ingestor


def test_merge_videos_includes_remote_when_missing(tmp_path):
    ingestor = build_ingestor(tmp_path)
    local = []
    remote = [
        {"video_id": "A1", "title": "Remote", "published_at": None, "order_index": 0},
        {"video_id": "A2", "title": "Remote 2", "published_at": "2024-01-01T00:00:00Z", "order_index": 1},
    ]

    merged = ingestor._merge_videos(local, remote, limit=10)

    assert len(merged) == 2
    assert merged[0]["video_id"] == "A2"
    assert merged[1]["video_id"] == "A1"


def test_fetch_channel_videos_from_page_parses_videos(tmp_path, monkeypatch):
    ingestor = build_ingestor(tmp_path)

    yt_initial_data = {
        "contents": {
            "twoColumnBrowseResultsRenderer": {
                "tabs": [
                    {
                        "tabRenderer": {
                            "selected": True,
                            "content": {
                                "richGridRenderer": {
                                    "contents": [
                                        {
                                            "richItemRenderer": {
                                                "content": {
                                                    "videoRenderer": {
                                                        "videoId": "vid1",
                                                        "title": {"runs": [{"text": "Video One"}]},
                                                        "ownerText": {"runs": [{"text": "Channel"}]},
                                                        "publishedTimeText": {"simpleText": "1 day ago"},
                                                    }
                                                }
                                            }
                                        },
                                        {
                                            "richItemRenderer": {
                                                "content": {
                                                    "videoRenderer": {
                                                        "videoId": "vid2",
                                                        "title": {"runs": [{"text": "Video Two"}]},
                                                        "ownerText": {"runs": [{"text": "Channel"}]},
                                                        "publishedTimeText": {"simpleText": "2 days ago"},
                                                    }
                                                }
                                            }
                                        },
                                    ]
                                }
                            }
                        }
                    }
                ]
            }
        }
    }

    page_html = f"<script>var ytInitialData = {json.dumps(yt_initial_data)};</script>"

    def fake_get(url, timeout):
        return DummyResponse(page_html)

    monkeypatch.setattr(ingestor.session, "get", fake_get)

    videos = ingestor._fetch_channel_videos_from_page("UC1234567890", limit=5)
    ids = [video["video_id"] for video in videos]

    assert ids == ["vid1", "vid2"]
    assert videos[0]["title"] == "Video One"
    assert videos[0]["channel_name"] == "Channel"

