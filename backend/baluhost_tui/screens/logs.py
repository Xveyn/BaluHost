"""Audit Log Viewer screen for BaluHost TUI."""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from textual.app import ComposeResult
from textual.screen import Screen, ModalScreen
from textual.containers import Container, Vertical, Horizontal, VerticalScroll
from textual.widgets import Header, Footer, Static, Label, DataTable, Button, Input
from textual.binding import Binding
from rich.text import Text
from rich.json import JSON

from app.services.audit_logger_db import get_audit_logger_db
from app.models.audit_log import AuditLog
from app.core.database import SessionLocal


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
        self.search_filters = {}
    
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
        """Load audit logs from database."""
        try:
            table = self.query_one("#logs-table", DataTable)
            table.clear()
            
            db = SessionLocal()
            try:
                # Build query
                query = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
                
                # Apply filters
                if self.search_filters.get('user'):
                    query = query.filter(AuditLog.user.contains(self.search_filters['user']))
                
                if self.search_filters.get('action'):
                    query = query.filter(AuditLog.action.contains(self.search_filters['action']))
                
                if self.search_filters.get('search'):
                    search_term = self.search_filters['search']
                    query = query.filter(
                        (AuditLog.action.contains(search_term)) |
                        (AuditLog.resource.contains(search_term)) |
                        (AuditLog.user.contains(search_term))
                    )
                
                logs = query.limit(limit).all()
                
                for log in logs:
                    # Success status with color
                    status_color = "green" if log.success else "red"
                    status_text = Text("✓", style=status_color) if log.success else Text("✗", style=status_color)
                    
                    # User with color (system in gray)
                    user = log.user or "system"
                    user_color = "dim" if user == "system" else "white"
                    user_text = Text(user, style=user_color)
                    
                    # Timestamp formatting
                    time_str = log.timestamp.strftime("%H:%M:%S") if log.timestamp else "N/A"
                    
                    table.add_row(
                        str(log.id),
                        time_str,
                        user_text,
                        log.action[:30],  # Truncate long actions
                        log.resource[:20] if log.resource else "",
                        status_text,
                        log.ip_address[:15] if log.ip_address else "",
                        key=str(log.id)
                    )
                
                # Update filter info
                if self.search_filters:
                    filter_parts = []
                    if self.search_filters.get('search'):
                        filter_parts.append(f"Search: {self.search_filters['search']}")
                    if self.search_filters.get('user'):
                        filter_parts.append(f"User: {self.search_filters['user']}")
                    if self.search_filters.get('action'):
                        filter_parts.append(f"Action: {self.search_filters['action']}")
                    
                    filter_text = " | ".join(filter_parts)
                    self.query_one("#filter-info", Label).update(f"[yellow]Filters active:[/yellow] {filter_text}")
                else:
                    self.query_one("#filter-info", Label).update("[dim]No filters active[/dim]")
                
            finally:
                db.close()
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
        """View details of selected log."""
        table = self.query_one("#logs-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            self.notify("No log selected", severity="warning")
            return
        
        try:
            row = table.get_row_at(table.cursor_row)
            log_id = int(row[0])
            
            db = SessionLocal()
            try:
                log = db.query(AuditLog).filter(AuditLog.id == log_id).first()
                if not log:
                    self.notify("Log not found", severity="error")
                    return
                
                log_data = {
                    "id": log.id,
                    "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S") if log.timestamp else "N/A",
                    "user": log.user or "system",
                    "action": log.action,
                    "resource": log.resource or "N/A",
                    "ip_address": log.ip_address or "N/A",
                    "user_agent": log.user_agent or "N/A",
                    "success": log.success,
                    "details": log.details
                }
                
                self.app.push_screen(LogDetailDialog(log_data))
            finally:
                db.close()
        except Exception as e:
            self.notify(f"Error: {str(e)}", severity="error")
