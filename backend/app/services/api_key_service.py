"""Service layer for API Key management."""
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.api_key import ApiKey
from app.models.user import User

logger = logging.getLogger(__name__)

# Max active keys per admin to prevent key sprawl
MAX_ACTIVE_KEYS_PER_ADMIN = 25


class ApiKeyService:
    """Business logic for API key CRUD operations."""

    @staticmethod
    def generate_key() -> str:
        """Generate a cryptographically secure API key with ``balu_`` prefix."""
        return "balu_" + secrets.token_urlsafe(30)

    @staticmethod
    def create_api_key(
        db: Session,
        name: str,
        created_by_id: int,
        target_user_id: int,
        expires_in_days: Optional[int] = None,
    ) -> tuple[ApiKey, str]:
        """
        Create a new API key.

        Args:
            db: Database session.
            name: Human-readable name.
            created_by_id: Admin user ID creating the key.
            target_user_id: User identity the key will act as.
            expires_in_days: Optional expiry in days (1-365).

        Returns:
            Tuple of (ApiKey model, raw_key). The raw key is only available here.

        Raises:
            ValueError: On validation errors (user not found, limit exceeded, etc.).
        """
        # Validate target user exists and is active
        target_user = db.query(User).filter(User.id == target_user_id).first()
        if not target_user:
            raise ValueError("Target user not found")
        if not target_user.is_active:
            raise ValueError("Target user is inactive")

        # Prevent creating keys for other admins (unless self-key)
        if target_user.role == "admin" and target_user.id != created_by_id:
            raise ValueError("Cannot create API keys for other admin users")

        # Check active key limit for this admin
        active_count = (
            db.query(ApiKey)
            .filter(ApiKey.created_by_user_id == created_by_id, ApiKey.is_active == True)  # noqa: E712
            .count()
        )
        if active_count >= MAX_ACTIVE_KEYS_PER_ADMIN:
            raise ValueError(
                f"Maximum number of active API keys ({MAX_ACTIVE_KEYS_PER_ADMIN}) reached"
            )

        # Generate key and hash
        raw_key = ApiKeyService.generate_key()
        key_hash = ApiKey.hash_key(raw_key)
        key_prefix = raw_key[:12]

        # Build expiry
        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        api_key = ApiKey(
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            created_by_user_id=created_by_id,
            target_user_id=target_user_id,
            is_active=True,
            expires_at=expires_at,
            use_count=0,
        )
        db.add(api_key)
        db.commit()
        db.refresh(api_key)

        logger.info(
            "API key created: id=%d name='%s' creator=%d target=%d",
            api_key.id, name, created_by_id, target_user_id,
        )
        return api_key, raw_key

    @staticmethod
    def validate_api_key(db: Session, raw_key: str) -> Optional[ApiKey]:
        """
        Validate a raw API key and return the corresponding model if valid.

        Updates usage stats on success. Returns None if key is invalid,
        revoked, or expired.
        """
        key_hash = ApiKey.hash_key(raw_key)

        api_key = (
            db.query(ApiKey)
            .filter(ApiKey.key_hash == key_hash, ApiKey.is_active == True)  # noqa: E712
            .first()
        )
        if not api_key:
            return None

        if not api_key.is_valid():
            return None

        return api_key

    @staticmethod
    def record_usage(db: Session, api_key: ApiKey, ip: Optional[str] = None) -> None:
        """Record a usage event for an API key (call after validation)."""
        api_key.record_usage(ip)
        db.commit()

    @staticmethod
    def list_api_keys(db: Session, admin_user_id: int) -> list[ApiKey]:
        """List all API keys created by a specific admin."""
        return (
            db.query(ApiKey)
            .filter(ApiKey.created_by_user_id == admin_user_id)
            .order_by(ApiKey.created_at.desc())
            .all()
        )

    @staticmethod
    def get_api_key(db: Session, key_id: int, admin_user_id: int) -> Optional[ApiKey]:
        """Get a specific API key by ID (must belong to the admin)."""
        return (
            db.query(ApiKey)
            .filter(ApiKey.id == key_id, ApiKey.created_by_user_id == admin_user_id)
            .first()
        )

    @staticmethod
    def delete_api_key(
        db: Session,
        key_id: int,
        admin_user_id: int,
    ) -> bool:
        """
        Permanently delete an API key.

        Revoking a key removes it outright — an invalid key has no reason to
        linger in the database. The audit log keeps the record of the action.

        Returns True if the key was found and deleted, False otherwise.
        """
        api_key = (
            db.query(ApiKey)
            .filter(
                ApiKey.id == key_id,
                ApiKey.created_by_user_id == admin_user_id,
            )
            .first()
        )
        if not api_key:
            return False

        db.delete(api_key)
        db.commit()

        logger.info("API key deleted: id=%d", key_id)
        return True

    @staticmethod
    def delete_all_for_user(db: Session, user_id: int) -> int:
        """
        Permanently delete all API keys targeting a specific user.

        Useful when a user is deleted or deactivated.

        Returns the number of keys deleted.
        """
        deleted = (
            db.query(ApiKey)
            .filter(ApiKey.target_user_id == user_id)
            .delete(synchronize_session=False)
        )
        db.commit()

        if deleted:
            logger.info("Deleted %d API keys for user %d", deleted, user_id)
        return deleted

    @staticmethod
    def cleanup_expired(db: Session) -> int:
        """
        Permanently delete expired API keys.

        Returns the number of keys cleaned up.
        """
        now = datetime.now(timezone.utc)
        deleted = (
            db.query(ApiKey)
            .filter(
                ApiKey.expires_at != None,  # noqa: E711
                ApiKey.expires_at <= now,
            )
            .delete(synchronize_session=False)
        )
        db.commit()

        if deleted:
            logger.info("Cleaned up %d expired API keys", deleted)
        return deleted
