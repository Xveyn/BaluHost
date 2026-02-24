"""Path utilities for file operations — leaf module with no files/ imports.

Provides storage root, well-known directory names, path-related exceptions,
and pure path helpers.  Intentionally free of database or service imports so
it can be used as a dependency leaf in the files/ package graph.
"""
from __future__ import annotations

from pathlib import Path

from app.core.config import settings

# ── Storage root ──────────────────────────────────────────────────────────────

ROOT_DIR = Path(settings.nas_storage_path).expanduser().resolve()
ROOT_DIR.mkdir(parents=True, exist_ok=True)

# ── Well-known directory names ────────────────────────────────────────────────

SHARED_DIR_NAME = "Shared"
SHARED_WITH_ME_DIR = "Shared with me"
SYSTEM_DIR_NAME = ".system"
SYSTEM_DIRS = {".system", "lost+found", ".tmp"}
SYSTEM_DIR_PREFIXES = (".Trash-",)


# ── Exceptions ────────────────────────────────────────────────────────────────

class FileAccessError(Exception):
    """Raised when an operation would leave the permitted storage sandbox."""


class QuotaExceededError(Exception):
    """Raised when an operation would exceed the configured NAS quota."""


class SystemDirectoryError(FileAccessError):
    """Raised when an operation targets a protected system directory."""


# ── Pure path helpers ─────────────────────────────────────────────────────────

def is_system_directory(name: str) -> bool:
    """Check if a directory name is a filesystem-managed system directory."""
    return name in SYSTEM_DIRS or any(name.startswith(p) for p in SYSTEM_DIR_PREFIXES)


def is_in_shared_dir(relative_path: str) -> bool:
    """Check if a relative path is inside (or is) the Shared directory."""
    return relative_path == SHARED_DIR_NAME or relative_path.startswith(f"{SHARED_DIR_NAME}/")


def _resolve_path(relative_path: str) -> Path:
    """Resolve a user-supplied relative path against ROOT_DIR with sandbox enforcement."""
    normalized = Path(relative_path.strip("/")) if relative_path else Path()
    target = (ROOT_DIR / normalized).resolve()
    try:
        target.relative_to(ROOT_DIR)
    except ValueError as exc:  # pragma: no cover - simple guard
        raise FileAccessError("Path is outside of the NAS storage boundary") from exc
    return target


def _relative_posix(path: Path) -> str:
    """Return the POSIX-style relative path from ROOT_DIR."""
    return path.relative_to(ROOT_DIR).as_posix()


def get_absolute_path(relative_path: str) -> Path:
    """Expose resolved paths for read-only operations like downloads."""
    return _resolve_path(relative_path)
