"""Main TUI application using Textual."""
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Header, Footer, Button, Static
from textual.binding import Binding

from baluhost_tui.client import BackendClient
from baluhost_tui.screens.login import LoginScreen
from baluhost_tui.screens.dashboard import DashboardScreen
from baluhost_tui.screens.users import UserManagementScreen
from baluhost_tui.screens.logs import AuditLogViewerScreen
from baluhost_tui.screens.raid import RaidControlScreen
from baluhost_tui.screens.power import PowerActionsScreen
from baluhost_tui.screens.services import ServiceHealthScreen
from baluhost_tui.screens.smart import SmartScreen


class WelcomeScreen(Static):
    """Welcome screen widget."""
    
    def compose(self) -> ComposeResult:
        """Compose welcome screen."""
        yield Static("""
[cyan]╔══════════════════════════════════════════╗
║                                          ║
║         🖥️  BaluHost NAS TUI 🖥️          ║
║                                          ║
║    Terminal User Interface v1.0.0        ║
║                                          ║
╚══════════════════════════════════════════╝[/cyan]

[yellow]Welcome to BaluHost NAS Terminal Interface![/yellow]

This is the SSH-friendly admin interface for your NAS server.

[green]Features:[/green]
• Real-time system monitoring
• User management
• File operations
• RAID & backup management
• Audit log viewer
• SSH key-based authentication

[cyan]Press any key to continue or 'q' to quit...[/cyan]
""", id="welcome-text")


class BaluHostApp(App):
    """BaluHost TUI Application."""
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    #welcome-text {
        width: 100%;
        height: 100%;
        content-align: center middle;
        text-align: center;
    }
    
    .box {
        border: solid $primary;
        width: 100%;
        height: 100%;
        padding: 1 2;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("d", "dashboard", "Dashboard"),
        Binding("u", "users", "Users"),
        Binding("l", "logs", "Logs"),
        Binding("R", "raid", "RAID Controls"),
        Binding("p", "power", "Power"),
        Binding("s", "services", "Services"),
        Binding("S", "smart", "SMART"),
    ]
    
    def __init__(self, client: BackendClient | None = None, token: str | None = None):
        """Initialize app.

        Args:
            client: Pre-built BackendClient (UDS in prod / TCP loopback in dev).
                    Built with defaults (auto-detect transport) when omitted.
            token: Optional pre-supplied bearer token (set on the client).
        """
        super().__init__()
        self.client = client if client is not None else BackendClient()
        self.token = token
        if token:
            self.client.set_token(token)
        self.title = "BaluHost NAS TUI"
        self.sub_title = "Companion (local channel)"
        self.current_user = None  # Set after login
    
    def on_mount(self) -> None:
        """Show login screen on startup."""
        self.push_screen(LoginScreen())
    
    def compose(self) -> ComposeResult:
        """Compose main layout."""
        yield Header()
        yield Container(
            WelcomeScreen(),
            id="main-container"
        )
        yield Footer()
    
    def action_dashboard(self) -> None:
        """Show dashboard."""
        if not self.current_user:
            self.notify("Please login first", severity="error")
            return
        self.push_screen(DashboardScreen())
    
    def action_users(self) -> None:
        """Show user management."""
        if not self.current_user:
            self.notify("Please login first", severity="error")
            return
        self.push_screen(UserManagementScreen())
    
    def action_raid(self) -> None:
        """Show RAID controls screen."""
        if not self.current_user:
            self.notify("Please login first", severity="error")
            return
        self.push_screen(RaidControlScreen())
    
    def action_logs(self) -> None:
        """Show audit logs."""
        if not self.current_user:
            self.notify("Please login first", severity="error")
            return
        self.push_screen(AuditLogViewerScreen())

    def action_power(self) -> None:
        """Show power actions (sleep/wake/suspend/WoL)."""
        if not self.current_user:
            self.notify("Please login first", severity="error")
            return
        if (self.current_user or {}).get("role") != "admin":
            self.notify("Admin role required", severity="error")
            return
        self.push_screen(PowerActionsScreen())

    def action_services(self) -> None:
        """Show service health & restart."""
        if not self.current_user:
            self.notify("Please login first", severity="error")
            return
        if (self.current_user or {}).get("role") != "admin":
            self.notify("Admin role required", severity="error")
            return
        self.push_screen(ServiceHealthScreen())

    def action_smart(self) -> None:
        """Show SMART / disk-health screen."""
        if not self.current_user:
            self.notify("Please login first", severity="error")
            return
        if (self.current_user or {}).get("role") != "admin":
            self.notify("Admin role required", severity="error")
            return
        self.push_screen(SmartScreen())
