"""Service Health & Restart screen — /api/admin/services + /restart."""
from __future__ import annotations

from typing import Any

import httpx
from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container
from textual.widgets import Header, Footer, Label, DataTable
from textual.binding import Binding

from baluhost_tui.context import get_context


def fetch_services(client: httpx.Client) -> list[dict[str, Any]]:
    """GET /api/admin/services. Returns [] on any failure."""
    try:
        resp = client.get("/api/admin/services")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


def restart_service(client: httpx.Client, name: str) -> tuple[bool, str]:
    """POST /api/admin/services/{name}/restart. Returns (ok, message)."""
    try:
        resp = client.post(f"/api/admin/services/{name}/restart")
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", "")
            except Exception:
                detail = ""
            return False, f"HTTP {resp.status_code}: {detail}".strip()
        body = resp.json()
        return bool(body.get("success", True)), body.get("message", "restarted")
    except Exception as exc:
        return False, f"request failed: {exc}"


class ServiceHealthScreen(Screen):
    """List services with state + uptime; press Enter to restart."""

    BINDINGS = [
        Binding("q", "back", "Back"),
        Binding("r", "refresh", "Refresh"),
    ]

    CSS = """
    #services-container { padding: 1 2; }
    #services-title { text-style: bold; color: $accent; margin-bottom: 1; }
    """

    def __init__(self, mode: str, server: str, token: str | None) -> None:
        super().__init__()
        self.mode = mode
        self.server = server
        self.token = token

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="services-container"):
            yield Label("\U0001f6e0️  Services (Enter = restart)", id="services-title")
            yield DataTable(id="services-table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#services-table", DataTable)
        table.add_columns("Name", "State", "Uptime (s)", "Errors")
        table.cursor_type = "row"
        if not self.token:
            self.notify("No API token — service actions unavailable", severity="warning")
            return
        self.load_services()

    def load_services(self) -> None:
        table = self.query_one("#services-table", DataTable)
        table.clear()
        with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
            services = fetch_services(ctx.get_api_client())
        if not services:
            table.add_row("(none)", "-", "-", "-", key="__empty__")
            return
        for svc in services:
            name = svc.get("name", "?")
            state = svc.get("state", "?")
            uptime = svc.get("uptime_seconds")
            uptime_str = "-" if uptime is None else str(int(uptime))
            errors = svc.get("error_count", 0)
            table.add_row(name, state, uptime_str, str(errors), key=name)

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self.load_services()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if not self.token:
            self.notify("No API token", severity="error")
            return
        key = event.row_key
        name = key.value if hasattr(key, "value") else str(key)
        if name is None or name in ("__empty__", ""):
            return
        with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
            ok, msg = restart_service(ctx.get_api_client(), name)
        self.notify(f"{name}: {msg}", severity="information" if ok else "error")
        if ok:
            self.load_services()
