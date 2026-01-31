#!/usr/bin/env python3
"""
YouTube Channel Transcript Tracker

This tool monitors YouTube channels for new videos and downloads their transcripts
to a local dataset. It tracks metadata including channel name, publish date, 
download date, duration, and text length.
"""

import json
import os
import re
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

# Import our transcript functionality
from youtube_transcript import get_youtube_transcript, extract_video_id


class YouTubeChannelTracker:
    def __init__(self, base_dir=None):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.base_dir = base_dir
        self.transcripts_dir = os.path.join(base_dir, "transcripts")
        self.metadata_file = os.path.join(base_dir, "transcript_metadata.json")
        self.channels_file = os.path.join(base_dir, "youtubechannel.md")
        
        # Create directories
        os.makedirs(self.transcripts_dir, exist_ok=True)
        
        # Load existing metadata
        self.metadata = self.load_metadata()
        
        # Session for web requests
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
    
    def load_metadata(self):
        """Load existing transcript metadata"""
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Could not load metadata: {e}")
        return {}
    
    def save_metadata(self):
        """Save transcript metadata"""
        try:
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving metadata: {e}")
    
    def extract_channel_id(self, channel_url):
        """Extract channel ID from various YouTube channel URL formats"""
        # Already a channel ID
        if channel_url.startswith('UC') and len(channel_url) == 24:
            return channel_url
        
        # Channel ID from URL
        if 'channel/' in channel_url:
            match = re.search(r'channel/([a-zA-Z0-9_-]{24})', channel_url)
            if match:
                return match.group(1)
        
        # Handle @username format or /c/ format - need to resolve to channel ID
        if '@' in channel_url or '/c/' in channel_url or '/user/' in channel_url:
            return self.resolve_channel_id(channel_url)
        
        return None
    
    def resolve_channel_id(self, channel_url):
        """Resolve @username or /c/ URLs to actual channel IDs"""
        try:
            # Get the channel page
            response = self.session.get(channel_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for channel ID in meta tags or links
            patterns = [
                r'"channelId":"([a-zA-Z0-9_-]{24})"',
                r'"externalId":"([a-zA-Z0-9_-]{24})"',
                r'channel/([a-zA-Z0-9_-]{24})',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, response.text)
                if matches:
                    return matches[0]
            
            print(f"Warning: Could not resolve channel ID for {channel_url}")
            return None
            
        except Exception as e:
            print(f"Error resolving channel ID for {channel_url}: {e}")
            return None
    
    def get_channel_videos(self, channel_id, max_videos=50):
        """Get recent videos from a channel using RSS feed"""
        try:
            # Use YouTube RSS feed (public, no API key needed)
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            
            response = self.session.get(rss_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'xml')
            
            videos = []
            entries = soup.find_all('entry')
            
            for entry in entries[:max_videos]:
                try:
                    video_id = entry.find('yt:videoId').text
                    title = entry.find('title').text
                    published = entry.find('published').text
                    channel_title = entry.find('author').find('name').text
                    
                    # Parse published date
                    pub_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
                    
                    videos.append({
                        'video_id': video_id,
                        'title': title,
                        'published_date': pub_date.isoformat(),
                        'channel_name': channel_title,
                        'channel_id': channel_id,
                        'url': f"https://www.youtube.com/watch?v={video_id}"
                    })
                    
                except Exception as e:
                    print(f"Error parsing video entry: {e}")
                    continue
            
            return videos
            
        except Exception as e:
            print(f"Error fetching videos for channel {channel_id}: {e}")
            return []
    
    def is_transcript_downloaded(self, video_id):
        """Check if transcript is already downloaded"""
        return video_id in self.metadata
    
    def download_transcript(self, video_info):
        """Download transcript for a video"""
        video_id = video_info['video_id']
        
        if self.is_transcript_downloaded(video_id):
            print(f"  ✅ Already downloaded: {video_info['title'][:50]}...")
            return True
        
        print(f"  📝 Downloading: {video_info['title'][:50]}...")
        
        # Get transcript
        result = get_youtube_transcript(video_id)
        
        if not result['success']:
            print(f"    ❌ Failed: {result['error']}")
            return False
        
        # Save transcript to file
        transcript_file = os.path.join(self.transcripts_dir, f"{video_id}.txt")
        
        try:
            with open(transcript_file, 'w', encoding='utf-8') as f:
                f.write(result['transcript'])
        except Exception as e:
            print(f"    ❌ Error saving transcript: {e}")
            return False
        
        # Save metadata
        download_time = datetime.now(timezone.utc).isoformat()
        
        self.metadata[video_id] = {
            'video_id': video_id,
            'title': video_info['title'],
            'channel_name': video_info['channel_name'],
            'channel_id': video_info['channel_id'],
            'url': video_info['url'],
            'published_date': video_info['published_date'],
            'download_date': download_time,
            'duration_seconds': result.get('total_duration', 0),
            'text_length': len(result['transcript']),
            'language': result.get('language', 'unknown'),
            'is_generated': result.get('is_generated', True),
            'transcript_file': transcript_file
        }
        
        print(f"    ✅ Downloaded transcript ({len(result['transcript'])} chars, {result.get('total_duration', 0):.1f}s)")
        return True

    def download_transcript_by_url(self, video_input: str) -> bool:
        """Download a single transcript given a URL or video ID."""
        video_id = extract_video_id(video_input) or self._maybe_video_id(video_input)
        if not video_id:
            print("  ❌ Could not extract a video ID.")
            return False

        video_url = f"https://www.youtube.com/watch?v={video_id}"
        metadata = self._fetch_oembed_metadata(video_url)
        video_info = {
            "video_id": video_id,
            "title": metadata.get("title") or video_id,
            "channel_name": metadata.get("author_name"),
            "channel_id": None,
            "url": video_url,
            "published_date": metadata.get("published_date"),
        }
        success = self.download_transcript(video_info)
        if success:
            self.save_metadata()
        return success

    def _maybe_video_id(self, value: str) -> str | None:
        value = value.strip()
        if re.fullmatch(r"[a-zA-Z0-9_-]{11}", value):
            return value
        return None

    def _fetch_oembed_metadata(self, video_url: str) -> dict:
        try:
            response = self.session.get(
                "https://www.youtube.com/oembed",
                params={"url": video_url, "format": "json"},
                timeout=15,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            print(f"  ⚠️ Unable to fetch metadata for {video_url}: {exc}")
            return {}
    
    def extract_channels_from_file(self):
        """Extract channel URLs/IDs from youtubechannel.md"""
        if not os.path.exists(self.channels_file):
            print(f"Error: {self.channels_file} not found")
            return []
        
        channels = []
        
        try:
            with open(self.channels_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract URLs from markdown
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                
                # Skip comments and empty lines
                if line.startswith('#') or line.startswith('<!--') or not line:
                    continue
                
                # Extract URLs from lines (with or without - prefix)
                if line.startswith('- '):
                    # Markdown list format
                    url_match = re.search(r'https?://[^\s]+', line)
                    if url_match:
                        channels.append(url_match.group(0))
                    else:
                        # Maybe it's just a channel ID
                        parts = line.replace('- ', '').strip()
                        if parts.startswith('UC') and len(parts) == 24:
                            channels.append(parts)
                elif re.match(r'https?://[^\s]+', line):
                    # Direct URL format
                    channels.append(line.strip())
                elif line.startswith('UC') and len(line.strip()) == 24:
                    # Direct channel ID format
                    channels.append(line.strip())
        
        except Exception as e:
            print(f"Error reading channels file: {e}")
        
        return channels
    
    def process_channels(self):
        """Process all channels and download new transcripts"""
        print("Bulk transcript downloads are disabled.")
        print("Use: python youtube_channel_tracker.py --download <youtube_url_or_id>")
        return
    
    def get_stats(self):
        """Get statistics about the transcript dataset"""
        if not self.metadata:
            return {
                'total_videos': 0,
                'total_channels': 0,
                'total_text_length': 0,
                'total_duration': 0,
                'languages': {},
                'channels': {}
            }
        
        channels = set()
        languages = {}
        total_text_length = 0
        total_duration = 0
        
        for video_id, data in self.metadata.items():
            channels.add(data['channel_name'])
            
            lang = data.get('language', 'unknown')
            languages[lang] = languages.get(lang, 0) + 1
            
            total_text_length += data.get('text_length', 0)
            total_duration += data.get('duration_seconds', 0)
        
        channel_counts = {}
        for video_id, data in self.metadata.items():
            ch = data['channel_name']
            channel_counts[ch] = channel_counts.get(ch, 0) + 1
        
        return {
            'total_videos': len(self.metadata),
            'total_channels': len(channels),
            'total_text_length': total_text_length,
            'total_duration': total_duration,
            'languages': languages,
            'channels': channel_counts
        }


def main():
    """Main function to run the channel tracker"""
    import argparse
    
    parser = argparse.ArgumentParser(description='YouTube Channel Transcript Tracker')
    parser.add_argument('--stats', action='store_true', help='Show dataset statistics')
    parser.add_argument('--update', action='store_true', help='(disabled) Former bulk download')
    parser.add_argument('--download', type=str, help='Download a single transcript by URL or video ID')
    
    args = parser.parse_args()
    
    tracker = YouTubeChannelTracker()
    
    if args.stats:
        stats = tracker.get_stats()
        print("📊 Dataset Statistics:")
        print(f"  Videos: {stats['total_videos']}")
        print(f"  Channels: {stats['total_channels']}")
        print(f"  Total text: {stats['total_text_length']:,} characters")
        print(f"  Total duration: {stats['total_duration']:.1f} seconds ({stats['total_duration']/3600:.1f} hours)")
        
        if stats['languages']:
            print(f"  Languages: {dict(sorted(stats['languages'].items()))}")
        
        if stats['channels']:
            print("  Videos per channel:")
            for channel, count in sorted(stats['channels'].items()):
                print(f"    {channel}: {count}")
    
    elif args.download:
        tracker.download_transcript_by_url(args.download)
    elif args.update:
        tracker.process_channels()
    
    else:
        print("YouTube Channel Transcript Tracker")
        print("Usage:")
        print("  python youtube_channel_tracker.py --update   # Download new transcripts")
        print("  python youtube_channel_tracker.py --download <url_or_id>  # Download one transcript")
        print("  python youtube_channel_tracker.py --stats    # Show dataset statistics")
        print("\nEdit youtubechannel.md to add channels to track.")


if __name__ == "__main__":
    main()
