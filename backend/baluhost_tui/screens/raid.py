"""RAID control screen with safe two-step confirmation flow."""
import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, DataTable, Label
from textual.binding import Binding
from textual.containers import Container
from rich.text import Text

from baluhost_tui.context import get_context


class RaidControlScreen(Screen):
    BINDINGS = [
        Binding("q", "back", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("d", "request_delete", "Request Delete"),
        Binding("e", "execute_token", "Execute Token"),
    ]

    def __init__(self):
        super().__init__()
        self.last_token: str | None = None
        self.last_expires: int | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="raid-container"):
            yield Label("🛡️ RAID Controls", id="raid-title")
            yield DataTable(id="raid-table")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#raid-table", DataTable)
        table.add_columns("Name", "Level", "Status", "Devices")
        table.cursor_type = "row"
        self.load_status()

    def load_status(self) -> None:
        table = self.query_one("#raid-table", DataTable)
        table.clear()
        try:
            with get_context() as ctx:
                if ctx.is_remote:
                    client = ctx.get_api_client()
                    res = client.get("/api/system/raid/status")
                    res.raise_for_status()
                    data = res.json()
                    arrays = data.get("arrays", [])
                else:
                    # local import
                    from app.services import raid as raid_service
                    st = raid_service.get_status()
                    arrays = [a.__dict__ for a in st.arrays]

            for a in arrays:
                devices = ",".join([d.get("name") or d.name for d in (a.get("devices") if isinstance(a, dict) else a.devices)])
                name = a.get("name") if isinstance(a, dict) else a.name
                level = a.get("level") if isinstance(a, dict) else a.level
                status = a.get("status") if isinstance(a, dict) else a.status
                table.add_row(name, level, status, devices, key=name)
        except Exception as exc:
            self.notify(f"Failed to load RAID status: {exc}", severity="error")

    def action_refresh(self) -> None:
        self.load_status()

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_request_delete(self) -> None:
        table = self.query_one("#raid-table", DataTable)
        if not table.cursor_row:
            self.notify("Select an array first", severity="warning")
            return
        array = table.row_keys[table.cursor_row]
        try:
            with get_context() as ctx:
                if ctx.is_remote:
                    client = ctx.get_api_client()
                    payload = {"action": "delete_array", "payload": {"array": array}}
                    res = client.post("/api/system/raid/confirm/request", json=payload)
                    res.raise_for_status()
                    data = res.json()
                    token = data.get("token")
                    expires = data.get("expires_at")
                else:
                    from app.services.raid import request_confirmation
                    data = request_confirmation("delete_array", {"array": array})
                    token = data["token"]
                    expires = data["expires_at"]

            self.last_token = token
            self.last_expires = expires
            self.notify(Text(f"Confirmation token: {token}\nExpires: {time.ctime(expires)}"), severity="information")
        except Exception as exc:
            self.notify(f"Failed to request confirmation: {exc}", severity="error")

    def action_execute_token(self) -> None:
        if not self.last_token:
            self.notify("No token available. Request one first.", severity="warning")
            return
        try:
            with get_context() as ctx:
                if ctx.is_remote:
                    client = ctx.get_api_client()
                    res = client.post("/api/system/raid/confirm/execute", json={"token": self.last_token})
                    res.raise_for_status()
                    data = res.json()
                else:
                    from app.services.raid import execute_confirmation
                    data = execute_confirmation(self.last_token)

            self.notify(f"Execute result: {data}", severity="information")
            self.last_token = None
            self.load_status()
        except Exception as exc:
            self.notify(f"Failed to execute token: {exc}", severity="error")
