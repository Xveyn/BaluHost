from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, field_validator, model_validator
import logging

class Settings(BaseSettings):
    app_name: str = "Baluhost NAS API"
    debug: bool = True
    environment: str = "development"

    # Logging configuration
    log_level: str = "INFO"  # DEBUG|INFO|WARNING|ERROR|CRITICAL
    log_format: str = "text"  # json|text (json recommended for production)

    nas_mode: str = "dev"
    is_dev_mode: bool = True  # Added as a field for Pydantic compatibility
    api_prefix: str = "/api"
    host: str = "0.0.0.0"
    port: int = 3001

    cors_origins: list[AnyHttpUrl] | list[str] = [
        "http://localhost:5173",
        "https://localhost:5173",
        "http://localhost:8000",
        "https://localhost:8000",
        "app://-",  # Electron default origin
        "file://"  # Electron file protocol
    ]

    # Auth configuration
    SECRET_KEY: str = "change-me-in-prod"  # Used by security.py
    token_secret: str = "change-me-in-prod"  # Legacy: still used by auth_service
    token_algorithm: str = "HS256"
    token_expire_minutes: int = 60 * 12
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # Access token TTL (short)
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # Refresh token TTL (long)
    privileged_roles: list[str] = ["admin"]
    
    # Local-only access enforcement (Option B security)
    enforce_local_only: bool = False  # Set True to restrict sensitive endpoints to localhost
    allow_public_profile_list: bool = True  # Allow unauthenticated profile list for login screen

    # Admin seed
    admin_username: str = "admin"
    admin_email: str = "admin@example.com"
    admin_password: str = "DevMode2024"  # Not in blacklist, meets all validation requirements
    admin_role: str = "admin"

    # Mobile device registration
    mobile_server_url: str | None = None  # Optional: Override server URL for mobile QR codes

    # VPN Configuration
    vpn_encryption_key: str = ""  # Fernet key for encrypting VPN private/preshared keys
    
    # RAID backend and safety options
    # Force using the development (simulated) RAID backend even on Linux.
    raid_force_dev_backend: bool = False
    # When creating arrays with mdadm, do not assume clean by default in production.
    # Set True to add `--assume-clean` when creating arrays (useful for tests/dev only).
    raid_assume_clean_by_default: bool = False
    # Dry-run mode: when True, mdadm and other destructive operations are simulated.
    raid_dry_run: bool = False
    # Path to append audit log entries for RAID actions (JSON lines). If None, auditing is disabled.
    raid_audit_log: str | None = None
    # RAID scrub scheduler options
    # Enable periodic RAID scrubbing (recommended: weekly)
    raid_scrub_enabled: bool = False
    # Interval in hours between automatic scrubs when enabled (default: 168 = 1 week)
    raid_scrub_interval_hours: int = 168
    # SMART scan scheduler options
    smart_scan_enabled: bool = False
    # Interval in minutes between automatic SMART scans when enabled (default: 60)
    smart_scan_interval_minutes: int = 60

    # Storage paths
    nas_storage_path: str = "./storage"
    nas_temp_path: str = "./tmp"
    nas_quota_bytes: int | None = 5 * 1024 * 1024 * 1024
    nas_backup_path: str = "./backups"
    nas_backup_retention_days: int = 30
    nas_backup_max_count: int = 10

    # Backup scheduler options
    # Enable automatic periodic backups (recommended for production)
    backup_auto_enabled: bool = False
    # Interval in hours between automatic backups when enabled (default: 24 = daily)
    backup_auto_interval_hours: int = 24
    # Type of backup to create automatically (full|incremental|database_only|files_only)
    backup_auto_type: str = "full"

    telemetry_interval_seconds: float = 2.0
    telemetry_history_size: int = 90

    # Database configuration
    database_url: str | None = None
    database_type: str = "sqlite"

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_dev_mode_prop(self) -> bool:
        return str(self.nas_mode).lower() == "dev"

    @model_validator(mode="after")
    def _apply_dev_defaults(self):
        # Sync is_dev_mode field with nas_mode
        self.is_dev_mode = str(self.nas_mode).lower() == "dev"
        if self.is_dev_mode:
            if self.nas_storage_path == "./storage":
                self.nas_storage_path = "./dev-storage"
            if self.nas_temp_path == "./tmp":
                self.nas_temp_path = "./dev-tmp"
            if self.nas_backup_path == "./backups":
                self.nas_backup_path = "./dev-backups"
        else:
            if self.nas_quota_bytes == 5 * 1024 * 1024 * 1024:
                self.nas_quota_bytes = None
        return self

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        """✅ Security Fix #1: Ensure SECRET_KEY is not using default value (production only)."""
        # Only enforce in production mode
        import os
        is_dev = os.getenv("NAS_MODE", "dev").lower() == "dev"
        is_test = os.getenv("SKIP_APP_INIT") == "1" or os.getenv("PYTEST_CURRENT_TEST")

        if not (is_dev or is_test):
            if v == "change-me-in-prod":
                raise ValueError(
                    "SECRET_KEY cannot use default value in production! "
                    "Generate a secure secret: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
                )
            if len(v) < 32:
                raise ValueError("SECRET_KEY must be at least 32 characters for security")
        return v

    @field_validator("token_secret")
    @classmethod
    def validate_token_secret(cls, v: str, info) -> str:
        """✅ Security Fix #1: Ensure token_secret is not using default value (production only)."""
        # Only enforce in production mode
        import os
        is_dev = os.getenv("NAS_MODE", "dev").lower() == "dev"
        is_test = os.getenv("SKIP_APP_INIT") == "1" or os.getenv("PYTEST_CURRENT_TEST")

        if not (is_dev or is_test):
            if v == "change-me-in-prod":
                raise ValueError(
                    "token_secret cannot use default value in production! "
                    "Generate a secure secret: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
                )
            if len(v) < 32:
                raise ValueError("token_secret must be at least 32 characters for security")
        return v

    @field_validator("cors_origins", mode="before")
    def assemble_cors_origins(cls, value: list[str] | str) -> list[str]:
        if isinstance(value, str) and not value.startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return value
        return ["http://localhost:5173"]

    @field_validator("privileged_roles", mode="before")
    def parse_privileged_roles(cls, value: list[str] | str) -> list[str]:
        if isinstance(value, str):
            return [role.strip() for role in value.split(",") if role.strip()]
        if isinstance(value, list):
            return value
        return ["admin"]

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

settings = get_settings()

def log_cors_origin(origin: str) -> None:
    logging.info(f"[CORS] Incoming Origin: {origin}")


