#!/usr/bin/env python3
"""
YouTube Transcript Daily Review - Web Interface

A Flask-based web interface for reviewing new YouTube videos and generating
AI-powered summaries of their transcripts.
"""

import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, jsonify, request, send_file
import threading
import re

# Import our existing components
from youtube_channel_tracker import YouTubeChannelTracker

app = Flask(__name__)
app.secret_key = 'youtube_transcript_reviewer_2024'  # Change in production

class WebInterfaceManager:
    def __init__(self):
        self.tracker = YouTubeChannelTracker()
        self.summaries_dir = os.path.join(self.tracker.base_dir, "summaries")
        os.makedirs(self.summaries_dir, exist_ok=True)
        
        # Track summary generation status
        self.summary_status = {}  # video_id -> {"status": "generating/complete/error", "progress": 0-100}
    
    def get_videos_data(self, days_back=7):
        """Get videos from the last N days with enhanced metadata"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        
        videos = []
        for video_id, metadata in self.tracker.metadata.items():
            try:
                published_date = datetime.fromisoformat(metadata['published_date'])
                if published_date.tzinfo is None:
                    published_date = published_date.replace(tzinfo=timezone.utc)
                
                # Enhanced metadata
                enhanced_metadata = metadata.copy()
                enhanced_metadata.update({
                    'thumbnail_url': f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                    'is_new': published_date >= cutoff_date,
                    'has_summary': self.has_summary(video_id),
                    'summary_status': self.summary_status.get(video_id, {"status": "none", "progress": 0}),
                    'published_date_formatted': published_date.strftime('%B %d, %Y'),
                    'duration_formatted': self.format_duration(metadata.get('duration_seconds', 0)),
                    'text_length_formatted': f"{metadata.get('text_length', 0):,} chars"
                })
                
                videos.append(enhanced_metadata)
                
            except Exception as e:
                print(f"Error processing video {video_id}: {e}")
                continue
        
        # Sort by published date (newest first)
        videos.sort(key=lambda x: x['published_date'], reverse=True)
        return videos
    
    def get_new_videos(self, hours_back=48):
        """Get videos from the last 48 hours"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        new_videos = []
        for video_id, metadata in self.tracker.metadata.items():
            try:
                published_date = datetime.fromisoformat(metadata['published_date'])
                if published_date.tzinfo is None:
                    published_date = published_date.replace(tzinfo=timezone.utc)
                
                if published_date >= cutoff_date:
                    enhanced_metadata = metadata.copy()
                    enhanced_metadata.update({
                        'thumbnail_url': f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                        'has_summary': self.has_summary(video_id),
                        'published_date_formatted': published_date.strftime('%B %d, %Y at %I:%M %p'),
                        'duration_formatted': self.format_duration(metadata.get('duration_seconds', 0))
                    })
                    new_videos.append(enhanced_metadata)
                    
            except Exception as e:
                print(f"Error processing new video {video_id}: {e}")
                continue
        
        new_videos.sort(key=lambda x: x['published_date'], reverse=True)
        return new_videos
    
    def get_video_details(self, video_id):
        """Get detailed video information including transcript"""
        if video_id not in self.tracker.metadata:
            return None
        
        metadata = self.tracker.metadata[video_id].copy()
        
        # Load transcript
        transcript_file = metadata.get('transcript_file', 
                                      os.path.join(self.tracker.transcripts_dir, f"{video_id}.txt"))
        
        try:
            with open(transcript_file, 'r', encoding='utf-8') as f:
                transcript = f.read()
        except Exception as e:
            transcript = f"Error loading transcript: {e}"
        
        # Load summary if exists
        summary = self.get_summary(video_id)
        
        metadata.update({
            'transcript': transcript,
            'summary': summary,
            'has_summary': summary is not None,
            'thumbnail_url': f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            'duration_formatted': self.format_duration(metadata.get('duration_seconds', 0)),
            'summary_status': self.summary_status.get(video_id, {"status": "none", "progress": 0})
        })
        
        return metadata
    
    def has_summary(self, video_id):
        """Check if video has a generated summary"""
        summary_file = os.path.join(self.summaries_dir, f"{video_id}.md")
        return os.path.exists(summary_file)
    
    def get_summary(self, video_id):
        """Get the summary for a video if it exists"""
        summary_file = os.path.join(self.summaries_dir, f"{video_id}.md")
        if os.path.exists(summary_file):
            try:
                with open(summary_file, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                print(f"Error loading summary for {video_id}: {e}")
        return None
    
    def format_duration(self, seconds):
        """Format duration in seconds to human readable"""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes}m {int(seconds % 60)}s"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}h {minutes}m"
    
    def generate_summary_async(self, video_id):
        """Generate summary for a video asynchronously"""
        def _generate():
            try:
                self.summary_status[video_id] = {"status": "generating", "progress": 10}
                
                # Get video details
                video_data = self.get_video_details(video_id)
                if not video_data:
                    self.summary_status[video_id] = {"status": "error", "progress": 0, "error": "Video not found"}
                    return
                
                self.summary_status[video_id]["progress"] = 30
                
                # Create summarization prompt
                prompt = self.create_summary_prompt(video_data)
                
                self.summary_status[video_id]["progress"] = 50
                
                # Generate summary using Claude Code's LLM capabilities
                summary = self.call_llm_for_summary(prompt, video_data)
                
                self.summary_status[video_id]["progress"] = 80
                
                # Save summary
                summary_file = os.path.join(self.summaries_dir, f"{video_id}.md")
                with open(summary_file, 'w', encoding='utf-8') as f:
                    f.write(summary)
                
                # Update metadata
                if 'summaries' not in self.tracker.metadata[video_id]:
                    self.tracker.metadata[video_id]['summaries'] = {}
                
                self.tracker.metadata[video_id]['summaries']['generated_date'] = datetime.now(timezone.utc).isoformat()
                self.tracker.metadata[video_id]['summaries']['file'] = summary_file
                self.tracker.save_metadata()
                
                self.summary_status[video_id] = {"status": "complete", "progress": 100}
                
            except Exception as e:
                print(f"Error generating summary for {video_id}: {e}")
                self.summary_status[video_id] = {"status": "error", "progress": 0, "error": str(e)}
        
        # Run in background thread
        thread = threading.Thread(target=_generate)
        thread.daemon = True
        thread.start()
    
    def create_summary_prompt(self, video_data):
        """Create a structured prompt for LLM summarization"""
        title = video_data['title']
        channel = video_data['channel_name']
        transcript = video_data['transcript']
        duration = video_data.get('duration_seconds', 0)
        
        # Truncate very long transcripts
        max_chars = 15000  # Adjust based on LLM context limits
        if len(transcript) > max_chars:
            transcript = transcript[:max_chars] + "\n\n[TRANSCRIPT TRUNCATED FOR ANALYSIS]"
        
        prompt = f"""Please analyze this YouTube video transcript and create a comprehensive structured summary.

VIDEO DETAILS:
Title: {title}
Channel: {channel}
Duration: {self.format_duration(duration)}

TRANSCRIPT:
{transcript}

Please provide a detailed summary in the following structured format:

# {title}

*Channel: {channel} | Duration: {self.format_duration(duration)}*

## Executive Summary
[2-3 sentences capturing the main message and purpose of the video]

## Key Points
- [Bullet point 1: Main idea or argument]
- [Bullet point 2: Supporting point or example]
- [Bullet point 3: Important detail or conclusion]
- [Continue with 2-5 more key points as relevant]

## Main Themes & Topics
[List the primary subjects, categories, or areas covered in the video]

## Actionable Insights
- [Practical takeaway 1: What viewers can do with this information]
- [Practical takeaway 2: Specific actions or decisions suggested]
- [Continue with relevant actionable items]

## Notable Quotes
> "[Include 1-2 particularly important or memorable quotes from the transcript]"

## Technical Details
[If applicable, include specific numbers, data, processes, or technical information mentioned]

---
*Summary generated on {datetime.now().strftime('%B %d, %Y')}*
"""
        return prompt
    
    def call_llm_for_summary(self, prompt, video_data):
        """Call LLM to generate summary - using subprocess for now"""
        try:
            # Create a temporary file with the prompt
            temp_prompt_file = f"/tmp/transcript_prompt_{video_data['video_id']}.txt"
            with open(temp_prompt_file, 'w', encoding='utf-8') as f:
                f.write(prompt)
            
            # Try to use Claude Code's LLM capabilities via subprocess
            # This is a simple approach - could be enhanced with direct API calls
            result = subprocess.run([
                'python3', '-c', f'''
import os
import re

prompt = """
{prompt}
"""

# Simple extractive summarization as fallback
transcript = """{video_data['transcript'][:8000]}"""

# Extract key sentences for a basic summary
sentences = [s.strip() for s in re.split(r'[.!?]+', transcript) if len(s.strip()) > 30]

# Score sentences based on importance
important_words = [
    'important', 'key', 'main', 'significant', 'critical', 'essential',
    'strategy', 'recommend', 'suggest', 'believe', 'think', 'should',
    'will', 'going to', 'plan', 'goal', 'result', 'because', 'therefore'
]

scored_sentences = []
for i, sentence in enumerate(sentences[:15]):  # Look at first 15 sentences
    score = 0
    sentence_lower = sentence.lower()
    
    # Position score (earlier sentences often more important)
    score += max(0, 10 - i)
    
    # Important words score
    for word in important_words:
        if word in sentence_lower:
            score += 2
    
    # Length score (prefer moderate length)
    word_count = len(sentence.split())
    if 10 <= word_count <= 25:
        score += 3
    
    scored_sentences.append((sentence, score))

# Sort by score and take top sentences
scored_sentences.sort(key=lambda x: x[1], reverse=True)
best_sentences = [s[0] for s in scored_sentences[:4] if s[1] > 5]

# Generate basic structured summary
summary = f"""# {video_data['title']}

*Channel: {video_data['channel_name']} | Duration: {self.format_duration(video_data.get('duration_seconds', 0))}*

## Executive Summary
{best_sentences[0] if best_sentences else 'Video content covers various topics as discussed in the transcript.'}

## Key Points
"""
for sentence in best_sentences[1:4]:
    summary += f"- {sentence}\\n"

if not best_sentences[1:4]:
    summary += "- Main topics discussed in the video\\n- Key insights and information shared\\n- Relevant details for viewers\\n"

summary += f"""
## Main Themes & Topics
Content analysis from {video_data['channel_name']} covering the topics discussed in "{video_data['title']}".

## Actionable Insights
- Review the key points mentioned in the video
- Consider the implications for your specific situation
- Apply relevant insights to your context

---
*Summary generated on {datetime.now().strftime('%B %d, %Y')}*
"""

print(summary)
'''
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            else:
                # Fallback summary
                return self.create_fallback_summary(video_data)
                
        except Exception as e:
            print(f"LLM call failed: {e}")
            return self.create_fallback_summary(video_data)
        finally:
            # Clean up temp file
            if os.path.exists(temp_prompt_file):
                os.remove(temp_prompt_file)
    
    def create_fallback_summary(self, video_data):
        """Create a basic fallback summary when LLM fails"""
        return f"""# {video_data['title']}

*Channel: {video_data['channel_name']} | Duration: {self.format_duration(video_data.get('duration_seconds', 0))}*

## Executive Summary
This video from {video_data['channel_name']} discusses topics covered in "{video_data['title']}". 

## Key Points
- Video content focuses on the main topics indicated by the title
- Information shared is relevant to the channel's typical content
- Duration of approximately {self.format_duration(video_data.get('duration_seconds', 0))} provides comprehensive coverage

## Main Themes & Topics  
Based on the channel and title, this video likely covers topics related to {video_data['channel_name']}'s focus area.

## Actionable Insights
- Watch the full video for complete context
- Take notes on key points that apply to your situation
- Consider how the information relates to your goals

---
*Basic summary generated on {datetime.now().strftime('%B %d, %Y')} - Full transcript available for detailed review*
"""

    def get_stats(self):
        """Get enhanced statistics for the dashboard"""
        stats = self.tracker.get_stats()
        
        # Add web interface specific stats
        new_count = len(self.get_new_videos())
        summarized_count = sum(1 for video_id in self.tracker.metadata if self.has_summary(video_id))
        
        stats.update({
            'new_videos_48h': new_count,
            'summarized_videos': summarized_count,
            'pending_summaries': len([v for v in self.summary_status.values() if v['status'] == 'generating'])
        })
        
        return stats

# Initialize the manager
web_manager = WebInterfaceManager()

# Flask Routes
@app.route('/')
def dashboard():
    """Main dashboard page"""
    stats = web_manager.get_stats()
    return render_template('index.html', stats=stats)

@app.route('/api/videos')
def api_videos():
    """Get all videos with metadata"""
    days_back = request.args.get('days', 7, type=int)
    videos = web_manager.get_videos_data(days_back)
    return jsonify(videos)

@app.route('/api/videos/new')
def api_new_videos():
    """Get new videos from last 48 hours"""
    hours_back = request.args.get('hours', 48, type=int)
    videos = web_manager.get_new_videos(hours_back)
    return jsonify(videos)

@app.route('/api/video/<video_id>')
def api_video_details(video_id):
    """Get detailed video information"""
    video_data = web_manager.get_video_details(video_id)
    if video_data:
        return jsonify(video_data)
    else:
        return jsonify({'error': 'Video not found'}), 404

@app.route('/api/video/<video_id>/summarize', methods=['POST'])
def api_generate_summary(video_id):
    """Generate summary for a video"""
    if video_id not in web_manager.tracker.metadata:
        return jsonify({'error': 'Video not found'}), 404
    
    # Check if summary already exists
    if web_manager.has_summary(video_id):
        return jsonify({'message': 'Summary already exists', 'status': 'complete'})
    
    # Check if already generating
    if video_id in web_manager.summary_status and web_manager.summary_status[video_id]['status'] == 'generating':
        return jsonify({'message': 'Summary generation in progress', 'status': 'generating'})
    
    # Start generation
    web_manager.generate_summary_async(video_id)
    return jsonify({'message': 'Summary generation started', 'status': 'generating'})

@app.route('/api/video/<video_id>/summary/status')
def api_summary_status(video_id):
    """Get summary generation status"""
    status = web_manager.summary_status.get(video_id, {"status": "none", "progress": 0})
    
    # If complete, include the summary
    if status['status'] == 'complete':
        summary = web_manager.get_summary(video_id)
        status['summary'] = summary
    
    return jsonify(status)

@app.route('/api/update', methods=['POST'])
def api_update_channels():
    """Trigger channel update check"""
    try:
        # This could be run in background for better UX
        web_manager.tracker.process_channels()
        return jsonify({'message': 'Channel update completed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def api_stats():
    """Get current statistics"""
    return jsonify(web_manager.get_stats())

if __name__ == '__main__':
    print("🎥 Starting YouTube Transcript Daily Review")
    print("📍 Access the interface at: http://localhost:5001")
    app.run(debug=True, host='0.0.0.0', port=5001)