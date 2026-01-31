from pathlib import Path

from pipeline.readinglist_parser import ReadingListParser


SAMPLE = """
# Youtube Videos
- [Finance] https://www.youtube.com/watch?v=dQw4w9WgXcQ

# Youtube Channels
- [Technology] AI Channel: https://www.youtube.com/@example | tags: ai, ml

# Blogs
- [Productivity] Writer Name: https://example.com/blog (tags: habits, focus)
"""


def test_reading_list_parser_extracts_categories(tmp_path: Path) -> None:
    file_path = tmp_path / "readinglist.md"
    file_path.write_text(SAMPLE, encoding="utf-8")

    parser = ReadingListParser(file_path)
    entries = parser.parse()

    assert len(entries) == 3
    video = entries[0]
    assert video.source_type == "youtube_video"
    assert video.category == "Finance"
    assert video.metadata["video_id"] == "dQw4w9WgXcQ"

    channel = entries[1]
    assert channel.tags == ["ai", "ml"]
    assert channel.category == "Technology"

    blog = entries[2]
    assert blog.source_type == "blog"
    assert blog.category == "Productivity"
    assert blog.tags == ["habits", "focus"]
