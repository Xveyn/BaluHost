"""Tests for services/user_metadata_cache.py — pure logic, no DB needed."""

from app.services.user_metadata_cache import fetch_metadata_from_db, get_user_metadata


class TestFetchMetadataFromDb:
    def test_returns_dict_with_expected_keys(self):
        result = fetch_metadata_from_db(1)
        assert result == {"user_id": 1, "name": "User1", "role": "user"}

    def test_different_user_ids(self):
        for uid in (0, 42, 9999):
            result = fetch_metadata_from_db(uid)
            assert result["user_id"] == uid
            assert result["name"] == f"User{uid}"


class TestGetUserMetadata:
    def test_returns_correct_metadata(self):
        get_user_metadata.cache_clear()
        result = get_user_metadata(10)
        assert result["user_id"] == 10
        assert result["role"] == "user"

    def test_caching_returns_same_object(self):
        get_user_metadata.cache_clear()
        first = get_user_metadata(5)
        second = get_user_metadata(5)
        # lru_cache should return the exact same object
        assert first is second

    def test_cache_info_shows_hits(self):
        get_user_metadata.cache_clear()
        get_user_metadata(7)
        get_user_metadata(7)
        info = get_user_metadata.cache_info()
        assert info.hits >= 1
        assert info.misses >= 1
