"""Quota-checked, per-(plugin, user) key-value store for plugin UIs."""
import json
from typing import Any, Tuple

from sqlalchemy.orm import Session

from app.models.plugin_storage import PluginStorage

MAX_VALUE_BYTES = 64 * 1024
MAX_KEYS = 100


class StorageQuotaError(Exception):
    """Raised when a write would exceed the per-(plugin, user) quota."""
    code = "storage_quota"


def get_value(db: Session, plugin_name: str, user_id: int, key: str) -> Tuple[bool, Any]:
    """Return (found, value) for the given (plugin_name, user_id, key) triple."""
    row = (
        db.query(PluginStorage)
        .filter_by(plugin_name=plugin_name, user_id=user_id, key=key)
        .one_or_none()
    )
    return (True, row.value) if row is not None else (False, None)


def list_keys(db: Session, plugin_name: str, user_id: int) -> list[str]:
    """Return all keys stored for (plugin_name, user_id), sorted alphabetically."""
    rows = (
        db.query(PluginStorage.key)
        .filter_by(plugin_name=plugin_name, user_id=user_id)
        .order_by(PluginStorage.key)
        .all()
    )
    return [r[0] for r in rows]


def set_value(db: Session, plugin_name: str, user_id: int, key: str, value: Any) -> None:
    """Store value under key for (plugin_name, user_id).

    Raises:
        StorageQuotaError: if the serialized value exceeds MAX_VALUE_BYTES,
            or if the user already has MAX_KEYS entries for this plugin.
    """
    serialized = json.dumps(value)
    if len(serialized.encode("utf-8")) > MAX_VALUE_BYTES:
        raise StorageQuotaError(f"value exceeds {MAX_VALUE_BYTES} bytes")

    row = (
        db.query(PluginStorage)
        .filter_by(plugin_name=plugin_name, user_id=user_id, key=key)
        .one_or_none()
    )
    if row is None:
        count = (
            db.query(PluginStorage)
            .filter_by(plugin_name=plugin_name, user_id=user_id)
            .count()
        )
        if count >= MAX_KEYS:
            raise StorageQuotaError(f"key limit {MAX_KEYS} reached")
        row = PluginStorage(plugin_name=plugin_name, user_id=user_id, key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()


def delete_value(db: Session, plugin_name: str, user_id: int, key: str) -> bool:
    """Delete the entry for (plugin_name, user_id, key).

    Returns True if the entry existed and was deleted, False if it was not found.
    """
    row = (
        db.query(PluginStorage)
        .filter_by(plugin_name=plugin_name, user_id=user_id, key=key)
        .one_or_none()
    )
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
