"""Background plugin update check + compatibility scanner.

Runs on a timer from the scheduler worker. For every row in
``installed_plugins`` this service:

1. Reads the installed plugin's on-disk ``plugin.json`` (the version of the
   manifest the loader actually uses).
2. Runs the full resolver against the Core's current ``core_versions.json``
   to detect "Core update broke this plugin" — a plugin that was fine on
   install but is no longer satisfiable after a Core upgrade. Any conflict
   fires a ``plugin.incompatible`` notification.
3. Asks the marketplace service for the upstream index (force-refresh) and
   compares the locally installed version against ``latest_version``. If a
   newer version is available, the row's ``available_update`` column is
   populated and a ``plugin.update_available`` notification fires the first
   time that exact version is observed.

The service is intentionally pure — no HTTP in this module, no scheduler
glue. The caller (scheduler worker or API) is responsible for building the
``MarketplaceService`` and handing in a ``Session``. That makes the service
easy to test with an in-memory fake marketplace.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from packaging.version import InvalidVersion, Version
from sqlalchemy.orm import Session

from app.models.plugin import InstalledPlugin
from app.plugins.core_versions import CoreVersions
from app.plugins.manifest import ManifestError, load_manifest
from app.plugins.resolver import Conflict, resolve_install
from app.services.plugin_marketplace import (
    IndexFetchError,
    IndexParseError,
    MarketplaceService,
    PluginNotFoundError,
)

logger = logging.getLogger(__name__)


@dataclass
class PluginUpdateInfo:
    """Per-plugin result of a single update check."""

    name: str
    current_version: str
    latest_version: Optional[str] = None
    has_update: bool = False
    conflicts: List[Conflict] = field(default_factory=list)

    @property
    def is_incompatible(self) -> bool:
        return bool(self.conflicts)


@dataclass
class PluginUpdateCheckResult:
    """Aggregated output of ``run_plugin_update_check``."""

    checked: List[PluginUpdateInfo] = field(default_factory=list)
    index_fetched: bool = False
    errors: List[str] = field(default_factory=list)

    @property
    def updates_available(self) -> List[PluginUpdateInfo]:
        return [p for p in self.checked if p.has_update]

    @property
    def incompatible(self) -> List[PluginUpdateInfo]:
        return [p for p in self.checked if p.is_incompatible]


# Notifier signatures — injected so tests can assert calls without wiring
# the full notification emitter.
UpdateAvailableNotifier = Callable[[str, str, str], None]
IncompatibleNotifier = Callable[[str, str, str], None]


def _compare_versions(current: str, latest: str) -> bool:
    """Return True if ``latest`` is strictly newer than ``current``.

    Falls back to raw string inequality for unparseable versions — the
    resolver already catches most malformed versions elsewhere, so this is
    defense in depth, not a hot path.
    """
    try:
        return Version(latest) > Version(current)
    except InvalidVersion:
        return latest != current


def _format_conflicts(conflicts: Sequence[Conflict]) -> str:
    """Render a compact one-line reason string for notifications."""
    return "; ".join(
        f"{c.package} needs {c.requirement} (got {c.found})" for c in conflicts
    )


def run_plugin_update_check(
    db: Session,
    *,
    plugins_dir: Path,
    core_versions: CoreVersions,
    marketplace: MarketplaceService,
    notify_update_available: Optional[UpdateAvailableNotifier] = None,
    notify_incompatible: Optional[IncompatibleNotifier] = None,
) -> PluginUpdateCheckResult:
    """Check every installed plugin for updates and Core compatibility.

    Args:
        db: Active DB session (the service owns commits).
        plugins_dir: Filesystem directory holding installed plugin sources
            (each subdirectory matches an ``installed_plugins`` row).
        core_versions: The Core's locked-version snapshot. Used by the
            resolver to detect "Core update broke this plugin".
        marketplace: Configured :class:`MarketplaceService` used to fetch
            the upstream index. Failure to fetch is **not fatal** — the
            compatibility check still runs against the local state.
        notify_update_available: Optional callback fired once per newly
            discovered update. Defaults to the global event emitter.
        notify_incompatible: Optional callback fired once per incompatible
            installed plugin. Defaults to the global event emitter.

    Returns:
        :class:`PluginUpdateCheckResult` describing every plugin that was
        examined, whether an update is available, and whether any conflicts
        against the current Core were found.
    """
    if notify_update_available is None:
        from app.services.notifications.events import emit_plugin_update_available_sync

        notify_update_available = emit_plugin_update_available_sync
    if notify_incompatible is None:
        from app.services.notifications.events import emit_plugin_incompatible_sync

        notify_incompatible = emit_plugin_incompatible_sync

    result = PluginUpdateCheckResult()

    try:
        index = marketplace.get_index(force_refresh=True)
        result.index_fetched = True
    except (IndexFetchError, IndexParseError) as exc:
        logger.warning("plugin update check: marketplace fetch failed: %s", exc)
        result.errors.append(f"marketplace: {exc}")
        index = None

    rows = db.query(InstalledPlugin).all()
    now = datetime.now(timezone.utc)

    for row in rows:
        info = PluginUpdateInfo(name=row.name, current_version=row.version)
        result.checked.append(info)

        # 1. Compatibility scan against the current Core.
        plugin_dir = plugins_dir / row.name
        try:
            manifest = load_manifest(plugin_dir)
        except (ManifestError, FileNotFoundError) as exc:
            logger.warning(
                "plugin update check: cannot load manifest for %s: %s", row.name, exc
            )
            result.errors.append(f"{row.name}: manifest unreadable: {exc}")
        else:
            resolve = resolve_install(manifest, core_versions, installed=())
            if not resolve.ok:
                info.conflicts = list(resolve.conflicts)
                try:
                    notify_incompatible(
                        row.name,
                        row.version,
                        _format_conflicts(resolve.conflicts),
                    )
                except Exception:
                    logger.exception(
                        "plugin update check: notify_incompatible failed for %s",
                        row.name,
                    )

        # 2. Marketplace version comparison.
        if index is not None:
            entry = index.get_plugin(row.name)
            if entry is not None:
                info.latest_version = entry.latest_version
                if _compare_versions(row.version, entry.latest_version):
                    info.has_update = True
                    # Only fire a notification when this exact version first
                    # becomes visible — avoids pinging admins on every tick.
                    previous = row.available_update
                    if previous != entry.latest_version:
                        try:
                            notify_update_available(
                                row.name, row.version, entry.latest_version
                            )
                        except Exception:
                            logger.exception(
                                "plugin update check: notify_update_available "
                                "failed for %s",
                                row.name,
                            )
                    row.available_update = entry.latest_version
                else:
                    row.available_update = None

        row.last_update_check_at = now

    db.commit()
    return result


def run_plugin_update_check_default(db: Session) -> PluginUpdateCheckResult:
    """Convenience wrapper that builds the default marketplace + core_versions.

    Used by the scheduler worker dispatch — it has no dependency injection
    and just needs a one-liner to call into this service.
    """
    from app.core.config import settings
    from app.plugins.core_versions import load_core_versions
    from app.services.plugin_marketplace import get_marketplace_service

    plugins_dir = Path(settings.plugins_external_dir)
    core_versions = load_core_versions()
    marketplace = get_marketplace_service()
    return run_plugin_update_check(
        db,
        plugins_dir=plugins_dir,
        core_versions=core_versions,
        marketplace=marketplace,
    )
