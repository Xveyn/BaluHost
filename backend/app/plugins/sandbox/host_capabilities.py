"""Production wiring for the sandbox CapabilityRouter.

The Phase 3 CapabilityRouter takes its host dependencies by injection so it
stays testable. This module supplies the real ones — a DB session factory,
a read-only metrics reader, an in-app notifier, and the audit logger — and
filters the plugin's granted scopes down to the known host catalog.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from app.core.database import SessionLocal
from app.plugins.sandbox.capabilities import (
    CAPABILITY_SCOPE,
    CapabilityContext,
    CapabilityRouter,
)
from app.services.audit.logger_db import get_audit_logger_db
from app.services.monitoring.shm import TELEMETRY_FILE, read_shm
from app.services.notifications.service import get_notification_service

logger = logging.getLogger(__name__)

# The full set of scope strings the host knows how to enforce. Anything a
# plugin was granted that is not in here is silently dropped (defensive).
KNOWN_SCOPES: frozenset[str] = frozenset(CAPABILITY_SCOPE.values())

def _read_metrics() -> dict:
    """Curated read-only system metrics from the monitoring SHM snapshot.

    The telemetry SHM (telemetry.py) exposes ``latest_cpu_usage`` and a
    ``latest_memory_sample`` dict with a ``percent`` field — NOT top-level
    ``cpu_percent``/``memory_percent``. Project a small, stable subset.
    """
    snapshot = read_shm(TELEMETRY_FILE) or {}
    mem = snapshot.get("latest_memory_sample") or {}
    out: dict = {}
    if snapshot.get("latest_cpu_usage") is not None:
        out["cpu_usage"] = snapshot["latest_cpu_usage"]
    if isinstance(mem, dict) and mem.get("percent") is not None:
        out["memory_percent"] = mem["percent"]
    return out


def _make_notifier(
    session_factory: Callable[[], Any]
) -> Callable[[CapabilityContext, dict], Awaitable[None]]:
    """Create a notifier closure that captures the injected session_factory.

    Returns an async function that creates an in-app notification for the
    request's acting user only, using the provided session factory.
    """

    async def _notify(context: CapabilityContext, payload: dict) -> None:
        service = get_notification_service()
        with session_factory() as db:
            await service.create(
                db,
                user_id=context.user_id,
                category="plugin",
                notification_type=payload["type"],
                title=payload["title"],
                message=payload["message"],
            )

    return _notify


def build_capability_router(
    plugin_name: str, granted_scopes: "set[str] | frozenset[str]"
) -> CapabilityRouter:
    """Build a CapabilityRouter with production host dependencies."""
    filtered = frozenset(granted_scopes) & KNOWN_SCOPES
    return CapabilityRouter(
        plugin_name=plugin_name,
        granted_scopes=filtered,
        session_factory=SessionLocal,
        metrics_reader=_read_metrics,
        notifier=_make_notifier(SessionLocal),
        audit_logger=get_audit_logger_db(),
    )
