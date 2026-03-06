"""SQLAlchemy models for Pi-hole DNS query logging in PostgreSQL.

Persists DNS queries independently of the Pi-hole Docker container lifecycle,
enabling long-term analytics and historical analysis.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DnsQuery(Base):
    """Individual DNS query record from Pi-hole."""

    __tablename__ = "dns_queries"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    timestamp: Mapped[datetime] = mapped_column(index=True)
    domain: Mapped[str] = mapped_column(String(253), index=True)
    client: Mapped[str] = mapped_column(String(45), index=True)
    query_type: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), index=True)
    reply_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    response_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    __table_args__ = (
        Index("ix_dns_queries_ts_domain", "timestamp", "domain"),
        Index("ix_dns_queries_ts_status", "timestamp", "status"),
        Index("ix_dns_queries_ts_client", "timestamp", "client"),
    )

    def __repr__(self) -> str:
        return f"<DnsQuery(domain={self.domain}, status={self.status}, ts={self.timestamp})>"


class DnsQueryHourlyStat(Base):
    """Pre-aggregated hourly DNS query statistics."""

    __tablename__ = "dns_query_hourly_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hour: Mapped[datetime] = mapped_column(unique=True, index=True)
    total_queries: Mapped[int] = mapped_column(Integer, default=0)
    blocked_queries: Mapped[int] = mapped_column(Integer, default=0)
    cached_queries: Mapped[int] = mapped_column(Integer, default=0)
    forwarded_queries: Mapped[int] = mapped_column(Integer, default=0)
    unique_domains: Mapped[int] = mapped_column(Integer, default=0)
    unique_clients: Mapped[int] = mapped_column(Integer, default=0)
    avg_response_time_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<DnsQueryHourlyStat(hour={self.hour}, total={self.total_queries})>"


class DnsQueryCollectorState(Base):
    """Singleton (id=1) storing collector state and configuration."""

    __tablename__ = "dns_query_collector_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_fetched_timestamp: Mapped[float] = mapped_column(Float, default=0.0)
    last_poll_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    total_queries_stored: Mapped[int] = mapped_column(BigInteger, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=30)
    retention_days: Mapped[int] = mapped_column(Integer, default=30)
    is_enabled: Mapped[bool] = mapped_column(default=True)

    def __repr__(self) -> str:
        return f"<DnsQueryCollectorState(enabled={self.is_enabled}, stored={self.total_queries_stored})>"
