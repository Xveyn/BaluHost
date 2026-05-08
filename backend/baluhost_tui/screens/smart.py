"""SMART / Disk-Health screen — /api/system/smart."""
from __future__ import annotations

from typing import Any

from rich.markup import escape
import httpx
from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container
from textual.widgets import Header, Footer, Label, DataTable
from textual.binding import Binding

from baluhost_tui.context import get_context


def fetch_smart(client: httpx.Client) -> list[dict[str, Any]]:
    """GET /api/system/smart. Accepts either {disks: [...]} or [...]. Returns [] on failure."""
    try:
        resp = client.get("/api/system/smart")
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            disks = data.get("disks")
            return disks if isinstance(disks, list) else []
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

    def __init__(self, mode: str, server: str, token: str | None) -> None:
        super().__init__()
        self.mode = mode
        self.server = server
        self.token = token

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
        if not self.token:
            self.notify("No API token — SMART data unavailable", severity="warning")
            return
        self.load_smart()

    def load_smart(self) -> None:
        table = self.query_one("#smart-table", DataTable)
        table.clear()
        with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
            disks = fetch_smart(ctx.get_api_client())
        if not disks:
            table.add_row("(none)", "-", "-", "-", "-", key="__empty__")
            return
        for i, d in enumerate(disks):
            device = d.get("device") or d.get("name") or "?"
            health = d.get("health") or d.get("smart_status") or "?"
            color = _health_color(str(health))
            temp = d.get("temperature")
            poh = d.get("power_on_hours")
            realloc = d.get("reallocated_sectors", "-")
            table.add_row(
                device,
                f"[{color}]{escape(str(health))}[/{color}]",
                "-" if temp is None else str(temp),
                "-" if poh is None else str(poh),
                str(realloc),
                key=f"{device}-{i}",
            )

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self.load_smart()
