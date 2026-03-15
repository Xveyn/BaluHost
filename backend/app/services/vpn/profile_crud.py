"""CRUD operations for VPN profiles.

Keeps all database access out of the route handlers.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models import VPNProfile, VPNType, ServerProfile
from app.services.vpn.encryption import VPNEncryption

logger = logging.getLogger(__name__)


def list_user_profiles(db: Session, user_id: int) -> list[VPNProfile]:
    """List VPN profiles owned by a user, newest first."""
    return (
        db.query(VPNProfile)
        .filter(VPNProfile.user_id == user_id)
        .order_by(VPNProfile.created_at.desc())
        .all()
    )


def get_user_profile(
    db: Session, profile_id: int, user_id: int
) -> Optional[VPNProfile]:
    """Get a VPN profile by ID, scoped to the given user."""
    return (
        db.query(VPNProfile)
        .filter(VPNProfile.id == profile_id, VPNProfile.user_id == user_id)
        .first()
    )


def create_profile(
    db: Session,
    *,
    user_id: int,
    name: str,
    vpn_type: VPNType,
    config_content: str,
    certificate_content: Optional[str] = None,
    private_key_content: Optional[str] = None,
    auto_connect: bool = False,
    description: str = "",
) -> VPNProfile:
    """Create a VPN profile with encrypted config/cert/key."""
    encrypted_config = VPNEncryption.encrypt_vpn_config(config_content)
    encrypted_cert = (
        VPNEncryption.encrypt_vpn_config(certificate_content)
        if certificate_content
        else None
    )
    encrypted_key = (
        VPNEncryption.encrypt_vpn_config(private_key_content)
        if private_key_content
        else None
    )

    profile = VPNProfile(
        user_id=user_id,
        name=name,
        vpn_type=vpn_type,
        config_file_encrypted=encrypted_config,
        certificate_encrypted=encrypted_cert,
        private_key_encrypted=encrypted_key,
        auto_connect=auto_connect,
        description=description,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    logger.info("VPN profile '%s' created by user %d", name, user_id)
    return profile


def update_profile_fields(
    db: Session,
    profile: VPNProfile,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    auto_connect: Optional[bool] = None,
    config_content: Optional[str] = None,
    certificate_content: Optional[str] = None,
    private_key_content: Optional[str] = None,
    user_id: int,
) -> VPNProfile:
    """Update fields on a VPN profile. Only non-None values are applied."""
    if name is not None:
        profile.name = name  # type: ignore[assignment]
    if description is not None:
        profile.description = description  # type: ignore[assignment]
    if auto_connect is not None:
        profile.auto_connect = auto_connect  # type: ignore[assignment]
    if config_content is not None:
        profile.config_file_encrypted = VPNEncryption.encrypt_vpn_config(config_content)  # type: ignore[assignment]
    if certificate_content is not None:
        profile.certificate_encrypted = VPNEncryption.encrypt_vpn_config(certificate_content)  # type: ignore[assignment]
    if private_key_content is not None:
        profile.private_key_encrypted = VPNEncryption.encrypt_vpn_config(private_key_content)  # type: ignore[assignment]

    db.commit()
    db.refresh(profile)

    logger.info("VPN profile %s updated by user %d", profile.id, user_id)
    return profile


def delete_profile(db: Session, profile: VPNProfile, user_id: int) -> None:
    """Delete a VPN profile and clear references from server profiles."""
    profile_id = profile.id
    db.delete(profile)
    db.commit()
    logger.info("VPN profile %s deleted by user %d", profile_id, user_id)
