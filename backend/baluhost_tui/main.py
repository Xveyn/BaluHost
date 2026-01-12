"""Main entry point for BaluHost TUI."""
import os
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

# Add parent directory to path for local imports
sys.path.insert(0, str(Path(__file__).parent.parent))

console = Console()


@click.group()
@click.option('--mode', type=click.Choice(['auto', 'local', 'remote']), default='auto',
              help='Connection mode: auto (detect), local (direct DB), remote (API)')
@click.option('--server', default='http://localhost:8000',
              help='Server URL for remote mode')
@click.option('--token', default=None,
              help='Bearer token for remote API access')
@click.option('--debug/--no-debug', default=False,
              help='Enable debug logging')
@click.pass_context
def cli(ctx: click.Context, mode: str, server: str, token: str | None, debug: bool):
    """BaluHost NAS Terminal Interface
    
    Manage your NAS server from the command line.
    
    Examples:
        baluhost-tui                    # Launch interactive TUI
        baluhost-tui dashboard          # Launch dashboard directly
        baluhost-tui reset-password admin  # Emergency password reset
        baluhost-tui --mode remote --server https://nas.local
    """
    ctx.ensure_object(dict)
    ctx.obj['mode'] = mode
    ctx.obj['server'] = server
    ctx.obj['token'] = token
    ctx.obj['debug'] = debug


@cli.command()
@click.pass_context
def dashboard(ctx: click.Context):
    """Launch the interactive TUI dashboard."""
    from .app import BaluHostApp
    
    mode = ctx.obj['mode']
    server = ctx.obj['server']
    token = ctx.obj.get('token') or os.environ.get('BALUHOST_TOKEN')
    
    console.print(f"[cyan]Starting BaluHost TUI[/cyan] (mode: {mode})")
    
    app = BaluHostApp(mode=mode, server=server, token=token)
    app.run()


@cli.command()
@click.argument('username')
@click.option('--password', prompt=True, hide_input=True,
              confirmation_prompt=True,
              help='New password for user')
@click.pass_context
def reset_password(ctx: click.Context, username: str, password: str):
    """Emergency password reset (requires local access)."""
    from .commands.emergency import reset_user_password
    
    mode = ctx.obj['mode']
    
    if mode == 'remote':
        console.print("[red]Error: Password reset requires local access[/red]")
        console.print("Run this command on the server directly.")
        sys.exit(1)
    
    try:
        reset_user_password(username, password)
        console.print(f"[green]✓[/green] Password reset successfully for user: {username}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


@cli.command()
@click.pass_context
def status(ctx: click.Context):
    """Quick system status check."""
    from .commands.status import show_status
    
    mode = ctx.obj['mode']
    server = ctx.obj['server']
    
    show_status(mode=mode, server=server)


@cli.command()
@click.pass_context
def users(ctx: click.Context):
    """List all users."""
    from .commands.users import list_users
    
    mode = ctx.obj['mode']
    server = ctx.obj['server']
    
    list_users(mode=mode, server=server)


@cli.command()
@click.pass_context
def files(ctx: click.Context):
    """Open file browser TUI."""
    from .app import BaluHostApp

    mode = ctx.obj['mode']
    server = ctx.obj['server']
    token = ctx.obj.get('token') or os.environ.get('BALUHOST_TOKEN')

    console.print(f"[cyan]Starting BaluHost TUI - Files[/cyan] (mode: {mode})")
    app = BaluHostApp(mode=mode, server=server, token=token)
    app.run()


@cli.command("files-download")
@click.argument('remote_path')
@click.argument('local_dest')
@click.option('--server', default=None, help='Server URL (overrides global)')
@click.option('--token', default=None, help='Auth token')
@click.pass_context
def files_download(ctx: click.Context, remote_path: str, local_dest: str, server: str | None, token: str | None):
    """Download a remote file via API to a local path."""
    from .commands.files import download_remote_file
    svr = server or ctx.obj.get('server')
    tok = token or ctx.obj.get('token') or os.environ.get('BALUHOST_TOKEN')
    download_remote_file(remote_path, local_dest, server=svr, token=tok)


@cli.command("files-upload")
@click.argument('local_path')
@click.argument('remote_dest', required=False)
@click.option('--server', default=None, help='Server URL (overrides global)')
@click.option('--token', default=None, help='Auth token')
@click.pass_context
def files_upload(ctx: click.Context, local_path: str, remote_dest: str | None, server: str | None, token: str | None):
    """Upload a local file to the remote server via API."""
    from .commands.files import upload_local_file
    svr = server or ctx.obj.get('server')
    tok = token or ctx.obj.get('token') or os.environ.get('BALUHOST_TOKEN')
    upload_local_file(local_path, remote_dest or '', server=svr, token=tok)


if __name__ == '__main__':
    cli()
