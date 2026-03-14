"""Service layer for Server Profile management.

Handles all database operations for server profiles, keeping
routes free of ORM logic.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import ServerProfile
from app.schemas.server_profile import ServerProfileCreate, ServerProfileUpdate
from app.services.vpn.encryption import VPNEncryption

logger = logging.getLogger(__name__)


def list_all_profiles(db: Session) -> list[ServerProfile]:
    """List all server profiles (for public endpoint)."""
    return db.query(ServerProfile).all()


def list_user_profiles(db: Session, user_id: int) -> list[ServerProfile]:
    """List server profiles owned by a specific user, newest first."""
    return (
        db.query(ServerProfile)
        .filter(ServerProfile.user_id == user_id)
        .order_by(ServerProfile.created_at.desc())
        .all()
    )


def get_user_profile(
    db: Session, profile_id: int, user_id: int
) -> Optional[ServerProfile]:
    """Get a server profile by ID, scoped to the given user."""
    return (
        db.query(ServerProfile)
        .filter(ServerProfile.id == profile_id, ServerProfile.user_id == user_id)
        .first()
    )


def create_profile(
    db: Session, user_id: int, data: ServerProfileCreate
) -> ServerProfile:
    """Create a new server profile with encrypted SSH key.

    Raises:
        ValueError: If SSH key encryption fails.
    """
    encrypted_key = VPNEncryption.encrypt_ssh_private_key(data.ssh_private_key)

    profile = ServerProfile(
        user_id=user_id,
        name=data.name,
        ssh_host=data.ssh_host,
        ssh_port=data.ssh_port,
        ssh_username=data.ssh_username,
        ssh_key_encrypted=encrypted_key,
        vpn_profile_id=data.vpn_profile_id,
        power_on_command=data.power_on_command,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    logger.info("Server profile '%s' created by user %d", data.name, user_id)
    return profile


def update_profile(
    db: Session, profile: ServerProfile, data: ServerProfileUpdate, user_id: int
) -> ServerProfile:
    """Update an existing server profile.

    Raises:
        ValueError: If SSH key encryption fails.
    """
    if data.name is not None:
        profile.name = data.name  # type: ignore[assignment]
    if data.ssh_host is not None:
        profile.ssh_host = data.ssh_host  # type: ignore[assignment]
    if data.ssh_port is not None:
        profile.ssh_port = data.ssh_port  # type: ignore[assignment]
    if data.ssh_username is not None:
        profile.ssh_username = data.ssh_username  # type: ignore[assignment]
    if data.ssh_private_key is not None:
        profile.ssh_key_encrypted = VPNEncryption.encrypt_ssh_private_key(  # type: ignore[assignment]
            data.ssh_private_key
        )
    if data.vpn_profile_id is not None:
        profile.vpn_profile_id = data.vpn_profile_id  # type: ignore[assignment]
    if data.power_on_command is not None:
        profile.power_on_command = data.power_on_command  # type: ignore[assignment]

    db.commit()
    db.refresh(profile)

    logger.info("Server profile %s updated by user %d", profile.id, user_id)
    return profile


def delete_profile(db: Session, profile: ServerProfile, user_id: int) -> None:
    """Delete a server profile."""
    profile_id = profile.id
    db.delete(profile)
    db.commit()
    logger.info("Server profile %s deleted by user %d", profile_id, user_id)


def mark_last_used(db: Session, profile: ServerProfile) -> None:
    """Update the last_used timestamp on a profile."""
    profile.last_used = datetime.now(timezone.utc)  # type: ignore[assignment]
    db.commit()
