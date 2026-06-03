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
DisplayMode = Literal["always", "when_off", "when_on"]


class PillConfigItem(BaseModel):
    pill_id: PILL_IDS
    enabled: bool
    visibility: PillVisibility
    sort_order: int
    display_mode: DisplayMode = "always"


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
    display_mode: DisplayMode
    display_mode_configurable: bool


class StatusBarConfigResponse(BaseModel):
    pills: list[PillCatalogEntry]
    show_bottom_upload: bool


class PillState(BaseModel):
    """A rendered pill for the /state payload."""
    id: PILL_IDS
    kind: PillKind
    tone: PillTone
    label_key: str                        # i18n key for the short live label, e.g. "pills.vpn.live"
    label_params: Optional[dict] = None   # interpolation params for label_key (only `power` uses it)
    value: Optional[str] = None           # pure-data value ("72°C", "14:30", "3") AND defaultValue fallback
    value_key: Optional[str] = None       # i18n key for a translatable value, e.g. "pills.vpn.connected"
    value_params: Optional[dict] = None   # interpolation params for value_key, e.g. {"n": 1}
    icon: Optional[str] = None
    href: str
    extra: Optional[dict] = None


class StatusBarStateResponse(BaseModel):
    pills: list[PillState]
    show_bottom_upload: bool
