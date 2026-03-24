"""Heuristic pattern-matching engine for scoring domains."""

from __future__ import annotations

import concurrent.futures
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Thread pool for regex timeout protection (ReDoS guard)
_regex_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
_REGEX_TIMEOUT_S = 0.1  # 100ms per domain


@dataclass
class ScoredResult:
    """Result of scoring a single domain."""
    domain: str
    score: float = 0.0
    matched_patterns: list[str] = field(default_factory=list)


class Scorer:
    """Scores domains against configurable heuristic patterns."""

    def __init__(self) -> None:
        self._substring_patterns: list[dict] = []
        self._regex_patterns: list[dict] = []

    def load_patterns(self, patterns: list[dict]) -> None:
        """Load patterns from a list of dicts (from DB or test fixtures).

        Each dict: {pattern: str, is_regex: bool, weight: float, category: str}
        """
        self._substring_patterns = []
        self._regex_patterns = []

        for p in patterns:
            if p.get("is_regex"):
                try:
                    compiled = re.compile(p["pattern"], re.IGNORECASE)
                    self._regex_patterns.append({**p, "_compiled": compiled})
                except re.error:
                    logger.warning("Skipping invalid regex pattern: %s", p["pattern"])
            else:
                self._substring_patterns.append(p)

    def load_patterns_from_db(self, db) -> None:
        """Load enabled patterns from the database."""
        from app.models.ad_discovery import AdDiscoveryPattern

        rows = db.query(AdDiscoveryPattern).filter(
            AdDiscoveryPattern.enabled == True  # noqa: E712
        ).all()
        self.load_patterns([
            {
                "pattern": r.pattern,
                "is_regex": r.is_regex,
                "weight": r.weight,
                "category": r.category,
            }
            for r in rows
        ])

    def score_domain(self, domain: str) -> ScoredResult:
        """Score a single domain against all loaded patterns."""
        domain_lower = domain.lower()
        highest_weight = 0.0
        matched: list[str] = []

        for p in self._substring_patterns:
            if p["pattern"].lower() in domain_lower:
                matched.append(p["pattern"])
                if p["weight"] > highest_weight:
                    highest_weight = p["weight"]

        for p in self._regex_patterns:
            try:
                future = _regex_executor.submit(p["_compiled"].search, domain)
                match = future.result(timeout=_REGEX_TIMEOUT_S)
                if match:
                    matched.append(p["pattern"])
                    if p["weight"] > highest_weight:
                        highest_weight = p["weight"]
            except (concurrent.futures.TimeoutError, Exception):
                continue  # Skip patterns that timeout (ReDoS) or error

        return ScoredResult(domain=domain, score=highest_weight, matched_patterns=matched)

    def score_domains(self, domains: list[str]) -> list[ScoredResult]:
        """Score a batch of domains."""
        return [self.score_domain(d) for d in domains]
