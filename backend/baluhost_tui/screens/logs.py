"""Audit Log Viewer screen for BaluHost TUI (over the BackendClient)."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen, ModalScreen
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Header, Footer, Static, Label, DataTable, Button, Input
from textual.binding import Binding
from rich.text import Text

from baluhost_tui.api import logging as logging_api


class LogDetailDialog(ModalScreen):
    """Modal dialog for viewing log details."""
    
    CSS = """
    LogDetailDialog {
        align: center middle;
    }
    
    #dialog-container {
        width: 80;
        height: 30;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    
    #detail-content {
        height: 1fr;
        overflow-y: auto;
    }
    
    .button-row {
        height: auto;
        margin-top: 1;
        align: center middle;
    }
    """
    
    BINDINGS = [
        Binding("escape", "close", "Close"),
    ]
    
    def __init__(self, log_data: dict):
        super().__init__()
        self.log_data = log_data
    
    def compose(self) -> ComposeResult:
        """Compose the dialog."""
        with Container(id="dialog-container"):
            yield Label("📝 Audit Log Details", id="dialog-title")
            
            with VerticalScroll(id="detail-content"):
                lines = [
                    f"[cyan]ID:[/cyan] {self.log_data.get('id', 'N/A')}",
                    f"[cyan]Timestamp:[/cyan] {self.log_data.get('timestamp', 'N/A')}",
                    f"[cyan]User:[/cyan] {self.log_data.get('user', 'system')}",
                    f"[cyan]Action:[/cyan] {self.log_data.get('action', 'N/A')}",
                    f"[cyan]Resource:[/cyan] {self.log_data.get('resource', 'N/A')}",
                    f"[cyan]IP Address:[/cyan] {self.log_data.get('ip_address', 'N/A')}",
                    f"[cyan]User Agent:[/cyan] {self.log_data.get('user_agent', 'N/A')}",
                    "",
                ]
                
                # Success status with color
                success = self.log_data.get('success', False)
                status_color = "green" if success else "red"
                status_text = "✓ Success" if success else "✗ Failed"
                lines.append(f"[cyan]Status:[/cyan] [{status_color}]{status_text}[/{status_color}]")
                lines.append("")
                
                # Details JSON
                if self.log_data.get('details'):
                    lines.append("[cyan]Details:[/cyan]")
                    lines.append("")
                    import json
                    try:
                        details_str = json.dumps(self.log_data['details'], indent=2)
                        lines.append(details_str)
                    except:
                        lines.append(str(self.log_data['details']))
                
                yield Static("\n".join(lines))
            
            with Horizontal(classes="button-row"):
                yield Button("Close", variant="primary", id="btn-close")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "btn-close":
            self.dismiss()
    
    def action_close(self) -> None:
        """Close dialog."""
        self.dismiss()


class SearchDialog(ModalScreen):
    """Modal dialog for searching logs."""
    
    CSS = """
    SearchDialog {
        align: center middle;
    }
    
    #dialog-container {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    
    .form-row {
        height: auto;
        margin-bottom: 1;
    }
    
    .form-label {
        width: 12;
        content-align: left middle;
    }
    
    Input {
        width: 1fr;
    }
    
    .button-row {
        height: auto;
        margin-top: 1;
        align: center middle;
    }
    
    Button {
        margin: 0 1;
    }
    """
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]
    
    def compose(self) -> ComposeResult:
        """Compose the dialog."""
        with Container(id="dialog-container"):
            yield Label("🔍 Search Logs", id="dialog-title")
            
            with Horizontal(classes="form-row"):
                yield Label("Search:", classes="form-label")
                yield Input(placeholder="Enter search term...", id="input-search")
            
            with Horizontal(classes="form-row"):
                yield Label("User:", classes="form-label")
                yield Input(placeholder="Filter by username", id="input-user")
            
            with Horizontal(classes="form-row"):
                yield Label("Action:", classes="form-label")
                yield Input(placeholder="Filter by action", id="input-action")
            
            with Horizontal(classes="button-row"):
                yield Button("Search", variant="primary", id="btn-search")
                yield Button("Clear", variant="default", id="btn-clear")
                yield Button("Cancel", variant="default", id="btn-cancel")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-clear":
            self.dismiss({"clear": True})
        elif event.button.id == "btn-search":
            search_term = self.query_one("#input-search", Input).value
            user_filter = self.query_one("#input-user", Input).value
            action_filter = self.query_one("#input-action", Input).value
            
            self.dismiss({
                "search": search_term,
                "user": user_filter,
                "action": action_filter
            })
    
    def action_cancel(self) -> None:
        """Cancel and close dialog."""
        self.dismiss(None)


class AuditLogViewerScreen(Screen):
    """Audit log viewer screen with filtering and search."""
    
    CSS = """
    AuditLogViewerScreen {
        background: $surface;
    }
    
    #logs-container {
        width: 100%;
        height: 100%;
        padding: 1 2;
    }
    
    #logs-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    
    #filter-info {
        color: $text-muted;
        margin-bottom: 1;
    }
    
    DataTable {
        height: 1fr;
    }
    """
    
    BINDINGS = [
        Binding("q", "back", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "search", "Search"),
        Binding("v", "view_details", "View Details"),
        Binding("c", "clear_filters", "Clear Filters"),
    ]
    
    def __init__(self):
        super().__init__()
        self.search_filters: dict = {}
        self._logs_by_id: dict[int, dict] = {}
    
    def compose(self) -> ComposeResult:
        """Compose the log viewer layout."""
        yield Header()
        with Container(id="logs-container"):
            yield Label("📝 Audit Log Viewer", id="logs-title")
            yield Label("No filters active", id="filter-info")
            yield DataTable(id="logs-table")
        yield Footer()
    
    def on_mount(self) -> None:
        """Setup table when mounted."""
        table = self.query_one("#logs-table", DataTable)
        table.add_columns("ID", "Time", "User", "Action", "Resource", "Status", "IP")
        table.cursor_type = "row"
        self.load_logs()
        # Auto-refresh every 5 seconds
        self.set_interval(5.0, self.load_logs)
    
    def load_logs(self, limit: int = 100) -> None:
        """Load audit logs from the backend API (server-side user/action filters,
        client-side free-text search)."""
        try:
            table = self.query_one("#logs-table", DataTable)
            table.clear()

            logs = logging_api.query_audit(
                self.app.client,
                limit=limit,
                user=self.search_filters.get("user"),
                action=self.search_filters.get("action"),
                days=365,
            )
            logs = logging_api.filter_logs(logs, self.search_filters.get("search", ""))

            self._logs_by_id = {}
            for log in logs:
                log_id = log.get("id")
                if log_id is not None:
                    self._logs_by_id[int(log_id)] = log

                success = bool(log.get("success"))
                status_color = "green" if success else "red"
                status_text = Text("✓", style=status_color) if success else Text("✗", style=status_color)

                user = log.get("user") or "system"
                user_color = "dim" if user == "system" else "white"
                user_text = Text(user, style=user_color)

                ts = str(log.get("timestamp", ""))
                time_str = ts[11:19] if len(ts) >= 19 else ts

                table.add_row(
                    str(log.get("id", "")),
                    time_str,
                    user_text,
                    str(log.get("action", ""))[:30],
                    (str(log.get("resource") or ""))[:20],
                    status_text,
                    (str(log.get("ip_address") or ""))[:15],
                    key=str(log.get("id", "")),
                )

            if self.search_filters:
                filter_parts = []
                if self.search_filters.get("search"):
                    filter_parts.append(f"Search: {self.search_filters['search']}")
                if self.search_filters.get("user"):
                    filter_parts.append(f"User: {self.search_filters['user']}")
                if self.search_filters.get("action"):
                    filter_parts.append(f"Action: {self.search_filters['action']}")
                self.query_one("#filter-info", Label).update(
                    f"[yellow]Filters active:[/yellow] {' | '.join(filter_parts)}"
                )
            else:
                self.query_one("#filter-info", Label).update("[dim]No filters active[/dim]")
        except Exception as e:
            self.notify(f"Error loading logs: {str(e)}", severity="error")
    
    def action_back(self) -> None:
        """Go back to dashboard."""
        self.app.pop_screen()
    
    def action_refresh(self) -> None:
        """Refresh log list."""
        self.load_logs()
        self.notify("Logs refreshed", severity="information")
    
    def action_search(self) -> None:
        """Open search dialog."""
        def handle_result(filters):
            if filters:
                if filters.get('clear'):
                    self.search_filters = {}
                    self.notify("Filters cleared", severity="information")
                else:
                    self.search_filters = {k: v for k, v in filters.items() if v}
                    self.notify("Filters applied", severity="information")
                self.load_logs()
        
        self.app.push_screen(SearchDialog(), handle_result)
    
    def action_clear_filters(self) -> None:
        """Clear all filters."""
        self.search_filters = {}
        self.load_logs()
        self.notify("Filters cleared", severity="information")
    
    def action_view_details(self) -> None:
        """View details of the selected log (from the last loaded page)."""
        table = self.query_one("#logs-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            self.notify("No log selected", severity="warning")
            return
        try:
            row = table.get_row_at(table.cursor_row)
            log_id = int(row[0])
        except Exception:
            self.notify("No log selected", severity="warning")
            return

        log = self._logs_by_id.get(log_id)
        if not log:
            self.notify("Log details unavailable — refresh and retry", severity="error")
            return

        log_data = {
            "id": log.get("id"),
            "timestamp": str(log.get("timestamp") or "N/A"),
            "user": log.get("user") or "system",
            "action": log.get("action") or "N/A",
            "resource": log.get("resource") or "N/A",
            "ip_address": log.get("ip_address") or "N/A",
            "user_agent": log.get("user_agent") or "N/A",
            "success": bool(log.get("success")),
            "details": log.get("details"),
        }
        self.app.push_screen(LogDetailDialog(log_data))
