"""DNS query collector — polls Pi-hole API and stores queries in PostgreSQL.

Runs as a background asyncio task on the primary worker.  Uses a timestamp
watermark to avoid duplicate inserts across restarts.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import delete, distinct, func
from sqlalchemy.orm import Session

from app.core.database import DATABASE_URL, commit_with_retry
from app.models.dns_queries import (
    DnsQuery,
    DnsQueryCollectorState,
    DnsQueryHourlyStat,
)

logger = logging.getLogger(__name__)

# Batch size when fetching from Pi-hole API
_FETCH_BATCH = 200


class DnsQueryCollector:
    """Periodically polls Pi-hole for new queries and stores them in PostgreSQL."""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._db_factory: Callable[[], Session] | None = None
        # Hourly stats recomputation tracking
        self._last_hourly_recompute: datetime | None = None
        # Retention cleanup tracking
        self._last_retention_run: datetime | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self, db_session_factory: Callable[[], Session]) -> None:
        """Start the collector background task."""
        if self._task and not self._task.done():
            logger.warning("DnsQueryCollector already running")
            return
        self._db_factory = db_session_factory
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("DnsQueryCollector started")

    async def stop(self) -> None:
        """Stop the collector gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("DnsQueryCollector stopped")

    # ── Main Loop ────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        # Warmup delay — let services initialise
        await asyncio.sleep(15)

        while self._running:
            try:
                state = self._read_state()
                if state is None:
                    self._ensure_state_row()
                    state = self._read_state()

                if not state or not state.get("is_enabled", True):
                    await asyncio.sleep(10)
                    continue

                interval = state.get("poll_interval_seconds", 30)

                # Fetch & store new queries
                await self._fetch_and_store()

                # Hourly stats recomputation (every hour)
                now = datetime.now(timezone.utc)
                if (
                    self._last_hourly_recompute is None
                    or (now - self._last_hourly_recompute).total_seconds() >= 3600
                ):
                    self._compute_hourly_stats(hours=2)
                    self._last_hourly_recompute = now

                # Retention cleanup (every 6 hours)
                if (
                    self._last_retention_run is None
                    or (now - self._last_retention_run).total_seconds() >= 21600
                ):
                    self._run_retention()
                    self._last_retention_run = now

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("DnsQueryCollector poll cycle failed")
                self._record_error("Poll cycle exception")
                await asyncio.sleep(30)

    # ── Fetch & Store ────────────────────────────────────────────────

    async def _fetch_and_store(self) -> None:
        """Fetch new queries from Pi-hole and bulk-insert into PostgreSQL."""
        from app.services.pihole.service import get_pihole_service

        assert self._db_factory is not None
        db = self._db_factory()
        try:
            state_row = db.query(DnsQueryCollectorState).filter_by(id=1).first()
            if state_row is None:
                return
            watermark = state_row.last_fetched_timestamp

            service = get_pihole_service(db)
            backend = service._get_backend()

            new_count = 0
            highest_ts = watermark

            # Fetch a single batch — Pi-hole returns the most recent queries.
            # The watermark filter below skips already-seen entries.
            data = await backend.get_queries(limit=_FETCH_BATCH, offset=0)
            queries_raw: list[dict[str, Any]] = data.get("queries", [])

            to_insert: list[dict[str, Any]] = []
            for q in queries_raw:
                ts = q.get("timestamp", 0)
                if ts <= watermark:
                    continue
                if ts > highest_ts:
                    highest_ts = ts
                to_insert.append({
                    "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc),
                    "domain": (q.get("domain") or "")[:253],
                    "client": (q.get("client") or "")[:45],
                    "query_type": (q.get("query_type") or "")[:10],
                    "status": (q.get("status") or "")[:20],
                    "reply_type": (q.get("reply_type") or "")[:20] if q.get("reply_type") else None,
                    "response_time_ms": q.get("response_time"),
                })

            if to_insert:
                db.add_all([DnsQuery(**row) for row in to_insert])
                new_count = len(to_insert)

            # Update watermark
            if highest_ts > watermark:
                state_row.last_fetched_timestamp = highest_ts
            state_row.last_poll_at = datetime.now(timezone.utc)
            state_row.total_queries_stored = (state_row.total_queries_stored or 0) + new_count
            state_row.last_error = None
            state_row.last_error_at = None
            commit_with_retry(db)

            if new_count > 0:
                logger.debug("DnsQueryCollector stored %d new queries", new_count)

        except Exception:
            db.rollback()
            logger.exception("DnsQueryCollector _fetch_and_store failed")
            self._record_error("Fetch failed")
            raise
        finally:
            db.close()

    # ── Hourly Stats ─────────────────────────────────────────────────

    def _compute_hourly_stats(self, hours: int = 2) -> None:
        """Recompute hourly aggregations for the last N hours."""
        assert self._db_factory is not None
        db = self._db_factory()
        try:
            now = datetime.now(timezone.utc)
            since = now - timedelta(hours=hours)
            # Truncate to hour boundary
            since = since.replace(minute=0, second=0, microsecond=0)

            # Get distinct hours with data (cross-database compatible)
            if DATABASE_URL.startswith("sqlite"):
                # SQLite: use strftime to truncate to hour
                hour_expr = func.strftime("%Y-%m-%d %H:00:00", DnsQuery.timestamp)
            else:
                # PostgreSQL
                hour_expr = func.date_trunc("hour", DnsQuery.timestamp)
            rows = (
                db.query(
                    hour_expr.label("hour"),
                    func.count().label("total"),
                    func.count().filter(DnsQuery.status == "BLOCKED").label("blocked"),
                    func.count().filter(DnsQuery.status == "CACHED").label("cached"),
                    func.count().filter(DnsQuery.status == "FORWARDED").label("forwarded"),
                    func.count(distinct(DnsQuery.domain)).label("domains"),
                    func.count(distinct(DnsQuery.client)).label("clients"),
                    func.avg(DnsQuery.response_time_ms).label("avg_rt"),
                )
                .filter(DnsQuery.timestamp >= since)
                .group_by(hour_expr)
                .all()
            )

            _is_sqlite = DATABASE_URL.startswith("sqlite")
            for row in rows:
                # SQLite strftime returns a string — parse to datetime
                hour_val = (
                    datetime.strptime(row.hour, "%Y-%m-%d %H:%M:%S")
                    .replace(tzinfo=timezone.utc)
                    if _is_sqlite and isinstance(row.hour, str)
                    else row.hour
                )
                # Upsert
                existing = db.query(DnsQueryHourlyStat).filter_by(hour=hour_val).first()
                if existing:
                    existing.total_queries = row.total
                    existing.blocked_queries = row.blocked
                    existing.cached_queries = row.cached
                    existing.forwarded_queries = row.forwarded
                    existing.unique_domains = row.domains
                    existing.unique_clients = row.clients
                    existing.avg_response_time_ms = round(row.avg_rt, 2) if row.avg_rt else None
                else:
                    db.add(DnsQueryHourlyStat(
                        hour=hour_val,
                        total_queries=row.total,
                        blocked_queries=row.blocked,
                        cached_queries=row.cached,
                        forwarded_queries=row.forwarded,
                        unique_domains=row.domains,
                        unique_clients=row.clients,
                        avg_response_time_ms=round(row.avg_rt, 2) if row.avg_rt else None,
                    ))

            commit_with_retry(db)
            logger.debug("Hourly stats recomputed for %d hours", len(rows))
        except Exception:
            db.rollback()
            logger.exception("Hourly stats computation failed")
        finally:
            db.close()

    # ── Retention ────────────────────────────────────────────────────

    def _run_retention(self) -> None:
        """Delete queries and hourly stats older than retention_days."""
        assert self._db_factory is not None
        db = self._db_factory()
        try:
            state_row = db.query(DnsQueryCollectorState).filter_by(id=1).first()
            retention = state_row.retention_days if state_row else 30
            cutoff = datetime.now(timezone.utc) - timedelta(days=retention)

            q_result: Any = db.execute(
                delete(DnsQuery).where(DnsQuery.timestamp < cutoff)
            )
            deleted_queries: int = q_result.rowcount or 0
            s_result: Any = db.execute(
                delete(DnsQueryHourlyStat).where(DnsQueryHourlyStat.hour < cutoff)
            )
            deleted_stats: int = s_result.rowcount or 0

            commit_with_retry(db)
            if deleted_queries or deleted_stats:
                logger.info(
                    "Retention cleanup: deleted %d queries, %d hourly stats (cutoff=%s)",
                    deleted_queries, deleted_stats, cutoff.isoformat(),
                )
        except Exception:
            db.rollback()
            logger.exception("Retention cleanup failed")
        finally:
            db.close()

    # ── State Helpers ────────────────────────────────────────────────

    def _read_state(self) -> dict[str, Any] | None:
        """Read collector state from DB."""
        assert self._db_factory is not None
        db = self._db_factory()
        try:
            row = db.query(DnsQueryCollectorState).filter_by(id=1).first()
            if row is None:
                return None
            return {
                "is_enabled": row.is_enabled,
                "poll_interval_seconds": row.poll_interval_seconds,
                "retention_days": row.retention_days,
                "last_fetched_timestamp": row.last_fetched_timestamp,
            }
        finally:
            db.close()

    def _ensure_state_row(self) -> None:
        """Create the singleton state row if missing."""
        assert self._db_factory is not None
        db = self._db_factory()
        try:
            existing = db.query(DnsQueryCollectorState).filter_by(id=1).first()
            if not existing:
                db.add(DnsQueryCollectorState(id=1))
                commit_with_retry(db)
        except Exception:
            db.rollback()
        finally:
            db.close()

    def _record_error(self, message: str) -> None:
        """Record an error in the collector state."""
        if not self._db_factory:
            return
        db = self._db_factory()
        try:
            row = db.query(DnsQueryCollectorState).filter_by(id=1).first()
            if row:
                row.last_error = message[:500]
                row.last_error_at = datetime.now(timezone.utc)
                commit_with_retry(db)
        except Exception:
            db.rollback()
        finally:
            db.close()

    # ── Public Status ────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Return collector status for the admin dashboard."""
        running = self._task is not None and not self._task.done()
        result: dict[str, Any] = {"running": running}

        if not self._db_factory:
            return result

        db = self._db_factory()
        try:
            row = db.query(DnsQueryCollectorState).filter_by(id=1).first()
            if row:
                result.update({
                    "is_enabled": row.is_enabled,
                    "last_poll_at": row.last_poll_at.isoformat() if row.last_poll_at else None,
                    "total_queries_stored": row.total_queries_stored or 0,
                    "last_error": row.last_error,
                    "last_error_at": row.last_error_at.isoformat() if row.last_error_at else None,
                    "poll_interval_seconds": row.poll_interval_seconds,
                    "retention_days": row.retention_days,
                })
        finally:
            db.close()

        return result


# Module-level singleton
_collector = DnsQueryCollector()


def get_dns_query_collector() -> DnsQueryCollector:
    """Return the singleton DnsQueryCollector."""
    return _collector
