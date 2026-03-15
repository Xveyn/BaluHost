"""Service layer for plugin database operations.

Handles all InstalledPlugin CRUD, keeping route handlers free of ORM logic.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.plugin import InstalledPlugin

logger = logging.getLogger(__name__)


def get_installed_plugin(db: Session, name: str) -> Optional[InstalledPlugin]:
    """Get an installed plugin record by name."""
    return db.query(InstalledPlugin).filter(InstalledPlugin.name == name).first()


def get_enabled_plugin(db: Session, name: str) -> Optional[InstalledPlugin]:
    """Get an installed plugin record that is enabled."""
    return (
        db.query(InstalledPlugin)
        .filter(InstalledPlugin.name == name, InstalledPlugin.is_enabled == True)  # noqa: E712
        .first()
    )


def enable_plugin(
    db: Session,
    *,
    name: str,
    version: str,
    display_name: str,
    permissions: list[str],
    default_config: dict,
    installed_by: str,
) -> InstalledPlugin:
    """Enable a plugin — create or update the DB record.

    Returns the updated InstalledPlugin record (already committed).
    """
    record = get_installed_plugin(db, name)

    if record is None:
        record = InstalledPlugin(
            name=name,
            version=version,
            display_name=display_name,
            is_enabled=True,
            granted_permissions=permissions,
            config=default_config,
            installed_by=installed_by,
            enabled_at=datetime.now(timezone.utc),
        )
        db.add(record)
    else:
        record.is_enabled = True
        record.granted_permissions = permissions
        record.enabled_at = datetime.now(timezone.utc)
        record.disabled_at = None

    db.commit()
    return record


def disable_plugin_record(db: Session, name: str) -> None:
    """Mark a plugin as disabled in the database."""
    record = get_installed_plugin(db, name)
    if record:
        record.is_enabled = False
        record.disabled_at = datetime.now(timezone.utc)
        db.commit()


def rollback_enable(db: Session, name: str) -> None:
    """Rollback an enable — set is_enabled back to False."""
    record = get_installed_plugin(db, name)
    if record:
        record.is_enabled = False
        db.commit()


def update_config(
    db: Session,
    *,
    name: str,
    validated_config: dict,
    version: str = "",
    display_name: str = "",
    installed_by: str = "",
) -> InstalledPlugin:
    """Update (or create) the plugin config record.

    Returns the InstalledPlugin record (already committed).
    """
    record = get_installed_plugin(db, name)

    if record is None:
        record = InstalledPlugin(
            name=name,
            version=version,
            display_name=display_name,
            is_enabled=False,
            granted_permissions=[],
            config=validated_config,
            installed_by=installed_by,
        )
        db.add(record)
    else:
        record.config = validated_config

    db.commit()
    return record


def uninstall_plugin(db: Session, name: str) -> bool:
    """Remove the installed plugin record.

    Returns True if a record was deleted, False if not found.
    """
    record = get_installed_plugin(db, name)
    if not record:
        return False

    db.delete(record)
    db.commit()
    return True
