#!/usr/bin/env python3
"""Utility helpers for downloading YouTube transcripts (with graceful fallbacks)."""

from __future__ import annotations

from typing import Iterable, List, Optional
import re

try:
    from youtube_transcript_api import (  # type: ignore
        YouTubeTranscriptApi,
        TranscriptsDisabled,
        NoTranscriptFound,
        CouldNotRetrieveTranscript,
    )
except ImportError:  # pragma: no cover - library not installed in test env
    YouTubeTranscriptApi = None  # type: ignore
    TranscriptsDisabled = NoTranscriptFound = CouldNotRetrieveTranscript = Exception  # type: ignore


def extract_video_id(video_url: str | None) -> Optional[str]:
    if not video_url:
        return None
    if len(video_url) == 11 and '/' not in video_url and '.' not in video_url:
        return video_url
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/v\/([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, video_url)
        if match:
            return match.group(1)
    return None


def _normalize_snippet(snippet):
    if isinstance(snippet, dict):
        text = snippet.get('text', '')
        start = float(snippet.get('start', 0.0))
        duration = float(snippet.get('duration', 0.0))
    else:
        text = getattr(snippet, 'text', '')
        start = float(getattr(snippet, 'start', 0.0))
        duration = float(getattr(snippet, 'duration', 0.0))
    return text, start, duration


def _build_success_response(
    video_id: str,
    transcript_data: Iterable,
    language: str,
    *,
    is_generated: bool = False,
    note: Optional[str] = None,
) -> dict:
    text_segments: List[str] = []
    segments: List[dict] = []
    last_end = 0.0
    for snippet in transcript_data:
        text, start, duration = _normalize_snippet(snippet)
        text_segments.append(text)
        segments.append({'text': text, 'start': start, 'duration': duration})
        last_end = start + duration
    result = {
        'success': True,
        'transcript': ' '.join(text_segments),
        'segments': segments,
        'video_id': video_id,
        'language': language,
        'is_generated': is_generated,
        'total_duration': last_end,
    }
    if note:
        result['note'] = note
    return result


def _list_available_languages(video_id: str) -> List[str]:
    if YouTubeTranscriptApi is None:
        return []
    list_result = _invoke_list(video_id)
    if isinstance(list_result, dict) or list_result is None:  # pragma: no cover - defensive
        return []
    try:
        return [transcript.language_code for transcript in list_result]
    except Exception:
        return []


def _invoke_list(video_id: str):
    """Return the transcript list object for a video across API versions."""
    if YouTubeTranscriptApi is None:
        return None

    # Newer versions expose an instance method called `list`, older versions expose
    # a classmethod called `list_transcripts`. We try both in a deterministic order.
    if hasattr(YouTubeTranscriptApi, 'list_transcripts'):
        try:
            return YouTubeTranscriptApi.list_transcripts(video_id)  # type: ignore[attr-defined]
        except TranscriptsDisabled:
            return {'success': False, 'error': 'Transcripts are disabled for this video.', 'video_id': video_id}
        except CouldNotRetrieveTranscript as exc:
            return {'success': False, 'error': f'Could not retrieve transcript: {exc}', 'video_id': video_id}
        except Exception as exc:
            return {'success': False, 'error': f'Failed to list transcripts: {exc}', 'video_id': video_id}

    if hasattr(YouTubeTranscriptApi, 'list'):
        try:
            instance = YouTubeTranscriptApi()  # type: ignore[call-arg]
        except Exception as exc:
            return {'success': False, 'error': f'Failed to initialise YouTubeTranscriptApi: {exc}', 'video_id': video_id}
        try:
            return instance.list(video_id)  # type: ignore[attr-defined]
        except TranscriptsDisabled:
            return {'success': False, 'error': 'Transcripts are disabled for this video.', 'video_id': video_id}
        except CouldNotRetrieveTranscript as exc:
            return {'success': False, 'error': f'Could not retrieve transcript: {exc}', 'video_id': video_id}
        except Exception as exc:
            return {'success': False, 'error': f'Failed to list transcripts: {exc}', 'video_id': video_id}

    return {'success': False, 'error': 'This version of youtube-transcript-api does not support listing transcripts.', 'video_id': video_id}


def _get_transcript_via_list(video_id: str, preferred_languages: List[str]) -> dict:
    transcript_list = _invoke_list(video_id)
    if isinstance(transcript_list, dict):
        return transcript_list
    if transcript_list is None:
        return {
            'success': False,
            'error': 'Unable to list transcripts for this video.',
            'video_id': video_id,
        }

    available_languages: List[str] = []
    try:
        available_languages = [transcript.language_code for transcript in transcript_list]
    except TypeError:
        pass

    transcript_obj = None
    note = None
    for lang in preferred_languages:
        try:
            transcript_obj = transcript_list.find_transcript([lang])
            if lang != preferred_languages[0]:
                note = f'Fallback language used: {lang}'
            break
        except NoTranscriptFound:
            continue

    if transcript_obj is None:
        try:
            transcript_obj = transcript_list.find_generated_transcript(preferred_languages)
            if transcript_obj:
                note = 'Generated transcript used'
        except NoTranscriptFound:
            transcript_obj = None

    if transcript_obj is None:
        return {
            'success': False,
            'error': f'No transcript available in requested languages {preferred_languages}. Available: {available_languages}',
            'video_id': video_id,
            'available_languages': available_languages,
        }

    try:
        transcript = transcript_obj.fetch()
    except CouldNotRetrieveTranscript as exc:
        return {
            'success': False,
            'error': f'Unable to fetch transcript: {exc}',
            'video_id': video_id,
            'available_languages': available_languages,
        }

    return _build_success_response(
        video_id,
        transcript,
        transcript_obj.language_code,
        is_generated=getattr(transcript_obj, 'is_generated', False),
        note=note,
    )


def _get_transcript_via_fetch(video_id: str, preferred_languages: List[str]) -> dict:
    last_error: Optional[Exception] = None
    has_direct = hasattr(YouTubeTranscriptApi, 'get_transcript')
    instance = None
    if not has_direct and hasattr(YouTubeTranscriptApi, 'fetch'):
        try:
            instance = YouTubeTranscriptApi()  # type: ignore
        except Exception as exc:
            last_error = exc
    for lang in preferred_languages:
        try:
            if has_direct:
                transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])  # type: ignore[attr-defined]
            elif instance:
                transcript = instance.fetch(video_id, languages=[lang])  # type: ignore[attr-defined]
            else:
                raise AttributeError('No get_transcript or fetch method available')
            return _build_success_response(video_id, transcript, lang, is_generated=False)
        except TranscriptsDisabled:
            return {'success': False, 'error': 'Transcripts are disabled for this video.', 'video_id': video_id}
        except NoTranscriptFound as exc:
            last_error = exc
            continue
        except CouldNotRetrieveTranscript as exc:
            last_error = exc
            continue
        except Exception as exc:
            last_error = exc
            continue
    available_languages = _list_available_languages(video_id)
    return {
        'success': False,
        'error': f'No transcript available in requested languages {preferred_languages}. Last error: {last_error}',
        'video_id': video_id,
        'available_languages': available_languages,
    }


def get_youtube_transcript(video_url_or_id, language: str = 'en') -> dict:
    video_id = extract_video_id(video_url_or_id)
    if not video_id:
        return {'success': False, 'error': 'Invalid YouTube URL or video ID', 'video_id': video_url_or_id}

    if YouTubeTranscriptApi is None:
        return {'success': False, 'error': 'youtube-transcript-api not installed', 'video_id': video_id}

    preferred_languages = list(dict.fromkeys([language, 'en', 'en-US', 'en-GB', 'en-CA', 'en-AU']))

    if hasattr(YouTubeTranscriptApi, 'list_transcripts') or hasattr(YouTubeTranscriptApi, 'list'):
        result = _get_transcript_via_list(video_id, preferred_languages)
        if result.get('success'):
            return result
        if 'available_languages' in result:
            return result
        error = result.get('error', '')
        error_lower = error.lower()
        # When the list endpoint reports a fatal error (e.g. transcripts disabled or
        # an IP block) retrying via fetch will yield the same result, so surface it.
        if any(keyword in error_lower for keyword in ('disabled', 'blocked', 'quota')):
            return result
        # Otherwise attempt the legacy fetch path for backwards compatibility.
    return _get_transcript_via_fetch(video_id, preferred_languages)


def main():
    import sys

    if len(sys.argv) != 2:
        print("Usage: python youtube_transcript.py <youtube_url_or_video_id>")
        print("Example: python youtube_transcript.py 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'")
        sys.exit(1)

    video_input = sys.argv[1]
    print(f"Retrieving transcript for: {video_input}")
    result = get_youtube_transcript(video_input)
    print(f"\nSuccess: {result['success']}")
    if result['success']:
        print(f"Video ID: {result['video_id']}")
        print(f"Language: {result['language']}")
        print(f"Generated: {result['is_generated']}")
        print(f"Segments: {len(result['segments'])}")
        print(f"Text length: {len(result['transcript'])} characters")
        print(f"Duration: {result.get('total_duration', 0):.1f} seconds")
        if 'note' in result:
            print(f"Note: {result['note']}")
    else:
        print(f"Error: {result['error']}")
        if 'available_languages' in result:
            print(f"Available languages: {result['available_languages']}")


if __name__ == "__main__":
    main()
