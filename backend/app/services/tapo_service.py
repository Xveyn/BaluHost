"""Service layer for Tapo device CRUD operations.

Handles all database access for Tapo smart plug management,
keeping route handlers free of ORM logic.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.tapo_device import TapoDevice
from app.schemas.tapo import TapoDeviceCreate, TapoDeviceUpdate
from app.services.vpn.encryption import VPNEncryption

logger = logging.getLogger(__name__)


def get_device(db: Session, device_id: int) -> Optional[TapoDevice]:
    """Get a Tapo device by ID."""
    return db.query(TapoDevice).filter(TapoDevice.id == device_id).first()


def get_device_by_ip(db: Session, ip_address: str) -> Optional[TapoDevice]:
    """Get a Tapo device by IP address."""
    return db.query(TapoDevice).filter(TapoDevice.ip_address == ip_address).first()


def list_devices(db: Session) -> list[TapoDevice]:
    """List all Tapo devices, newest first."""
    return db.query(TapoDevice).order_by(TapoDevice.created_at.desc()).all()


def list_active_devices(db: Session) -> list[TapoDevice]:
    """List all active Tapo devices."""
    return db.query(TapoDevice).filter(TapoDevice.is_active == True).all()  # noqa: E712


def create_device(
    db: Session, data: TapoDeviceCreate, user_id: int
) -> TapoDevice:
    """Create a new Tapo device with encrypted credentials.

    Raises:
        ValueError: If a device with the same IP already exists or encryption fails.
    """
    existing = get_device_by_ip(db, data.ip_address)
    if existing:
        raise ValueError(f"Device with IP {data.ip_address} already exists")

    email_encrypted = VPNEncryption.encrypt_key(data.email)
    password_encrypted = VPNEncryption.encrypt_key(data.password)

    device = TapoDevice(
        name=data.name,
        device_type=data.device_type,
        ip_address=data.ip_address,
        email_encrypted=email_encrypted,
        password_encrypted=password_encrypted,
        is_active=True,
        is_monitoring=data.is_monitoring,
        created_by_user_id=user_id,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def update_device(
    db: Session, device: TapoDevice, data: TapoDeviceUpdate
) -> TapoDevice:
    """Update a Tapo device. Partial updates are supported.

    Raises:
        ValueError: If credential encryption fails.
    """
    update_data = data.model_dump(exclude_unset=True)

    # Encrypt credentials if provided
    if "email" in update_data:
        device.email_encrypted = VPNEncryption.encrypt_key(update_data.pop("email"))  # type: ignore[assignment]
    if "password" in update_data:
        device.password_encrypted = VPNEncryption.encrypt_key(update_data.pop("password"))  # type: ignore[assignment]

    # Apply remaining updates
    for field, value in update_data.items():
        setattr(device, field, value)

    db.commit()
    db.refresh(device)
    return device


def delete_device(db: Session, device: TapoDevice) -> None:
    """Delete a Tapo device."""
    db.delete(device)
    db.commit()
