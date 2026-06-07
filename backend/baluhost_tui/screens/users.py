"""User Management screen for BaluHost TUI (over the BackendClient)."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen, ModalScreen
from textual.containers import Container, Horizontal
from textual.widgets import Header, Footer, Static, Label, DataTable, Button, Input, Select
from textual.binding import Binding
from rich.text import Text

from baluhost_tui.api import users as users_api


class CreateUserDialog(ModalScreen):
    """Modal dialog for creating a new user."""
    
    CSS = """
    CreateUserDialog {
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
            yield Label("Create New User", id="dialog-title")
            
            with Horizontal(classes="form-row"):
                yield Label("Username:", classes="form-label")
                yield Input(placeholder="Enter username", id="input-username")
            
            with Horizontal(classes="form-row"):
                yield Label("Email:", classes="form-label")
                yield Input(placeholder="user@example.com", id="input-email")
            
            with Horizontal(classes="form-row"):
                yield Label("Password:", classes="form-label")
                yield Input(placeholder="Enter password", password=True, id="input-password")
            
            with Horizontal(classes="form-row"):
                yield Label("Role:", classes="form-label")
                yield Select(
                    [(line, line) for line in ["user", "admin"]],
                    value="user",
                    id="input-role"
                )
            
            with Horizontal(classes="button-row"):
                yield Button("Create", variant="primary", id="btn-create")
                yield Button("Cancel", variant="default", id="btn-cancel")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-create":
            username = self.query_one("#input-username", Input).value
            email = self.query_one("#input-email", Input).value
            password = self.query_one("#input-password", Input).value
            role = self.query_one("#input-role", Select).value
            
            if not username or not password:
                self.notify("Username and password are required", severity="error")
                return
            
            self.dismiss({
                "username": username,
                "email": email,
                "password": password,
                "role": role
            })
    
    def action_cancel(self) -> None:
        """Cancel and close dialog."""
        self.dismiss(None)


class EditUserDialog(ModalScreen):
    """Modal dialog for editing a user."""
    
    CSS = """
    EditUserDialog {
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
    
    def __init__(self, user_data: dict):
        super().__init__()
        self.user_data = user_data
    
    def compose(self) -> ComposeResult:
        """Compose the dialog."""
        with Container(id="dialog-container"):
            yield Label(f"Edit User: {self.user_data['username']}", id="dialog-title")
            
            with Horizontal(classes="form-row"):
                yield Label("Email:", classes="form-label")
                yield Input(placeholder="user@example.com", id="input-email", value=self.user_data.get('email', ''))
            
            with Horizontal(classes="form-row"):
                yield Label("Role:", classes="form-label")
                yield Select(
                    [(line, line) for line in ["user", "admin"]],
                    value=self.user_data['role'],
                    id="input-role"
                )
            
            with Horizontal(classes="form-row"):
                yield Label("Active:", classes="form-label")
                yield Input(placeholder="true or false", id="input-active", value=str(self.user_data['is_active']).lower())
            
            with Horizontal(classes="button-row"):
                yield Button("Save", variant="primary", id="btn-save")
                yield Button("Cancel", variant="default", id="btn-cancel")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-save":
            email = self.query_one("#input-email", Input).value
            role = self.query_one("#input-role", Select).value
            active_str = self.query_one("#input-active", Input).value.lower()
            
            if active_str not in ["true", "false"]:
                self.notify("Active must be 'true' or 'false'", severity="error")
                return
            
            self.dismiss({
                "email": email,
                "role": role,
                "is_active": active_str == "true"
            })
    
    def action_cancel(self) -> None:
        """Cancel and close dialog."""
        self.dismiss(None)


class PasswordResetDialog(ModalScreen):
    """Modal dialog for resetting user password."""
    
    CSS = """
    PasswordResetDialog {
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
        width: 15;
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
    
    def __init__(self, username: str):
        super().__init__()
        self.username = username
    
    def compose(self) -> ComposeResult:
        """Compose the dialog."""
        with Container(id="dialog-container"):
            yield Label(f"Reset Password: {self.username}", id="dialog-title")
            
            with Horizontal(classes="form-row"):
                yield Label("New Password:", classes="form-label")
                yield Input(placeholder="Enter new password", password=True, id="input-password")
            
            with Horizontal(classes="form-row"):
                yield Label("Confirm:", classes="form-label")
                yield Input(placeholder="Confirm password", password=True, id="input-confirm")
            
            with Horizontal(classes="button-row"):
                yield Button("Reset", variant="primary", id="btn-reset")
                yield Button("Cancel", variant="default", id="btn-cancel")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-reset":
            password = self.query_one("#input-password", Input).value
            confirm = self.query_one("#input-confirm", Input).value
            
            if not password:
                self.notify("Password cannot be empty", severity="error")
                return
            
            if password != confirm:
                self.notify("Passwords do not match", severity="error")
                return
            
            self.dismiss(password)
    
    def action_cancel(self) -> None:
        """Cancel and close dialog."""
        self.dismiss(None)


class DeleteConfirmDialog(ModalScreen):
    """Modal dialog for confirming user deletion."""
    
    CSS = """
    DeleteConfirmDialog {
        align: center middle;
    }
    
    #dialog-container {
        width: 60;
        height: auto;
        border: thick $error;
        background: $surface;
        padding: 1 2;
    }
    
    .warning-text {
        color: $error;
        text-style: bold;
        margin-bottom: 1;
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
    
    def __init__(self, username: str, is_admin: bool):
        super().__init__()
        self.username = username
        self.is_admin = is_admin
    
    def compose(self) -> ComposeResult:
        """Compose the dialog."""
        with Container(id="dialog-container"):
            yield Label("⚠️  Delete User", id="dialog-title")
            yield Label(
                f"Are you sure you want to delete user '{self.username}'?",
                classes="warning-text"
            )
            
            if self.is_admin:
                yield Label(
                    "⚠️  WARNING: This is an admin account!",
                    classes="warning-text"
                )
            
            yield Label("This action cannot be undone.")
            
            with Horizontal(classes="button-row"):
                yield Button("Delete", variant="error", id="btn-delete")
                yield Button("Cancel", variant="default", id="btn-cancel")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "btn-cancel":
            self.dismiss(False)
        elif event.button.id == "btn-delete":
            self.dismiss(True)
    
    def action_cancel(self) -> None:
        """Cancel and close dialog."""
        self.dismiss(False)


class UserManagementScreen(Screen):
    """User management screen with CRUD operations."""

    def __init__(self) -> None:
        super().__init__()
        self._users_by_id: dict[int, dict] = {}

    CSS = """
    UserManagementScreen {
        background: $surface;
    }
    
    #users-container {
        width: 100%;
        height: 100%;
        padding: 1 2;
    }
    
    #users-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    
    DataTable {
        height: 1fr;
    }
    """
    
    BINDINGS = [
        Binding("q", "back", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("n", "new_user", "New User"),
        Binding("e", "edit_user", "Edit"),
        Binding("p", "reset_password", "Password"),
        Binding("d", "delete_user", "Delete"),
    ]
    
    def compose(self) -> ComposeResult:
        """Compose the user management layout."""
        yield Header()
        with Container(id="users-container"):
            yield Label("👥 User Management", id="users-title")
            yield DataTable(id="users-table")
        yield Footer()
    
    def on_mount(self) -> None:
        """Setup table when mounted."""
        table = self.query_one("#users-table", DataTable)
        table.add_columns("ID", "Username", "Email", "Role", "Active", "Created")
        table.cursor_type = "row"
        self.load_users()
    
    def load_users(self) -> None:
        """Load users from the backend API."""
        try:
            table = self.query_one("#users-table", DataTable)
            table.clear()

            data = users_api.list_users(self.app.client)
            users = data.get("users", [])
            self._users_by_id = {}
            for user in users:
                uid = user.get("id")
                if uid is not None:
                    self._users_by_id[int(uid)] = user

                is_active = bool(user.get("is_active"))
                status_color = "green" if is_active else "red"
                status_text = Text("✓", style=status_color) if is_active else Text("✗", style=status_color)

                role = user.get("role", "user")
                role_color = "yellow" if role == "admin" else "white"
                role_text = Text(str(role), style=role_color)

                created = str(user.get("created_at") or "")
                created_str = created[:10] if created else "N/A"

                table.add_row(
                    str(user.get("id", "")),
                    user.get("username", ""),
                    user.get("email") or "",
                    role_text,
                    status_text,
                    created_str,
                    key=str(user.get("id", "")),
                )

            self.notify(f"Loaded {len(users)} users", severity="information")
        except Exception as e:
            self.notify(f"Error loading users: {str(e)}", severity="error")
    
    def action_back(self) -> None:
        """Go back to dashboard."""
        self.app.pop_screen()
    
    def action_refresh(self) -> None:
        """Refresh user list."""
        self.load_users()
    
    def action_new_user(self) -> None:
        """Create a new user via the API."""
        def handle_result(data):
            if not data:
                return
            ok, msg = users_api.create_user(
                self.app.client,
                username=data["username"],
                password=data["password"],
                email=data.get("email") or None,
                role=data.get("role", "user"),
            )
            self.notify(msg, severity="information" if ok else "error")
            if ok:
                self.load_users()

        self.app.push_screen(CreateUserDialog(), handle_result)
    
    def action_edit_user(self) -> None:
        """Edit the selected user via the API."""
        table = self.query_one("#users-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            self.notify("No user selected", severity="warning")
            return
        try:
            row = table.get_row_at(table.cursor_row)
            user_id = int(row[0])
        except Exception:
            self.notify("No user selected", severity="warning")
            return

        user = self._users_by_id.get(user_id)
        if not user:
            self.notify("User not found — refresh and retry", severity="error")
            return

        user_data = {
            "id": user.get("id"),
            "username": user.get("username", ""),
            "email": user.get("email") or "",
            "role": user.get("role", "user"),
            "is_active": bool(user.get("is_active")),
        }

        def handle_result(data):
            if not data:
                return
            ok, msg = users_api.update_user(
                self.app.client,
                user_id,
                email=data.get("email") or None,
                role=data.get("role"),
                is_active=data.get("is_active"),
            )
            self.notify(msg, severity="information" if ok else "error")
            if ok:
                self.load_users()

        self.app.push_screen(EditUserDialog(user_data), handle_result)
    
    def action_reset_password(self) -> None:
        """Reset the selected user's password via the API."""
        table = self.query_one("#users-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            self.notify("No user selected", severity="warning")
            return
        try:
            row = table.get_row_at(table.cursor_row)
            user_id = int(row[0])
            username = str(row[1])
        except Exception:
            self.notify("No user selected", severity="warning")
            return

        def handle_result(new_password):
            if not new_password:
                return
            ok, msg = users_api.set_password(self.app.client, user_id, new_password)
            self.notify(f"{username}: {msg}", severity="information" if ok else "error")

        self.app.push_screen(PasswordResetDialog(username), handle_result)
    
    def action_delete_user(self) -> None:
        """Delete the selected user via the API."""
        table = self.query_one("#users-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            self.notify("No user selected", severity="warning")
            return
        try:
            row = table.get_row_at(table.cursor_row)
            user_id = int(row[0])
            username = str(row[1])
        except Exception:
            self.notify("No user selected", severity="warning")
            return

        cached = self._users_by_id.get(user_id, {})
        is_admin = str(cached.get("role", "")).lower() == "admin"

        def handle_result(confirmed):
            if not confirmed:
                return
            ok, msg = users_api.delete_user(self.app.client, user_id)
            self.notify(f"{username}: {msg}", severity="information" if ok else "error")
            if ok:
                self.load_users()

        self.app.push_screen(DeleteConfirmDialog(username, is_admin), handle_result)
