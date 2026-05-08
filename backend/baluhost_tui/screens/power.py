"""Power Actions screen — sleep / wake / suspend / WoL via /api/system/sleep/*."""
from __future__ import annotations

from typing import Any

import httpx
from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, Horizontal
from textual.widgets import Header, Footer, Button, Label, Static
from textual.binding import Binding

from baluhost_tui.context import get_context


_ACTIONS: dict[str, str] = {
    "soft": "/api/system/sleep/soft",
    "wake": "/api/system/sleep/wake",
    "suspend": "/api/system/sleep/suspend",
    "wol": "/api/system/sleep/wol",
}


def fetch_status(client: httpx.Client) -> dict[str, Any] | None:
    """GET /api/system/sleep/status. Returns parsed dict or None on any failure."""
    try:
        resp = client.get("/api/system/sleep/status")
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def perform_action(client: httpx.Client, action: str) -> tuple[bool, str]:
    """POST a sleep action. Returns (ok, message)."""
    path = _ACTIONS.get(action)
    if path is None:
        return False, f"unknown action: {action}"
    try:
        resp = client.post(path, json={})
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", "")
            except Exception:
                detail = ""
            return False, f"HTTP {resp.status_code}: {detail}".strip()
        return True, resp.json().get("message", "ok")
    except Exception as exc:
        return False, f"request failed: {exc}"


class PowerActionsScreen(Screen):
    """Sleep / Wake / Suspend / WoL — admin only, requires API token."""

    BINDINGS = [
        Binding("q", "back", "Back"),
        Binding("r", "refresh", "Refresh"),
    ]

    CSS = """
    #power-container { padding: 1 2; }
    #power-status { margin-bottom: 1; }
    .power-row { height: auto; margin-bottom: 1; }
    Button { margin: 0 1; }
    """

    def __init__(self, mode: str, server: str, token: str | None) -> None:
        super().__init__()
        self.mode = mode
        self.server = server
        self.token = token

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="power-container"):
            yield Label("⚡ Power Actions", id="power-title")
            yield Static("Loading...", id="power-status")
            with Horizontal(classes="power-row"):
                yield Button("Sleep", id="btn-soft", variant="primary")
                yield Button("Wake", id="btn-wake", variant="success")
                yield Button("Suspend", id="btn-suspend", variant="warning")
                yield Button("WoL", id="btn-wol", variant="default")
        yield Footer()

    def on_mount(self) -> None:
        if not self.token:
            self.query_one("#power-status", Static).update(
                "[red]No API token — admin actions disabled. Login with backend online.[/red]"
            )
            for btn_id in ("btn-soft", "btn-wake", "btn-suspend", "btn-wol"):
                try:
                    self.query_one(f"#{btn_id}", Button).disabled = True
                except Exception:
                    pass
            return
        self.refresh_status()

    def refresh_status(self) -> None:
        with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
            status = fetch_status(ctx.get_api_client())
        if status is None:
            self.query_one("#power-status", Static).update("[red]Failed to load status[/red]")
            return
        state = status.get("current_state", "?")
        since = status.get("state_since", "?")
        always_obj = status.get("always_awake") or {}
        always = bool(always_obj.get("enabled", False)) if isinstance(always_obj, dict) else False
        self.query_one("#power-status", Static).update(
            f"State: [cyan]{state}[/cyan]   Since: {since}   Always-Awake: {'on' if always else 'off'}"
        )

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self.refresh_status()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action_map = {"btn-soft": "soft", "btn-wake": "wake", "btn-suspend": "suspend", "btn-wol": "wol"}
        action = action_map.get(event.button.id or "")
        if not action:
            return
        with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
            ok, msg = perform_action(ctx.get_api_client(), action)
        self.notify(msg, severity="information" if ok else "error")
        if ok:
            self.refresh_status()
