"""Service for the Desktop Device Code Flow (BaluDesk pairing)."""

import secrets
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.desktop_pairing import DesktopPairingCode
from app.models.sync_state import SyncState
from app.models.user import User
from app.core.security import create_access_token, create_refresh_token
from app.schemas.desktop_pairing import (
    DeviceCodeRequest,
    DeviceCodeResponse,
    DeviceCodePollResponse,
    DeviceCodeApprovalInfo,
)

logger = logging.getLogger(__name__)

# Constants
CODE_LIFETIME_MINUTES = 10
CLEANUP_THRESHOLD_HOURS = 1
MAX_FAILED_ATTEMPTS = 5
POLL_INTERVAL_SECONDS = 5


class DesktopPairingService:
    """Handles the Device Code Flow for BaluDesk pairing."""

    @staticmethod
    def request_device_code(
        db: Session,
        request: DeviceCodeRequest,
        server_url: str,
    ) -> DeviceCodeResponse:
        """Generate a new device code + user code pair.

        Args:
            db: Database session
            request: Device info from BaluDesk
            server_url: Base URL of the server for verification_url

        Returns:
            DeviceCodeResponse with codes and metadata
        """
        DesktopPairingService._cleanup_expired(db)

        user_code = DesktopPairingService._generate_unique_user_code(db)
        device_code = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=CODE_LIFETIME_MINUTES)

        pairing = DesktopPairingCode(
            device_code=device_code,
            user_code=user_code,
            device_name=request.device_name,
            device_id=request.device_id,
            platform=request.platform,
            status="pending",
            expires_at=expires_at,
        )
        db.add(pairing)
        db.commit()

        verification_url = f"{server_url.rstrip('/')}/devices?pair=1"

        logger.info(
            "Desktop pairing code created for device %s (%s)",
            request.device_name,
            request.platform,
        )

        return DeviceCodeResponse(
            device_code=device_code,
            user_code=user_code,
            verification_url=verification_url,
            expires_in=CODE_LIFETIME_MINUTES * 60,
            interval=POLL_INTERVAL_SECONDS,
        )

    @staticmethod
    def poll_device_code(db: Session, device_code: str) -> DeviceCodePollResponse:
        """Check the status of a pairing request.

        Returns tokens on approval, otherwise the current status.
        """
        pairing = db.query(DesktopPairingCode).filter(
            DesktopPairingCode.device_code == device_code,
        ).first()

        if not pairing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid device code",
            )

        # Check expiration
        expires_at = pairing.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            return DeviceCodePollResponse(status="expired")

        if pairing.status == "denied":
            return DeviceCodePollResponse(status="denied")

        if pairing.status == "pending":
            return DeviceCodePollResponse(status="authorization_pending")

        if pairing.status == "approved":
            # Fetch approving user
            user = db.query(User).filter(User.id == pairing.user_id).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Approving user not found",
                )

            # Generate tokens
            access_token = create_access_token(user)
            refresh_token, _jti = create_refresh_token(user)

            # Create SyncState entry (same as register-desktop)
            existing = db.query(SyncState).filter(
                SyncState.user_id == user.id,
                SyncState.device_id == pairing.device_id,
            ).first()
            if existing:
                existing.device_name = pairing.device_name
                existing.last_sync = datetime.now(timezone.utc)
            else:
                sync_state = SyncState(
                    user_id=user.id,
                    device_id=pairing.device_id,
                    device_name=pairing.device_name,
                )
                db.add(sync_state)

            # One-time delivery — delete the pairing record
            db.delete(pairing)
            db.commit()

            logger.info(
                "Desktop pairing completed: device %s paired to user %s",
                pairing.device_name,
                user.username,
            )

            return DeviceCodePollResponse(
                status="approved",
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="bearer",
                user={
                    "id": user.id,
                    "username": user.username,
                    "email": user.email or "",
                    "role": user.role,
                },
            )

        return DeviceCodePollResponse(status="authorization_pending")

    @staticmethod
    def verify_code(db: Session, user_code: str) -> DeviceCodeApprovalInfo:
        """Look up a user_code and return device details for the approval screen.

        Increments failed_attempts on miss; auto-denies after MAX_FAILED_ATTEMPTS.
        """
        pairing = db.query(DesktopPairingCode).filter(
            DesktopPairingCode.user_code == user_code,
            DesktopPairingCode.status == "pending",
        ).first()

        if not pairing:
            # Increment failed_attempts on any pending code that shares the
            # same *recent* window — but since we don't know which code the
            # user meant, we simply report "not found".
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid or expired code",
            )

        # Check expiration
        expires_at = pairing.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Code has expired",
            )

        # Check brute-force limit
        if pairing.failed_attempts >= MAX_FAILED_ATTEMPTS:
            pairing.status = "denied"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed attempts",
            )

        return DeviceCodeApprovalInfo(
            device_name=pairing.device_name,
            device_id=pairing.device_id,
            platform=pairing.platform,
            created_at=pairing.created_at,
            expires_at=pairing.expires_at,
        )

    @staticmethod
    def increment_failed_attempts(db: Session, user_code: str) -> None:
        """Increment the failed_attempts counter for brute-force tracking."""
        pairing = db.query(DesktopPairingCode).filter(
            DesktopPairingCode.user_code == user_code,
            DesktopPairingCode.status == "pending",
        ).first()
        if pairing:
            pairing.failed_attempts += 1
            if pairing.failed_attempts >= MAX_FAILED_ATTEMPTS:
                pairing.status = "denied"
            db.commit()

    @staticmethod
    def approve_code(db: Session, user_code: str, user_id: int) -> None:
        """Approve a pending pairing code."""
        pairing = db.query(DesktopPairingCode).filter(
            DesktopPairingCode.user_code == user_code,
            DesktopPairingCode.status == "pending",
        ).first()

        if not pairing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid or expired code",
            )

        expires_at = pairing.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Code has expired",
            )

        pairing.status = "approved"
        pairing.user_id = user_id
        pairing.approved_at = datetime.now(timezone.utc)
        db.commit()

        logger.info("Desktop pairing code approved by user_id=%s", user_id)

    @staticmethod
    def deny_code(db: Session, user_code: str) -> None:
        """Deny a pending pairing code."""
        pairing = db.query(DesktopPairingCode).filter(
            DesktopPairingCode.user_code == user_code,
            DesktopPairingCode.status == "pending",
        ).first()

        if not pairing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid or expired code",
            )

        pairing.status = "denied"
        db.commit()

        logger.info("Desktop pairing code denied")

    @staticmethod
    def _generate_unique_user_code(db: Session) -> str:
        """Generate a 6-digit numeric code that is unique among active codes."""
        for _ in range(50):
            code = f"{secrets.randbelow(1_000_000):06d}"
            exists = db.query(DesktopPairingCode).filter(
                DesktopPairingCode.user_code == code,
                DesktopPairingCode.status == "pending",
                DesktopPairingCode.expires_at > datetime.now(timezone.utc),
            ).first()
            if not exists:
                return code
        # Extremely unlikely — 1M codes and only a handful active at once
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to generate unique code, please try again",
        )

    @staticmethod
    def _cleanup_expired(db: Session) -> None:
        """Delete pairing codes that expired more than 1 hour ago."""
        threshold = datetime.now(timezone.utc) - timedelta(hours=CLEANUP_THRESHOLD_HOURS)
        deleted = db.query(DesktopPairingCode).filter(
            DesktopPairingCode.expires_at < threshold,
        ).delete(synchronize_session=False)
        if deleted:
            db.commit()
            logger.debug("Cleaned up %d expired desktop pairing codes", deleted)
