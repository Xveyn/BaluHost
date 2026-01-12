"""
Token service for managing refresh tokens with revocation support.

✅ Security Fix #6: Implements refresh token revocation to prevent
compromised tokens from being used indefinitely.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List
import logging

from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken
from app.models.user import User

logger = logging.getLogger(__name__)


class TokenService:
    """Service for managing refresh tokens with revocation support."""

    @staticmethod
    def store_refresh_token(
        db: Session,
        jti: str,
        user_id: int,
        token: str,
        expires_at: datetime,
        device_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> RefreshToken:
        """
        Store a refresh token in the database.

        Args:
            db: Database session
            jti: JWT ID (unique identifier for this token)
            user_id: User ID who owns this token
            token: The plaintext refresh token (will be hashed)
            expires_at: When this token expires
            device_id: Optional device identifier for mobile/desktop clients
            ip_address: IP address where token was issued
            user_agent: User agent string from request

        Returns:
            RefreshToken model instance
        """
        token_hash = RefreshToken.hash_token(token)

        refresh_token = RefreshToken(
            jti=jti,
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            device_id=device_id,
            created_ip=ip_address,
            last_used_ip=ip_address,
            user_agent=user_agent,
            revoked=False,
        )

        db.add(refresh_token)
        db.commit()
        db.refresh(refresh_token)

        logger.info(f"Stored refresh token for user_id={user_id}, jti={jti}, device_id={device_id}")
        return refresh_token

    @staticmethod
    def get_token_by_jti(db: Session, jti: str) -> Optional[RefreshToken]:
        """
        Retrieve a refresh token by its JTI.

        Args:
            db: Database session
            jti: JWT ID to lookup

        Returns:
            RefreshToken if found, None otherwise
        """
        return db.query(RefreshToken).filter(RefreshToken.jti == jti).first()

    @staticmethod
    def is_token_revoked(db: Session, jti: str) -> bool:
        """
        Check if a refresh token has been revoked.

        Args:
            db: Database session
            jti: JWT ID to check

        Returns:
            True if token is revoked or not found, False if token is valid
        """
        token = TokenService.get_token_by_jti(db, jti)
        if not token:
            logger.warning(f"Token not found in database: jti={jti}")
            return True  # Unknown token = revoked

        return not token.is_valid()

    @staticmethod
    def revoke_token(
        db: Session,
        jti: str,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Revoke a specific refresh token.

        Args:
            db: Database session
            jti: JWT ID to revoke
            reason: Optional reason for revocation

        Returns:
            True if token was revoked, False if not found
        """
        token = TokenService.get_token_by_jti(db, jti)
        if not token:
            logger.warning(f"Cannot revoke token - not found: jti={jti}")
            return False

        token.revoke(reason=reason)
        db.commit()

        logger.info(f"Revoked refresh token: jti={jti}, reason={reason}")
        return True

    @staticmethod
    def revoke_all_user_tokens(
        db: Session,
        user_id: int,
        reason: Optional[str] = None,
    ) -> int:
        """
        Revoke all refresh tokens for a user (e.g., on password change).

        Args:
            db: Database session
            user_id: User whose tokens to revoke
            reason: Optional reason for revocation

        Returns:
            Number of tokens revoked
        """
        tokens = db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked == False
        ).all()

        count = 0
        for token in tokens:
            token.revoke(reason=reason)
            count += 1

        db.commit()

        logger.info(f"Revoked {count} refresh tokens for user_id={user_id}, reason={reason}")
        return count

    @staticmethod
    def revoke_device_tokens(
        db: Session,
        device_id: str,
        reason: Optional[str] = None,
    ) -> int:
        """
        Revoke all refresh tokens for a specific device.

        Args:
            db: Database session
            device_id: Device whose tokens to revoke
            reason: Optional reason for revocation

        Returns:
            Number of tokens revoked
        """
        tokens = db.query(RefreshToken).filter(
            RefreshToken.device_id == device_id,
            RefreshToken.revoked == False
        ).all()

        count = 0
        for token in tokens:
            token.revoke(reason=reason)
            count += 1

        db.commit()

        logger.info(f"Revoked {count} refresh tokens for device_id={device_id}, reason={reason}")
        return count

    @staticmethod
    def update_token_usage(
        db: Session,
        jti: str,
        ip_address: Optional[str] = None,
    ) -> bool:
        """
        Update last_used_at timestamp for a token.

        Args:
            db: Database session
            jti: JWT ID to update
            ip_address: IP address of the request

        Returns:
            True if updated, False if token not found
        """
        token = TokenService.get_token_by_jti(db, jti)
        if not token:
            return False

        token.last_used_at = datetime.now(timezone.utc)
        if ip_address:
            token.last_used_ip = ip_address

        db.commit()
        return True

    @staticmethod
    def cleanup_expired_tokens(db: Session) -> int:
        """
        Delete expired tokens from the database (periodic cleanup task).

        Args:
            db: Database session

        Returns:
            Number of tokens deleted
        """
        now = datetime.now(timezone.utc)

        # Delete tokens that expired more than 7 days ago
        cutoff = now - timedelta(days=7)

        result = db.query(RefreshToken).filter(
            RefreshToken.expires_at < cutoff
        ).delete()

        db.commit()

        logger.info(f"Cleaned up {result} expired refresh tokens")
        return result

    @staticmethod
    def get_user_active_tokens(db: Session, user_id: int) -> List[RefreshToken]:
        """
        Get all active (non-revoked, non-expired) tokens for a user.

        Args:
            db: Database session
            user_id: User ID to query

        Returns:
            List of active RefreshToken instances
        """
        now = datetime.now(timezone.utc)

        tokens = db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked == False,
            RefreshToken.expires_at > now
        ).order_by(RefreshToken.created_at.desc()).all()

        return tokens

    @staticmethod
    def verify_token_ownership(
        db: Session,
        jti: str,
        user_id: int,
    ) -> bool:
        """
        Verify that a token belongs to a specific user.

        Args:
            db: Database session
            jti: JWT ID to check
            user_id: Expected owner user ID

        Returns:
            True if token belongs to user, False otherwise
        """
        token = TokenService.get_token_by_jti(db, jti)
        if not token:
            return False

        return token.user_id == user_id


# Global instance
token_service = TokenService()
