"""SQLAlchemy models for Pi-hole DNS query logging in PostgreSQL.

Persists DNS queries independently of the Pi-hole Docker container lifecycle,
enabling long-term analytics and historical analysis.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
)

from app.models.base import Base


class DnsQuery(Base):
    """Individual DNS query record from Pi-hole."""

    __tablename__ = "dns_queries"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    domain = Column(String(253), nullable=False, index=True)
    client = Column(String(45), nullable=False, index=True)
    query_type = Column(String(10), nullable=False)
    status = Column(String(20), nullable=False, index=True)
    reply_type = Column(String(20), nullable=True)
    response_time_ms = Column(Float, nullable=True)

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

    id = Column(Integer, primary_key=True, autoincrement=True)
    hour = Column(DateTime, nullable=False, unique=True, index=True)
    total_queries = Column(Integer, nullable=False, default=0)
    blocked_queries = Column(Integer, nullable=False, default=0)
    cached_queries = Column(Integer, nullable=False, default=0)
    forwarded_queries = Column(Integer, nullable=False, default=0)
    unique_domains = Column(Integer, nullable=False, default=0)
    unique_clients = Column(Integer, nullable=False, default=0)
    avg_response_time_ms = Column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<DnsQueryHourlyStat(hour={self.hour}, total={self.total_queries})>"


class DnsQueryCollectorState(Base):
    """Singleton (id=1) storing collector state and configuration."""

    __tablename__ = "dns_query_collector_state"

    id = Column(Integer, primary_key=True, default=1)
    last_fetched_timestamp = Column(Float, nullable=False, default=0.0)
    last_poll_at = Column(DateTime, nullable=True)
    total_queries_stored = Column(BigInteger, nullable=False, default=0)
    last_error = Column(String(500), nullable=True)
    last_error_at = Column(DateTime, nullable=True)
    poll_interval_seconds = Column(Integer, nullable=False, default=30)
    retention_days = Column(Integer, nullable=False, default=30)
    is_enabled = Column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<DnsQueryCollectorState(enabled={self.is_enabled}, stored={self.total_queries_stored})>"
