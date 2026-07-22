"""Hardcoded catalog of status-strip pills.

Each PillDefinition pairs static metadata (visibility rules, click-through
href) with i18n key. Collectors are wired separately in collectors.py.
"""
from dataclasses import dataclass
from typing import Optional

from app.schemas.status_bar import PillId


@dataclass(frozen=True)
class PillDefinition:
    id: PillId
    name_key: str                 # i18n key, e.g. "statusBar.pills.power.name"
    default_visibility: str       # "admin" | "all"
    visibility_locked: bool
    silent_when_ok: bool
    href: str
    icon: str                     # lucide icon name; must match the collector's emitted icon
    display_mode_configurable: bool = False  # only True for pills with an admin-chosen display mode
    # Set for plugin-contributed pills only:
    plugin_name: Optional[str] = None
    name_text: Optional[str] = None
    translations: Optional[dict] = None


CATALOG: list[PillDefinition] = [
    PillDefinition("power", "statusBar.pills.power.name", "admin", False, False,
                   "/admin/system-control?tab=energy", "Zap"),
    PillDefinition("pihole", "statusBar.pills.pihole.name", "admin", False, False,
                   "/pihole", "Shield"),
    PillDefinition("uploads", "statusBar.pills.uploads.name", "all", False, True,
                   "/files", "Upload"),
    PillDefinition("sync", "statusBar.pills.sync.name", "all", False, True,
                   "/devices", "RefreshCw"),
    PillDefinition("raid", "statusBar.pills.raid.name", "admin", True, True,
                   "/admin/system-control?tab=raid", "HardDrive"),
    PillDefinition("sleep", "statusBar.pills.sleep.name", "admin", True, True,
                   "/admin/system-control?tab=sleep", "Moon"),
    PillDefinition("vpn", "statusBar.pills.vpn.name", "admin", True, False,
                   "/admin/system-control?tab=vpn", "Lock"),
    PillDefinition("temp", "statusBar.pills.temp.name", "admin", True, True,
                   "/admin/system-control?tab=fan", "Thermometer"),
    PillDefinition("always_awake", "statusBar.pills.alwaysAwake.name", "admin", True, True,
                   "/admin/system-control?tab=sleep", "Coffee"),
    PillDefinition("scheduler", "statusBar.pills.scheduler.name", "admin", True, True,
                   "/schedulers", "Clock"),
    PillDefinition("backup", "statusBar.pills.backup.name", "admin", True, True,
                   "/admin/system-control?tab=backup", "Save"),
    PillDefinition("desktop", "statusBar.pills.desktop.name", "admin", False, False,
                   "/admin/system-control?tab=sleep", "Monitor", display_mode_configurable=True),
]

CATALOG_BY_ID: dict[str, PillDefinition] = {p.id: p for p in CATALOG}
