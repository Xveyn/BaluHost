# Ad Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Ad Discovery feature to the Pi-hole integration that identifies unblocked ad-serving domains via heuristic pattern-matching and community blocklist cross-referencing, with on-the-fly custom blocklist creation.

**Architecture:** New submodule `backend/app/services/pihole/ad_discovery/` with scorer, community matcher, custom lists, analyzer, and background task. New tab in frontend `PiholePage.tsx`. Follows existing DnsQueryCollector async pattern for background work. 6 new DB tables with Alembic migration.

**Tech Stack:** Python (FastAPI, SQLAlchemy 2.0, httpx), React + TypeScript + Tailwind CSS, PostgreSQL/SQLite

**Spec:** `docs/superpowers/specs/2026-03-24-ad-discovery-design.md`

---

## File Map

### Backend — New Files

| File | Responsibility |
|------|----------------|
| `backend/app/models/ad_discovery.py` | SQLAlchemy models for 6 tables (incl. config) |
| `backend/alembic/versions/033_add_ad_discovery_tables.py` | Migration + default seed data |
| `backend/app/schemas/ad_discovery.py` | Pydantic request/response schemas |
| `backend/app/services/pihole/ad_discovery/__init__.py` | Module init |
| `backend/app/services/pihole/ad_discovery/scorer.py` | Heuristic pattern-matching engine |
| `backend/app/services/pihole/ad_discovery/community_matcher.py` | Reference list download, cache, matching |
| `backend/app/services/pihole/ad_discovery/custom_lists.py` | Custom list CRUD + adlist file generation |
| `backend/app/services/pihole/ad_discovery/analyzer.py` | Orchestrator combining scorer + matcher |
| `backend/app/services/pihole/ad_discovery/background.py` | Async background task (like DnsQueryCollector) |
| `backend/app/api/routes/ad_discovery.py` | API endpoints under `/api/pihole/ad-discovery/` |
| `backend/tests/test_ad_discovery_scorer.py` | Scorer unit tests |
| `backend/tests/test_ad_discovery_community.py` | Community matcher unit tests |
| `backend/tests/test_ad_discovery_custom_lists.py` | Custom lists unit tests |
| `backend/tests/test_ad_discovery_analyzer.py` | Analyzer unit tests |
| `backend/tests/test_ad_discovery_api.py` | API route integration tests |

### Backend — Modified Files (also modify `backend/app/models/__init__.py` to register new models)

| File | Change |
|------|--------|
| `backend/app/core/lifespan.py:384-393` | Start/stop ad discovery background task alongside DnsQueryCollector |
| `backend/app/api/routes/pihole.py:58` | Include ad_discovery sub-router |
| `backend/app/core/rate_limiter.py:67-127` | Add `ad_discovery` rate limit entry to RATE_LIMITS |

### Frontend — New Files

| File | Responsibility |
|------|----------------|
| `client/src/api/adDiscovery.ts` | API client for ad discovery endpoints |
| `client/src/components/pihole/AdDiscoveryTab.tsx` | Main Ad Discovery tab (header + suspects table) |
| `client/src/components/pihole/ad-discovery/SuspectsTable.tsx` | Sortable/filterable suspects table with bulk actions |
| `client/src/components/pihole/ad-discovery/PatternsPanel.tsx` | Patterns configuration sub-tab |
| `client/src/components/pihole/ad-discovery/ReferenceListsPanel.tsx` | Reference lists sub-tab |
| `client/src/components/pihole/ad-discovery/CustomListsPanel.tsx` | Custom lists sub-tab |
| `client/src/components/pihole/ad-discovery/BlockDialog.tsx` | Block action dialog (deny-list vs custom list) |

### Frontend — Modified Files

| File | Change |
|------|--------|
| `client/src/pages/PiholePage.tsx:33-44` | Add `'ad-discovery'` to Tab type and TABS array, render `AdDiscoveryTab` |

---

## Task 1: Database Models

**Files:**
- Create: `backend/app/models/ad_discovery.py`

- [ ] **Step 1: Create the models file**

```python
"""SQLAlchemy models for Ad Discovery feature."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AdDiscoveryPattern(Base):
    """Heuristic pattern for scoring domains."""

    __tablename__ = "ad_discovery_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(String(253), nullable=False)
    is_regex: Mapped[bool] = mapped_column(Boolean, default=False)
    weight: Mapped[float] = mapped_column(Float, default=0.5)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<AdDiscoveryPattern(pattern={self.pattern!r}, category={self.category})>"


class AdDiscoveryReferenceList(Base):
    """Community blocklist used for cross-referencing."""

    __tablename__ = "ad_discovery_reference_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    domain_count: Mapped[int] = mapped_column(Integer, default=0)
    last_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fetch_interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<AdDiscoveryReferenceList(name={self.name!r}, enabled={self.enabled})>"


class AdDiscoverySuspect(Base):
    """Domain flagged as potentially ad-related."""

    __tablename__ = "ad_discovery_suspects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(253), unique=True, nullable=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    query_count: Mapped[int] = mapped_column(Integer, default=0)
    heuristic_score: Mapped[float] = mapped_column(Float, default=0.0)
    matched_patterns: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    community_hits: Mapped[int] = mapped_column(Integer, default=0)
    community_lists: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="heuristic")
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    previous_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    __table_args__ = (
        Index("ix_ad_suspects_status_score", "status", "heuristic_score"),
    )

    def __repr__(self) -> str:
        return f"<AdDiscoverySuspect(domain={self.domain!r}, status={self.status})>"


class AdDiscoveryCustomList(Base):
    """Named custom blocklist."""

    __tablename__ = "ad_discovery_custom_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    domain_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deployed: Mapped[bool] = mapped_column(Boolean, default=False)
    adlist_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    domains = relationship(
        "AdDiscoveryCustomListDomain", back_populates="custom_list", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<AdDiscoveryCustomList(name={self.name!r}, deployed={self.deployed})>"


class AdDiscoveryCustomListDomain(Base):
    """Domain belonging to a custom list."""

    __tablename__ = "ad_discovery_custom_list_domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    list_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ad_discovery_custom_lists.id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    comment: Mapped[str] = mapped_column(String(500), default="")

    custom_list = relationship("AdDiscoveryCustomList", back_populates="domains")

    __table_args__ = (
        UniqueConstraint("list_id", "domain", name="uq_custom_list_domain"),
    )

    def __repr__(self) -> str:
        return f"<AdDiscoveryCustomListDomain(list_id={self.list_id}, domain={self.domain!r})>"


class AdDiscoveryConfig(Base):
    """Singleton (id=1) storing ad discovery configuration."""

    __tablename__ = "ad_discovery_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    background_interval_hours: Mapped[int] = mapped_column(Integer, default=6)
    heuristic_weight: Mapped[float] = mapped_column(Float, default=0.4)
    community_weight: Mapped[float] = mapped_column(Float, default=0.6)
    min_score: Mapped[float] = mapped_column(Float, default=0.15)
    re_evaluation_threshold: Mapped[float] = mapped_column(Float, default=0.3)
    background_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_analysis_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_analysis_watermark: Mapped[float] = mapped_column(Float, default=0.0)

    def __repr__(self) -> str:
        return f"<AdDiscoveryConfig(interval={self.background_interval_hours}h, enabled={self.background_enabled})>"
```

- [ ] **Step 2: Register models in `backend/app/models/__init__.py`**

Add the following import after the `dns_queries` import (line 73):

```python
from app.models.ad_discovery import (
    AdDiscoveryPattern,
    AdDiscoveryReferenceList,
    AdDiscoverySuspect,
    AdDiscoveryCustomList,
    AdDiscoveryCustomListDomain,
    AdDiscoveryConfig,
)
```

And add all 6 names to the `__all__` list.

- [ ] **Step 3: Verify import works**

Run: `cd backend && python -c "from app.models.ad_discovery import AdDiscoveryPattern, AdDiscoverySuspect, AdDiscoveryConfig; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/ad_discovery.py backend/app/models/__init__.py
git commit -m "feat(ad-discovery): add SQLAlchemy models for 6 tables"
```

---

## Task 2: Alembic Migration + Default Seeds

**Files:**
- Create: `backend/alembic/versions/033_add_ad_discovery_tables.py`

- [ ] **Step 1: Create migration file**

Follow the pattern from `032_add_migration_jobs_table.py`. Create all 6 tables with indexes (including `ad_discovery_config` singleton). Seed default patterns, reference lists, and the config singleton row using `op.bulk_insert()`.

Default patterns to seed (~30 entries):
- Category `ads` (weight 0.7-0.9): `ad.`, `ads.`, `adservice`, `adserver`, `doubleclick`, `googlesyndication`, `googleadservices`, `moatads`, `adnxs`, `adsrvr`
- Category `tracking` (weight 0.5-0.8): `tracker.`, `tracking.`, `pixel.`, `beacon.`, `collect.`, `telemetry.`, `clickstream`
- Category `analytics` (weight 0.3-0.5): `analytics.`, `metrics.`, `stats.`, `measure.`, `segment.io`, `hotjar`, `mouseflow`
- Category `fingerprinting` (weight 0.6-0.8): `fingerprint`, `browser-update`, `device-api`

Default reference lists (all disabled): OISD Full, Hagezi Multi Pro, Steven Black Unified, EasyList Domains, AdGuard DNS Filter (URLs from spec).

- [ ] **Step 2: Run migration**

Run: `cd backend && alembic upgrade head`
Expected: Migration applies successfully

- [ ] **Step 3: Verify tables exist**

Run: `cd backend && python -c "from app.core.database import SessionLocal; from app.models.ad_discovery import AdDiscoveryPattern; db=SessionLocal(); print(db.query(AdDiscoveryPattern).count(), 'patterns seeded'); db.close()"`
Expected: `~30 patterns seeded`

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/033_add_ad_discovery_tables.py
git commit -m "feat(ad-discovery): add alembic migration with default seeds"
```

---

## Task 3: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/ad_discovery.py`

- [ ] **Step 1: Create schemas file**

Define all request/response schemas matching the API spec:

```python
"""Pydantic schemas for Ad Discovery feature."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


def _validate_domain(v: str) -> str:
    """Reject domains containing '..' sequences."""
    if ".." in v:
        raise ValueError("Domain must not contain '..' sequences")
    return v


# ── Patterns ────────────────────────────────────────────────────────

class PatternEntry(BaseModel):
    id: int
    pattern: str
    is_regex: bool
    weight: float
    category: str
    is_default: bool
    enabled: bool

    model_config = {"from_attributes": True}


class PatternCreateRequest(BaseModel):
    pattern: str = Field(..., min_length=1, max_length=253)
    is_regex: bool = False
    weight: float = Field(0.5, ge=0.1, le=1.0)
    category: str = Field(..., min_length=1, max_length=50,
                          pattern="^(ads|tracking|telemetry|analytics|fingerprinting|custom)$")


class PatternUpdateRequest(BaseModel):
    weight: Optional[float] = Field(None, ge=0.1, le=1.0)
    enabled: Optional[bool] = None
    category: Optional[str] = Field(None, pattern="^(ads|tracking|telemetry|analytics|fingerprinting|custom)$")


class PatternListResponse(BaseModel):
    patterns: list[PatternEntry] = []


# ── Reference Lists ─────────────────────────────────────────────────

class ReferenceListEntry(BaseModel):
    id: int
    name: str
    url: str
    is_default: bool
    enabled: bool
    domain_count: int
    last_fetched_at: Optional[datetime] = None
    fetch_interval_hours: int
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ReferenceListCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    url: str = Field(..., min_length=10, max_length=2000, pattern="^https://")
    fetch_interval_hours: int = Field(24, ge=1, le=168)


class ReferenceListUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    fetch_interval_hours: Optional[int] = Field(None, ge=1, le=168)


class ReferenceListResponse(BaseModel):
    lists: list[ReferenceListEntry] = []


# ── Suspects ────────────────────────────────────────────────────────

class SuspectEntry(BaseModel):
    id: int
    domain: str
    first_seen_at: datetime
    last_seen_at: datetime
    query_count: int
    heuristic_score: float
    matched_patterns: Optional[list] = None
    community_hits: int
    community_lists: Optional[list] = None
    source: str
    status: str
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SuspectListResponse(BaseModel):
    suspects: list[SuspectEntry] = []
    total: int = 0
    page: int = 1
    page_size: int = 50


class SuspectStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(confirmed|dismissed|blocked)$")


class SuspectManualAdd(BaseModel):
    domain: str = Field(..., min_length=1, max_length=253)
    _validate_domain = field_validator("domain")(_validate_domain)


class SuspectBlockRequest(BaseModel):
    domain: str = Field(..., min_length=1, max_length=253)
    _validate_domain = field_validator("domain")(_validate_domain)
    target: str = Field(..., pattern="^(deny_list|custom_list)$")
    list_id: Optional[int] = None


class SuspectBulkActionRequest(BaseModel):
    domains: list[str] = Field(..., min_length=1, max_length=100)

    @field_validator("domains")
    @classmethod
    def validate_domains(cls, v: list[str]) -> list[str]:
        for d in v:
            _validate_domain(d)
        return v
    action: str = Field(..., pattern="^(block|dismiss|confirm)$")
    target: Optional[str] = Field(None, pattern="^(deny_list|custom_list)$")
    list_id: Optional[int] = None


# ── Custom Lists ────────────────────────────────────────────────────

class CustomListEntry(BaseModel):
    id: int
    name: str
    description: str
    domain_count: int
    created_at: datetime
    updated_at: datetime
    deployed: bool
    adlist_url: Optional[str] = None

    model_config = {"from_attributes": True}


class CustomListCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=500)


class CustomListUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)


class CustomListResponse(BaseModel):
    lists: list[CustomListEntry] = []


class CustomListDomainEntry(BaseModel):
    id: int
    domain: str
    added_at: datetime
    comment: str = ""

    model_config = {"from_attributes": True}


class CustomListDomainsResponse(BaseModel):
    domains: list[CustomListDomainEntry] = []
    total: int = 0
    page: int = 1
    page_size: int = 100


class CustomListAddDomainsRequest(BaseModel):
    domains: list[str] = Field(..., min_length=1, max_length=100)
    comment: str = Field("", max_length=500)

    @field_validator("domains")
    @classmethod
    def validate_domains(cls, v: list[str]) -> list[str]:
        for d in v:
            _validate_domain(d)
        return v


# ── Analysis ────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    period: str = Field("24h", pattern="^(24h|7d|30d)$")
    min_score: float = Field(0.15, ge=0.0, le=1.0)


class AnalyzeResponse(BaseModel):
    new_suspects: int = 0
    updated_suspects: int = 0
    total_domains_analyzed: int = 0


# ── Status & Config ─────────────────────────────────────────────────

class AdDiscoveryStatusResponse(BaseModel):
    suspects_new: int = 0
    suspects_confirmed: int = 0
    suspects_dismissed: int = 0
    suspects_blocked: int = 0
    last_analysis_at: Optional[datetime] = None
    background_task_running: bool = False
    reference_lists_active: int = 0
    reference_lists_total: int = 0
    custom_lists_total: int = 0
    custom_lists_deployed: int = 0


class AdDiscoveryConfigResponse(BaseModel):
    background_interval_hours: int = 6
    heuristic_weight: float = 0.4
    community_weight: float = 0.6
    min_score: float = 0.15
    re_evaluation_threshold: float = 0.3
    background_enabled: bool = True


class AdDiscoveryConfigUpdate(BaseModel):
    background_interval_hours: Optional[int] = Field(None, ge=1, le=24)
    heuristic_weight: Optional[float] = Field(None, ge=0.0, le=1.0)
    community_weight: Optional[float] = Field(None, ge=0.0, le=1.0)
    min_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    re_evaluation_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    background_enabled: Optional[bool] = None
```

- [ ] **Step 2: Verify import works**

Run: `cd backend && python -c "from app.schemas.ad_discovery import SuspectEntry, AnalyzeRequest; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/ad_discovery.py
git commit -m "feat(ad-discovery): add Pydantic schemas"
```

---

## Task 4: Scorer (Heuristic Engine)

**Files:**
- Create: `backend/app/services/pihole/ad_discovery/__init__.py`
- Create: `backend/app/services/pihole/ad_discovery/scorer.py`
- Create: `backend/tests/test_ad_discovery_scorer.py`

- [ ] **Step 1: Create `__init__.py`**

Empty file to make the directory a package.

- [ ] **Step 2: Write scorer tests**

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_ad_discovery_scorer.py -v`
Expected: FAIL — module not found

- [ ] **Step 4: Implement scorer**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_ad_discovery_scorer.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/pihole/ad_discovery/__init__.py backend/app/services/pihole/ad_discovery/scorer.py backend/tests/test_ad_discovery_scorer.py
git commit -m "feat(ad-discovery): add heuristic scorer with tests"
```

---

## Task 5: Community Matcher

**Files:**
- Create: `backend/app/services/pihole/ad_discovery/community_matcher.py`
- Create: `backend/tests/test_ad_discovery_community.py`

- [ ] **Step 1: Write community matcher tests**

Test list parsing (hosts format, domain-per-line, comments), matching, SSRF validation, batch matching. Use mock data — no real HTTP downloads in tests.

Key test cases:
- Parse domain-per-line format
- Parse hosts format (`0.0.0.0 domain.com`)
- Ignore comment lines (`#`)
- Match domain against loaded sets
- Batch matching with multiple lists
- SSRF rejection (private IPs, non-https)
- Download size limit check

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_ad_discovery_community.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement community matcher**

Key implementation details:
- `CommunityMatcher` class with `_lists: dict[int, set[str]]` in-memory cache
- `_validate_url(url)`: check `https://` scheme, resolve hostname, reject RFC 1918 / loopback / link-local IPs
- `fetch_list(list_id, url)`: download via `httpx.AsyncClient` with 50MB limit + 60s timeout, parse into set, gzip-compress to disk cache at `backend/data/ad_discovery_cache/{list_id}.gz`
- `_parse_list_content(text) -> set[str]`: handle hosts format, domain-per-line, strip comments/blanks
- `load_from_cache(list_id)`: load gzip from disk into memory set
- `refresh_all(db)`: check `last_fetched_at` + `fetch_interval_hours`, refresh stale lists
- `match_domain(domain) -> MatchResult`: return list of matching reference list names
- `match_domains(domains) -> list[MatchResult]`: batch
- Module-level singleton `_matcher = CommunityMatcher()`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_ad_discovery_community.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/pihole/ad_discovery/community_matcher.py backend/tests/test_ad_discovery_community.py
git commit -m "feat(ad-discovery): add community matcher with SSRF protection and tests"
```

---

## Task 6: Custom Lists Service

**Files:**
- Create: `backend/app/services/pihole/ad_discovery/custom_lists.py`
- Create: `backend/tests/test_ad_discovery_custom_lists.py`

- [ ] **Step 1: Write custom lists tests**

Test CRUD operations, adlist file generation, export. Use test DB session.

Key test cases:
- Create list, verify in DB
- Add domains to list, verify domain_count updates
- Remove domain from list
- Generate adlist file content (header comment + domains)
- Export as bytes
- Delete list cascades domains
- Unique constraint on (list_id, domain)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_ad_discovery_custom_lists.py -v`
Expected: FAIL

- [ ] **Step 3: Implement custom lists service**

Key functions:
- `create_list(db, name, description) -> CustomListEntry`
- `delete_list(db, list_id)`: undeploy if deployed, then delete (cascade handles domains)
- `add_domains(db, list_id, domains, comment)`: bulk insert, update `domain_count`
- `remove_domain(db, list_id, domain)`: delete row, update `domain_count`
- `generate_adlist_file(db, list_id) -> Path`: write to `backend/data/ad_discovery_lists/{list_id}.txt`
- `export_list(db, list_id) -> bytes`: return file content
- `deploy_to_pihole(db, list_id, base_url)`: generate file, construct URL with token (UUID4), call `pihole_backend.add_adlist(url)`, update `deployed=True` and `adlist_url`
- `undeploy_from_pihole(db, list_id)`: call `pihole_backend.remove_adlist(url)`, set `deployed=False`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_ad_discovery_custom_lists.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/pihole/ad_discovery/custom_lists.py backend/tests/test_ad_discovery_custom_lists.py
git commit -m "feat(ad-discovery): add custom lists service with tests"
```

---

## Task 7: Analyzer (Orchestrator)

**Files:**
- Create: `backend/app/services/pihole/ad_discovery/analyzer.py`
- Create: `backend/tests/test_ad_discovery_analyzer.py`

- [ ] **Step 1: Write analyzer tests**

Test the orchestration logic. Mock scorer + community matcher, use test DB with seeded DnsQuery rows.

Key test cases:
- `analyze_queries` finds new suspects from FORWARDED/CACHED queries
- Blocked suspects are excluded
- Dismissed suspects are re-evaluated when score exceeds threshold
- Combined score formula applies correct weights
- Manual suspect add works
- Status update sets `resolved_at` and `previous_score`
- `block_suspect` with `target="deny_list"` calls pihole backend
- `block_suspect` with `target="custom_list"` adds to list

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_ad_discovery_analyzer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement analyzer**

Key implementation:
- `Analyzer` class taking `db`, `scorer`, `matcher` as constructor args
- `analyze_queries(period, min_score, heuristic_weight, community_weight)`:
  1. Query `DnsQuery` for FORWARDED/CACHED in period, aggregate unique domains + counts
  2. Filter blocked suspects
  3. For dismissed suspects: re-include if `combined_score > previous_score + re_evaluation_threshold`
  4. Run `scorer.score_domains()` + `matcher.match_domains()`
  5. Compute `combined_score = h_w * heuristic + c_w * community`
  6. Determine source: `heuristic`, `community`, `both`, based on which scores > 0
  7. Upsert into `ad_discovery_suspects`
  8. Return counts
- `add_manual_suspect(domain)`: insert with source=`manual`, status=`new`
- `update_suspect_status(domain, status)`: set status, `resolved_at=now()`, compute combined score dynamically as `(config.heuristic_weight * suspect.heuristic_score) + (config.community_weight * community_score_from_hits)` and save into `previous_score`
- `block_suspect(domain, target, list_id, pihole_backend)`: dispatch to deny-list or custom-list

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_ad_discovery_analyzer.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/pihole/ad_discovery/analyzer.py backend/tests/test_ad_discovery_analyzer.py
git commit -m "feat(ad-discovery): add analyzer orchestrator with tests"
```

---

## Task 8: Background Task + Lifespan Integration

**Files:**
- Create: `backend/app/services/pihole/ad_discovery/background.py`
- Modify: `backend/app/core/lifespan.py`

- [ ] **Step 1: Implement background task**

Follow the `DnsQueryCollector` pattern exactly:
- `AdDiscoveryBackgroundTask` class with `_task`, `_running`, `_db_factory`
- `start(db_session_factory)`: `asyncio.create_task(self._poll_loop())`
- `stop()`: cancel + await
- `_poll_loop()`: warmup sleep, loop with watermark-based analysis
- Module-level singleton `_background_task`
- `get_ad_discovery_task() -> AdDiscoveryBackgroundTask`

- [ ] **Step 2: Add to lifespan startup**

In `backend/app/core/lifespan.py`, **inside the `if IS_PRIMARY_WORKER:` block** (line 384), immediately after the DNS query collector try/except block (lines 388-393), add:

```python
        try:
            from app.services.pihole.ad_discovery.background import get_ad_discovery_task
            get_ad_discovery_task().start(SessionLocal)
            logger.info("Ad Discovery background task started")
        except Exception as e:
            logger.warning("Ad Discovery background task could not start: %s", e)
```

- [ ] **Step 3: Add to lifespan shutdown**

In `_shutdown()`, after DNS query collector stop (~line 532), add:

```python
    try:
        from app.services.pihole.ad_discovery.background import get_ad_discovery_task
        await get_ad_discovery_task().stop()
    except Exception:
        logger.debug("Ad Discovery background task shutdown skipped or failed")
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/pihole/ad_discovery/background.py backend/app/core/lifespan.py
git commit -m "feat(ad-discovery): add background task with lifespan integration"
```

---

## Task 9: API Routes

**Files:**
- Create: `backend/app/api/routes/ad_discovery.py`
- Modify: `backend/app/api/routes/pihole.py`
- Modify: `backend/app/core/rate_limiter.py`
- Create: `backend/tests/test_ad_discovery_api.py`

- [ ] **Step 1: Add rate limit entry**

In `backend/app/core/rate_limiter.py`, add to `RATE_LIMITS` dict:

```python
    # Ad Discovery operations
    "ad_discovery": "30/minute",
```

- [ ] **Step 2: Create API routes**

Create `backend/app/api/routes/ad_discovery.py` with all endpoints from the spec. Follow the pattern in `pihole.py`:
- `router = APIRouter(prefix="/ad-discovery", tags=["ad-discovery"])`
- All endpoints use `Depends(deps.get_current_admin)` except `GET /custom-lists/{id}/adlist.txt` (token-based)
- Rate limit with `@user_limiter.limit(get_limit("ad_discovery"))`
- Audit logging for state-changing operations

Key endpoints:
- `POST /analyze` — triggers manual analysis
- `GET /suspects` — paginated, filterable list
- `PATCH /suspects/{domain}` — status change
- `POST /suspects/manual` — add manual suspect
- `POST /suspects/block` — block domain
- `POST /suspects/bulk-action` — bulk operations
- `GET /patterns`, `POST /patterns`, `PATCH /patterns/{id}`, `DELETE /patterns/{id}`
- `GET /reference-lists`, `POST /reference-lists`, `PATCH /reference-lists/{id}`, `DELETE /reference-lists/{id}`, `POST /reference-lists/refresh`
- `GET /custom-lists`, `POST /custom-lists`, `PATCH /custom-lists/{id}`, `DELETE /custom-lists/{id}`
- `GET /custom-lists/{id}/domains`, `POST /custom-lists/{id}/domains`, `DELETE /custom-lists/{id}/domains/{domain:path}`
- `POST /custom-lists/{id}/deploy`, `POST /custom-lists/{id}/undeploy`
- `GET /custom-lists/{id}/export`, `GET /custom-lists/{id}/adlist.txt` (token-secured)
- `GET /status`, `GET /config`, `PATCH /config`

- [ ] **Step 3: Include sub-router in pihole router**

In `backend/app/api/routes/pihole.py`, after `router = APIRouter(...)` line 58, add:

```python
from app.api.routes.ad_discovery import router as ad_discovery_router
router.include_router(ad_discovery_router)
```

- [ ] **Step 4: Write API integration tests**

In `backend/tests/test_ad_discovery_api.py`, test:
- GET /status returns valid response
- GET/POST/PATCH/DELETE patterns CRUD
- POST /analyze runs without error
- GET /suspects returns paginated list
- Custom list create + add domains + export
- Unauthenticated access returns 401
- Adlist.txt with valid token returns content
- Adlist.txt without token returns 403

Use the same test client pattern as `test_pihole.py` (TestClient, dev mode).

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_ad_discovery_api.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/ad_discovery.py backend/app/api/routes/pihole.py backend/app/core/rate_limiter.py backend/tests/test_ad_discovery_api.py
git commit -m "feat(ad-discovery): add API routes with tests"
```

---

## Task 10: Frontend API Client

**Files:**
- Create: `client/src/api/adDiscovery.ts`

- [ ] **Step 1: Create API client with types**

Follow the pattern in `client/src/api/pihole.ts`:

```typescript
/**
 * API client for Ad Discovery feature.
 */
import { apiClient } from '../lib/api';

// ── Types ────────────────────────────────────────────────────────

export interface SuspectEntry {
  id: number;
  domain: string;
  first_seen_at: string;
  last_seen_at: string;
  query_count: number;
  heuristic_score: number;
  matched_patterns: string[] | null;
  community_hits: number;
  community_lists: string[] | null;
  source: string;
  status: string;
  resolved_at: string | null;
}

export interface PatternEntry {
  id: number;
  pattern: string;
  is_regex: boolean;
  weight: number;
  category: string;
  is_default: boolean;
  enabled: boolean;
}

export interface ReferenceListEntry {
  id: number;
  name: string;
  url: string;
  is_default: boolean;
  enabled: boolean;
  domain_count: number;
  last_fetched_at: string | null;
  fetch_interval_hours: number;
  last_error: string | null;
}

export interface CustomListEntry {
  id: number;
  name: string;
  description: string;
  domain_count: number;
  created_at: string;
  updated_at: string;
  deployed: boolean;
  adlist_url: string | null;
}

export interface CustomListDomainEntry {
  id: number;
  domain: string;
  added_at: string;
  comment: string;
}

export interface AdDiscoveryStatus {
  suspects_new: number;
  suspects_confirmed: number;
  suspects_dismissed: number;
  suspects_blocked: number;
  last_analysis_at: string | null;
  background_task_running: boolean;
  reference_lists_active: number;
  reference_lists_total: number;
  custom_lists_total: number;
  custom_lists_deployed: number;
}

export interface AdDiscoveryConfig {
  background_interval_hours: number;
  heuristic_weight: number;
  community_weight: number;
  min_score: number;
  re_evaluation_threshold: number;
  background_enabled: boolean;
}

// ── API Functions ────────────────────────────────────────────────

const BASE = '/api/pihole/ad-discovery';

// Status & Config
export async function getAdDiscoveryStatus(): Promise<AdDiscoveryStatus> {
  const { data } = await apiClient.get(`${BASE}/status`);
  return data;
}

export async function getAdDiscoveryConfig(): Promise<AdDiscoveryConfig> {
  const { data } = await apiClient.get(`${BASE}/config`);
  return data;
}

export async function updateAdDiscoveryConfig(update: Partial<AdDiscoveryConfig>): Promise<AdDiscoveryConfig> {
  const { data } = await apiClient.patch(`${BASE}/config`, update);
  return data;
}

// Analysis
export async function startAnalysis(period = '24h', minScore = 0.15) {
  const { data } = await apiClient.post(`${BASE}/analyze`, { period, min_score: minScore });
  return data;
}

// Suspects
export async function getSuspects(params: {
  status?: string; source?: string; sort_by?: string;
  page?: number; page_size?: number;
}) {
  const { data } = await apiClient.get(`${BASE}/suspects`, { params });
  return data as { suspects: SuspectEntry[]; total: number; page: number; page_size: number };
}

export async function updateSuspectStatus(domain: string, status: string) {
  const { data } = await apiClient.patch(`${BASE}/suspects/${encodeURIComponent(domain)}`, { status });
  return data;
}

export async function addManualSuspect(domain: string) {
  const { data } = await apiClient.post(`${BASE}/suspects/manual`, { domain });
  return data;
}

export async function blockSuspect(domain: string, target: string, listId?: number) {
  const { data } = await apiClient.post(`${BASE}/suspects/block`, {
    domain, target, list_id: listId,
  });
  return data;
}

export async function bulkAction(domains: string[], action: string, target?: string, listId?: number) {
  const { data } = await apiClient.post(`${BASE}/suspects/bulk-action`, {
    domains, action, target, list_id: listId,
  });
  return data;
}

// Patterns
export async function getPatterns() {
  const { data } = await apiClient.get(`${BASE}/patterns`);
  return data as { patterns: PatternEntry[] };
}

export async function createPattern(pattern: { pattern: string; is_regex: boolean; weight: number; category: string }) {
  const { data } = await apiClient.post(`${BASE}/patterns`, pattern);
  return data;
}

export async function updatePattern(id: number, update: { weight?: number; enabled?: boolean; category?: string }) {
  const { data } = await apiClient.patch(`${BASE}/patterns/${id}`, update);
  return data;
}

export async function deletePattern(id: number) {
  const { data } = await apiClient.delete(`${BASE}/patterns/${id}`);
  return data;
}

// Reference Lists
export async function getReferenceLists() {
  const { data } = await apiClient.get(`${BASE}/reference-lists`);
  return data as { lists: ReferenceListEntry[] };
}

export async function createReferenceList(list: { name: string; url: string; fetch_interval_hours?: number }) {
  const { data } = await apiClient.post(`${BASE}/reference-lists`, list);
  return data;
}

export async function updateReferenceList(id: number, update: { enabled?: boolean; fetch_interval_hours?: number }) {
  const { data } = await apiClient.patch(`${BASE}/reference-lists/${id}`, update);
  return data;
}

export async function deleteReferenceList(id: number) {
  const { data } = await apiClient.delete(`${BASE}/reference-lists/${id}`);
  return data;
}

export async function refreshReferenceLists() {
  const { data } = await apiClient.post(`${BASE}/reference-lists/refresh`);
  return data;
}

// Custom Lists
export async function getCustomLists() {
  const { data } = await apiClient.get(`${BASE}/custom-lists`);
  return data as { lists: CustomListEntry[] };
}

export async function createCustomList(list: { name: string; description?: string }) {
  const { data } = await apiClient.post(`${BASE}/custom-lists`, list);
  return data;
}

export async function updateCustomList(id: number, update: { name?: string; description?: string }) {
  const { data } = await apiClient.patch(`${BASE}/custom-lists/${id}`, update);
  return data;
}

export async function deleteCustomList(id: number) {
  const { data } = await apiClient.delete(`${BASE}/custom-lists/${id}`);
  return data;
}

export async function getCustomListDomains(id: number, page = 1, pageSize = 100) {
  const { data } = await apiClient.get(`${BASE}/custom-lists/${id}/domains`, {
    params: { page, page_size: pageSize },
  });
  return data as { domains: CustomListDomainEntry[]; total: number };
}

export async function addCustomListDomains(id: number, domains: string[], comment = '') {
  const { data } = await apiClient.post(`${BASE}/custom-lists/${id}/domains`, { domains, comment });
  return data;
}

export async function removeCustomListDomain(id: number, domain: string) {
  const { data } = await apiClient.delete(`${BASE}/custom-lists/${id}/domains/${encodeURIComponent(domain)}`);
  return data;
}

export async function deployCustomList(id: number) {
  const { data } = await apiClient.post(`${BASE}/custom-lists/${id}/deploy`);
  return data;
}

export async function undeployCustomList(id: number) {
  const { data } = await apiClient.post(`${BASE}/custom-lists/${id}/undeploy`);
  return data;
}

export async function exportCustomList(id: number): Promise<Blob> {
  const { data } = await apiClient.get(`${BASE}/custom-lists/${id}/export`, {
    responseType: 'blob',
  });
  return data;
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/api/adDiscovery.ts
git commit -m "feat(ad-discovery): add frontend API client with types"
```

---

## Task 11: Frontend — Ad Discovery Tab + Suspects Table

**Files:**
- Create: `client/src/components/pihole/AdDiscoveryTab.tsx`
- Create: `client/src/components/pihole/ad-discovery/SuspectsTable.tsx`
- Create: `client/src/components/pihole/ad-discovery/BlockDialog.tsx`
- Modify: `client/src/pages/PiholePage.tsx`

- [ ] **Step 1: Create BlockDialog component**

Modal dialog for choosing block target: deny-list or custom list (dropdown). If custom list selected, show list dropdown + "Create new list" option.

- [ ] **Step 2: Create SuspectsTable component**

Table with columns: Domain, Score (color-coded), Source, Queries, Community Hits, Status, Actions (Block/Dismiss). Includes:
- Filter bar: status dropdown, source dropdown, min-score slider
- Sort by column headers
- Checkbox selection for bulk actions
- Pagination

- [ ] **Step 3: Create AdDiscoveryTab component**

Main tab component with:
- Header status bar (new suspects count, last analysis, reference lists, custom lists stats)
- "Start Analysis" button
- SuspectsTable as main content
- Sub-tabs below: Patterns, Reference Lists, Custom Lists (initially rendered as placeholders — implemented in Tasks 12-14)

- [ ] **Step 4: Add tab to PiholePage**

In `client/src/pages/PiholePage.tsx`:
- Line 33: Add `'ad-discovery'` to Tab type union
- Line 35-45: Add `{ key: 'ad-discovery', label: 'Ad Discovery' }` to TABS array
- Add import: `import AdDiscoveryTab from '../components/pihole/AdDiscoveryTab';`
- In the tab content render section, add case for `'ad-discovery'` → `<AdDiscoveryTab />`

- [ ] **Step 5: Verify in browser**

Run: `python start_dev.py` (or frontend dev server)
Navigate to Pi-hole page → "Ad Discovery" tab should appear and render the shell UI

- [ ] **Step 6: Commit**

```bash
git add client/src/components/pihole/AdDiscoveryTab.tsx client/src/components/pihole/ad-discovery/ client/src/pages/PiholePage.tsx
git commit -m "feat(ad-discovery): add Ad Discovery tab with suspects table UI"
```

---

## Task 12: Frontend — Patterns Sub-Tab

**Files:**
- Create: `client/src/components/pihole/ad-discovery/PatternsPanel.tsx`
- Modify: `client/src/components/pihole/AdDiscoveryTab.tsx` (replace placeholder)

- [ ] **Step 1: Create PatternsPanel**

Table of patterns with:
- Columns: Pattern, Type (substring/regex badge), Weight, Category, Enabled toggle
- Default patterns visually distinguished (grey background), toggle only
- User-defined patterns: edit/delete buttons
- "Add Pattern" button → inline form or modal
- Calls `getPatterns()`, `createPattern()`, `updatePattern()`, `deletePattern()`

- [ ] **Step 2: Wire into AdDiscoveryTab**

Replace the "Patterns" placeholder with `<PatternsPanel />`.

- [ ] **Step 3: Commit**

```bash
git add client/src/components/pihole/ad-discovery/PatternsPanel.tsx client/src/components/pihole/AdDiscoveryTab.tsx
git commit -m "feat(ad-discovery): add patterns configuration panel"
```

---

## Task 13: Frontend — Reference Lists Sub-Tab

**Files:**
- Create: `client/src/components/pihole/ad-discovery/ReferenceListsPanel.tsx`
- Modify: `client/src/components/pihole/AdDiscoveryTab.tsx` (replace placeholder)

- [ ] **Step 1: Create ReferenceListsPanel**

Card layout per list:
- Name, URL (truncated), domain count, last fetch time
- Status badge: green "Current" if fetched within interval, yellow "Stale", red "Error"
- Toggle on/off switch
- Default lists distinguished, user-added can be deleted
- "Add List" button → form (name + URL)
- "Refresh All" button → calls `refreshReferenceLists()`

- [ ] **Step 2: Wire into AdDiscoveryTab**

Replace the "Reference Lists" placeholder with `<ReferenceListsPanel />`.

- [ ] **Step 3: Commit**

```bash
git add client/src/components/pihole/ad-discovery/ReferenceListsPanel.tsx client/src/components/pihole/AdDiscoveryTab.tsx
git commit -m "feat(ad-discovery): add reference lists panel"
```

---

## Task 14: Frontend — Custom Lists Sub-Tab

**Files:**
- Create: `client/src/components/pihole/ad-discovery/CustomListsPanel.tsx`
- Modify: `client/src/components/pihole/AdDiscoveryTab.tsx` (replace placeholder)

- [ ] **Step 1: Create CustomListsPanel**

Card layout per list:
- Name, domain count, deploy status badge (green "Active" / grey "Not deployed")
- Actions: View domains (expandable or modal), Deploy/Undeploy, Export .txt, Delete
- Domain list view with pagination and remove-domain action
- "Create List" button → form (name + description)
- Export triggers download via `exportCustomList(id)` → `saveAs` blob

- [ ] **Step 2: Wire into AdDiscoveryTab**

Replace the "Custom Lists" placeholder with `<CustomListsPanel />`.

- [ ] **Step 3: Commit**

```bash
git add client/src/components/pihole/ad-discovery/CustomListsPanel.tsx client/src/components/pihole/AdDiscoveryTab.tsx
git commit -m "feat(ad-discovery): add custom lists panel"
```

---

## Task 15: Dev Mode Support

**Files:**
- Modify: `backend/app/services/pihole/ad_discovery/community_matcher.py`
- Modify: `backend/app/services/pihole/ad_discovery/background.py`

- [ ] **Step 1: Add dev mode to community matcher**

When `settings.is_dev_mode`, skip HTTP downloads in `fetch_list()`. Instead, return a hardcoded set of ~100 known ad domains per list. This allows testing cross-reference logic without network access.

- [ ] **Step 2: Shorter background interval in dev mode**

In `background.py`, use 5-minute interval when `settings.is_dev_mode` instead of default 6 hours.

- [ ] **Step 3: Verify dev mode works**

Run: `python start_dev.py`
Check: Pi-hole Ad Discovery tab loads, "Start Analysis" works and finds suspects from the DnsQueryCollector's mock data + dev mode reference list overlap.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/pihole/ad_discovery/community_matcher.py backend/app/services/pihole/ad_discovery/background.py
git commit -m "feat(ad-discovery): add dev mode support for testing"
```

---

## Task 16: Final Integration Test

- [ ] **Step 1: Run full test suite**

Run: `cd backend && python -m pytest tests/test_ad_discovery_*.py -v`
Expected: All ad-discovery tests pass

- [ ] **Step 2: Run existing pihole tests (regression)**

Run: `cd backend && python -m pytest tests/test_pihole.py -v`
Expected: All existing tests still pass

- [ ] **Step 3: Manual smoke test**

1. Start dev server: `python start_dev.py`
2. Navigate to Pi-hole → Ad Discovery tab
3. Click "Start Analysis" — verify suspects appear
4. Toggle a pattern off, re-analyze — verify changed results
5. Enable a reference list, refresh, re-analyze — verify community hits
6. Block a suspect → deny list — verify it appears in Pi-hole domains
7. Create custom list, add suspects, deploy — verify adlist in Pi-hole
8. Export custom list as .txt — verify valid file downloads

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(ad-discovery): complete implementation with integration tests"
```
