"""Pydantic schemas for the topbar status strip."""
from typing import Literal, Optional

from pydantic import BaseModel

# Hardcoded to the current catalog. Kept in sync with CATALOG via
# test_pill_id_literal_matches_catalog (see catalog tests).
PILL_IDS = Literal[
    "power", "pihole", "uploads", "sync", "raid", "sleep", "vpn", "temp",
    "always_awake", "scheduler", "backup", "desktop",
]

PillVisibility = Literal["admin", "all"]
PillKind = Literal["state", "activity", "alert"]
PillTone = Literal["success", "info", "warning", "danger", "neutral"]


class PillConfigItem(BaseModel):
    pill_id: PILL_IDS
    enabled: bool
    visibility: PillVisibility
    sort_order: int


class StatusBarConfigUpdate(BaseModel):
    pills: list[PillConfigItem]
    show_bottom_upload: bool


class PillCatalogEntry(BaseModel):
    """One catalog pill plus its persisted config — for the admin config GET."""
    pill_id: PILL_IDS
    name_key: str
    enabled: bool
    visibility: PillVisibility
    visibility_locked: bool
    sort_order: int
    href: str


class StatusBarConfigResponse(BaseModel):
    pills: list[PillCatalogEntry]
    show_bottom_upload: bool


class PillState(BaseModel):
    """A rendered pill for the /state payload."""
    id: PILL_IDS
    kind: PillKind
    tone: PillTone
    label: str
    value: Optional[str] = None
    icon: Optional[str] = None
    href: str
    extra: Optional[dict] = None


class StatusBarStateResponse(BaseModel):
    pills: list[PillState]
    show_bottom_upload: bool
