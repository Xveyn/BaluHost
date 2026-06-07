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
@click.option('--socket', 'socket_path', default=None,
              help='Unix socket path (prod local channel). Auto-detected when omitted.')
@click.option('--server', default=None,
              help='Server URL (dev TCP, e.g. http://127.0.0.1:8000). Auto-detected when omitted.')
@click.option('--token', default=None,
              help='Bearer token for API access')
@click.option('--debug/--no-debug', default=False,
              help='Enable debug logging')
@click.pass_context
def cli(ctx: click.Context, socket_path: str | None, server: str | None, token: str | None, debug: bool):
    """BaluHost NAS Terminal Interface
    
    Manage your NAS server from the command line.
    
    Examples:
        baluhost-tui                    # Launch interactive TUI (local channel)
        baluhost-tui dashboard          # Launch dashboard directly
        baluhost-tui status             # Quick status (needs a token)
        baluhost-tui --server http://127.0.0.1:8000
    """
    ctx.ensure_object(dict)
    ctx.obj['socket_path'] = socket_path
    ctx.obj['server'] = server
    ctx.obj['token'] = token
    ctx.obj['debug'] = debug


@cli.command()
@click.pass_context
def dashboard(ctx: click.Context):
    """Launch the interactive TUI (UDS in prod, TCP loopback in dev)."""
    from .app import BaluHostApp
    from .client import BackendClient

    socket_path = ctx.obj.get('socket_path')
    server = ctx.obj.get('server')
    token = ctx.obj.get('token') or os.environ.get('BALUHOST_TOKEN')

    client = BackendClient(socket_path=socket_path, server=server)
    console.print("[cyan]Starting BaluHost TUI[/cyan] (local channel)")

    app = BaluHostApp(client=client, token=token)
    app.run()


@cli.command()
@click.option('--token', 'token_opt', default=None, help='Auth token (overrides global)')
@click.pass_context
def status(ctx: click.Context, token_opt: str | None):
    """Quick system status check (over the API)."""
    from .commands.status import show_status
    from .client import BackendClient
    from . import config

    tok = token_opt or ctx.obj.get('token') or os.environ.get('BALUHOST_TOKEN') or config.load_token()
    client = BackendClient(socket_path=ctx.obj.get('socket_path'), server=ctx.obj.get('server'), token=tok)
    show_status(client)


@cli.command()
@click.option('--token', 'token_opt', default=None, help='Auth token (overrides global)')
@click.pass_context
def users(ctx: click.Context, token_opt: str | None):
    """List all users (over the API)."""
    from .commands.users import render_users
    from .client import BackendClient
    from . import config

    tok = token_opt or ctx.obj.get('token') or os.environ.get('BALUHOST_TOKEN') or config.load_token()
    client = BackendClient(socket_path=ctx.obj.get('socket_path'), server=ctx.obj.get('server'), token=tok)
    render_users(client)


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
