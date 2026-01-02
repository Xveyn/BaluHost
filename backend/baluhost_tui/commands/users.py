"""Users command - list users."""
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

console = Console()


def list_users(mode: str = 'auto', server: str = 'http://localhost:8000') -> None:
    """List all users."""
    from baluhost_tui.context import get_context
    
    with get_context(mode=mode, server=server) as ctx:
        if ctx.is_local:
            _list_users_local(ctx)
        else:
            _list_users_remote(ctx)


def _list_users_local(ctx) -> None:
    """List users using local database."""
    from app.models.user import User
    
    db = ctx.get_db()
    users = db.query(User).all()
    
    _display_users_table(users)


def _list_users_remote(ctx) -> None:
    """List users using API."""
    client = ctx.get_api_client()
    
    try:
        response = client.get('/api/users')
        response.raise_for_status()
        users_data = response.json()
        
        _display_users_table(users_data, is_dict=True)
        
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


def _display_users_table(users, is_dict: bool = False):
    """Display users in table format."""
    table = Table(title="Users", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Username", style="green")
    table.add_column("Email", style="blue")
    table.add_column("Role", style="yellow")
    table.add_column("Active", style="magenta")
    
    for user in users:
        if is_dict:
            user_id = str(user.get('id', ''))
            username = user.get('username', '')
            email = user.get('email', '') or '-'
            role = user.get('role', '')
            active = '✓' if user.get('is_active') else '✗'
        else:
            user_id = str(user.id)
            username = user.username
            email = user.email or '-'
            role = user.role
            active = '✓' if user.is_active else '✗'
        
        table.add_row(user_id, username, email, role, active)
    
    console.print(table)
    console.print(f"\nTotal: {len(users)} users")
