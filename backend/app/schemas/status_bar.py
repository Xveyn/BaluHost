"""Pydantic schemas for the topbar status strip."""
import re
from typing import Annotated, Literal, Optional

from pydantic import BaseModel
from pydantic.functional_validators import AfterValidator

# Core pills. Kept in sync with CATALOG via test_core_pill_ids_match_the_catalog.
# Duplicated here rather than imported from the catalog, which imports this
# module — the test is what keeps the two honest.
CORE_PILL_IDS: frozenset[str] = frozenset({
    "power", "pihole", "uploads", "sync", "raid", "sleep", "vpn", "temp",
    "always_awake", "scheduler", "backup", "desktop",
})

# Plugin pills are namespaced by the core as plugin:<plugin_name>:<suffix>, so
# they can never collide with a core id.
_PLUGIN_PILL_RE = re.compile(r"^plugin:[a-z0-9_]+:[a-z0-9_]+$")


def _validate_pill_id(value: str) -> str:
    if value in CORE_PILL_IDS or _PLUGIN_PILL_RE.fullmatch(value):
        return value
    raise ValueError(
        f"unknown pill id {value!r}: expected a core pill or plugin:<name>:<suffix>"
    )


PillId = Annotated[str, AfterValidator(_validate_pill_id)]

PillVisibility = Literal["admin", "all"]
PillKind = Literal["state", "activity", "alert"]
PillTone = Literal["success", "info", "warning", "danger", "neutral"]
DisplayMode = Literal["always", "when_off", "when_on"]


class PillConfigItem(BaseModel):
    pill_id: PillId
    enabled: bool
    visibility: PillVisibility
    sort_order: int
    display_mode: DisplayMode = "always"


class StatusBarConfigUpdate(BaseModel):
    pills: list[PillConfigItem]
    show_bottom_upload: bool


class PillCatalogEntry(BaseModel):
    """One catalog pill plus its persisted config — for the admin config GET."""
    pill_id: PillId
    name_key: str
    enabled: bool
    visibility: PillVisibility
    visibility_locked: bool
    sort_order: int
    href: str
    icon: str
    display_mode: DisplayMode
    display_mode_configurable: bool
    name_text: Optional[str] = None       # literal fallback for plugin pills
    translations: Optional[dict] = None   # plugin translations, resolved client-side


class StatusBarConfigResponse(BaseModel):
    pills: list[PillCatalogEntry]
    show_bottom_upload: bool


class PillState(BaseModel):
    """A rendered pill for the /state payload."""
    id: PillId
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
    label_text: Optional[str] = None      # literal fallback for plugin pills
    translations: Optional[dict] = None   # plugin translations, resolved client-side


class StatusBarStateResponse(BaseModel):
    pills: list[PillState]
    show_bottom_upload: bool
