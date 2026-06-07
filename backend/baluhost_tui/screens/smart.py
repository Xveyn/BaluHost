"""SMART / Disk-Health screen — /api/system/smart/status."""
from __future__ import annotations

from typing import Any

from rich.markup import escape
import httpx
from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container
from textual.widgets import Header, Footer, Label, DataTable
from textual.binding import Binding


def fetch_smart(client: httpx.Client) -> list[dict[str, Any]]:
    """GET /api/system/smart/status. Accepts {devices: [...]} or [...]. Returns [] on failure."""
    try:
        resp = client.get("/api/system/smart/status")
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            devices = data.get("devices")
            return devices if isinstance(devices, list) else []
        return []
    except Exception:
        return []


def _health_color(health: str) -> str:
    h = (health or "").upper()
    if h in ("PASSED", "OK", "PASS"):
        return "green"
    if h in ("FAILED", "FAIL", "ERROR"):
        return "red"
    return "yellow"


def _attribute_raw(device: dict[str, Any], *names: str) -> str:
    """Look up a SMART attribute by its name (case-insensitive substring). Returns the raw value or '-'."""
    attrs = device.get("attributes") or []
    if not isinstance(attrs, list):
        return "-"
    for attr in attrs:
        if not isinstance(attr, dict):
            continue
        attr_name = (attr.get("name") or "").lower()
        for needle in names:
            if needle.lower() in attr_name:
                raw = attr.get("raw")
                if raw is None or raw == "":
                    return "-"
                return str(raw)
    return "-"


class SmartScreen(Screen):
    """Per-disk SMART overview."""

    BINDINGS = [
        Binding("q", "back", "Back"),
        Binding("r", "refresh", "Refresh"),
    ]

    CSS = """
    #smart-container { padding: 1 2; }
    #smart-title { text-style: bold; color: $accent; margin-bottom: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="smart-container"):
            yield Label("💽 SMART / Disk Health", id="smart-title")
            yield DataTable(id="smart-table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#smart-table", DataTable)
        table.add_columns("Device", "Health", "Temp °C", "Power-On h", "Reallocated")
        table.cursor_type = "row"
        if not self.app.token:
            self.notify("No API token — SMART data unavailable", severity="warning")
            return
        self.load_smart()

    def load_smart(self) -> None:
        table = self.query_one("#smart-table", DataTable)
        table.clear()
        disks = fetch_smart(self.app.client)
        if not disks:
            table.add_row("(none)", "-", "-", "-", "-", key="__empty__")
            return
        for i, d in enumerate(disks):
            device = d.get("name") or d.get("device") or "?"
            health = d.get("status") or d.get("health") or "?"
            color = _health_color(str(health))
            temp = d.get("temperature")
            poh = _attribute_raw(d, "power_on_hours", "power-on-hours", "power on hours")
            realloc = _attribute_raw(d, "reallocated_sector", "reallocated_sectors")
            table.add_row(
                device,
                f"[{color}]{escape(str(health))}[/{color}]",
                "-" if temp is None else str(temp),
                poh,
                realloc,
                key=f"{device}-{i}",
            )

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self.load_smart()
