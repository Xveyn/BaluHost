"""File browser screen for BaluHost TUI with remote download/upload support."""
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, DataTable, Label, Input
from textual.containers import Container
from textual.binding import Binding
from rich.text import Text

from app.core.config import settings
from baluhost_tui.context import get_context


class FileBrowserScreen(Screen):
    """File browser with remote-mode integration.

    Bindings:
    - Enter: open dir / preview file
    - b: up
    - r: refresh
    - q: back
    - d: download selected remote file to local `downloads/`
    - u: upload a local file into current remote directory (prompts for path)
    """

    BINDINGS = [
        Binding("q", "back", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("b", "up", "Up"),
        Binding("d", "download", "Download"),
        Binding("u", "upload", "Upload"),
    ]

    def __init__(self, start_path: str = "/", mode: str = 'auto', server: str = 'http://localhost:8000', token: Optional[str] = None):
        super().__init__()
        self.cwd = Path(start_path)
        self.storage_root = Path(settings.nas_storage_path or ".").resolve()
        self.mode = mode
        self.server = server
        self.token = token
        # Remote navigation state (posix relative path, empty for root)
        self.remote_cwd: str = ""
        # Map row key -> type ('file'|'dir') for remote entries
        self._entry_types: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="files-container"):
            yield Label("📁 File Browser", id="files-title")
            yield DataTable(id="files-table")
            yield Input(placeholder="(for upload) local path to upload", id="upload-input")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#files-table", DataTable)
        table.add_columns("Name", "Type", "Size", "Modified")
        table.cursor_type = "row"
        # normalize start path within storage_root
        if not self.cwd.is_absolute():
            try:
                self.cwd = (self.storage_root / self.cwd).resolve()
            except Exception:
                self.cwd = self.storage_root
        # Initialize remote cwd for remote mode
        if self.mode == 'remote':
            self.remote_cwd = ""
        self.load_entries()

    def load_entries(self) -> None:
        table = self.query_one("#files-table", DataTable)
        table.clear()

        try:
            # If in remote mode, use API to list
            with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
                if ctx.is_remote:
                    client = ctx.get_api_client()
                    params = {"path": self.remote_cwd or ""}
                    res = client.get("/api/files/list", params=params)
                    res.raise_for_status()
                    data = res.json()
                    entries = data.get("files", [])

                    for item in entries:
                        name = item.get("name")
                        ftype = "dir" if item.get("type") == "directory" else "file"
                        size = str(item.get("size")) if item.get("size") is not None else "-"
                        mtime = item.get("modified_at") or "?"
                        # Normalize remote key: always use posix relative path without leading '/'
                        raw_path = item.get("path") or name
                        if raw_path.startswith('/'):
                            raw_path = raw_path.lstrip('/')
                        if self.remote_cwd:
                            normalized_key = f"{self.remote_cwd}/{name}" if name else self.remote_cwd
                        else:
                            normalized_key = raw_path
                        normalized_key = normalized_key.strip('/')

                        table.add_row(name, ftype, size, mtime, key=normalized_key)
                        try:
                            if normalized_key:
                                self._entry_types[str(normalized_key)] = ftype
                                # also register the plain name for convenience
                                self._entry_types[str(name)] = ftype
                        except Exception:
                            pass
                else:
                    # local listing
                    try:
                        cwd_rel = self.cwd.resolve()
                    except Exception:
                        cwd_rel = self.cwd

                    if not str(cwd_rel).startswith(str(self.storage_root)):
                        self.cwd = self.storage_root

                    entries = list(self.cwd.iterdir()) if self.cwd.exists() else []
                    entries.sort(key=lambda p: (not p.is_dir(), p.name.lower()))

                    for p in entries:
                        name = p.name
                        ftype = "dir" if p.is_dir() else "file"
                        try:
                            size = str(p.stat().st_size) if p.is_file() else "-"
                            from datetime import datetime
                            mtime_str = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                        except Exception:
                            size = "?"
                            mtime_str = "?"
                        key = str(p)
                        table.add_row(name, ftype, size, mtime_str, key=key)
                        try:
                            self._entry_types[key] = ftype
                        except Exception:
                            pass

            self.app.title = f"BaluHost NAS TUI - Files: {str(self.cwd)}"
        except Exception as e:
            self.notify(f"Error listing files: {e}", severity="error")

    def action_refresh(self) -> None:
        self.load_entries()

    def action_up(self) -> None:
        if self.mode == 'remote':
            if not self.remote_cwd:
                self.notify("At storage root", severity="information")
                return
            parts = self.remote_cwd.split('/') if self.remote_cwd else []
            parent = '/'.join(parts[:-1]) if len(parts) > 1 else ''
            self.remote_cwd = parent
            self.load_entries()
            return

        if self.cwd == self.storage_root:
            self.notify("At storage root", severity="information")
            return
        self.cwd = self.cwd.parent
        self.load_entries()

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        # Enter on a row: open dir or preview
        raw = event.row_key
        table = self.query_one("#files-table", DataTable)
        # Normalize key: DataTable may provide an index or a key
        if raw is None:
            return
        if isinstance(raw, int):
            try:
                key = table.row_keys[raw]
            except Exception:
                key = str(raw)
        else:
            key = raw
            # If the DataTable returns a RowKey wrapper, try to extract inner value
            if not isinstance(key, str):
                for attr in ("key", "value", "_key"):
                    try:
                        candidate = getattr(raw, attr, None)
                    except Exception:
                        candidate = None
                    if candidate is not None:
                        key = candidate
                        break
            # final fallback: stringify
            key = str(key)
            # If it looks like a RowKey repr, fallback to using the table's row_keys at cursor position
            if (key.startswith("<textual") or "RowKey" in key) and table.cursor_row is not None:
                try:
                    key = table.row_keys[table.cursor_row]
                except Exception:
                    key = str(key)

        if self.mode == 'auto':
            # try local first
            try:
                p = Path(key)
                if p.exists() and p.is_dir():
                    self.cwd = p
                    self.load_entries()
                    return
            except Exception:
                pass

        # Remote navigation: check our cached entry types
        if self.mode in ('remote', 'auto'):
            try:
                entry_type = self._entry_types.get(str(key))
                if entry_type == 'directory':
                    # navigate into remote directory
                    # ensure posix style path without leading /
                    self.remote_cwd = str(key).lstrip('/')
                    self.load_entries()
                    return
                elif entry_type == 'file':
                    # fall through to preview below (remote file)
                    pass
            except Exception:
                pass

        # If remote/local unresolved, try local path fallback
        try:
            p = Path(key)
            if p.exists() and p.is_dir():
                self.cwd = p
                self.load_entries()
                return
        except Exception:
            pass

        # Preview textual files when local
        try:
            p = Path(key)
            if p.exists() and p.is_file() and p.suffix.lower() in [".txt", ".log", ".md", ".conf", ".json"]:
                content = p.read_text(errors="ignore")
                preview = content[:8192]
                self.notify(Text(preview[:400] + ("..." if len(preview) > 400 else "")), severity="information")
                return
        except Exception:
            pass

        # Remote preview: attempt to stream a small portion and show if decodable
        if self.mode in ('remote', 'auto'):
            try:
                with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
                    if ctx.is_remote:
                        client = ctx.get_api_client()
                        remote_path = key.lstrip('/')
                        with client.stream('GET', f"/api/files/download/{remote_path}", timeout=30.0) as r:
                            r.raise_for_status()
                            # read up to 8KiB
                            chunks = []
                            total = 0
                            for chunk in r.iter_bytes():
                                chunks.append(chunk)
                                total += len(chunk)
                                if total >= 8192:
                                    break
                            data = b''.join(chunks)
                            try:
                                text = data.decode('utf-8', errors='ignore')
                            except Exception:
                                text = ''
                            if text:
                                preview = text[:8192]
                                self.notify(Text(preview[:400] + ("..." if len(preview) > 400 else "")), severity="information")
                                return
            except Exception as exc:
                self.notify(f"Remote preview failed: {exc}", severity="warning")

        self.notify("Preview unavailable. Use download (d) to fetch file.", severity="information")

    def action_download(self) -> None:
        table = self.query_one("#files-table", DataTable)
        if not table.cursor_row:
            self.notify("Select a file first", severity="warning")
            return
        key = table.row_keys[table.cursor_row]
        # Determine remote path vs local
        try:
            # If remote mode, key is remote posix path
            with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
                if ctx.is_remote:
                    client = ctx.get_api_client()
                    remote_path = key.lstrip('/')
                    # prepare downloads dir
                    downloads = Path.cwd() / 'downloads'
                    downloads.mkdir(parents=True, exist_ok=True)
                    local_dest = downloads / Path(remote_path).name
                    # stream download
                    with client.stream('GET', f"/api/files/download/{remote_path}", timeout=120.0) as r:
                        r.raise_for_status()
                        with open(local_dest, 'wb') as fh:
                            for chunk in r.iter_bytes():
                                fh.write(chunk)

                    self.notify(f"Downloaded {remote_path} -> {local_dest}", severity="information")
                    return
        except Exception as exc:
            # Fall back to local behavior
            self.notify(f"Remote download failed: {exc}", severity="error")

        # Local fallback: nothing to do (handled by selection preview)
        self.notify("Local download not implemented (use external copy)", severity="warning")

    def action_upload(self) -> None:
        # Upload a local file into the currently viewed remote directory
        table = self.query_one("#files-table", DataTable)
        # use upload-input value
        input_widget = self.query_one("#upload-input", Input)
        local_path_text = input_widget.value.strip() if input_widget else ""
        if not local_path_text:
            self.notify("Enter a local path in the upload input first", severity="warning")
            return

        local_path = Path(local_path_text)
        if not local_path.exists() or not local_path.is_file():
            self.notify("Local file not found", severity="error")
            return

        # determine target remote path (current remote cwd if remote mode)
        remote_dir = ''
        if self.mode == 'remote':
            remote_dir = self.remote_cwd or ''
        else:
            try:
                # calculate relative to storage root for local->remote upload
                if self.cwd != self.storage_root:
                    remote_dir = str(self.cwd.relative_to(self.storage_root).as_posix())
            except Exception:
                remote_dir = ''

        try:
            with get_context(mode=self.mode, server=self.server, token=self.token) as ctx:
                if ctx.is_remote:
                    client = ctx.get_api_client()
                    url = f"/api/files/upload"
                    files = {"files": (local_path.name, open(local_path, 'rb'))}
                    data = {"path": remote_dir}
                    res = client.post(url, files=files, data=data)
                    res.raise_for_status()
                    self.notify(f"Uploaded {local_path} -> /{remote_dir or ''}", severity="information")
                    self.load_entries()
                    return
        except Exception as exc:
            self.notify(f"Upload failed: {exc}", severity="error")

        self.notify("Upload not available in local mode", severity="warning")
