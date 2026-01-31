import types

import pytest

import youtube_transcript as yt


@pytest.fixture(autouse=True)
def patch_transcript_api(monkeypatch):
    class DummyAPI:
        _transcripts = None

        @classmethod
        def list_transcripts(cls, video_id):
            if cls._transcripts is None:
                raise RuntimeError("No transcripts configured for test")
            return cls._transcripts

    monkeypatch.setattr(yt, "YouTubeTranscriptApi", DummyAPI, raising=False)
    return DummyAPI


class DummyTranscript:
    def __init__(self, language_code="en", is_generated=False, text="hello world"):
        self.language_code = language_code
        self.is_generated = is_generated
        self._text = text

    def fetch(self):
        return [
            {"text": self._text, "start": 0.0, "duration": 1.5},
            {"text": "segment", "start": 1.5, "duration": 1.0},
        ]


class DummyTranscriptList:
    def __init__(self, transcripts):
        self._transcripts = transcripts

    def find_transcript(self, languages):
        for transcript in self._transcripts:
            if not transcript.is_generated and transcript.language_code in languages:
                return transcript
        raise yt.NoTranscriptFound("video", languages, {})

    def find_generated_transcript(self, languages):
        for transcript in self._transcripts:
            if transcript.is_generated and transcript.language_code in languages:
                return transcript
        raise yt.NoTranscriptFound("video", languages, {})

    def __iter__(self):
        return iter(self._transcripts)


def test_get_transcript_prefers_manual_captions(monkeypatch, patch_transcript_api):
    manual = DummyTranscript(language_code="en", is_generated=False, text="manual text")
    patch_transcript_api._transcripts = DummyTranscriptList([manual])

    result = yt.get_youtube_transcript("https://www.youtube.com/watch?v=abcdefghijk")

    assert result["success"] is True
    assert result["language"] == "en"
    assert "manual text" in result["transcript"]
    assert result["is_generated"] is False
    assert "note" not in result


def test_get_transcript_falls_back_to_generated(monkeypatch, patch_transcript_api):
    generated = DummyTranscript(language_code="en", is_generated=True, text="generated text")
    patch_transcript_api._transcripts = DummyTranscriptList([generated])

    result = yt.get_youtube_transcript("abcdefghijk")

    assert result["success"] is True
    assert result["is_generated"] is True
    assert "generated text" in result["transcript"]
    assert result.get("note") == 'Generated transcript used'


def test_get_transcript_reports_unavailable(monkeypatch, patch_transcript_api):
    class EmptyList:
        def find_transcript(self, languages):
            raise yt.NoTranscriptFound("video", languages, {})

        def find_generated_transcript(self, languages):
            raise yt.NoTranscriptFound("video", languages, {})

        def __iter__(self):
            return iter([])

    patch_transcript_api._transcripts = EmptyList()

    result = yt.get_youtube_transcript("abcdefghijk")

    assert result["success"] is False
    assert "No transcript available" in result["error"]


def test_get_transcript_fetch_only(monkeypatch):
    class FetchOnlyAPI:
        @staticmethod
        def get_transcript(video_id, languages):
            if 'en' in languages:
                return [{"text": "direct", "start": 0.0, "duration": 1.0}]
            raise yt.NoTranscriptFound(video_id, languages, {})

    monkeypatch.setattr(yt, "YouTubeTranscriptApi", FetchOnlyAPI, raising=False)

    result = yt.get_youtube_transcript("abcdefghijk")

    assert result["success"] is True
    assert "direct" in result["transcript"]
