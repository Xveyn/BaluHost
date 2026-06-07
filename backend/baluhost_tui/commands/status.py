"""`status` CLI — quick system status over the BackendClient (API)."""
from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from baluhost_tui.api import users as users_api
from baluhost_tui.api import system as system_api

_console = Console()


def show_status(client: Any, console: Console | None = None) -> None:
    """Fetch a status summary via the API and print it."""
    console = console or _console

    channel = system_api.get_channel_status(client)
    users = users_api.list_users(client)
    storage = system_api.storage(client)

    table = Table(title="BaluHost System Status", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Channel", channel)
    table.add_row("Total Users", str(users.get("total", 0)))
    table.add_row("Active Users", str(users.get("active", 0)))
    table.add_row("Admin Users", str(users.get("admins", 0)))
    if storage and storage.get("total"):
        used = storage.get("used", 0)
        total = storage.get("total", 0)
        pct = storage.get("use_percent") or f"{round(used / total * 100, 1)}%"
        table.add_row("Storage", f"{pct} used ({used}/{total} bytes)")
    else:
        table.add_row("Storage", "[dim]unavailable[/dim]")

    console.print(table)
    ok = channel == "local"
    console.print(
        Panel(
            "[green]✓ Local channel[/green]" if ok else "[yellow]Remote channel[/yellow]",
            title="Status",
        )
    )
