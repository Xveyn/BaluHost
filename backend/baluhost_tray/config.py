"""Token store for the tray.

Separate from baluhost_tui.config on purpose: that one holds a single token
string, the device code flow yields an access *and* a refresh token, and two
programs writing the same file would clobber each other.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

TOKEN_DIR = Path.home() / ".baluhost"
TOKEN_FILE = TOKEN_DIR / "tray-tokens.json"


@dataclass(frozen=True)
class Tokens:
    access: str
    refresh: str


def save_tokens(tokens: Tokens) -> None:
    """Write tokens atomically, owner-only from the first byte.

    write_text() + chmod would create the file world-readable for the length
    of the write, with a token inside it. On a multi-user box that is a real
    window, so the mode goes into the open() call instead.
    """
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(TOKEN_DIR, 0o700)

    payload = json.dumps(asdict(tokens)).encode("utf-8")
    # Atomar: erst in eine Temp-Datei im selben Verzeichnis, dann ersetzen.
    # Ein Absturz mitten im Schreiben darf das rotierte Refresh-Token nicht
    # halb ueberschrieben zuruecklassen — es waere die einzige Kopplung.
    tmp = TOKEN_DIR / f".tray-tokens.{os.getpid()}.tmp"
    tmp.unlink(missing_ok=True)  # Rest eines frueheren Absturzes derselben PID
    try:
        fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, TOKEN_FILE)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def load_tokens() -> Tokens | None:
    """Read tokens, or None if absent, unreadable or incomplete."""
    if not TOKEN_FILE.exists():
        return None
    try:
        raw = json.loads(TOKEN_FILE.read_text())
        return Tokens(access=raw["access"], refresh=raw["refresh"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def clear_tokens() -> None:
    """Remove the token file. Idempotent."""
    TOKEN_FILE.unlink(missing_ok=True)
