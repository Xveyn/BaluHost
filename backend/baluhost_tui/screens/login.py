"""Login and authentication screen for BaluHost TUI."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, Static, Label, Button, Input
from textual.binding import Binding
import httpx
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.users import get_user_by_username, verify_password


class LoginScreen(Screen):
    """Login screen for admin authentication."""
    
    def __init__(self):
        super().__init__()
        self.backend_available = False
    
    CSS = """
    LoginScreen {
        align: center middle;
        background: $surface;
    }
    
    #login-container {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 2 4;
    }
    
    #login-title {
        text-style: bold;
        color: $accent;
        text-align: center;
        margin-bottom: 1;
    }
    
    #backend-status {
        text-align: center;
        margin-bottom: 2;
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
        margin-top: 2;
        align: center middle;
    }
    
    Button {
        margin: 0 1;
    }
    
    #error-message {
        color: $error;
        text-align: center;
        margin-top: 1;
    }
    """
    
    BINDINGS = [
        Binding("escape", "quit", "Quit"),
    ]
    
    def compose(self) -> ComposeResult:
        """Compose the login screen."""
        yield Header()
        with Container(id="login-container"):
            yield Label("🔐 BaluHost TUI - Admin Login", id="login-title")
            yield Static("Checking backend status...", id="backend-status")
            
            with Horizontal(classes="form-row"):
                yield Label("Username:", classes="form-label")
                yield Input(placeholder="Enter username", id="input-username")
            
            with Horizontal(classes="form-row"):
                yield Label("Password:", classes="form-label")
                yield Input(placeholder="Enter password", password=True, id="input-password")
            
            with Horizontal(classes="button-row"):
                yield Button("Login", variant="primary", id="btn-login")
                yield Button("Quit", variant="default", id="btn-quit")
            
            yield Label("", id="error-message")
        yield Footer()
    
    def on_mount(self) -> None:
        """Check backend status when mounted."""
        self.check_backend_status()
        # Focus username input
        self.query_one("#input-username", Input).focus()
    
    def check_backend_status(self) -> None:
        """Check if backend is running."""
        self.backend_available = False
        backend_running = False
        
        # Try HTTP health check first (primary method)
        try:
            server_url = getattr(self.app, 'server', 'http://localhost:8000')
            response = httpx.get(f"{server_url}/api/health", timeout=3.0)
            if response.status_code == 200:
                self.query_one("#backend-status", Static).update(f"[green]✓ Backend: HTTP API Connected ({server_url})[/green]")
                self.backend_available = True
                backend_running = True
            else:
                self.query_one("#backend-status", Static).update(f"[yellow]⚠ Backend HTTP: Status {response.status_code}[/yellow]")
        except Exception as http_error:
            pass
        
        # If HTTP failed, try local database access (TUI can work without HTTP backend)
        if not backend_running:
            try:
                db = SessionLocal()
                # Quick test query
                db.execute(text("SELECT 1"))
                db.close()
                
                self.query_one("#backend-status", Static).update("[green]✓ Database: Direct access (HTTP API offline)[/green]")
                self.backend_available = True
            except Exception as e:
                self.query_one("#backend-status", Static).update(
                    f"[red]✗ Database nicht erreichbar: {str(e)[:50]}[/red]\n"
                    "[yellow]Bitte überprüfe die Datenbank-Verbindung[/yellow]"
                )
                self.backend_available = False
                # Disable login button
                try:
                    btn = self.query_one("#btn-login", Button)
                    btn.disabled = True
                except:
                    pass
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "btn-quit":
            self.app.exit()
        elif event.button.id == "btn-login":
            self.attempt_login()
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in input fields."""
        if event.input.id == "input-username":
            # Move to password field
            self.query_one("#input-password", Input).focus()
        elif event.input.id == "input-password":
            # Submit login
            self.attempt_login()
    
    def attempt_login(self) -> None:
        """Attempt to login with provided credentials."""
        # Check if backend is available
        if not self.backend_available:
            self.show_error("Datenbank ist nicht erreichbar. Login nicht möglich.")
            return
        
        username = self.query_one("#input-username", Input).value.strip()
        password = self.query_one("#input-password", Input).value
        
        if not username or not password:
            self.show_error("Benutzername und Passwort erforderlich")
            return
        
        try:
            # Local database authentication
            db = SessionLocal()
            try:
                user = get_user_by_username(username, db)
                
                if not user:
                    self.show_error("Ungültiger Benutzername oder Passwort")
                    return
                
                # Verify password
                if not verify_password(password, user.hashed_password):
                    self.show_error("Ungültiger Benutzername oder Passwort")
                    return
                
                # Check if user is admin
                if user.role != "admin":
                    self.show_error("Zugriff verweigert. Admin-Rolle erforderlich.")
                    return
                
                # Check if user is active
                if not user.is_active:
                    self.show_error("Account ist deaktiviert")
                    return
                
                # Login successful
                self.app.current_user = {
                    "id": user.id,
                    "username": user.username,
                    "role": user.role,
                    "email": user.email
                }
                
                self.notify(f"Willkommen {username}!", severity="information")
                
                # Switch to dashboard
                from baluhost_tui.screens.dashboard import DashboardScreen
                self.app.switch_screen(DashboardScreen())
                
            finally:
                db.close()
        except Exception as e:
            self.show_error(f"Login Fehler: {str(e)}")
    
    def show_error(self, message: str) -> None:
        """Display error message."""
        self.query_one("#error-message", Label).update(f"[red]{message}[/red]")
        self.notify(message, severity="error")
