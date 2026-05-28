"""Hardcoded catalog of status-strip pills.

Each PillDefinition pairs static metadata (visibility rules, click-through
href) with i18n key. Collectors are wired separately in collectors.py.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PillDefinition:
    id: str
    name_key: str                 # i18n key, e.g. "statusBar.pills.power.name"
    default_visibility: str       # "admin" | "all"
    visibility_locked: bool
    silent_when_ok: bool
    href: str


CATALOG: list[PillDefinition] = [
    PillDefinition("power", "statusBar.pills.power.name", "admin", False, False,
                   "/admin/system-control?tab=energy"),
    PillDefinition("pihole", "statusBar.pills.pihole.name", "admin", False, False,
                   "/pihole"),
    PillDefinition("uploads", "statusBar.pills.uploads.name", "all", False, True,
                   "/files"),
    PillDefinition("sync", "statusBar.pills.sync.name", "all", False, True,
                   "/devices"),
    PillDefinition("raid", "statusBar.pills.raid.name", "admin", True, True,
                   "/admin/system-control?tab=raid"),
    PillDefinition("sleep", "statusBar.pills.sleep.name", "admin", True, True,
                   "/admin/system-control?tab=sleep"),
    PillDefinition("vpn", "statusBar.pills.vpn.name", "admin", True, False,
                   "/admin/system-control?tab=vpn"),
    PillDefinition("temp", "statusBar.pills.temp.name", "admin", True, True,
                   "/admin/system-control?tab=fan"),
    PillDefinition("always_awake", "statusBar.pills.alwaysAwake.name", "admin", True, True,
                   "/admin/system-control?tab=sleep"),
    PillDefinition("scheduler", "statusBar.pills.scheduler.name", "admin", True, True,
                   "/admin/schedulers"),
    PillDefinition("backup", "statusBar.pills.backup.name", "admin", True, True,
                   "/admin/system-control?tab=backup"),
]

CATALOG_BY_ID: dict[str, PillDefinition] = {p.id: p for p in CATALOG}
