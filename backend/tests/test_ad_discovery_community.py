"""Tests for community blocklist matcher."""
import os
import asyncio
import gzip
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("NAS_MODE", "dev")
os.environ.setdefault("NAS_QUOTA_BYTES", str(10 * 1024 * 1024 * 1024))

from app.services.pihole.ad_discovery.community_matcher import (
    CommunityMatcher,
    MatchResult,
    _parse_list_content,
    _validate_url,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestParseListContent:
    def test_parse_domain_per_line(self):
        """Parse one-domain-per-line format correctly."""
        content = "ads.example.com\ntracker.foo.com\nanalytics.bar.net"
        result = _parse_list_content(content)
        assert "ads.example.com" in result
        assert "tracker.foo.com" in result
        assert "analytics.bar.net" in result
        assert len(result) == 3

    def test_parse_hosts_format(self):
        """Parse hosts format '0.0.0.0 domain.com' correctly."""
        content = "0.0.0.0 ads.example.com\n127.0.0.1 tracker.foo.com\n0.0.0.0 analytics.bar.net"
        result = _parse_list_content(content)
        assert "ads.example.com" in result
        assert "tracker.foo.com" in result
        assert "analytics.bar.net" in result
        assert len(result) == 3

    def test_parse_ignores_comments(self):
        """Lines starting with '#' are skipped."""
        content = "# This is a comment\n# Another comment\nads.example.com\n# End"
        result = _parse_list_content(content)
        assert "ads.example.com" in result
        assert len(result) == 1

    def test_parse_ignores_blank_lines(self):
        """Empty/whitespace-only lines are skipped."""
        content = "\n\nads.example.com\n\n   \ntracker.foo.com\n\n"
        result = _parse_list_content(content)
        assert "ads.example.com" in result
        assert "tracker.foo.com" in result
        assert len(result) == 2

    def test_parse_mixed_format(self):
        """Handles mixed hosts and domain-per-line format."""
        content = (
            "# Pi-hole list\n"
            "0.0.0.0 ads.doubleclick.net\n"
            "\n"
            "tracker.example.com\n"
            "127.0.0.1 pixel.evil.com\n"
            "# Comment at end\n"
        )
        result = _parse_list_content(content)
        assert "ads.doubleclick.net" in result
        assert "tracker.example.com" in result
        assert "pixel.evil.com" in result
        assert len(result) == 3

    def test_parse_case_normalizes_to_lowercase(self):
        """Domains are lowercased during parsing."""
        content = "ADS.EXAMPLE.COM\nTracker.Foo.COM"
        result = _parse_list_content(content)
        assert "ads.example.com" in result
        assert "tracker.foo.com" in result

    def test_parse_skips_localhost_in_hosts_format(self):
        """'localhost' entry from hosts format is excluded."""
        content = "127.0.0.1 localhost\n0.0.0.0 ads.example.com"
        result = _parse_list_content(content)
        assert "localhost" not in result
        assert "ads.example.com" in result

    def test_parse_inline_comments_in_hosts(self):
        """Inline comments after the domain in hosts format are stripped."""
        content = "0.0.0.0 ads.example.com # This is blocked"
        result = _parse_list_content(content)
        assert "ads.example.com" in result
        assert len(result) == 1


class TestValidateUrl:
    def test_ssrf_rejects_non_https(self):
        """HTTP URLs are rejected (SSRF protection)."""
        with pytest.raises(ValueError, match="Only HTTPS"):
            _validate_url("http://example.com/blocklist.txt")

    def test_ssrf_rejects_ftp(self):
        """Non-https schemes are rejected."""
        with pytest.raises(ValueError, match="Only HTTPS"):
            _validate_url("ftp://example.com/blocklist.txt")

    def test_ssrf_rejects_private_ip(self):
        """Private IP URLs are rejected (SSRF protection)."""
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [(None, None, None, None, ("192.168.1.1", 0))]
            with pytest.raises(ValueError, match="private/reserved"):
                _validate_url("https://internal-server.example/list.txt")

    def test_ssrf_rejects_loopback_ip(self):
        """Loopback IP addresses are rejected."""
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [(None, None, None, None, ("127.0.0.1", 0))]
            with pytest.raises(ValueError, match="private/reserved"):
                _validate_url("https://localhost/list.txt")

    def test_ssrf_rejects_link_local_ip(self):
        """Link-local IP addresses are rejected."""
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [(None, None, None, None, ("169.254.0.1", 0))]
            with pytest.raises(ValueError, match="private/reserved"):
                _validate_url("https://example.com/list.txt")

    def test_valid_https_url_passes(self):
        """Valid HTTPS URL resolving to public IP passes validation."""
        with patch("socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [(None, None, None, None, ("1.1.1.1", 0))]
            # Should not raise
            _validate_url("https://raw.githubusercontent.com/list.txt")


class TestMatchDomain:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.matcher = CommunityMatcher()
        self.matcher.load_sets(1, "Test List A", {"ads.example.com", "tracker.foo.com"})
        self.matcher.load_sets(2, "Test List B", {"pixel.evil.com", "analytics.bad.net"})

    def test_match_domain_found(self):
        """Domain present in a loaded set returns a match."""
        result = self.matcher.match_domain("ads.example.com")
        assert isinstance(result, MatchResult)
        assert result.domain == "ads.example.com"
        assert result.hits == 1
        assert "Test List A" in result.matched_lists

    def test_match_domain_not_found(self):
        """Domain absent from all sets returns no match."""
        result = self.matcher.match_domain("github.com")
        assert result.domain == "github.com"
        assert result.hits == 0
        assert result.matched_lists == []

    def test_match_domain_in_multiple_lists(self):
        """Domain present in multiple lists reports all of them."""
        # Add same domain to second list
        self.matcher.load_sets(2, "Test List B", {"ads.example.com", "pixel.evil.com"})
        result = self.matcher.match_domain("ads.example.com")
        assert result.hits == 2
        assert "Test List A" in result.matched_lists
        assert "Test List B" in result.matched_lists

    def test_match_domain_case_insensitive(self):
        """Domain matching is case-insensitive."""
        result = self.matcher.match_domain("ADS.EXAMPLE.COM")
        assert result.hits == 1

    def test_match_domains_batch(self):
        """Batch matching works correctly for multiple domains."""
        domains = ["ads.example.com", "github.com", "tracker.foo.com", "pixel.evil.com"]
        results = self.matcher.match_domains(domains)

        assert len(results) == 4
        assert results[0].hits == 1   # ads.example.com — in List A
        assert results[1].hits == 0   # github.com — no match
        assert results[2].hits == 1   # tracker.foo.com — in List A
        assert results[3].hits == 1   # pixel.evil.com — in List B

    def test_match_domains_batch_empty(self):
        """Batch matching of empty list returns empty list."""
        results = self.matcher.match_domains([])
        assert results == []


class TestCacheRoundtrip:
    def test_cache_roundtrip(self, tmp_path: Path):
        """Write domains to gzip cache, load back, verify content matches."""
        matcher = CommunityMatcher(cache_dir=tmp_path)
        original_domains = {"ads.example.com", "tracker.foo.com", "pixel.evil.com"}
        matcher.load_sets(42, "Roundtrip List", original_domains)

        # Save to disk
        matcher.save_to_cache(42)

        # Verify file was created
        cache_file = tmp_path / "42.gz"
        assert cache_file.exists()

        # Load into a fresh matcher instance
        fresh_matcher = CommunityMatcher(cache_dir=tmp_path)
        count = fresh_matcher.load_from_cache(42, "Roundtrip List")

        assert count == len(original_domains)

        # Verify all domains survived the roundtrip
        for domain in original_domains:
            result = fresh_matcher.match_domain(domain)
            assert result.hits == 1, f"Expected {domain} to be found after cache roundtrip"

    def test_load_from_cache_missing_file_returns_zero(self, tmp_path: Path):
        """Loading a non-existent cache file returns 0 domains."""
        matcher = CommunityMatcher(cache_dir=tmp_path)
        count = matcher.load_from_cache(999, "Nonexistent")
        assert count == 0

    def test_cache_gzip_format(self, tmp_path: Path):
        """Cache file is valid gzip containing newline-separated domains."""
        matcher = CommunityMatcher(cache_dir=tmp_path)
        domains = {"alpha.com", "beta.com", "gamma.com"}
        matcher.load_sets(7, "Format Test", domains)
        matcher.save_to_cache(7)

        with gzip.open(tmp_path / "7.gz", "rt", encoding="utf-8") as f:
            content = f.read()

        loaded = set(line.strip() for line in content.splitlines() if line.strip())
        assert loaded == domains


class TestFetchList:
    def test_fetch_list_calls_validate_and_parses(self, tmp_path: Path):
        """fetch_list validates the URL, parses content, caches and loads it."""
        blocklist_content = "ads.example.com\ntracker.foo.com\n# comment\n0.0.0.0 pixel.bad.com"

        mock_response = MagicMock()
        mock_response.text = blocklist_content
        mock_response.content = blocklist_content.encode()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        matcher = CommunityMatcher(cache_dir=tmp_path)

        with patch("app.services.pihole.ad_discovery.community_matcher._validate_url") as mock_val, \
             patch("app.services.pihole.ad_discovery.community_matcher.httpx.AsyncClient", return_value=mock_client):
            count = _run(matcher.fetch_list(1, "https://example.com/list.txt", "Test"))

        mock_val.assert_called_once_with("https://example.com/list.txt")
        assert count == 3  # ads.example.com, tracker.foo.com, pixel.bad.com

        # Verify in-memory load
        result = matcher.match_domain("ads.example.com")
        assert result.hits == 1

        # Verify cache written
        assert (tmp_path / "1.gz").exists()

    def test_fetch_list_raises_on_ssrf(self, tmp_path: Path):
        """fetch_list propagates ValueError from _validate_url."""
        matcher = CommunityMatcher(cache_dir=tmp_path)

        with patch("app.services.pihole.ad_discovery.community_matcher._validate_url",
                   side_effect=ValueError("Only HTTPS URLs are allowed")):
            with pytest.raises(ValueError, match="Only HTTPS"):
                _run(matcher.fetch_list(1, "http://insecure.com/list.txt", "Bad"))
