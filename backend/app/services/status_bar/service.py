"""Aggregator + config service for the topbar status strip."""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.status_bar import StatusBarPillConfig, StatusBarSettings
from app.schemas.status_bar import (
    PillCatalogEntry,
    PillState,
    StatusBarConfigResponse,
    StatusBarConfigUpdate,
    StatusBarStateResponse,
)
from app.services.status_bar.catalog import CATALOG, CATALOG_BY_ID
from app.services.status_bar.collectors import COLLECTORS

logger = logging.getLogger(__name__)


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

    # ── pill config rows (seed-on-read) ─────────────────────────────
    def _ensure_rows(self) -> dict[str, StatusBarPillConfig]:
        existing = {r.pill_id: r for r in self.db.query(StatusBarPillConfig).all()}
        created = False
        for idx, definition in enumerate(CATALOG):
            if definition.id not in existing:
                row = StatusBarPillConfig(
                    pill_id=definition.id,
                    enabled=False,
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
        rows = self._ensure_rows()
        settings = self._get_settings()
        entries = []
        for definition in sorted(CATALOG, key=lambda d: rows[d.id].sort_order):
            row = rows[definition.id]
            entries.append(PillCatalogEntry(
                pill_id=definition.id,
                name_key=definition.name_key,
                enabled=row.enabled,
                visibility=row.visibility,
                visibility_locked=definition.visibility_locked,
                sort_order=row.sort_order,
                href=definition.href,
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

        rows = self._ensure_rows()
        diff: dict = {"changed": []}
        for item in update.pills:
            row = rows.get(item.pill_id)
            if row is None:
                continue
            before = (row.enabled, row.visibility, row.sort_order)
            row.enabled = item.enabled
            row.visibility = item.visibility
            row.sort_order = item.sort_order
            after = (row.enabled, row.visibility, row.sort_order)
            if before != after:
                diff["changed"].append({
                    "pill_id": item.pill_id,
                    "before": {"enabled": before[0], "visibility": before[1], "sort_order": before[2]},
                    "after": {"enabled": after[0], "visibility": after[1], "sort_order": after[2]},
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
        rows = self._ensure_rows()
        settings = self._get_settings()
        is_admin = role == "admin"

        enabled = [
            (CATALOG_BY_ID[r.pill_id], r)
            for r in rows.values()
            if r.enabled and r.pill_id in CATALOG_BY_ID
        ]
        # Role filter: non-admins only see pills whose visibility == "all".
        visible = [
            (d, r) for (d, r) in enabled
            if is_admin or r.visibility == "all"
        ]
        visible.sort(key=lambda pair: pair[1].sort_order)

        pills: list[PillState] = []
        for definition, _row in visible:
            collector = COLLECTORS.get(definition.id)
            if collector is None:
                continue
            partial = await collector(self.db, role)
            if partial is None:
                continue
            pills.append(PillState(id=definition.id, href=definition.href, **partial))

        return StatusBarStateResponse(pills=pills, show_bottom_upload=settings.show_bottom_upload)
