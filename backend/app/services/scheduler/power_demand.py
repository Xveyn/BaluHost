"""Power demands of scheduler jobs, written straight into ``power_demands``.

The scheduler worker is a separate process. Instead of an HTTP loopback to the
API (which needed a per-process token and woke the NAS from soft sleep before
authentication), it writes its demand row directly; the primary applies it on
its next tick (<= 5 s).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.schemas.power import PowerProfile, ServicePowerProperty
from app.services.power import config_store

# Power level per scheduler job. ``idle`` jobs register no demand:
# sync_check is one DB query every 5 min, auto_update returns immediately.
SCHEDULER_POWER_LEVELS: dict[str, str] = {
    "backup": "surge",
    "raid_scrub": "surge",
    "smart_scan": "medium",
    "sync_check": "idle",
    "notification_check": "idle",
    "upload_cleanup": "low",
    "auto_update": "idle",
    "cloud_sync": "medium",
    "file_activity_cleanup": "low",
    "plugin_update_check": "low",
}

DEMAND_TIMEOUT_S = 3600  # 1h safety timeout


def _level_for(name: str) -> str | None:
    level = SCHEDULER_POWER_LEVELS.get(name)
    if not level or level == "idle":
        return None
    return level


def register_scheduler_demand(name: str) -> bool:
    """Write the demand row for a scheduler job.

    Returns False if the job needs no demand or the write failed.
    """
    level = _level_for(name)
    if level is None:
        return False
    source = f"scheduler:{name}"
    description = f"Scheduler job: {name}"
    now = datetime.now(timezone.utc)
    ok = config_store.upsert_demand(
        source=source,
        level=PowerProfile(level),
        power_property=ServicePowerProperty(level),
        registered_at=now,
        expires_at=now + timedelta(seconds=DEMAND_TIMEOUT_S),
        description=description,
    )
    config_store.persist_demand_log(
        action="registered",
        source=source,
        level=level,
        description=description,
        resulting_profile="pending",
        timeout_seconds=DEMAND_TIMEOUT_S,
    )
    return ok


def unregister_scheduler_demand(name: str) -> None:
    """Remove the demand row of a scheduler job."""
    level = _level_for(name)
    if level is None:
        return
    source = f"scheduler:{name}"
    if config_store.delete_demand(source):
        config_store.persist_demand_log(
            action="unregistered",
            source=source,
            level=level,
            description=f"Scheduler job: {name}",
            resulting_profile="pending",
        )
