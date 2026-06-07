"""`users` CLI — list users over the BackendClient (API)."""
from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table

from baluhost_tui.api import users as users_api

_console = Console()


def render_users(client: Any, console: Console | None = None) -> None:
    """Fetch users via the API and print a table."""
    console = console or _console
    data = users_api.list_users(client)
    users = data.get("users", [])

    table = Table(title="Users", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Username", style="green")
    table.add_column("Email", style="blue")
    table.add_column("Role", style="yellow")
    table.add_column("Active", style="magenta")

    for user in users:
        table.add_row(
            str(user.get("id", "")),
            user.get("username", ""),
            user.get("email") or "-",
            user.get("role", ""),
            "✓" if user.get("is_active") else "✗",
        )

    console.print(table)
    console.print(f"\nTotal: {data.get('total', 0)} users")
