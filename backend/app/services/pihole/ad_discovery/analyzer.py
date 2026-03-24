"""Analyzer orchestrator — combines scorer and community matcher to find ad domains."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.services.pihole.ad_discovery.scorer import Scorer, ScoredResult
from app.services.pihole.ad_discovery.community_matcher import CommunityMatcher, MatchResult

logger = logging.getLogger(__name__)


class Analyzer:
    """Orchestrates domain analysis using scorer + community matcher.

    Combines heuristic scoring and community list matching to identify
    ad-serving or tracker domains from DNS query history.
    """

    def __init__(self, db: Session, scorer: Scorer, matcher: CommunityMatcher) -> None:
        self._db = db
        self._scorer = scorer
        self._matcher = matcher

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_config(self):
        """Return the singleton AdDiscoveryConfig (id=1), or None if missing."""
        from app.models.ad_discovery import AdDiscoveryConfig

        return self._db.query(AdDiscoveryConfig).filter(AdDiscoveryConfig.id == 1).first()

    def _period_to_timedelta(self, period: str) -> timedelta:
        """Convert a period string to a timedelta."""
        mapping: dict[str, timedelta] = {
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
        }
        return mapping.get(period, timedelta(hours=24))

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    def analyze_queries(
        self,
        period: str = "24h",
        min_score: Optional[float] = None,
    ) -> dict:
        """Analyze DNS queries for ad-serving domains.

        Fetches FORWARDED/CACHED domains from the given period, scores them
        with the heuristic scorer and community matcher, and upserts suspects
        into the database.

        Args:
            period: Time window to look back ("24h", "7d", "30d").
            min_score: Minimum combined score to consider a suspect.
                       Defaults to config.min_score (0.15).

        Returns:
            Dict with keys:
              - new_suspects: int — domains newly added
              - updated_suspects: int — existing suspects updated
              - total_domains_analyzed: int — domains evaluated (excl. blocked)
        """
        from app.models.dns_queries import DnsQuery
        from app.models.ad_discovery import AdDiscoverySuspect, AdDiscoveryReferenceList

        config = self._get_config()
        if min_score is None:
            min_score = config.min_score if config else 0.15

        heuristic_weight = config.heuristic_weight if config else 0.4
        community_weight = config.community_weight if config else 0.6
        re_eval_threshold = config.re_evaluation_threshold if config else 0.3

        # 1. Fetch unique domains with query stats within the period
        cutoff = datetime.now(timezone.utc) - self._period_to_timedelta(period)
        query_results = (
            self._db.query(
                DnsQuery.domain,
                sa_func.count(DnsQuery.id).label("query_count"),
                sa_func.min(DnsQuery.timestamp).label("first_seen"),
                sa_func.max(DnsQuery.timestamp).label("last_seen"),
            )
            .filter(
                DnsQuery.status.in_(["FORWARDED", "CACHED"]),
                DnsQuery.timestamp >= cutoff,
            )
            .group_by(DnsQuery.domain)
            .all()
        )

        if not query_results:
            return {"new_suspects": 0, "updated_suspects": 0, "total_domains_analyzed": 0}

        domains = [r.domain for r in query_results]
        domain_data = {
            r.domain: {
                "count": r.query_count,
                "first": r.first_seen,
                "last": r.last_seen,
            }
            for r in query_results
        }

        # 2. Exclude already-blocked domains from analysis
        blocked_domains: set[str] = set(
            row.domain
            for row in self._db.query(AdDiscoverySuspect.domain).filter(
                AdDiscoverySuspect.status == "blocked"
            ).all()
        )
        domains_to_analyze = [d for d in domains if d not in blocked_domains]

        if not domains_to_analyze:
            return {"new_suspects": 0, "updated_suspects": 0, "total_domains_analyzed": 0}

        # 3. Score and match
        scored = self._scorer.score_domains(domains_to_analyze)
        scored_map: dict[str, ScoredResult] = {s.domain: s for s in scored}

        matched = self._matcher.match_domains(domains_to_analyze)
        matched_map: dict[str, MatchResult] = {m.domain: m for m in matched}

        # 4. Compute community score normalization factor
        active_lists = self._db.query(AdDiscoveryReferenceList).filter(
            AdDiscoveryReferenceList.enabled == True  # noqa: E712
        ).count()
        norm_factor = max(3.0, active_lists * 0.5)

        new_count = 0
        updated_count = 0
        now = datetime.now(timezone.utc)

        for domain in domains_to_analyze:
            score_result = scored_map.get(domain, ScoredResult(domain=domain))
            match_result = matched_map.get(domain, MatchResult(domain=domain))

            heuristic_score = score_result.score
            community_score = (
                min(1.0, match_result.hits / norm_factor)
                if match_result.hits > 0
                else 0.0
            )
            combined_score = (heuristic_weight * heuristic_score) + (community_weight * community_score)

            if combined_score < min_score:
                continue

            # Determine source label
            has_heuristic = heuristic_score > 0
            has_community = match_result.hits > 0
            if has_heuristic and has_community:
                source = "both"
            elif has_heuristic:
                source = "heuristic"
            elif has_community:
                source = "community"
            else:
                # combined_score would be 0 here; skip (shouldn't reach this normally)
                continue

            data = domain_data[domain]

            # Upsert suspect
            existing = self._db.query(AdDiscoverySuspect).filter(
                AdDiscoverySuspect.domain == domain
            ).first()

            if existing:
                if existing.status == "dismissed":
                    # Re-open only if score significantly increased
                    prev = existing.previous_score or 0.0
                    if combined_score <= prev + re_eval_threshold:
                        continue
                    existing.status = "new"
                    existing.resolved_at = None

                existing.query_count = data["count"]
                existing.last_seen_at = data["last"]
                existing.heuristic_score = heuristic_score
                existing.matched_patterns = score_result.matched_patterns
                existing.community_hits = match_result.hits
                existing.community_lists = match_result.matched_lists
                existing.source = source
                updated_count += 1
            else:
                suspect = AdDiscoverySuspect(
                    domain=domain,
                    first_seen_at=data["first"],
                    last_seen_at=data["last"],
                    query_count=data["count"],
                    heuristic_score=heuristic_score,
                    matched_patterns=score_result.matched_patterns,
                    community_hits=match_result.hits,
                    community_lists=match_result.matched_lists,
                    source=source,
                    status="new",
                )
                self._db.add(suspect)
                new_count += 1

        # Update config analysis timestamp
        if config:
            config.last_analysis_at = now

        self._db.commit()

        return {
            "new_suspects": new_count,
            "updated_suspects": updated_count,
            "total_domains_analyzed": len(domains_to_analyze),
        }

    # ------------------------------------------------------------------
    # Manual suspect management
    # ------------------------------------------------------------------

    def add_manual_suspect(self, domain: str) -> "AdDiscoverySuspect":
        """Add a domain as a manual suspect.

        If the domain already exists as a suspect (any status), the existing
        record is returned unchanged.

        Args:
            domain: The domain to flag (will be lowercased).

        Returns:
            The new or existing AdDiscoverySuspect record.
        """
        from app.models.ad_discovery import AdDiscoverySuspect

        normalised = domain.lower()
        existing = self._db.query(AdDiscoverySuspect).filter(
            AdDiscoverySuspect.domain == normalised
        ).first()

        if existing:
            return existing

        now = datetime.now(timezone.utc)
        suspect = AdDiscoverySuspect(
            domain=normalised,
            first_seen_at=now,
            last_seen_at=now,
            query_count=0,
            heuristic_score=0.0,
            matched_patterns=[],
            community_hits=0,
            community_lists=[],
            source="manual",
            status="new",
        )
        self._db.add(suspect)
        self._db.commit()
        self._db.refresh(suspect)
        return suspect

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------

    def update_suspect_status(
        self, domain: str, status: str
    ) -> Optional["AdDiscoverySuspect"]:
        """Update a suspect's status, recording resolved_at and previous_score.

        The previous_score is computed from the stored heuristic and community
        data so re-evaluation thresholds can be applied on future analyses.

        Args:
            domain: Domain to update (will be lowercased).
            status: New status string (e.g. "confirmed", "dismissed", "blocked").

        Returns:
            Updated AdDiscoverySuspect, or None if not found.
        """
        from app.models.ad_discovery import AdDiscoverySuspect

        normalised = domain.lower()
        suspect = self._db.query(AdDiscoverySuspect).filter(
            AdDiscoverySuspect.domain == normalised
        ).first()

        if not suspect:
            return None

        config = self._get_config()
        h_w = config.heuristic_weight if config else 0.4
        c_w = config.community_weight if config else 0.6

        # Compute current combined score from stored values
        # Use norm_factor=3 as minimum (no active list count available without a query)
        norm_factor = max(3.0, 1.0)
        community_score = (
            min(1.0, suspect.community_hits / norm_factor)
            if suspect.community_hits > 0
            else 0.0
        )
        combined = (h_w * suspect.heuristic_score) + (c_w * community_score)

        suspect.status = status
        suspect.resolved_at = datetime.now(timezone.utc)
        suspect.previous_score = combined

        self._db.commit()
        self._db.refresh(suspect)
        return suspect

    # ------------------------------------------------------------------
    # Blocking
    # ------------------------------------------------------------------

    async def block_suspect(
        self,
        domain: str,
        target: str,
        list_id: Optional[int],
        pihole_backend,
        custom_lists_service=None,
    ) -> None:
        """Block a suspect domain via Pi-hole deny list or a custom blocklist.

        After blocking, the suspect's status is updated to "blocked".

        Args:
            domain: Domain to block.
            target: Either "deny_list" (add to Pi-hole deny list) or
                    "custom_list" (add to a BaluHost custom blocklist).
            list_id: Required when target="custom_list"; the custom list ID.
            pihole_backend: Pi-hole backend protocol instance.
            custom_lists_service: CustomListsService instance (required for
                                   target="custom_list").
        """
        from app.models.ad_discovery import AdDiscoverySuspect

        if target == "deny_list":
            await pihole_backend.add_domain(
                "deny", "exact", domain, comment="Blocked by Ad Discovery"
            )
        elif target == "custom_list" and list_id is not None and custom_lists_service is not None:
            custom_lists_service.add_domains(
                self._db, list_id, [domain], comment="Ad Discovery"
            )

        # Mark suspect as blocked
        suspect = self._db.query(AdDiscoverySuspect).filter(
            AdDiscoverySuspect.domain == domain.lower()
        ).first()
        if suspect:
            suspect.status = "blocked"
            suspect.resolved_at = datetime.now(timezone.utc)
            self._db.commit()
