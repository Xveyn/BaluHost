"""Status command - quick system overview."""
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

console = Console()


def show_status(mode: str = 'auto', server: str = 'http://localhost:8000') -> None:
    """Show quick system status."""
    from baluhost_tui.context import get_context
    
    with get_context(mode=mode, server=server) as ctx:
        if ctx.is_local:
            _show_local_status(ctx)
        else:
            _show_remote_status(ctx)


def _show_local_status(ctx) -> None:
    """Show status using local database access."""
    from app.models.user import User
    from app.core.config import settings
    
    db = ctx.get_db()
    
    # User statistics
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    admin_users = db.query(User).filter(User.role == 'admin').count()
    
    # Create status table
    table = Table(title="BaluHost System Status", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Mode", settings.nas_mode)
    table.add_row("Storage Path", str(settings.nas_storage_path))
    table.add_row("Total Users", str(total_users))
    table.add_row("Active Users", str(active_users))
    table.add_row("Admin Users", str(admin_users))
    
    console.print(table)
    console.print(Panel("[green]✓[/green] System operational", title="Status"))


def _show_remote_status(ctx) -> None:
    """Show status using API client."""
    client = ctx.get_api_client()
    
    try:
        # Try to get system info
        response = client.get('/api/system/info')
        response.raise_for_status()
        data = response.json()
        
        # Create status table
        table = Table(title="BaluHost System Status (Remote)", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Hostname", data.get('hostname', 'N/A'))
        table.add_row("OS", data.get('os', 'N/A'))
        table.add_row("CPU Cores", str(data.get('cpu_count', 'N/A')))
        
        console.print(table)
        console.print(Panel("[green]✓[/green] Connected to server", title="Status"))
        
    except Exception as e:
        console.print(f"[red]Error connecting to server:[/red] {e}")
        sys.exit(1)
