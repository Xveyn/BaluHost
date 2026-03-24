"""Tests for the Ad Discovery analyzer (orchestrator)."""
import os
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("NAS_MODE", "dev")
os.environ.setdefault("NAS_QUOTA_BYTES", str(10 * 1024 * 1024 * 1024))

from app.models.base import Base
from app.models.dns_queries import DnsQuery
from app.models.ad_discovery import (
    AdDiscoverySuspect,
    AdDiscoveryConfig,
    AdDiscoveryCustomList,
    AdDiscoveryCustomListDomain,
    AdDiscoveryPattern,
)
from app.services.pihole.ad_discovery.scorer import ScoredResult
from app.services.pihole.ad_discovery.community_matcher import MatchResult
from app.services.pihole.ad_discovery.analyzer import Analyzer


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    # Seed config singleton
    session.add(AdDiscoveryConfig(id=1))
    session.commit()
    yield session
    session.close()


@pytest.fixture
def mock_scorer():
    scorer = MagicMock()
    scorer.score_domains.return_value = []
    scorer.load_patterns_from_db = MagicMock()
    return scorer


@pytest.fixture
def mock_matcher():
    matcher = MagicMock()
    matcher.match_domains.return_value = []
    return matcher


@pytest.fixture
def analyzer(db_session, mock_scorer, mock_matcher):
    return Analyzer(db=db_session, scorer=mock_scorer, matcher=mock_matcher)


def _make_dns_query(domain: str, status: str = "FORWARDED", offset_seconds: int = 0) -> DnsQuery:
    """Helper to create a DnsQuery with a recent timestamp."""
    ts = datetime.now(timezone.utc) - timedelta(seconds=offset_seconds)
    return DnsQuery(
        timestamp=ts,
        domain=domain,
        client="192.168.1.100",
        query_type="A",
        status=status,
        reply_type="IP",
        response_time_ms=1.0,
    )


class TestAnalyzeQueries:
    def test_analyze_finds_new_suspects(self, db_session, mock_scorer, mock_matcher, analyzer):
        """FORWARDED DNS query for a high-score domain creates a new suspect."""
        db_session.add(_make_dns_query("ads.evil.com", status="FORWARDED"))
        db_session.commit()

        mock_scorer.score_domains.return_value = [
            ScoredResult(domain="ads.evil.com", score=0.8, matched_patterns=["ad."]),
        ]
        mock_matcher.match_domains.return_value = [
            MatchResult(domain="ads.evil.com", hits=0, matched_lists=[]),
        ]

        result = analyzer.analyze_queries()

        assert result["new_suspects"] == 1
        assert result["updated_suspects"] == 0

        suspect = db_session.query(AdDiscoverySuspect).filter_by(domain="ads.evil.com").first()
        assert suspect is not None
        assert suspect.heuristic_score == 0.8
        assert suspect.source == "heuristic"
        assert suspect.status == "new"

    def test_analyze_excludes_blocked_suspects(self, db_session, mock_scorer, mock_matcher, analyzer):
        """Domains with status='blocked' are not re-analyzed or updated."""
        db_session.add(_make_dns_query("blocked.ads.com", status="FORWARDED"))
        db_session.add(AdDiscoverySuspect(
            domain="blocked.ads.com",
            first_seen_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            query_count=5,
            heuristic_score=0.9,
            matched_patterns=[],
            community_hits=0,
            community_lists=[],
            source="heuristic",
            status="blocked",
        ))
        db_session.commit()

        mock_scorer.score_domains.return_value = [
            ScoredResult(domain="blocked.ads.com", score=0.9, matched_patterns=["ad."]),
        ]
        mock_matcher.match_domains.return_value = [
            MatchResult(domain="blocked.ads.com", hits=0, matched_lists=[]),
        ]

        result = analyzer.analyze_queries()

        # Domain is excluded before scoring, so score_domains is called with empty list
        # OR score_domains is called but the result is skipped; either way no update
        assert result["new_suspects"] == 0
        assert result["updated_suspects"] == 0

        suspect = db_session.query(AdDiscoverySuspect).filter_by(domain="blocked.ads.com").first()
        assert suspect.query_count == 5  # Unchanged
        assert suspect.status == "blocked"

    def test_analyze_updates_existing_suspect(self, db_session, mock_scorer, mock_matcher, analyzer):
        """Re-analyzing a domain with status='new' updates query_count and last_seen_at."""
        old_time = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.add(AdDiscoverySuspect(
            domain="tracker.example.com",
            first_seen_at=old_time,
            last_seen_at=old_time,
            query_count=3,
            heuristic_score=0.7,
            matched_patterns=["tracker."],
            community_hits=0,
            community_lists=[],
            source="heuristic",
            status="new",
        ))
        db_session.add(_make_dns_query("tracker.example.com", status="FORWARDED"))
        db_session.add(_make_dns_query("tracker.example.com", status="CACHED"))
        db_session.commit()

        mock_scorer.score_domains.return_value = [
            ScoredResult(domain="tracker.example.com", score=0.7, matched_patterns=["tracker."]),
        ]
        mock_matcher.match_domains.return_value = [
            MatchResult(domain="tracker.example.com", hits=0, matched_lists=[]),
        ]

        result = analyzer.analyze_queries()

        assert result["updated_suspects"] == 1
        assert result["new_suspects"] == 0

        suspect = db_session.query(AdDiscoverySuspect).filter_by(domain="tracker.example.com").first()
        assert suspect.query_count == 2  # 2 DNS query rows added
        # SQLite returns naive datetimes from aggregate functions; strip tzinfo for comparison
        last_seen = suspect.last_seen_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        assert last_seen > old_time
        assert suspect.status == "new"

    def test_analyze_re_evaluates_dismissed(self, db_session, mock_scorer, mock_matcher, analyzer):
        """A dismissed suspect reopens if combined_score > previous_score + re_evaluation_threshold."""
        # previous_score=0.2, threshold=0.3 → needs combined_score > 0.5 to reopen
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        db_session.add(AdDiscoverySuspect(
            domain="resurgent.ads.com",
            first_seen_at=old_time,
            last_seen_at=old_time,
            query_count=1,
            heuristic_score=0.2,
            matched_patterns=[],
            community_hits=0,
            community_lists=[],
            source="heuristic",
            status="dismissed",
            previous_score=0.2,
        ))
        db_session.add(_make_dns_query("resurgent.ads.com", status="FORWARDED"))
        db_session.commit()

        # heuristic_score=0.8, community_hits=0 → combined = 0.4*0.8 + 0.6*0 = 0.32
        # Wait, need combined > 0.2 + 0.3 = 0.5
        # Use heuristic=0.8, community=2 hits (norm=3) → community_score=0.667
        # combined = 0.4*0.8 + 0.6*0.667 = 0.32 + 0.4 = 0.72 > 0.5 ✓
        mock_scorer.score_domains.return_value = [
            ScoredResult(domain="resurgent.ads.com", score=0.8, matched_patterns=["ad."]),
        ]
        mock_matcher.match_domains.return_value = [
            MatchResult(domain="resurgent.ads.com", hits=2, matched_lists=["List A", "List B"]),
        ]

        result = analyzer.analyze_queries()

        assert result["updated_suspects"] == 1

        suspect = db_session.query(AdDiscoverySuspect).filter_by(domain="resurgent.ads.com").first()
        assert suspect.status == "new"
        assert suspect.resolved_at is None

    def test_analyze_skips_dismissed_below_threshold(self, db_session, mock_scorer, mock_matcher, analyzer):
        """Dismissed suspect with previous_score=0.4 is NOT reopened if combined_score <= 0.7."""
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        db_session.add(AdDiscoverySuspect(
            domain="dismissed.ads.com",
            first_seen_at=old_time,
            last_seen_at=old_time,
            query_count=1,
            heuristic_score=0.4,
            matched_patterns=[],
            community_hits=0,
            community_lists=[],
            source="heuristic",
            status="dismissed",
            previous_score=0.4,
        ))
        db_session.add(_make_dns_query("dismissed.ads.com", status="FORWARDED"))
        db_session.commit()

        # combined = 0.4*0.5 + 0.6*0 = 0.2 → does NOT exceed 0.4 + 0.3 = 0.7
        mock_scorer.score_domains.return_value = [
            ScoredResult(domain="dismissed.ads.com", score=0.5, matched_patterns=["ad."]),
        ]
        mock_matcher.match_domains.return_value = [
            MatchResult(domain="dismissed.ads.com", hits=0, matched_lists=[]),
        ]

        result = analyzer.analyze_queries()

        # Score is below threshold, suspect should be skipped entirely
        assert result["updated_suspects"] == 0
        assert result["new_suspects"] == 0

        suspect = db_session.query(AdDiscoverySuspect).filter_by(domain="dismissed.ads.com").first()
        assert suspect.status == "dismissed"
        assert suspect.query_count == 1  # Unchanged

    def test_combined_score_formula(self, db_session, mock_scorer, mock_matcher, analyzer):
        """Verify the combined score formula: heuristic=0.8, community=2 hits, 4 active lists."""
        from app.models.ad_discovery import AdDiscoveryReferenceList

        # Add 4 enabled reference lists
        for i in range(4):
            db_session.add(AdDiscoveryReferenceList(
                name=f"List {i}",
                url=f"https://example.com/list{i}.txt",
                enabled=True,
                domain_count=100,
            ))
        db_session.commit()

        db_session.add(_make_dns_query("formula.test.com", status="FORWARDED"))
        db_session.commit()

        mock_scorer.score_domains.return_value = [
            ScoredResult(domain="formula.test.com", score=0.8, matched_patterns=["ad."]),
        ]
        mock_matcher.match_domains.return_value = [
            MatchResult(domain="formula.test.com", hits=2, matched_lists=["List A", "List B"]),
        ]

        result = analyzer.analyze_queries()

        # norm_factor = max(3, 4 * 0.5) = max(3, 2.0) = 3
        # community_score = min(1.0, 2 / 3) = 0.667
        # combined = 0.4 * 0.8 + 0.6 * 0.667 = 0.32 + 0.4 = 0.72
        # 0.72 >= min_score (0.15) → should be inserted
        assert result["new_suspects"] == 1

        suspect = db_session.query(AdDiscoverySuspect).filter_by(domain="formula.test.com").first()
        assert suspect is not None
        # Both heuristic and community contribute
        assert suspect.source == "both"
        assert suspect.heuristic_score == pytest.approx(0.8)
        assert suspect.community_hits == 2

    def test_min_score_filter(self, db_session, mock_scorer, mock_matcher, analyzer):
        """Domains with combined_score below min_score (0.15) are not inserted as suspects."""
        db_session.add(_make_dns_query("clean.example.com", status="FORWARDED"))
        db_session.commit()

        mock_scorer.score_domains.return_value = [
            ScoredResult(domain="clean.example.com", score=0.05, matched_patterns=["ad."]),
        ]
        mock_matcher.match_domains.return_value = [
            MatchResult(domain="clean.example.com", hits=0, matched_lists=[]),
        ]

        result = analyzer.analyze_queries()

        # combined = 0.4*0.05 + 0.6*0 = 0.02 < 0.15 → not inserted
        assert result["new_suspects"] == 0
        suspect = db_session.query(AdDiscoverySuspect).filter_by(domain="clean.example.com").first()
        assert suspect is None

    def test_no_dns_queries_returns_zeros(self, db_session, mock_scorer, mock_matcher, analyzer):
        """If no DNS queries exist in the period, return zeroed result dict."""
        result = analyzer.analyze_queries()

        assert result["new_suspects"] == 0
        assert result["updated_suspects"] == 0
        assert result["total_domains_analyzed"] == 0

    def test_source_community_only(self, db_session, mock_scorer, mock_matcher, analyzer):
        """Domain with no heuristic match but community hits gets source='community'."""
        db_session.add(_make_dns_query("community.tracker.com", status="FORWARDED"))
        db_session.commit()

        mock_scorer.score_domains.return_value = [
            ScoredResult(domain="community.tracker.com", score=0.0, matched_patterns=[]),
        ]
        mock_matcher.match_domains.return_value = [
            MatchResult(domain="community.tracker.com", hits=3, matched_lists=["List A", "List B", "List C"]),
        ]

        result = analyzer.analyze_queries()

        # community_score = min(1.0, 3/3) = 1.0
        # combined = 0.4*0 + 0.6*1.0 = 0.6 >= 0.15 → inserted
        assert result["new_suspects"] == 1
        suspect = db_session.query(AdDiscoverySuspect).filter_by(domain="community.tracker.com").first()
        assert suspect.source == "community"

    def test_analyze_updates_config_timestamp(self, db_session, mock_scorer, mock_matcher, analyzer):
        """After analysis, config.last_analysis_at is updated even if no suspects are found."""
        before = datetime.now(timezone.utc) - timedelta(seconds=1)

        # Add a DNS query so the analysis proceeds past the early-return guard
        db_session.add(_make_dns_query("timestamp-test.com", status="FORWARDED"))
        db_session.commit()

        mock_scorer.score_domains.return_value = [
            ScoredResult(domain="timestamp-test.com", score=0.0, matched_patterns=[]),
        ]
        mock_matcher.match_domains.return_value = [
            MatchResult(domain="timestamp-test.com", hits=0, matched_lists=[]),
        ]

        analyzer.analyze_queries()

        config = db_session.query(AdDiscoveryConfig).filter_by(id=1).first()
        assert config.last_analysis_at is not None
        # SQLite may return naive datetime; normalize for comparison
        last_at = config.last_analysis_at
        if last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=timezone.utc)
        assert last_at > before


class TestAddManualSuspect:
    def test_add_manual_suspect(self, db_session, analyzer):
        """Adding a manual suspect creates a new record with correct fields."""
        suspect = analyzer.add_manual_suspect("evil.com")

        assert suspect.domain == "evil.com"
        assert suspect.source == "manual"
        assert suspect.status == "new"
        assert suspect.heuristic_score == 0.0
        assert suspect.community_hits == 0
        assert suspect.matched_patterns == []
        assert suspect.community_lists == []
        assert suspect.query_count == 0
        assert suspect.id is not None

    def test_add_manual_suspect_lowercases(self, db_session, analyzer):
        """Domain is normalized to lowercase."""
        suspect = analyzer.add_manual_suspect("Evil.COM")
        assert suspect.domain == "evil.com"

    def test_add_manual_suspect_idempotent(self, db_session, analyzer):
        """Adding the same domain twice returns the existing record without duplicating."""
        first = analyzer.add_manual_suspect("duplicate.com")
        second = analyzer.add_manual_suspect("duplicate.com")

        assert first.id == second.id
        count = db_session.query(AdDiscoverySuspect).filter_by(domain="duplicate.com").count()
        assert count == 1


class TestUpdateSuspectStatus:
    def test_update_suspect_status(self, db_session, analyzer):
        """Updating status to 'confirmed' sets resolved_at and previous_score."""
        now = datetime.now(timezone.utc)
        db_session.add(AdDiscoverySuspect(
            domain="suspicious.com",
            first_seen_at=now,
            last_seen_at=now,
            query_count=10,
            heuristic_score=0.7,
            matched_patterns=["ad."],
            community_hits=0,
            community_lists=[],
            source="heuristic",
            status="new",
        ))
        db_session.commit()

        updated = analyzer.update_suspect_status("suspicious.com", "confirmed")

        assert updated is not None
        assert updated.status == "confirmed"
        assert updated.resolved_at is not None
        assert updated.previous_score is not None

    def test_update_nonexistent_domain_returns_none(self, db_session, analyzer):
        """Updating a domain that doesn't exist returns None."""
        result = analyzer.update_suspect_status("notexist.com", "confirmed")
        assert result is None

    def test_update_suspect_status_dismissed(self, db_session, analyzer):
        """Dismissing a suspect stores previous_score for re-evaluation."""
        now = datetime.now(timezone.utc)
        db_session.add(AdDiscoverySuspect(
            domain="maybe.com",
            first_seen_at=now,
            last_seen_at=now,
            query_count=2,
            heuristic_score=0.5,
            matched_patterns=[],
            community_hits=0,
            community_lists=[],
            source="heuristic",
            status="new",
        ))
        db_session.commit()

        updated = analyzer.update_suspect_status("maybe.com", "dismissed")

        assert updated.status == "dismissed"
        assert updated.previous_score is not None
        assert updated.resolved_at is not None


class TestBlockSuspect:
    def test_block_suspect_deny_list(self, db_session, analyzer):
        """Blocking via deny_list calls pihole_backend.add_domain and sets status='blocked'."""
        now = datetime.now(timezone.utc)
        db_session.add(AdDiscoverySuspect(
            domain="evil-ad.com",
            first_seen_at=now,
            last_seen_at=now,
            query_count=5,
            heuristic_score=0.9,
            matched_patterns=["ad."],
            community_hits=0,
            community_lists=[],
            source="heuristic",
            status="new",
        ))
        db_session.commit()

        pihole_backend = MagicMock()
        pihole_backend.add_domain = AsyncMock(return_value={"success": True})

        import asyncio
        asyncio.run(
            analyzer.block_suspect(
                domain="evil-ad.com",
                target="deny_list",
                list_id=None,
                pihole_backend=pihole_backend,
            )
        )

        pihole_backend.add_domain.assert_awaited_once_with(
            "deny", "exact", "evil-ad.com", comment="Blocked by Ad Discovery"
        )

        suspect = db_session.query(AdDiscoverySuspect).filter_by(domain="evil-ad.com").first()
        assert suspect.status == "blocked"
        assert suspect.resolved_at is not None

    def test_block_suspect_custom_list(self, db_session, analyzer):
        """Blocking via custom_list calls custom_lists_service.add_domains."""
        import uuid
        now = datetime.now(timezone.utc)
        db_session.add(AdDiscoverySuspect(
            domain="tracker.ad.com",
            first_seen_at=now,
            last_seen_at=now,
            query_count=3,
            heuristic_score=0.8,
            matched_patterns=["tracker."],
            community_hits=0,
            community_lists=[],
            source="heuristic",
            status="new",
        ))
        # Add a custom list to block into
        db_session.add(AdDiscoveryCustomList(
            id=42,
            name="My List",
            description="",
            domain_count=0,
            adlist_token=str(uuid.uuid4()),
        ))
        db_session.commit()

        pihole_backend = MagicMock()
        custom_lists_service = MagicMock()
        custom_lists_service.add_domains = MagicMock(return_value=1)

        import asyncio
        asyncio.run(
            analyzer.block_suspect(
                domain="tracker.ad.com",
                target="custom_list",
                list_id=42,
                pihole_backend=pihole_backend,
                custom_lists_service=custom_lists_service,
            )
        )

        custom_lists_service.add_domains.assert_called_once_with(
            db_session, 42, ["tracker.ad.com"], comment="Ad Discovery"
        )

        # pihole_backend.add_domain should NOT have been called
        pihole_backend.add_domain.assert_not_called()

        suspect = db_session.query(AdDiscoverySuspect).filter_by(domain="tracker.ad.com").first()
        assert suspect.status == "blocked"
