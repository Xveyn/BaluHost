"""RAID control screen — status + local-channel array deletion."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container
from textual.widgets import Header, Footer, DataTable, Label
from textual.binding import Binding

from baluhost_tui.api import system as system_api
from baluhost_tui.widgets.confirm import ConfirmDialog


class RaidControlScreen(Screen):
    """List RAID arrays; press 'd' to delete the selected array (local channel)."""

    BINDINGS = [
        Binding("q", "back", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("d", "delete_array", "Delete Array"),
    ]

    CSS = """
    #raid-container { padding: 1 2; }
    #raid-title { text-style: bold; color: $accent; margin-bottom: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="raid-container"):
            yield Label("🛡️  RAID Controls (d = delete array)", id="raid-title")
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
        arrays = system_api.raid_status(self.app.client)
        if not arrays:
            table.add_row("(none)", "-", "-", "-", key="__empty__")
            return
        for a in arrays:
            devices = ", ".join(d.get("name", "?") for d in a.get("devices", []))
            name = str(a.get("name", "?"))
            table.add_row(
                name,
                str(a.get("level", "?")),
                str(a.get("status", "?")),
                devices,
                key=name,
            )

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        self.load_status()

    def action_delete_array(self) -> None:
        table = self.query_one("#raid-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            self.notify("Select an array first", severity="warning")
            return
        try:
            row = table.get_row_at(table.cursor_row)
            array = str(row[0])
        except Exception:
            self.notify("Select an array first", severity="warning")
            return
        if array in ("(none)", "", "__empty__"):
            self.notify("No array selected", severity="warning")
            return

        def _cb(confirmed):
            if not confirmed:
                return
            ok, msg = system_api.delete_array(self.app.client, array)
            self.notify(f"{array}: {msg}", severity="information" if ok else "error")
            if ok:
                self.load_status()

        self.app.push_screen(
            ConfirmDialog(
                title="⚠️  Delete RAID Array",
                message=f"This permanently destroys array '{array}'. This cannot be undone.",
                confirm_label="Delete Array",
                require_text=array,
            ),
            _cb,
        )
