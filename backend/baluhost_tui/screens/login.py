"""Login screen for BaluHost TUI — JWT auth over the local-channel client."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Container, Horizontal
from textual.widgets import Header, Footer, Static, Label, Button, Input
from textual.binding import Binding

from baluhost_tui.api import auth as auth_api
from baluhost_tui import config


class LoginScreen(Screen):
    """Admin login. Authenticates via the backend over the app's BackendClient."""

    def __init__(self) -> None:
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
        self.check_backend_status()
        self.query_one("#input-username", Input).focus()

    def check_backend_status(self) -> None:
        """Probe the backend over the app's client; disable login if unreachable."""
        self.backend_available = False
        try:
            resp = self.app.client.get("/api/health")
            if resp.status_code == 200:
                self.query_one("#backend-status", Static).update(
                    "[green]✓ Backend erreichbar (local channel)[/green]"
                )
                self.backend_available = True
                return
            self.query_one("#backend-status", Static).update(
                f"[yellow]⚠ Backend-Status {resp.status_code}[/yellow]"
            )
        except Exception as exc:
            self.query_one("#backend-status", Static).update(
                f"[red]✗ Backend nicht erreichbar: {str(exc)[:60]}[/red]\n"
                "[yellow]Läuft baluhost-backend-local.service? (bzw. start_dev.py in Dev)[/yellow]"
            )
        try:
            self.query_one("#btn-login", Button).disabled = True
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-quit":
            self.app.exit()
        elif event.button.id == "btn-login":
            self.attempt_login()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "input-username":
            self.query_one("#input-password", Input).focus()
        elif event.input.id == "input-password":
            self.attempt_login()

    def attempt_login(self) -> None:
        if not self.backend_available:
            self.show_error("Backend nicht erreichbar. Login nicht möglich.")
            return

        username = self.query_one("#input-username", Input).value.strip()
        password = self.query_one("#input-password", Input).value
        if not username or not password:
            self.show_error("Benutzername und Passwort erforderlich")
            return

        client = self.app.client
        try:
            token = auth_api.login(client, username, password)
        except auth_api.TwoFactorRequired:
            self.show_error("2FA-Konten werden in der TUI noch nicht unterstützt.")
            return
        except auth_api.LoginError as exc:
            self.show_error(f"Login fehlgeschlagen: {exc}")
            return

        client.set_token(token)
        try:
            user = auth_api.me(client)
        except auth_api.LoginError as exc:
            client.clear_token()
            self.show_error(f"Konnte Benutzer nicht laden: {exc}")
            return

        if user.get("role") != "admin":
            client.clear_token()
            self.show_error("Zugriff verweigert. Admin-Rolle erforderlich.")
            return

        self.app.token = token
        self.app.current_user = user
        try:
            config.save_token(token)
        except Exception:
            pass  # token persistence is best-effort; login still succeeds
        self.notify(f"Willkommen {user.get('username', username)}!", severity="information")

        from baluhost_tui.screens.dashboard import DashboardScreen
        self.app.switch_screen(DashboardScreen())

    def show_error(self, message: str) -> None:
        self.query_one("#error-message", Label).update(f"[red]{message}[/red]")
        self.notify(message, severity="error")
