"""Service for managing per-user OAuth credentials (DB-first, env-fallback)."""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.cloud import CloudOAuthConfig
from app.services.cloud.crypto import encrypt_credentials, decrypt_credentials

logger = logging.getLogger(__name__)


class CloudOAuthConfigService:
    """Manages per-user OAuth client credentials stored in the database with env-var fallback."""

    def __init__(self, db: Session):
        self.db = db

    # ─── Read ─────────────────────────────────────────────────────

    def get_credentials(self, provider: str, user_id: int) -> Optional[tuple[str, str]]:
        """
        Return (client_id, client_secret) for the given provider and user.

        Checks user's DB credentials first, then falls back to environment variables.
        Returns None if nothing is configured.
        """
        # DB first (user-specific)
        config = self._get_config(provider, user_id)
        if config:
            try:
                client_id = decrypt_credentials(config.encrypted_client_id)
                client_secret = decrypt_credentials(config.encrypted_client_secret)
                return (client_id, client_secret)
            except ValueError:
                logger.error("Failed to decrypt OAuth credentials for %s (user %d)", provider, user_id)

        # Env-var fallback
        if provider == "google_drive":
            cid, csec = settings.google_client_id, settings.google_client_secret
        elif provider == "onedrive":
            cid, csec = settings.microsoft_client_id, settings.microsoft_client_secret
        else:
            return None

        if cid and csec:
            return (cid, csec)
        return None

    def is_configured(self, provider: str, user_id: int) -> bool:
        """Check whether OAuth credentials exist (DB or env) for the provider and user."""
        return self.get_credentials(provider, user_id) is not None

    def get_config_source(self, provider: str, user_id: int) -> Optional[str]:
        """Return 'db' if configured in DB, 'env' if only via env-var, None if unconfigured."""
        if self._get_config(provider, user_id):
            return "db"
        # Check env
        if provider == "google_drive" and settings.google_client_id and settings.google_client_secret:
            return "env"
        if provider == "onedrive" and settings.microsoft_client_id and settings.microsoft_client_secret:
            return "env"
        return None

    def get_client_id_hint(self, provider: str, user_id: int) -> Optional[str]:
        """
        Return a masked hint for the configured client_id.

        DB credentials: first 4 + '...' + last 4 chars.
        Env-only: '(env)'.
        Unconfigured: None.
        """
        source = self.get_config_source(provider, user_id)
        if source == "db":
            config = self._get_config(provider, user_id)
            if config:
                try:
                    cid = decrypt_credentials(config.encrypted_client_id)
                    if len(cid) > 8:
                        return f"{cid[:4]}...{cid[-4:]}"
                    return cid
                except ValueError:
                    return None
        elif source == "env":
            return "(env)"
        return None

    # ─── Write ────────────────────────────────────────────────────

    def save_credentials(
        self, provider: str, client_id: str, client_secret: str, user_id: int
    ) -> CloudOAuthConfig:
        """
        Upsert OAuth credentials for a provider and user.

        Encrypts both values and stores/updates them in the database.
        """
        config = self._get_config(provider, user_id)
        now = datetime.now(timezone.utc)

        if config:
            config.encrypted_client_id = encrypt_credentials(client_id)
            config.encrypted_client_secret = encrypt_credentials(client_secret)
            config.updated_at = now
        else:
            config = CloudOAuthConfig(
                provider=provider,
                encrypted_client_id=encrypt_credentials(client_id),
                encrypted_client_secret=encrypt_credentials(client_secret),
                user_id=user_id,
            )
            self.db.add(config)

        self.db.commit()
        self.db.refresh(config)
        logger.info("Saved OAuth credentials for provider %s (user %d)", provider, user_id)
        return config

    def delete_credentials(self, provider: str, user_id: int) -> bool:
        """Delete DB-stored OAuth credentials for a provider and user. Returns True if deleted."""
        config = self._get_config(provider, user_id)
        if not config:
            return False
        self.db.delete(config)
        self.db.commit()
        logger.info("Deleted OAuth credentials for provider %s (user %d)", provider, user_id)
        return True

    # ─── Internal ─────────────────────────────────────────────────

    def _get_config(self, provider: str, user_id: int) -> Optional[CloudOAuthConfig]:
        try:
            return (
                self.db.query(CloudOAuthConfig)
                .filter(
                    CloudOAuthConfig.provider == provider,
                    CloudOAuthConfig.user_id == user_id,
                )
                .first()
            )
        except ProgrammingError:
            # Table doesn't exist yet (migration not applied) — fall back to env vars
            self.db.rollback()
            logger.debug("cloud_oauth_configs table not found, falling back to env vars")
            return None
