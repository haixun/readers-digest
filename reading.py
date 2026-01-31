#!/usr/bin/env python3
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os
import sys
from urllib.parse import urljoin, urlparse
import time
import json
import hashlib
import subprocess
try:
    import dateutil.parser
except ImportError:
    print("Warning: python-dateutil not installed. Date parsing may be limited.")
    dateutil = None

class NewsletterAnalyzer:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        self.cache_file = "/Users/haixun/projects/0 Life/Reading/.processed_posts.json"
        self.processed_posts = self.load_cache()
    
    def load_cache(self):
        """Load previously processed posts from cache"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load cache: {e}")
        return {}
    
    def save_cache(self):
        """Save processed posts to cache"""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.processed_posts, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save cache: {e}")
    
    def get_post_hash(self, url):
        """Generate a hash for a post URL"""
        return hashlib.md5(url.encode()).hexdigest()
    
    def is_likely_content_link(self, href, title, full_url, base_url):
        """Intelligently determine if a link is likely to be content/post"""
        href_lower = href.lower()
        title_lower = title.lower()
        
        # Skip obvious non-content links
        skip_patterns = [
            'about', 'contact', 'privacy', 'terms', 'subscribe', 'login', 'register',
            'search', 'tag', 'category', 'archive', 'rss', 'feed', 'xml',
            'twitter', 'facebook', 'linkedin', 'instagram', 'youtube',
            'mailto:', 'tel:', '#', 'javascript:', 'share', 'comment',
            '.pdf', '.jpg', '.png', '.gif', '.svg', '.css', '.js'
        ]
        
        if any(pattern in href_lower or pattern in title_lower for pattern in skip_patterns):
            return False
        
        # Skip if it's just a domain or very short path
        if href in ['/', ''] or len(href.strip('/')) < 3:
            return False
        
        # Skip external links - allow same domain with different paths
        if not href.startswith(('/', '#')):
            # Allow same domain links (e.g., blog.site.com vs site.com/letters)
            try:
                base_domain = urlparse(base_url).netloc.lower()
                href_domain = urlparse(full_url).netloc.lower()
                
                # Remove 'www.' prefix for comparison
                base_domain = base_domain.replace('www.', '')
                href_domain = href_domain.replace('www.', '')
                
                if base_domain != href_domain:
                    return False
            except:
                return False
        
        # Positive signals for content
        content_signals = [
            # URL patterns
            '/20', '/19',  # Years in URL (common in blog posts)
            '-', '_',      # Dashes/underscores often in post URLs
            
            # Title signals  
            'how to', 'why', 'what', 'when', 'where', 'guide', 'tips',
            'analysis', 'review', 'insights', 'lessons', 'thoughts',
            'introduction', 'understanding', 'explaining', 'deep dive',
            'case study', 'framework', 'strategy', 'approach'
        ]
        
        # Check for content signals
        signal_count = sum(1 for signal in content_signals if signal in href_lower or signal in title_lower)
        
        # URL structure analysis
        path_parts = [part for part in href.split('/') if part]
        has_date_pattern = any(part.isdigit() and len(part) == 4 and part.startswith(('19', '20')) for part in path_parts)
        has_slug_pattern = any(len(part) > 10 and ('-' in part or '_' in part) for part in path_parts)
        
        # Title analysis - longer titles are more likely to be articles
        title_length_score = min(len(title.split()), 10) / 10  # Normalize to 0-1
        
        # Combine all signals
        score = (
            signal_count * 0.3 +
            (1 if has_date_pattern else 0) * 0.3 +
            (1 if has_slug_pattern else 0) * 0.2 +
            title_length_score * 0.2
        )
        
        return score > 0.3  # Threshold for considering it content

    def extract_urls_from_readinglist(self, file_path):
        """Extract URLs from the readinglist.md file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extract URLs from both org-mode links [[URL][title]] and plain URLs
        # First try org-mode links
        org_links = re.findall(r'\[\[([^]]+)\]\[[^]]*\]\]', content)
        
        # Then try markdown links
        markdown_links = re.findall(r'\[([^]]*)\]\(([^)]+)\)', content)
        
        # Also find plain URLs
        plain_urls = re.findall(r'https?://[^\s\]\)]+(?:\.[^\s\]\)]+)*/?', content)
        
        # Combine all URLs
        all_urls = []
        all_urls.extend(org_links)  # org-mode URLs
        all_urls.extend([url for _, url in markdown_links])  # markdown URLs
        all_urls.extend(plain_urls)  # plain URLs
        
        # Clean up URLs and deduplicate more aggressively
        clean_urls = []
        seen_domains = set()
        
        for url in all_urls:
            # Clean URL
            clean_url = url.rstrip('.,;:!?').strip()
            
            if not clean_url.startswith('http'):
                continue
            
            # Extract domain for better deduplication
            try:
                parsed = urlparse(clean_url)
                domain = parsed.netloc.lower()
                
                # Skip if we've seen this domain before
                if domain in seen_domains:
                    continue
                    
                clean_urls.append(clean_url)
                seen_domains.add(domain)
            except:
                # If URL parsing fails, skip it
                continue
        
        return clean_urls
    
    def fetch_recent_posts(self, base_url):
        """Fetch recent posts from a newsletter/blog URL"""
        try:
            response = self.session.get(base_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract site title
            site_title = soup.find('title')
            site_title = site_title.text.strip() if site_title else urlparse(base_url).netloc
            
            # Look for article links and titles
            articles = []
            
            # Enhanced selectors for blog posts/articles
            selectors = [
                # Direct article links
                'article h1 a, article h2 a, article h3 a, article .title a',
                '.post-title a, .entry-title a, .post-link a',
                '.article-title a, .blog-title a, .story-title a',
                
                # Content area headings
                'main h1 a, main h2 a, main h3 a',
                '.content h1 a, .content h2 a, .content h3 a',
                '.posts h1 a, .posts h2 a, .posts h3 a',
                
                # Common blog structures
                '.post h1 a, .post h2 a, .entry h1 a, .entry h2 a',
                '.blog-post a, .article a, .story a',
                
                # Newsletter/feed structures
                '.newsletter-item a, .feed-item a, .post-item a',
                
                # General heading links (broader search)
                'h1 a, h2 a, h3 a'
            ]
            
            for selector in selectors:
                links = soup.select(selector)
                for link in links[:8]:  # Get up to 8 recent posts
                    href = link.get('href')
                    title = link.get_text(strip=True)
                    if href and title and len(title) > 5:  # Reduced from 10 to 5
                        full_url = urljoin(base_url, href)
                        # Use intelligent filtering
                        if self.is_likely_content_link(href, title, full_url, base_url):
                            articles.append({'title': title, 'url': full_url})
                
                if len(articles) >= 5:  # Stop when we have enough
                    break
            
            # If no articles found with selectors, intelligently analyze all links
            if not articles:
                all_links = soup.find_all('a', href=True)
                for link in all_links[:50]:  # Increased from 20 to 50
                    href = link['href']
                    title = link.get_text(strip=True)
                    if href and title and len(title) > 10:
                        full_url = urljoin(base_url, href)
                        
                        # Intelligent filtering - look for content-like characteristics
                        if self.is_likely_content_link(href, title, full_url, base_url):
                            articles.append({'title': title, 'url': full_url})
                            if len(articles) >= 5:  # Increased from 3 to 5
                                break
            
            # Remove duplicates while preserving order
            seen_urls = set()
            unique_articles = []
            for article in articles:
                if article['url'] not in seen_urls:
                    unique_articles.append(article)
                    seen_urls.add(article['url'])
                    if len(unique_articles) >= 5:  # Increased from 3 to 5
                        break

            return {
                'site_title': site_title,
                'base_url': base_url,
                'articles': unique_articles,
                'success': True
            }
            
        except Exception as e:
            return {
                'site_title': urlparse(base_url).netloc,
                'base_url': base_url,
                'articles': [],
                'success': False,
                'error': str(e)
            }
    
    def extract_post_date(self, soup):
        """Extract post publication date from HTML"""
        date_selectors = [
            'time[datetime]', 'time[pubdate]', '.date', '.published', '.post-date',
            '.entry-date', '.article-date', '[datetime]', '.timestamp', '.pub-date'
        ]
        
        for selector in date_selectors:
            date_elem = soup.select_one(selector)
            if date_elem:
                # Try datetime attribute first
                date_attr = date_elem.get('datetime') or date_elem.get('pubdate')
                if date_attr:
                    try:
                        # Parse various date formats
                        if dateutil:
                            parsed_date = dateutil.parser.parse(date_attr)
                            return parsed_date.strftime('%B %d, %Y')
                    except:
                        pass
                
                # Try text content
                date_text = date_elem.get_text().strip()
                if date_text:
                    try:
                        if dateutil:
                            parsed_date = dateutil.parser.parse(date_text)
                            return parsed_date.strftime('%B %d, %Y')
                    except:
                        pass
        
        # Look for date patterns in text
        date_patterns = [
            r'(\w+ \d{1,2}, \d{4})',  # January 15, 2024
            r'(\d{4}-\d{2}-\d{2})',   # 2024-01-15
            r'(\d{1,2}/\d{1,2}/\d{4})'  # 1/15/2024
        ]
        
        page_text = soup.get_text()
        for pattern in date_patterns:
            matches = re.findall(pattern, page_text)
            if matches:
                try:
                    if dateutil:
                        parsed_date = dateutil.parser.parse(matches[0])
                        return parsed_date.strftime('%B %d, %Y')
                except:
                    continue
        
        return None

    def analyze_content(self, article_url):
        """Fetch and analyze content from an article URL"""
        try:
            response = self.session.get(article_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract post date
            post_date = self.extract_post_date(soup)
            
            # Remove unwanted elements
            for element in soup(["script", "style", "nav", "header", "footer", 
                                "aside", ".sidebar", ".navigation", ".menu", 
                                ".comments", ".related", ".share", ".tags"]):
                element.decompose()
            
            # Try to find the main article content
            content_selectors = [
                'article .content, article .post-content, article .entry-content',
                '.post-content, .entry-content, .article-content',
                'article p, .content p, main p',
                'article', '.post', '.entry', 'main'
            ]
            
            content_text = ""
            for selector in content_selectors:
                elements = soup.select(selector)
                if elements:
                    # Get text from paragraphs specifically
                    paragraphs = []
                    for elem in elements:
                        # Look for paragraph tags within the element
                        ps = elem.find_all('p')
                        if ps:
                            for p in ps:
                                text = p.get_text().strip()
                                if len(text) > 30:  # Skip very short paragraphs
                                    paragraphs.append(text)
                    
                    if paragraphs:
                        content_text = ' '.join(paragraphs)
                        break
            
            # Fallback: get all paragraph text
            if not content_text:
                paragraphs = soup.find_all('p')
                content_paragraphs = []
                for p in paragraphs:
                    text = p.get_text().strip()
                    if (len(text) > 50 and 
                        not any(skip in text.lower() for skip in ['subscribe', 'follow', 'share', 'comment', 'navigation', 'menu', 'copyright'])):
                        content_paragraphs.append(text)
                
                content_text = ' '.join(content_paragraphs)
            
            # Clean up the text
            if content_text:
                # Remove extra whitespace
                content_text = ' '.join(content_text.split())
                
                # Remove common boilerplate patterns
                patterns_to_remove = [
                    r'Subscribe.*?Newsletter',
                    r'Follow.*?Twitter',
                    r'Share.*?Facebook',
                    r'Comments.*?below',
                    r'Originally published.*?\d{4}',
                    r'Read more.*?here',
                    r'Click here.*?experience'
                ]
                
                for pattern in patterns_to_remove:
                    content_text = re.sub(pattern, '', content_text, flags=re.IGNORECASE)
                
                # Limit content length for analysis
                content_text = content_text[:3000]  # Increased for better summarization
            
            return {
                'content': content_text if content_text else "No substantial content found",
                'date': post_date
            }
            
        except Exception as e:
            return {
                'content': f"Could not fetch content: {str(e)}",
                'date': None
            }
    
    def create_proper_summary(self, content):
        """Create a proper summary from article content"""
        if "Could not fetch content:" in content or content == "No substantial content found":
            return None, []
        
        # Clean and prepare content
        content = content.strip()
        if not content:
            return None, []
        
        # Split into sentences
        sentences = [s.strip() for s in re.split(r'[.!?]+', content) if len(s.strip()) > 20]
        
        if not sentences:
            return None, []
        
        # Score sentences based on importance indicators
        scored_sentences = []
        for i, sentence in enumerate(sentences[:20]):  # Limit to first 20 sentences
            score = 0
            sentence_lower = sentence.lower()
            
            # Position scoring (earlier sentences often more important)
            score += max(0, 10 - i)
            
            # Length scoring (moderate length preferred)
            word_count = len(sentence.split())
            if 10 <= word_count <= 30:
                score += 5
            elif word_count < 10:
                score -= 2
            
            # Content quality indicators
            importance_words = [
                'however', 'therefore', 'because', 'shows', 'demonstrates', 'reveals', 
                'suggests', 'argues', 'important', 'key', 'main', 'primary', 'central',
                'problem', 'solution', 'approach', 'method', 'strategy', 'insight',
                'research', 'study', 'analysis', 'finding', 'result', 'conclusion'
            ]
            
            for word in importance_words:
                if word in sentence_lower:
                    score += 3
            
            # Avoid promotional/boilerplate content
            avoid_words = [
                'subscribe', 'follow', 'share', 'click', 'link', 'newsletter', 
                'twitter', 'facebook', 'comment', 'below', 'above', 'here'
            ]
            
            for word in avoid_words:
                if word in sentence_lower:
                    score -= 5
            
            # Avoid sentences that seem like fragments or references
            if (sentence.startswith(('to ', 'and ', 'or ', 'but ', 'so ')) or 
                len([c for c in sentence if c.isupper()]) > len(sentence) * 0.3):
                score -= 3
            
            scored_sentences.append((sentence, score))
        
        # Sort by score and take top sentences
        scored_sentences.sort(key=lambda x: x[1], reverse=True)
        
        # Select best sentences to create summary
        selected_sentences = []
        total_words = 0
        target_words = 80  # Target summary length
        
        for sentence, score in scored_sentences:
            if score > 0:  # Only include sentences with positive scores
                word_count = len(sentence.split())
                if total_words + word_count <= target_words + 20:  # Allow some flexibility
                    selected_sentences.append(sentence)
                    total_words += word_count
                    if total_words >= target_words:
                        break
        
        # If no good sentences found, fall back to first few sentences
        if not selected_sentences and sentences:
            selected_sentences = sentences[:2]
        
        # Create summary
        if selected_sentences:
            summary = '. '.join(selected_sentences)
            if not summary.endswith('.'):
                summary += '.'
            return summary
        
        return None
    
    def detect_topics(self, content):
        """Detect topics from content"""
        if not content:
            return []
        
        content_lower = content.lower()
        topics = []
        
        theme_keywords = {
            'business strategy': ['business', 'strategy', 'startup', 'entrepreneur', 'growth', 'market', 'revenue', 'company', 'competitive', 'industry'],
            'psychology': ['psychology', 'behavior', 'mental', 'mind', 'cognitive', 'brain', 'emotion', 'human', 'thinking', 'perception'],
            'technology': ['technology', 'tech', 'software', 'ai', 'artificial intelligence', 'digital', 'internet', 'data', 'algorithm', 'computer'],
            'productivity': ['productivity', 'efficiency', 'time', 'habits', 'systems', 'workflow', 'organization', 'focus', 'performance'],
            'finance': ['investing', 'finance', 'money', 'wealth', 'economics', 'financial', 'investment', 'capital', 'income', 'profit'],
            'leadership': ['leadership', 'management', 'team', 'culture', 'organization', 'people', 'communication', 'influence', 'management'],
            'creativity': ['creativity', 'innovation', 'design', 'thinking', 'creative', 'art', 'ideas', 'imagination', 'innovation'],
            'writing': ['writing', 'content', 'storytelling', 'communication', 'words', 'language', 'narrative', 'author', 'publish'],
            'personal development': ['development', 'improvement', 'growth', 'learning', 'skills', 'habits', 'mindset', 'success', 'goals']
        }
        
        for theme, keywords in theme_keywords.items():
            keyword_count = sum(1 for keyword in keywords if keyword in content_lower)
            if keyword_count >= 2:  # Require at least 2 matching keywords
                topics.append(theme)
        
        return topics[:4]  # Limit to 4 topics
    
    def generate_post_summary(self, article_title, article_url, content_data):
        """Generate a ~100 word summary for a specific post"""
        # Handle both old string format and new dict format
        if isinstance(content_data, str):
            content = content_data
            post_date = None
        else:
            content = content_data.get('content', '')
            post_date = content_data.get('date', None)
        
        if "Could not fetch content:" in content or content == "No substantial content found":
            return f"**[{article_title}]({article_url})**\n\nUnable to fetch content from this post.\n\n---\n\n"
        
        # Create proper summary
        summary_text = self.create_proper_summary(content)
        topics = self.detect_topics(content)
        
        # Build the final summary
        summary = f"**[{article_title}]({article_url})**"
        
        # Add date if available
        if post_date:
            summary += f"\n\n*Published: {post_date}*"
        
        summary += "\n\n"
        
        if summary_text:
            summary += summary_text
        else:
            summary += "Content could not be properly summarized."
        
        # Add topics
        if topics:
            summary += f"\n\n*Topics: {', '.join(topics)}*"
        
        summary += "\n\n---\n\n"
        return summary
    
    def generate_newsletter_summary(self, newsletter_data):
        """Generate summaries for all posts from a newsletter"""
        if not newsletter_data['success'] or not newsletter_data['articles']:
            return f"## {newsletter_data['site_title']}\n\nUnable to fetch recent content from [{newsletter_data['base_url']}]({newsletter_data['base_url']})\n\n---\n\n"
        
        site_title = newsletter_data['site_title']
        base_url = newsletter_data['base_url']
        
        summary = f"## {site_title}\n\n*Source: [{base_url}]({base_url})*\n\n"
        
        new_posts_count = 0
        cached_posts_count = 0
        
        # Generate individual post summaries
        for article in newsletter_data['articles']:
            article_hash = self.get_post_hash(article['url'])
            
            # Check if we've already processed this post
            if article_hash in self.processed_posts:
                print(f"  ✅ Using cached: {article['title'][:50]}...")
                cached_summary = self.processed_posts[article_hash]
                summary += cached_summary
                cached_posts_count += 1
            else:
                print(f"  📝 Analyzing: {article['title'][:50]}...")
                content_data = self.analyze_content(article['url'])
                post_summary = self.generate_post_summary(article['title'], article['url'], content_data)
                summary += post_summary
                
                # Cache the summary
                self.processed_posts[article_hash] = post_summary
                new_posts_count += 1
                
                # Be respectful with requests
                time.sleep(0.5)
        
        if new_posts_count > 0:
            print(f"  💾 Cached {new_posts_count} new summaries, reused {cached_posts_count} cached summaries")
        
        return summary

def main():
    analyzer = NewsletterAnalyzer()
    
    # Path to the reading list
    reading_list_path = "/Users/haixun/projects/0 Life/Reading/readinglist.md"
    output_dir = "/Users/haixun/projects/0 Life/Reading"
    
    if not os.path.exists(reading_list_path):
        print(f"Error: Reading list not found at {reading_list_path}")
        return
    
    print("🔍 Extracting URLs from reading list...")
    urls = analyzer.extract_urls_from_readinglist(reading_list_path)
    
    print(f"📰 Found {len(urls)} sources to analyze...")
    
    # Analyze each newsletter/blog
    summaries = []
    total_posts = 0
    for i, url in enumerate(urls, 1):
        print(f"📖 Analyzing {i}/{len(urls)}: {url}")
        
        newsletter_data = analyzer.fetch_recent_posts(url)
        summary = analyzer.generate_newsletter_summary(newsletter_data)
        summaries.append(summary)
        
        if newsletter_data['success']:
            total_posts += len(newsletter_data['articles'])
        
        # Be respectful with requests
        time.sleep(1)
    
    # Generate final report
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    report = f"# Reading List Analysis\n\n"
    report += f"*Generated on {timestamp}*\n\n"
    report += f"Individual post summaries from {len(urls)} newsletters and blogs in your reading list.\n\n"
    report += f"**Total posts analyzed: {total_posts}**\n\n"
    report += "---\n\n"
    
    for summary in summaries:
        report += summary
    
    # Save the report
    output_path = os.path.join(output_dir, f"update_{datetime.now().strftime('%Y%m%d')}.md")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    # Save cache for future runs
    analyzer.save_cache()
    
    print(f"✅ Analysis complete! Report saved to: {output_path}")
    print(f"📊 Analyzed {total_posts} individual posts from {len(summaries)} sources")

if __name__ == "__main__":
    main()