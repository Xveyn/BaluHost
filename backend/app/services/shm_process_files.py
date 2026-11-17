"""Per-process JSON files in the SHM directory.

Some facts live in every API process and are needed summed up in one of them:
HTTP requests per minute (`power/http_activity.py`, #823) and uploads in
flight (`upload_activity.py`, #834). Each process writes its own figure to
``<prefix><pid>.json`` and reads the files of all the others.

This module is the file mechanics only — it knows nothing about what a file
means. Both functions take the directory as an argument and never raise: a
counter must not fail the request that feeds it.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def write_process_file(directory: Path, prefix: str, pid: int, payload: dict[str, Any]) -> None:
    """Atomically write *payload* to ``<prefix><pid>.json`` in *directory*.

    Temp file plus `os.replace`, so a reader never sees half a file. Creates
    the directory if it is missing.
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(directory), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f)
            os.replace(tmp_path, str(directory / f"{prefix}{pid}.json"))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:
        logger.debug("Writing %s%s.json failed: %s", prefix, pid, exc)


def read_other_process_files(
    directory: Path,
    prefix: str,
    own_pid: int,
    now: float,
    stale_after: float,
) -> list[dict[str, Any]]:
    """The JSON objects every *other* process wrote under *prefix*.

    - The caller's own file (``own_pid``) is skipped: it has that figure in
      memory, and reading it back would count it twice.
    - A file whose mtime is more than *stale_after* seconds before *now* was
      left behind by a process that is gone; it is removed (best effort).
    - Symlinks are neither read nor removed: only regular files are ever
      written here, and a link must not lead out of the directory.
    - Anything unreadable, or not a JSON object, is ignored.
    """
    name_re = re.compile(re.escape(prefix) + r"\d+\.json")
    own_name = f"{prefix}{own_pid}.json"
    try:
        entries = list(directory.iterdir())
    except OSError:
        return []
    found: list[dict[str, Any]] = []
    for path in entries:
        name = path.name
        if not name_re.fullmatch(name) or name == own_name:
            continue
        try:
            if path.is_symlink():
                continue
            if now - path.stat().st_mtime > stale_after:
                path.unlink(missing_ok=True)
                continue
            with open(path, "r") as f:
                data = json.load(f)
        except Exception as exc:
            logger.debug("Ignoring unreadable %s: %s", name, exc)
            continue
        if isinstance(data, dict):
            found.append(data)
    return found
