#!/usr/bin/env python3

import sys
sys.path.append('/Users/haixun/projects/0 Life/Reading')

from youtube_channel_tracker import YouTubeChannelTracker

# Test with just one channel and one video
tracker = YouTubeChannelTracker()

# Test channel resolution
test_url = "https://www.youtube.com/@clearvaluetax9382"
print(f"Testing channel: {test_url}")

channel_id = tracker.extract_channel_id(test_url)
print(f"Channel ID: {channel_id}")

if channel_id:
    print("Getting recent videos...")
    videos = tracker.get_channel_videos(channel_id, max_videos=3)  # Only get 3 videos
    print(f"Found {len(videos)} videos")
    
    if videos:
        print(f"First video: {videos[0]['title']}")
        print(f"Video ID: {videos[0]['video_id']}")
        
        # Try to download transcript for just the first video
        print("Downloading first transcript...")
        success = tracker.download_transcript(videos[0])
        print(f"Download success: {success}")
        
        if success:
            tracker.save_metadata()
            print("Metadata saved successfully")