"""Utility script to wipe the dev storage sandbox.

Usage::

    python -m scripts.reset_dev_storage

The script respects the configured ``NAS_MODE`` and refuses to run when the
backend is not in development mode to avoid destructive operations in other
environments.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.core.config import settings
from app.services import files as file_service


def reset_dev_storage() -> None:
    if not settings.is_dev_mode:
        raise RuntimeError("reset_dev_storage can only run in dev mode")

    root = Path(settings.nas_storage_path).expanduser().resolve()
    if not root.exists():
        return

    for child in root.iterdir():
        target = root / child.name
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()


def main() -> None:
    reset_dev_storage()


if __name__ == "__main__":
    main()
