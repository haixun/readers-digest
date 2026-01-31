from cache_manager import CacheManager


def test_cache_manager_round_trip(tmp_path):
    cache = CacheManager(raw_dir=tmp_path / "raw", summary_dir=tmp_path / "summaries")

    payload = {"content_hash": "abc123", "value": 42}
    cache.save_raw("blogs", "item1", payload)

    retrieved = cache.load_raw("blogs", "item1")
    assert retrieved["value"] == 42
    assert cache.raw_is_current("blogs", "item1", "abc123")

    summary_payload = {"summary": "Summary text", "content_hash": "abc123"}
    cache.save_summary("item1", summary_payload)

    summary = cache.load_summary("item1")
    assert summary["summary"] == "Summary text"
