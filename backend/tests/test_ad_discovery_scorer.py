"""Tests for the heuristic scoring engine."""
import os
import asyncio
import pytest

os.environ.setdefault("NAS_MODE", "dev")
os.environ.setdefault("NAS_QUOTA_BYTES", str(10 * 1024 * 1024 * 1024))

from app.services.pihole.ad_discovery.scorer import Scorer, ScoredResult


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestScorer:
    @pytest.fixture(autouse=True)
    def _setup(self):
        # Load patterns directly (no DB needed for unit tests)
        self.scorer = Scorer()
        self.scorer.load_patterns([
            {"pattern": "ad.", "is_regex": False, "weight": 0.8, "category": "ads"},
            {"pattern": "tracker.", "is_regex": False, "weight": 0.7, "category": "tracking"},
            {"pattern": r"^pixel\.", "is_regex": True, "weight": 0.6, "category": "tracking"},
            {"pattern": "analytics.", "is_regex": False, "weight": 0.4, "category": "analytics"},
        ])

    def test_substring_match(self):
        result = self.scorer.score_domain("ad.doubleclick.net")
        assert result.score > 0
        assert any("ad." in p for p in result.matched_patterns)

    def test_regex_match(self):
        result = self.scorer.score_domain("pixel.facebook.com")
        assert result.score > 0
        assert len(result.matched_patterns) > 0

    def test_no_match(self):
        result = self.scorer.score_domain("github.com")
        assert result.score == 0.0
        assert result.matched_patterns == []

    def test_highest_weight_wins(self):
        result = self.scorer.score_domain("ad.tracker.example.com")
        # "ad." has weight 0.8, "tracker." has 0.7 — score should be 0.8
        assert result.score == 0.8

    def test_batch_scoring(self):
        domains = ["ad.example.com", "github.com", "tracker.evil.com"]
        results = self.scorer.score_domains(domains)
        assert len(results) == 3
        assert results[0].score > 0  # ad.example.com
        assert results[1].score == 0  # github.com
        assert results[2].score > 0  # tracker.evil.com

    def test_case_insensitive_substring(self):
        result = self.scorer.score_domain("AD.EXAMPLE.COM")
        assert result.score > 0

    def test_invalid_regex_rejected(self):
        """Scorer should skip patterns that fail to compile."""
        scorer = Scorer()
        scorer.load_patterns([
            {"pattern": "[invalid", "is_regex": True, "weight": 0.5, "category": "ads"},
        ])
        result = scorer.score_domain("anything")
        assert result.score == 0.0
