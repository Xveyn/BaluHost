"""Log lines must survive a console that cannot encode them (#495).

On Windows, stdout is often cp1252 (pipes, Git Bash, IDE runners). A log call
with a character outside it made StreamHandler raise UnicodeEncodeError;
logging swallowed it via handleError(), printed a traceback and DROPPED the
line - typically an error path marked with an emoji.

Two layers, tested separately:
- setup_logging() makes the console stream escape what it can't encode, so no
  line is lost, whatever a future call site writes.
- Log message literals stay cp1252-encodable, so the escaped form never has to
  show up in the first place (the ratchet against the pattern coming back).
"""
import ast
import io
import logging
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
SCANNED_DIRS = ("app", "baluhost_tui", "baluhost_tray", "scripts")
_LOG_METHODS = {"debug", "info", "warning", "error", "critical", "exception"}


@pytest.fixture
def restore_root_logger():
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    yield
    root.handlers[:] = saved[0]
    root.setLevel(saved[1])


def test_unencodable_line_is_escaped_not_dropped(monkeypatch, restore_root_logger):
    # sys.stdout is swapped here, not in a fixture: pytest's output capture
    # re-installs its own sys.stdout between setup and call, which would
    # silently undo a fixture's patch.
    buf = io.BytesIO()
    monkeypatch.setattr(
        sys, "stdout", io.TextIOWrapper(buf, encoding="cp1252", errors="strict", write_through=True)
    )
    from app.core.logging_config import setup_logging

    setup_logging()
    logging.getLogger("test.encoding").warning("[Scheduler] ❌ Backup failed: disk full")

    out = buf.getvalue().decode("cp1252")
    assert "Logging configured" in out  # control: the stream is really the handler's
    assert "Backup failed: disk full" in out
    assert "\\u274c" in out


def _unencodable_log_literals() -> list[str]:
    found = []
    for d in SCANNED_DIRS:
        for path in (BACKEND / d).rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in _LOG_METHODS and node.args):
                    continue
                msg = node.args[0]
                if isinstance(msg, ast.Constant) and isinstance(msg.value, str):
                    text = msg.value
                elif isinstance(msg, ast.JoinedStr):
                    text = "".join(
                        v.value for v in msg.values
                        if isinstance(v, ast.Constant) and isinstance(v.value, str)
                    )
                else:
                    continue
                bad = sorted({c for c in text if not c.encode("cp1252", "ignore")})
                if bad:
                    rel = path.relative_to(BACKEND)
                    found.append(f"{rel}:{node.lineno} {[hex(ord(c)) for c in bad]}")
    return found


def test_log_messages_are_cp1252_encodable():
    offenders = _unencodable_log_literals()
    assert offenders == [], (
        "log message literals with characters a cp1252 console can't show "
        "(use ASCII: '->' for arrows, words instead of emoji):\n" + "\n".join(offenders)
    )
