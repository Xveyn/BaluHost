"""Aggregator + config service for the topbar status strip."""
import asyncio
import logging
from typing import Optional, cast

from sqlalchemy.orm import Session

from app.models.status_bar import StatusBarPillConfig, StatusBarSettings
from app.plugins.base import PluginBase
from app.schemas.status_bar import (
    DisplayMode,
    PillCatalogEntry,
    PillState,
    PillVisibility,
    StatusBarConfigResponse,
    StatusBarConfigUpdate,
    StatusBarStateResponse,
)
from app.services.status_bar.catalog import CATALOG, CATALOG_BY_ID, PillDefinition
from app.services.status_bar.collectors import COLLECTORS

logger = logging.getLogger(__name__)

# A plugin collector that never returns must not stall the whole strip.
PLUGIN_COLLECTOR_TIMEOUT_SECONDS = 2.0


def iter_enabled_plugins() -> list[tuple[str, PluginBase]]:
    """Enabled plugins, or an empty list when the plugin system is unavailable.

    Module-level so tests can patch it.
    """
    try:
        from app.plugins.manager import PluginManager

        return list(PluginManager.get_instance().iter_enabled_plugins())
    except Exception:  # noqa: BLE001 - the strip works without plugins
        logger.debug("plugin pills unavailable", exc_info=True)
        return []


class StatusBarService:
    def __init__(self, db: Session):
        self.db = db

    # ── settings singleton ──────────────────────────────────────────
    def _get_settings(self) -> StatusBarSettings:
        row = self.db.query(StatusBarSettings).filter(StatusBarSettings.id == 1).first()
        if row is None:
            row = StatusBarSettings(id=1, show_bottom_upload=True)
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
        return row

    # ── plugin pill merging ──────────────────────────────────────────
    def _effective_catalog(self) -> list[PillDefinition]:
        """Core catalog plus the pills of every enabled plugin."""
        pills = list(CATALOG)
        for plugin_name, plugin in iter_enabled_plugins():
            try:
                specs = plugin.get_status_pills()
            except Exception:  # noqa: BLE001 - one bad plugin must not hide the rest
                logger.warning("plugin %s failed to declare pills", plugin_name, exc_info=True)
                continue
            try:
                # get_translations() is a PluginBase default (returns None); guard
                # anyway so a minimal/duck-typed plugin without it still gets pills.
                translations = plugin.get_translations() or None
            except Exception:  # noqa: BLE001 - translations are optional, pills are not
                translations = None
            for spec in specs:
                pills.append(PillDefinition(
                    id=f"plugin:{plugin_name}:{spec.id}",
                    name_key=spec.name_key,
                    default_visibility=spec.default_visibility,
                    visibility_locked=spec.visibility_locked,
                    silent_when_ok=spec.silent_when_ok,
                    href=spec.href,
                    icon=spec.icon,
                    plugin_name=plugin_name,
                    name_text=spec.name_text,
                    translations=translations,
                ))
        return pills

    def _plugin_for(self, definition: PillDefinition) -> Optional[PluginBase]:
        for name, plugin in iter_enabled_plugins():
            if name == definition.plugin_name:
                return plugin
        return None

    # ── pill config rows (seed-on-read) ─────────────────────────────
    def _ensure_rows(self, catalog: list[PillDefinition]) -> dict[str, StatusBarPillConfig]:
        existing = {r.pill_id: r for r in self.db.query(StatusBarPillConfig).all()}
        created = False
        for idx, definition in enumerate(catalog):
            if definition.id not in existing:
                row = StatusBarPillConfig(
                    pill_id=definition.id,
                    # Core pills start hidden and are opted into by the admin.
                    # A plugin pill is the whole point of installing the plugin,
                    # so it starts visible (see design doc).
                    enabled=definition.plugin_name is not None,
                    visibility=definition.default_visibility,
                    sort_order=idx,
                )
                self.db.add(row)
                existing[definition.id] = row
                created = True
        if created:
            self.db.commit()
        return existing

    def get_config(self) -> StatusBarConfigResponse:
        catalog = self._effective_catalog()
        rows = self._ensure_rows(catalog)
        settings = self._get_settings()
        entries = []
        for definition in sorted(catalog, key=lambda d: rows[d.id].sort_order):
            row = rows[definition.id]
            entries.append(PillCatalogEntry(
                pill_id=definition.id,
                name_key=definition.name_key,
                enabled=row.enabled,
                visibility=cast(PillVisibility, row.visibility),
                visibility_locked=definition.visibility_locked,
                sort_order=row.sort_order,
                href=definition.href,
                icon=definition.icon,
                display_mode=cast(DisplayMode, getattr(row, "display_mode", "always")),
                display_mode_configurable=definition.display_mode_configurable,
                name_text=definition.name_text,
                translations=definition.translations,
            ))
        return StatusBarConfigResponse(pills=entries, show_bottom_upload=settings.show_bottom_upload)

    def update_config(self, update: StatusBarConfigUpdate) -> dict:
        """Apply config. Returns a diff dict for audit logging.

        Raises ValueError if a visibility_locked pill is set to visibility='all'.
        """
        # Validate locked-visibility first (reject the whole update atomically).
        for item in update.pills:
            definition = CATALOG_BY_ID.get(item.pill_id)
            if definition and definition.visibility_locked and item.visibility == "all":
                raise ValueError(
                    f"pill '{item.pill_id}' is visibility_locked and cannot be set to 'all'"
                )
            if (definition and not definition.display_mode_configurable
                    and item.display_mode != "always"):
                raise ValueError(
                    f"pill '{item.pill_id}' does not support a custom display_mode"
                )

        catalog = self._effective_catalog()
        rows = self._ensure_rows(catalog)
        diff: dict = {"changed": []}
        for item in update.pills:
            row = rows.get(item.pill_id)
            if row is None:
                continue
            before = (row.enabled, row.visibility, row.sort_order, getattr(row, "display_mode", "always"))
            row.enabled = item.enabled
            row.visibility = item.visibility
            row.sort_order = item.sort_order
            row.display_mode = item.display_mode
            after = (row.enabled, row.visibility, row.sort_order, row.display_mode)
            if before != after:
                diff["changed"].append({
                    "pill_id": item.pill_id,
                    "before": {"enabled": before[0], "visibility": before[1], "sort_order": before[2], "display_mode": before[3]},
                    "after": {"enabled": after[0], "visibility": after[1], "sort_order": after[2], "display_mode": after[3]},
                })

        settings = self._get_settings()
        if settings.show_bottom_upload != update.show_bottom_upload:
            diff["show_bottom_upload"] = {
                "before": settings.show_bottom_upload, "after": update.show_bottom_upload
            }
            settings.show_bottom_upload = update.show_bottom_upload

        self.db.commit()
        return diff

    async def collect_state(self, role: str) -> StatusBarStateResponse:
        catalog = self._effective_catalog()
        by_id = {d.id: d for d in catalog}
        rows = self._ensure_rows(catalog)
        settings = self._get_settings()
        is_admin = role == "admin"

        enabled = [
            (by_id[r.pill_id], r)
            for r in rows.values()
            if r.enabled and r.pill_id in by_id
        ]
        # Role filter: non-admins only see pills whose visibility == "all".
        visible = [
            (d, r) for (d, r) in enabled
            if is_admin or r.visibility == "all"
        ]
        visible.sort(key=lambda pair: pair[1].sort_order)

        pills: list[PillState] = []
        for definition, _row in visible:
            if definition.plugin_name is not None:
                partial = await self._collect_plugin_pill(definition)
            else:
                collector = COLLECTORS.get(definition.id)
                if collector is None:
                    continue
                partial = await collector(self.db, role)
            if partial is None:
                continue
            if definition.display_mode_configurable:
                state = partial.pop("_state", None)
                mode = getattr(_row, "display_mode", "always")
                if (mode == "when_off" and state != "stopped") or \
                   (mode == "when_on" and state != "running"):
                    continue
            try:
                pills.append(PillState(
                    id=definition.id,
                    href=definition.href,
                    translations=definition.translations,
                    **partial,
                ))
            except Exception as exc:  # noqa: BLE001 - one bad pill must not 5xx the strip
                logger.warning("status bar pill %s produced invalid output: %s", definition.id, exc)
                continue

        return StatusBarStateResponse(pills=pills, show_bottom_upload=settings.show_bottom_upload)

    async def _collect_plugin_pill(self, definition: PillDefinition) -> Optional[dict]:
        """Run a plugin collector under a timeout; never raise."""
        plugin = self._plugin_for(definition)
        if plugin is None:
            return None
        suffix = definition.id.split(":", 2)[2]
        try:
            return await asyncio.wait_for(
                plugin.collect_status_pill(suffix, self.db),
                timeout=PLUGIN_COLLECTOR_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("plugin pill %s timed out", definition.id)
        except Exception:  # noqa: BLE001 - one bad pill must not 5xx the strip
            logger.warning("plugin pill %s failed", definition.id, exc_info=True)
        return None
