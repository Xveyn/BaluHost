"""Main TUI application using Textual."""
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Header, Footer, Button, Static
from textual.binding import Binding

from app.core.config import settings
from app.services.users import ensure_admin_user

from baluhost_tui.screens.login import LoginScreen
from baluhost_tui.screens.dashboard import DashboardScreen
from baluhost_tui.screens.users import UserManagementScreen
from baluhost_tui.screens.logs import AuditLogViewerScreen


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
        Binding("f", "files", "Files"),
        Binding("l", "logs", "Logs"),
    ]
    
    def __init__(self, mode: str = 'auto', server: str = 'http://localhost:8000'):
        """Initialize app.
        
        Args:
            mode: Connection mode (auto, local, remote)
            server: Server URL for remote mode
        """
        super().__init__()
        self.mode = mode
        self.server = server
        self.title = "BaluHost NAS TUI"
        self.sub_title = f"Mode: {mode}"
        self.current_user = None  # Will be set after login
        
        # Ensure admin user exists (same as backend does)
        try:
            ensure_admin_user(settings)
        except Exception as e:
            pass  # Will be handled by login screen
    
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
    
    def action_files(self) -> None:
        """Show file browser (TODO: implement)."""
        if not self.current_user:
            self.notify("Please login first", severity="error")
            return
        self.notify("File Browser - Coming soon!", severity="information")
    
    def action_logs(self) -> None:
        """Show audit logs."""
        if not self.current_user:
            self.notify("Please login first", severity="error")
            return
        self.push_screen(AuditLogViewerScreen())
    
    def action_logs(self) -> None:
        """Show audit logs."""
        self.push_screen(AuditLogViewerScreen())
