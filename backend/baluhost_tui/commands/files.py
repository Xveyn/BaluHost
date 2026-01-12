"""CLI helpers for file listing (used by `baluhost-tui files` or for scripts)."""
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

console = Console()


def list_files_local(start_path: str | Path):
    p = Path(start_path)
    if not p.exists():
        console.print(f"[red]Path not found:[/red] {p}")
        return

    rows = []
    for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        rows.append((child.name, 'dir' if child.is_dir() else 'file', str(child.stat().st_size) if child.is_file() else '-', child.stat().st_mtime))

    table = Table(title=f"Files: {p}")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Size")
    table.add_column("MTime")

    from datetime import datetime
    for r in rows:
        table.add_row(r[0], r[1], r[2], datetime.fromtimestamp(r[3]).strftime('%Y-%m-%d %H:%M'))

    console.print(table)


def download_remote_file(remote_path: str, local_dest: str | Path, server: str = 'http://localhost:8000', token: str | None = None):
    import httpx
    dest = Path(local_dest)
    dest_parent = dest.parent
    dest_parent.mkdir(parents=True, exist_ok=True)

    headers = {}
    if token:
        headers['Authorization'] = f'Bearer {token}'

    url = server.rstrip('/') + f"/api/files/download/{remote_path.lstrip('/')}"
    with httpx.stream('GET', url, headers=headers, timeout=60.0) as r:
        r.raise_for_status()
        with open(dest, 'wb') as fh:
            for chunk in r.iter_bytes():
                fh.write(chunk)

    console.print(f"[green]Downloaded[/green] {remote_path} -> {dest}")


def upload_local_file(local_path: str | Path, remote_dest: str = '', server: str = 'http://localhost:8000', token: str | None = None):
    import httpx
    p = Path(local_path)
    if not p.exists() or not p.is_file():
        console.print(f"[red]Local file not found:[/red] {p}")
        return

    headers = {}
    if token:
        headers['Authorization'] = f'Bearer {token}'

    url = server.rstrip('/') + "/api/files/upload"
    files = {"files": (p.name, open(p, 'rb'))}
    data = {"path": remote_dest}
    with httpx.Client(headers=headers, timeout=120.0) as client:
        res = client.post(url, files=files, data=data)
        res.raise_for_status()

    console.print(f"[green]Uploaded[/green] {p} -> {remote_dest or '/'}")
