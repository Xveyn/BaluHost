from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from threading import Lock
from typing import Dict, Optional

from app.core.config import settings

ROOT_DIR = Path(settings.nas_storage_path).expanduser().resolve()
ROOT_DIR.mkdir(parents=True, exist_ok=True)
METADATA_FILE = ROOT_DIR / ".metadata.json"
_LOCK = Lock()


def _normalize_path(relative_path: str) -> str:
    if not relative_path:
        return ""
    normalized = Path(relative_path.strip("/")).as_posix()
    return normalized


def _load() -> Dict[str, Dict[str, str]]:
    if not METADATA_FILE.exists():
        return {}
    try:
        data = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): dict(v) for k, v in data.items() if isinstance(v, dict)}


def _save(data: Dict[str, Dict[str, str]]) -> None:
    METADATA_FILE.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def get_owner(relative_path: str) -> Optional[str]:
    key = _normalize_path(relative_path)
    with _LOCK:
        data = _load()
        entry = data.get(key, {})
    return entry.get("ownerId")


def set_owner(relative_path: str, owner_id: str) -> None:
    key = _normalize_path(relative_path)
    with _LOCK:
        data = _load()
        entry = data.get(key, {})
        entry["ownerId"] = owner_id
        data[key] = entry
        _save(data)


def clear_path(relative_path: str) -> None:
    key = _normalize_path(relative_path)
    with _LOCK:
        data = _load()
        keys_to_remove = [k for k in data if k == key or k.startswith(f"{key}/")]
        for candidate in keys_to_remove:
            data.pop(candidate, None)
        _save(data)


def move_path(old_path: str, new_path: str) -> None:
    old_key = _normalize_path(old_path)
    new_key = _normalize_path(new_path)
    if old_key == new_key:
        return
    with _LOCK:
        data = _load()
        updates: Dict[str, Dict[str, str]] = {}
        for key, value in list(data.items()):
            if key == old_key or key.startswith(f"{old_key}/"):
                suffix = key[len(old_key) :]
                candidate = f"{new_key}{suffix}" if suffix else new_key
                updates[candidate] = value
                data.pop(key, None)
        data.update(updates)
        if updates:
            _save(data)


def ensure_root_metadata() -> None:
    with _LOCK:
        if not METADATA_FILE.exists():
            _save({})
