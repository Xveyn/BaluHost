"""DNS query analytics from the local PostgreSQL store.

Extracts all direct ORM queries from the pihole route handlers into
reusable service functions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.models.dns_queries import DnsQuery, DnsQueryCollectorState, DnsQueryHourlyStat


def _period_to_delta(period: str) -> timedelta:
    """Convert period string to timedelta."""
    if period == "7d":
        return timedelta(days=7)
    if period == "30d":
        return timedelta(days=30)
    return timedelta(hours=24)


def get_stored_queries(
    db: Session,
    *,
    page: int,
    page_size: int,
    period: str,
    domain: Optional[str] = None,
    client: Optional[str] = None,
    query_status: Optional[str] = None,
) -> dict:
    """Get paginated DNS query history."""
    since = datetime.now(timezone.utc) - _period_to_delta(period)
    q = db.query(DnsQuery).filter(DnsQuery.timestamp >= since)

    if domain:
        q = q.filter(DnsQuery.domain.ilike(f"%{domain}%"))
    if client:
        q = q.filter(DnsQuery.client == client)
    if query_status:
        q = q.filter(DnsQuery.status == query_status)

    total = q.count()
    offset = (page - 1) * page_size
    rows = q.order_by(DnsQuery.timestamp.desc()).offset(offset).limit(page_size).all()

    return {"rows": rows, "total": total, "page": page, "page_size": page_size}


def get_stored_stats(db: Session, *, period: str) -> dict:
    """Get aggregated DNS stats for a time period."""
    since = datetime.now(timezone.utc) - _period_to_delta(period)
    base = db.query(DnsQuery).filter(DnsQuery.timestamp >= since)

    total = base.count()
    blocked = base.filter(DnsQuery.status == "BLOCKED").count()
    cached = base.filter(DnsQuery.status == "CACHED").count()
    forwarded = base.filter(DnsQuery.status == "FORWARDED").count()
    domains = (
        db.query(func.count(distinct(DnsQuery.domain)))
        .filter(DnsQuery.timestamp >= since)
        .scalar()
        or 0
    )
    clients = (
        db.query(func.count(distinct(DnsQuery.client)))
        .filter(DnsQuery.timestamp >= since)
        .scalar()
        or 0
    )
    avg_rt = (
        db.query(func.avg(DnsQuery.response_time_ms))
        .filter(DnsQuery.timestamp >= since)
        .scalar()
    )

    return {
        "total_queries": total,
        "blocked_queries": blocked,
        "cached_queries": cached,
        "forwarded_queries": forwarded,
        "unique_domains": domains,
        "unique_clients": clients,
        "avg_response_time_ms": round(avg_rt, 2) if avg_rt else None,
        "block_rate": round(blocked / total * 100, 1) if total > 0 else 0.0,
        "period": period,
    }


def get_stored_top_domains(db: Session, *, count: int, period: str) -> list:
    """Get top queried domains."""
    since = datetime.now(timezone.utc) - _period_to_delta(period)
    return (
        db.query(DnsQuery.domain, func.count().label("cnt"))
        .filter(DnsQuery.timestamp >= since)
        .group_by(DnsQuery.domain)
        .order_by(func.count().desc())
        .limit(count)
        .all()
    )


def get_stored_top_blocked(db: Session, *, count: int, period: str) -> list:
    """Get top blocked domains."""
    since = datetime.now(timezone.utc) - _period_to_delta(period)
    return (
        db.query(DnsQuery.domain, func.count().label("cnt"))
        .filter(DnsQuery.timestamp >= since, DnsQuery.status == "BLOCKED")
        .group_by(DnsQuery.domain)
        .order_by(func.count().desc())
        .limit(count)
        .all()
    )


def get_stored_top_clients(db: Session, *, count: int, period: str) -> list:
    """Get top clients by query count."""
    since = datetime.now(timezone.utc) - _period_to_delta(period)
    return (
        db.query(DnsQuery.client, func.count().label("cnt"))
        .filter(DnsQuery.timestamp >= since)
        .group_by(DnsQuery.client)
        .order_by(func.count().desc())
        .limit(count)
        .all()
    )


def get_stored_history(db: Session, *, period: str) -> list:
    """Get hourly query timeline from pre-aggregated stats."""
    since = datetime.now(timezone.utc) - _period_to_delta(period)
    return (
        db.query(DnsQueryHourlyStat)
        .filter(DnsQueryHourlyStat.hour >= since)
        .order_by(DnsQueryHourlyStat.hour.asc())
        .all()
    )


def update_collector_config(db: Session, update_data: dict) -> None:
    """Update DNS query collector configuration in DB."""
    row = db.query(DnsQueryCollectorState).filter_by(id=1).first()
    if not row:
        row = DnsQueryCollectorState(id=1)
        db.add(row)

    for key, val in update_data.items():
        setattr(row, key, val)
    db.commit()
