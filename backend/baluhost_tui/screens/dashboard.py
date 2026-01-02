"""Dashboard screen with live system monitoring."""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, Horizontal, Vertical, Grid
from textual.widgets import Header, Footer, Static, Label, ProgressBar, DataTable
from textual.reactive import reactive
from rich.text import Text

from app.services.telemetry import get_history, get_latest_cpu_usage, get_latest_memory_sample
from app.services.raid import get_status as get_raid_status
from app.services.users import list_users
from app.services.audit_logger_db import get_audit_logger_db
from app.core.config import settings


def get_current_telemetry():
    """Build current telemetry from latest samples."""
    import psutil
    
    cpu_usage = get_latest_cpu_usage() or 0.0
    memory_sample = get_latest_memory_sample()
    
    if memory_sample:
        memory_used = memory_sample.used
        memory_total = memory_sample.total
    else:
        mem = psutil.virtual_memory()
        memory_used = mem.used
        memory_total = mem.total
    
    # Storage info
    try:
        storage_path = settings.nas_storage_path
        stat = psutil.disk_usage(storage_path)
        storage_used = stat.used
        storage_total = stat.total
        storage_percent = stat.percent
    except:
        storage_used = 0
        storage_total = 0
        storage_percent = 0.0
    
    # Network - use history if available
    history = get_history()
    if history.network:
        last_net = history.network[-1]
        download_mbps = last_net.downloadMbps
        upload_mbps = last_net.uploadMbps
    else:
        download_mbps = 0.0
        upload_mbps = 0.0
    
    class TelemetrySnapshot:
        def __init__(self):
            self.system = type('SystemTelemetry', (), {
                'cpu_usage': cpu_usage,
                'memory_used': memory_used,
                'memory_total': memory_total
            })()
            self.storage = type('StorageTelemetry', (), {
                'used': storage_used,
                'total': storage_total,
                'percent': storage_percent
            })()
            self.network = type('NetworkTelemetry', (), {
                'download_speed_mbps': download_mbps,
                'upload_speed_mbps': upload_mbps
            })()
    
    return TelemetrySnapshot()


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
        """Update system metrics from telemetry service."""
        try:
            telemetry = get_current_telemetry()
            
            self.cpu_usage = telemetry.system.cpu_usage
            self.memory_usage = (telemetry.system.memory_used / telemetry.system.memory_total * 100) if telemetry.system.memory_total > 0 else 0
            
            # Storage from settings
            if settings.nas_quota_bytes:
                used_gb = telemetry.storage.used / (1024**3)
                total_gb = settings.nas_quota_bytes / (1024**3)
                self.storage_usage = (telemetry.storage.used / settings.nas_quota_bytes * 100) if settings.nas_quota_bytes > 0 else 0
            else:
                self.storage_usage = telemetry.storage.percent
            
            self.network_down = telemetry.network.download_speed_mbps
            self.network_up = telemetry.network.upload_speed_mbps
            
            # Update progress bars - use try/except for each widget
            try:
                cpu_bar = self.query_one("#cpu-bar", ProgressBar)
                cpu_bar.update(progress=self.cpu_usage)
                self.query_one("#cpu-value", Label).update(f"{self.cpu_usage:.1f}%")
            except Exception:
                pass
            
            try:
                memory_bar = self.query_one("#memory-bar", ProgressBar)
                memory_bar.update(progress=self.memory_usage)
                self.query_one("#memory-value", Label).update(f"{self.memory_usage:.1f}%")
            except Exception:
                pass
            
            try:
                storage_bar = self.query_one("#storage-bar", ProgressBar)
                storage_bar.update(progress=self.storage_usage)
                self.query_one("#storage-value", Label).update(f"{self.storage_usage:.1f}%")
            except Exception:
                pass
            
            try:
                self.query_one("#network-value", Label).update(
                    f"↓ {self.network_down:.1f} Mbps  ↑ {self.network_up:.1f} Mbps"
                )
            except Exception:
                pass
        except Exception as e:
            import traceback
            error_msg = f"Metrics Error: {str(e)}"
            try:
                self.query_one("#cpu-value", Label).update(error_msg)
            except:
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
        """Update RAID status from service."""
        try:
            # Check if we're in dev mode - skip mock data for TUI
            from app.core.config import settings
            if settings.is_dev_mode:
                self.query_one("#raid-content", Static).update("[dim]RAID not available in TUI dev mode[/dim]")
                return
            
            status = get_raid_status()
            
            if not status.arrays:
                content = "[dim]No RAID arrays configured[/dim]"
            else:
                lines = []
                for array in status.arrays:
                    # RaidArray has 'status' not 'state', and 'name' not 'device'
                    status_lower = array.status.lower()
                    state_color = "green" if status_lower == "active" else "yellow" if "degrad" in status_lower else "red"
                    lines.append(f"[{state_color}]●[/{state_color}] {array.name}: {array.level} - {array.status}")
                    # Devices is a list of RaidDevice objects with .name attribute
                    device_names = [d.name for d in array.devices]
                    lines.append(f"   Devices: {', '.join(device_names)}")
                    if array.resync_progress is not None:
                        lines.append(f"   Resync: {array.resync_progress:.1f}%")
                content = "\n".join(lines)
            
            self.query_one("#raid-content", Static).update(content)
        except Exception as e:
            import traceback
            self.query_one("#raid-content", Static).update(f"[red]Error: {str(e)}[/red]")


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
        """Update user statistics."""
        try:
            from app.core.database import SessionLocal
            db = SessionLocal()
            try:
                users = list(list_users(db))
                total = len(users)
                active = sum(1 for u in users if u.is_active)
                admins = sum(1 for u in users if u.role == "admin")
                regular = sum(1 for u in users if u.role == "user")
                
                lines = [
                    f"Total Users: {total}",
                    f"Active: {active}",
                    f"Admins: {admins}",
                    f"Regular: {regular}"
                ]
                
                self.query_one("#users-content", Static).update("\n".join(lines))
            finally:
                db.close()
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
        """Update recent audit logs."""
        try:
            from app.core.database import SessionLocal
            db = SessionLocal()
            try:
                audit_logger = get_audit_logger_db()
                from app.models.audit_log import AuditLog
                
                # Get last 5 logs
                logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(5).all()
                
                if not logs:
                    content = "[dim]No recent activity[/dim]"
                else:
                    lines = []
                    for log in logs:
                        time_str = log.timestamp.strftime("%H:%M:%S")
                        user_str = log.user or "system"
                        action_str = log.action[:20]
                        success_icon = "✓" if log.success else "✗"
                        success_color = "green" if log.success else "red"
                        lines.append(f"[{success_color}]{success_icon}[/{success_color}] {time_str} {user_str}: {action_str}")
                    content = "\n".join(lines)
                
                self.query_one("#logs-content", Static).update(content)
            finally:
                db.close()
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
        ("f", "files_screen", "Files"),
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
        self.notify("User management - Coming soon!", severity="information")
    
    def action_files_screen(self) -> None:
        """Navigate to files screen."""
        self.notify("File browser - Coming soon!", severity="information")
    
    def action_logs_screen(self) -> None:
        """Navigate to logs screen."""
        self.notify("Audit logs - Coming soon!", severity="information")
