"""Cloud connection management service."""
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.cloud import CloudConnection
from app.services.cloud.adapters.base import CloudAdapter, CloudFile
from app.services.cloud.crypto import encrypt_credentials, decrypt_credentials

logger = logging.getLogger(__name__)

# Supported providers
PROVIDERS = {"google_drive", "onedrive", "icloud"}


class CloudService:
    """Manages cloud provider connections and file browsing."""

    def __init__(self, db: Session):
        self.db = db

    # ─── Connection Management ────────────────────────────────────

    def get_connections(self, user_id: int) -> list[CloudConnection]:
        """Get all cloud connections for a user."""
        return (
            self.db.query(CloudConnection)
            .filter(CloudConnection.user_id == user_id)
            .order_by(CloudConnection.created_at.desc())
            .all()
        )

    def get_connection(self, connection_id: int, user_id: int) -> CloudConnection:
        """Get a specific connection, ensuring ownership."""
        conn = (
            self.db.query(CloudConnection)
            .filter(
                CloudConnection.id == connection_id,
                CloudConnection.user_id == user_id,
            )
            .first()
        )
        if not conn:
            raise ValueError(f"Connection {connection_id} not found")
        return conn

    def delete_connection(self, connection_id: int, user_id: int) -> None:
        """Delete a cloud connection."""
        conn = self.get_connection(connection_id, user_id)
        self.db.delete(conn)
        self.db.commit()
        logger.info("Deleted cloud connection %d for user %d", connection_id, user_id)

    # ─── OAuth Flow (Google Drive, OneDrive) ──────────────────────

    def get_oauth_url(self, provider: str, user_id: int, redirect_uri: str | None = None) -> str:
        """Generate an OAuth authorization URL for the given provider."""
        if provider not in ("google_drive", "onedrive"):
            raise ValueError(f"OAuth not supported for provider: {provider}")

        from app.services.cloud.oauth_config import CloudOAuthConfigService
        creds = CloudOAuthConfigService(self.db).get_credentials(provider, user_id)
        if not creds:
            raise ValueError(f"OAuth not configured for {provider}")
        client_id, _client_secret = creds
        callback_uri = redirect_uri or self._get_redirect_uri()

        state = json.dumps({"provider": provider, "user_id": user_id})

        if provider == "google_drive":
            params = {
                "client_id": client_id,
                "redirect_uri": callback_uri,
                "response_type": "code",
                "scope": "https://www.googleapis.com/auth/drive.readonly",
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
            }
            return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

        elif provider == "onedrive":
            params = {
                "client_id": client_id,
                "redirect_uri": callback_uri,
                "response_type": "code",
                "scope": "Files.Read offline_access",
                "state": state,
            }
            return f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{urlencode(params)}"

        raise ValueError(f"Unknown provider: {provider}")

    def handle_oauth_callback(
        self,
        provider: str,
        code: str,
        user_id: int,
        upgrade_connection_id: int | None = None,
        redirect_uri: str | None = None,
    ) -> CloudConnection:
        """Exchange OAuth code for tokens and create a connection."""
        import httpx

        from app.services.cloud.oauth_config import CloudOAuthConfigService
        creds = CloudOAuthConfigService(self.db).get_credentials(provider, user_id)
        if not creds:
            raise ValueError(f"OAuth not configured for {provider}")
        client_id, client_secret = creds
        callback_uri = redirect_uri or self._get_redirect_uri()

        if provider == "google_drive":
            token_url = "https://oauth2.googleapis.com/token"
            data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": callback_uri,
            }
        elif provider == "onedrive":
            token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
            data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": callback_uri,
            }
        else:
            raise ValueError(f"OAuth not supported for provider: {provider}")

        resp = httpx.post(token_url, data=data, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"OAuth token exchange failed: {resp.text}")

        token_data = resp.json()
        token_json = json.dumps(token_data)

        # Handle scope upgrade — update existing connection instead of creating new
        if upgrade_connection_id is not None:
            existing = self.get_connection(upgrade_connection_id, user_id)
            from app.services.cloud.adapters.rclone import RcloneAdapter
            _remote_name, config_content = RcloneAdapter.generate_config(provider, token_json)
            existing.encrypted_config = encrypt_credentials(config_content)
            existing.rclone_remote_name = _remote_name
            self.db.commit()
            self.db.refresh(existing)
            logger.info("Upgraded scope for connection %d (user %d)", upgrade_connection_id, user_id)
            return existing

        # Generate rclone config
        from app.services.cloud.adapters.rclone import RcloneAdapter
        remote_name, config_content = RcloneAdapter.generate_config(provider, token_json)

        # Determine display name
        display_name = "Google Drive" if provider == "google_drive" else "OneDrive"

        conn = CloudConnection(
            user_id=user_id,
            provider=provider,
            display_name=display_name,
            rclone_remote_name=remote_name,
            encrypted_config=encrypt_credentials(config_content),
            is_active=True,
        )
        self.db.add(conn)
        self.db.commit()
        self.db.refresh(conn)

        logger.info(
            "Created %s connection %d for user %d", provider, conn.id, user_id
        )
        return conn

    # ─── iCloud Connection ────────────────────────────────────────

    def connect_icloud(
        self, user_id: int, apple_id: str, password: str
    ) -> tuple[CloudConnection, bool]:
        """
        Connect to iCloud with credentials.

        Returns:
            Tuple of (connection, requires_2fa)
        """
        # Store credentials encrypted
        creds = json.dumps({"apple_id": apple_id, "password": password})

        conn = CloudConnection(
            user_id=user_id,
            provider="icloud",
            display_name=f"iCloud ({apple_id})",
            encrypted_config=encrypt_credentials(creds),
            is_active=True,
        )
        self.db.add(conn)
        self.db.commit()
        self.db.refresh(conn)

        # Check if 2FA is needed
        requires_2fa = False
        if not settings.is_dev_mode:
            try:
                adapter = self._get_adapter(conn)
                if hasattr(adapter, "requires_2fa"):
                    requires_2fa = getattr(adapter, "requires_2fa")
            except Exception as e:
                logger.warning("Could not check 2FA status: %s", e)
                requires_2fa = True  # Assume 2FA needed

        logger.info(
            "Created iCloud connection %d for user %d (2fa=%s)",
            conn.id, user_id, requires_2fa,
        )
        return conn, requires_2fa

    def validate_icloud_2fa(self, connection_id: int, user_id: int, code: str) -> bool:
        """Validate a 2FA code for an iCloud connection."""
        conn = self.get_connection(connection_id, user_id)
        if conn.provider != "icloud":
            raise ValueError("Connection is not iCloud")

        adapter = self._get_adapter(conn)
        validate_fn = getattr(adapter, "validate_2fa", None)
        if validate_fn is not None:
            return validate_fn(code)
        return False

    # ─── Scope Check & Upgrade ───────────────────────────────────

    EXPORT_SCOPES = {
        "google_drive": "https://www.googleapis.com/auth/drive.file",
        "onedrive": "Files.ReadWrite offline_access",
    }

    READONLY_SCOPES = {
        "google_drive": "drive.readonly",
        "onedrive": "Files.Read",
    }

    def check_connection_scope(self, connection_id: int, user_id: int) -> dict:
        """Check if a connection has export-capable (ReadWrite) scope."""
        conn = self.get_connection(connection_id, user_id)

        has_export_scope = False
        if conn.provider in ("google_drive", "onedrive") and conn.encrypted_config:
            try:
                config = decrypt_credentials(conn.encrypted_config)
                if conn.provider == "google_drive":
                    has_export_scope = "drive.file" in config or ("drive" in config.lower() and "readonly" not in config.lower())
                elif conn.provider == "onedrive":
                    has_export_scope = "ReadWrite" in config or "readwrite" in config.lower()
            except Exception:
                pass

        return {"has_export_scope": has_export_scope, "provider": conn.provider}

    def get_export_oauth_url(
        self,
        provider: str,
        user_id: int,
        connection_id: int,
        redirect_uri: str | None = None,
    ) -> str:
        """Generate OAuth URL with export scopes, including upgrade_connection_id in state."""
        if provider not in ("google_drive", "onedrive"):
            raise ValueError(f"Export not supported for provider: {provider}")

        from app.services.cloud.oauth_config import CloudOAuthConfigService
        creds = CloudOAuthConfigService(self.db).get_credentials(provider, user_id)
        if not creds:
            raise ValueError(f"OAuth not configured for {provider}")
        client_id, _client_secret = creds
        callback_uri = redirect_uri or self._get_redirect_uri()

        state = json.dumps({
            "provider": provider,
            "user_id": user_id,
            "upgrade_connection_id": connection_id,
        })

        if provider == "google_drive":
            params = {
                "client_id": client_id,
                "redirect_uri": callback_uri,
                "response_type": "code",
                "scope": self.EXPORT_SCOPES["google_drive"],
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
            }
            return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

        elif provider == "onedrive":
            params = {
                "client_id": client_id,
                "redirect_uri": callback_uri,
                "response_type": "code",
                "scope": self.EXPORT_SCOPES["onedrive"],
                "state": state,
            }
            return f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{urlencode(params)}"

        raise ValueError(f"Unknown provider: {provider}")

    # ─── File Browsing ────────────────────────────────────────────

    async def list_files(
        self, connection_id: int, user_id: int, path: str = "/"
    ) -> list[CloudFile]:
        """List files in a cloud connection at the given path."""
        conn = self.get_connection(connection_id, user_id)
        adapter = self._get_adapter(conn)

        try:
            files = await adapter.list_files(path)

            # Update last_used_at
            conn.last_used_at = datetime.now(timezone.utc)
            self.db.commit()

            return files
        finally:
            await adapter.close()

    # ─── Adapter Factory ─────────────────────────────────────────

    def _get_adapter(self, connection: CloudConnection) -> CloudAdapter:
        """Create the appropriate adapter for a connection."""
        if settings.is_dev_mode:
            from app.services.cloud.adapters.dev import DevCloudAdapter
            return DevCloudAdapter(provider=connection.provider)

        if connection.provider in ("google_drive", "onedrive"):
            from app.services.cloud.adapters.rclone import RcloneAdapter
            config = decrypt_credentials(connection.encrypted_config)
            return RcloneAdapter(
                remote_name=connection.rclone_remote_name or "",
                config_content=config,
            )
        elif connection.provider == "icloud":
            from app.services.cloud.adapters.icloud import ICloudAdapter
            creds = json.loads(decrypt_credentials(connection.encrypted_config))
            return ICloudAdapter(
                apple_id=creds["apple_id"],
                password=creds["password"],
            )
        else:
            raise ValueError(f"Unknown provider: {connection.provider}")

    def get_adapter_for_connection(self, connection: CloudConnection) -> CloudAdapter:
        """Public accessor for adapter creation (used by import job service)."""
        return self._get_adapter(connection)

    # ─── Dev Mode Helpers ─────────────────────────────────────────

    def create_dev_connection(self, user_id: int, provider: str) -> CloudConnection:
        """Create a mock connection for dev mode."""
        display_names = {
            "google_drive": "Google Drive (Dev)",
            "onedrive": "OneDrive (Dev)",
            "icloud": "iCloud (Dev)",
        }

        conn = CloudConnection(
            user_id=user_id,
            provider=provider,
            display_name=display_names.get(provider, f"{provider} (Dev)"),
            rclone_remote_name=f"dev_{provider}_{secrets.token_hex(4)}",
            encrypted_config=encrypt_credentials(json.dumps({"dev": True})),
            is_active=True,
        )
        self.db.add(conn)
        self.db.commit()
        self.db.refresh(conn)
        return conn

    # ─── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _get_redirect_uri() -> str:
        """Get the OAuth redirect URI based on current config."""
        if settings.public_url:
            return f"{settings.public_url.rstrip('/')}/api/cloud/oauth/callback"
        host = settings.host if settings.host != "0.0.0.0" else "localhost"
        return f"http://{host}:{settings.port}/api/cloud/oauth/callback"
