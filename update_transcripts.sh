#!/bin/bash
#
# YouTube Channel Transcript Update Script
#
# This script updates the transcript dataset by checking for new videos
# from channels listed in youtubechannel.md
#

cd "$(dirname "$0")"

echo "🎥 YouTube Channel Transcript Updater"
echo "======================================"

# Show current stats
echo "📊 Current dataset:"
python3 youtube_channel_tracker.py --stats

echo ""
echo "🔍 Checking for new videos..."

# Run the update
python3 youtube_channel_tracker.py --update

echo ""
echo "📊 Updated dataset:"
python3 youtube_channel_tracker.py --stats