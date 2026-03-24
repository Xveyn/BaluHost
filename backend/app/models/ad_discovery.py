"""SQLAlchemy models for Ad Discovery feature.

Stores heuristic-based ad/tracker domain suspects, community reference lists,
custom block lists, pattern definitions, and singleton configuration.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class AdDiscoveryPattern(Base):
    """Heuristic pattern used to score domains as potential ads/trackers."""

    __tablename__ = "ad_discovery_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(String(253), nullable=False)
    is_regex: Mapped[bool] = mapped_column(Boolean, default=False)
    weight: Mapped[float] = mapped_column(Float, default=0.5)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<AdDiscoveryPattern(pattern={self.pattern!r}, category={self.category}, weight={self.weight})>"


class AdDiscoveryReferenceList(Base):
    """Remote community-maintained blocklist used for cross-referencing suspects."""

    __tablename__ = "ad_discovery_reference_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    domain_count: Mapped[int] = mapped_column(Integer, default=0)
    last_fetched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fetch_interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<AdDiscoveryReferenceList(name={self.name!r}, enabled={self.enabled}, domains={self.domain_count})>"


class AdDiscoverySuspect(Base):
    """Domain flagged by heuristic analysis or community lists as a potential ad/tracker."""

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
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    previous_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    __table_args__ = (
        Index("ix_ad_discovery_suspects_status_score", "status", "heuristic_score"),
    )

    def __repr__(self) -> str:
        return f"<AdDiscoverySuspect(domain={self.domain!r}, status={self.status}, score={self.heuristic_score})>"


class AdDiscoveryCustomList(Base):
    """User-managed custom blocklist that can be deployed to Pi-hole."""

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

    domains: Mapped[list["AdDiscoveryCustomListDomain"]] = relationship(
        "AdDiscoveryCustomListDomain",
        back_populates="custom_list",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<AdDiscoveryCustomList(name={self.name!r}, domains={self.domain_count}, deployed={self.deployed})>"


class AdDiscoveryCustomListDomain(Base):
    """Individual domain entry within a custom blocklist."""

    __tablename__ = "ad_discovery_custom_list_domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    list_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ad_discovery_custom_lists.id", ondelete="CASCADE"),
        nullable=False,
    )
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    comment: Mapped[str] = mapped_column(String(500), default="")

    custom_list: Mapped["AdDiscoveryCustomList"] = relationship(
        "AdDiscoveryCustomList",
        back_populates="domains",
    )

    __table_args__ = (
        UniqueConstraint("list_id", "domain", name="uq_ad_custom_list_domain"),
    )

    def __repr__(self) -> str:
        return f"<AdDiscoveryCustomListDomain(list_id={self.list_id}, domain={self.domain!r})>"


class AdDiscoveryConfig(Base):
    """Singleton (id=1) configuration for the Ad Discovery background analyzer."""

    __tablename__ = "ad_discovery_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    background_interval_hours: Mapped[int] = mapped_column(Integer, default=6)
    heuristic_weight: Mapped[float] = mapped_column(Float, default=0.4)
    community_weight: Mapped[float] = mapped_column(Float, default=0.6)
    min_score: Mapped[float] = mapped_column(Float, default=0.15)
    re_evaluation_threshold: Mapped[float] = mapped_column(Float, default=0.3)
    background_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_analysis_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_analysis_watermark: Mapped[float] = mapped_column(Float, default=0.0)

    def __repr__(self) -> str:
        return (
            f"<AdDiscoveryConfig(enabled={self.background_enabled}, "
            f"interval={self.background_interval_hours}h, "
            f"min_score={self.min_score})>"
        )
