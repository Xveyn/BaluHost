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
