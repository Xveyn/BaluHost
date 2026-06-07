"""Dashboard screen with live system monitoring (over the BackendClient)."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Horizontal, Vertical, Grid
from textual.widgets import Header, Footer, Static, Label, ProgressBar
from textual.reactive import reactive

from baluhost_tui.api import monitoring as monitoring_api
from baluhost_tui.api import system as system_api
from baluhost_tui.api import users as users_api
from baluhost_tui.api import logging as logging_api
from baluhost_tui.screens.users import UserManagementScreen
from baluhost_tui.screens.logs import AuditLogViewerScreen


class SystemMetricsWidget(Static):
    """Widget for displaying system metrics."""
    
    cpu_usage: reactive[float] = reactive(0.0)
    memory_usage: reactive[float] = reactive(0.0)
    storage_usage: reactive[float] = reactive(0.0)
    network_down: reactive[float] = reactive(0.0)
    network_up: reactive[float] = reactive(0.0)
    
    def compose(self) -> ComposeResult:
        """Compose the metrics widget."""
        with Vertical(id="metrics-container"):
            yield Label("📊 System Metrics", id="metrics-title")
            
            with Horizontal(classes="metric-row"):
                yield Label("CPU:", classes="metric-label")
                yield ProgressBar(total=100, show_eta=False, id="cpu-bar")
                yield Label("0%", id="cpu-value")
            
            with Horizontal(classes="metric-row"):
                yield Label("Memory:", classes="metric-label")
                yield ProgressBar(total=100, show_eta=False, id="memory-bar")
                yield Label("0%", id="memory-value")
            
            with Horizontal(classes="metric-row"):
                yield Label("Storage:", classes="metric-label")
                yield ProgressBar(total=100, show_eta=False, id="storage-bar")
                yield Label("0%", id="storage-value")
            
            with Horizontal(classes="metric-row"):
                yield Label("Network:", classes="metric-label")
                yield Label("↓ 0 KB/s  ↑ 0 KB/s", id="network-value")
    
    def on_mount(self) -> None:
        """Start updating metrics when mounted."""
        self.update_metrics()
        self.set_interval(2.0, self.update_metrics)
    
    def update_metrics(self) -> None:
        """Update system metrics from the backend API."""
        client = self.app.client

        cpu = monitoring_api.current_cpu(client)
        mem = monitoring_api.current_memory(client)
        net = monitoring_api.current_network(client)
        stor = system_api.storage(client)

        self.cpu_usage = float(cpu.get("usage_percent", 0.0)) if cpu else 0.0
        self.memory_usage = float(mem.get("percent", 0.0)) if mem else 0.0
        if stor and stor.get("total"):
            self.storage_usage = round(stor["used"] / stor["total"] * 100, 1)
        else:
            self.storage_usage = 0.0
        self.network_down = float(net.get("download_mbps", 0.0)) if net else 0.0
        self.network_up = float(net.get("upload_mbps", 0.0)) if net else 0.0

        try:
            self.query_one("#cpu-bar", ProgressBar).update(progress=self.cpu_usage)
            self.query_one("#cpu-value", Label).update(f"{self.cpu_usage:.1f}%")
        except Exception:
            pass
        try:
            self.query_one("#memory-bar", ProgressBar).update(progress=self.memory_usage)
            self.query_one("#memory-value", Label).update(f"{self.memory_usage:.1f}%")
        except Exception:
            pass
        try:
            self.query_one("#storage-bar", ProgressBar).update(progress=self.storage_usage)
            self.query_one("#storage-value", Label).update(f"{self.storage_usage:.1f}%")
        except Exception:
            pass
        try:
            self.query_one("#network-value", Label).update(
                f"↓ {self.network_down:.1f} Mbps  ↑ {self.network_up:.1f} Mbps"
            )
        except Exception:
            pass


class RaidStatusWidget(Static):
    """Widget for displaying RAID status."""
    
    def compose(self) -> ComposeResult:
        """Compose the RAID widget."""
        with Vertical(id="raid-container"):
            yield Label("💾 RAID Status", id="raid-title")
            yield Static(id="raid-content")
    
    def on_mount(self) -> None:
        """Load RAID status when mounted."""
        self.update_raid_status()
        self.set_interval(10.0, self.update_raid_status)
    
    def update_raid_status(self) -> None:
        """Update RAID status from the backend API."""
        try:
            arrays = system_api.raid_status(self.app.client)
            if not arrays:
                content = "[dim]No RAID arrays[/dim]"
            else:
                lines = []
                for array in arrays:
                    status = str(array.get("status", "?"))
                    sl = status.lower()
                    color = "green" if sl == "active" else "yellow" if "degrad" in sl else "red"
                    lines.append(f"[{color}]●[/{color}] {array.get('name', '?')}: {array.get('level', '?')} - {status}")
                    devices = ", ".join(d.get("name", "?") for d in array.get("devices", []))
                    lines.append(f"   Devices: {devices}")
                    if array.get("resync_progress") is not None:
                        lines.append(f"   Resync: {float(array['resync_progress']):.1f}%")
                content = "\n".join(lines)
            self.query_one("#raid-content", Static).update(content)
        except Exception as e:
            self.query_one("#raid-content", Static).update(f"[red]Error: {e}[/red]")


class UsersWidget(Static):
    """Widget for displaying active users."""
    
    def compose(self) -> ComposeResult:
        """Compose the users widget."""
        with Vertical(id="users-container"):
            yield Label("👥 Users", id="users-title")
            yield Static(id="users-content")
    
    def on_mount(self) -> None:
        """Load user stats when mounted."""
        self.update_users()
        self.set_interval(30.0, self.update_users)
    
    def update_users(self) -> None:
        """Update user statistics from the backend API."""
        try:
            data = users_api.list_users(self.app.client)
            lines = [
                f"Total Users: {data.get('total', 0)}",
                f"Active: {data.get('active', 0)}",
                f"Admins: {data.get('admins', 0)}",
                f"Regular: {data.get('total', 0) - data.get('admins', 0)}",
            ]
            self.query_one("#users-content", Static).update("\n".join(lines))
        except Exception as e:
            self.query_one("#users-content", Static).update(f"[red]Error: {e}[/red]")


class AuditLogsWidget(Static):
    """Widget for displaying recent audit logs."""
    
    def compose(self) -> ComposeResult:
        """Compose the logs widget."""
        with Vertical(id="logs-container"):
            yield Label("📝 Recent Activity", id="logs-title")
            yield Static(id="logs-content")
    
    def on_mount(self) -> None:
        """Load recent logs when mounted."""
        self.update_logs()
        self.set_interval(5.0, self.update_logs)
    
    def update_logs(self) -> None:
        """Update recent audit logs from the backend API."""
        try:
            logs = logging_api.query_audit(self.app.client, limit=5)
            if not logs:
                content = "[dim]No recent activity[/dim]"
            else:
                lines = []
                for log in logs[:5]:
                    ts = str(log.get("timestamp", ""))
                    time_str = ts[11:19] if len(ts) >= 19 else ts
                    user_str = log.get("user") or "system"
                    action_str = str(log.get("action", ""))[:20]
                    ok = bool(log.get("success"))
                    icon = "✓" if ok else "✗"
                    color = "green" if ok else "red"
                    lines.append(f"[{color}]{icon}[/{color}] {time_str} {user_str}: {action_str}")
                content = "\n".join(lines)
            self.query_one("#logs-content", Static).update(content)
        except Exception as e:
            self.query_one("#logs-content", Static).update(f"[red]Error: {e}[/red]")


class DashboardScreen(Screen):
    """Main dashboard screen with live monitoring."""
    
    CSS = """
    DashboardScreen {
        background: $surface;
    }
    
    Grid {
        grid-size: 2 2;
        grid-gutter: 1 2;
        padding: 1 2;
        height: 100%;
    }
    
    #metrics-container, #raid-container, #users-container, #logs-container {
        border: solid $primary;
        padding: 1 2;
        height: 100%;
    }
    
    #metrics-title, #raid-title, #users-title, #logs-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    
    .metric-row {
        height: auto;
        margin-bottom: 1;
    }
    
    .metric-label {
        width: 12;
        content-align: left middle;
    }
    
    ProgressBar {
        width: 1fr;
    }
    
    #cpu-value, #memory-value, #storage-value, #network-value {
        width: 15;
        content-align: right middle;
        text-style: bold;
    }
    
    #raid-content, #users-content, #logs-content {
        margin-top: 1;
    }
    """
    
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("u", "users_screen", "Users"),

        ("l", "logs_screen", "Logs"),
    ]
    
    def compose(self) -> ComposeResult:
        """Compose the dashboard layout."""
        yield Header()
        with Grid():
            yield SystemMetricsWidget()
            yield RaidStatusWidget()
            yield UsersWidget()
            yield AuditLogsWidget()
        yield Footer()
    
    def action_refresh(self) -> None:
        """Manual refresh of all widgets."""
        for widget in self.query(SystemMetricsWidget):
            widget.update_metrics()
        for widget in self.query(RaidStatusWidget):
            widget.update_raid_status()
        for widget in self.query(UsersWidget):
            widget.update_users()
        for widget in self.query(AuditLogsWidget):
            widget.update_logs()
        self.notify("Dashboard refreshed", severity="information")
    
    def action_users_screen(self) -> None:
        """Navigate to users screen."""
        try:
            self.app.push_screen(UserManagementScreen())
        except Exception as exc:
            self.notify(f"Failed to open Users screen: {exc}", severity="error")
    
    def action_logs_screen(self) -> None:
        """Navigate to logs screen."""
        try:
            self.app.push_screen(AuditLogViewerScreen())
        except Exception as exc:
            self.notify(f"Failed to open Audit Logs: {exc}", severity="error")
