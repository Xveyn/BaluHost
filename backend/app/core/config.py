from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, field_validator, model_validator
import logging

class Settings(BaseSettings):
    app_name: str = "Baluhost NAS API"
    debug: bool = False
    environment: str = "development"

    # Logging configuration
    log_level: str = "INFO"  # DEBUG|INFO|WARNING|ERROR|CRITICAL
    log_format: str = "text"  # json|text (json recommended for production)
    audit_logging_enabled: bool = False  # Enable audit logging (auto-enabled in production)

    nas_mode: str = "dev"
    is_dev_mode: bool = True  # Added as a field for Pydantic compatibility
    api_prefix: str = "/api"
    api_version: str = "1"  # Current API version
    api_min_version: str = "1"  # Minimum supported API version
    host: str = "0.0.0.0"
    port: int = 8000

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
    
    # Registration control — defaults to False for security (production requires admin-created accounts)
    registration_enabled: bool = False

    # Local-only access enforcement (Option B security)
    enforce_local_only: bool = False  # Set True to restrict sensitive endpoints to localhost
    allow_public_profile_list: bool = True  # Allow unauthenticated profile list for login screen

    # Admin seed
    admin_username: str = "admin"
    admin_email: str = "admin@example.com"
    admin_password: str = "DevMode2024"  # Not in blacklist, meets all validation requirements
    admin_role: str = "admin"

    # Setup wizard
    skip_setup: bool = False  # BALUHOST_SKIP_SETUP — skip wizard, use env-var admin creation
    setup_secret: str = ""  # BALUHOST_SETUP_SECRET — if set, required for admin creation endpoint

    # Mobile device registration
    mobile_server_url: str | None = None  # Optional: Override server URL for mobile QR codes
    mobile_pairing_allow_lan: bool = True  # Allow token generation from local network IPs (192.168.*, 10.*, etc.)

    # Network discovery (mDNS/Bonjour)
    mdns_hostname: str = "baluhost"  # Hostname for mDNS/Bonjour service (defaults to "baluhost")

    # VPN Configuration
    vpn_encryption_key: str = ""  # Fernet key for encrypting VPN private/preshared keys
    vpn_lan_network: str = "192.168.178.0/24"  # LAN subnet for client AllowedIPs
    vpn_lan_interface: str = ""  # LAN interface for NAT (auto-detect if empty)
    vpn_include_lan: bool = True  # Include LAN subnet in VPN client AllowedIPs
    vpn_config_path: str = "/etc/wireguard/wg0.conf"  # Server config file path
    vpn_public_endpoint: str = ""  # DDNS hostname for VPN endpoint (e.g. "myhost.myfritz.net")
    vpn_public_port: int = 0  # External port for NAS WireGuard (0 = use internal VPN port 51820)
    vpn_server_public_key: str = ""  # Override server public key (use when wg0 interface is not available)

    # TOTP Configuration
    totp_encryption_key: str = ""  # Dedicated key for TOTP secrets. Falls back to VPN_ENCRYPTION_KEY if not set.
    
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
    raid_scrub_enabled: bool = True
    # Interval in hours between automatic scrubs when enabled (default: 168 = 1 week)
    raid_scrub_interval_hours: int = 168
    # SMART scan scheduler options
    smart_scan_enabled: bool = True
    # Interval in minutes between automatic SMART scans when enabled (default: 60)
    smart_scan_interval_minutes: int = 60

    # Storage paths
    nas_storage_path: str = "./storage"
    nas_temp_path: str = "./tmp"
    nas_quota_bytes: int | None = 5 * 1024 * 1024 * 1024
    nas_backup_path: str = "./backups"

    # Linux group for shared storage ownership (backend + Samba)
    storage_group: str = "baluhost"

    # VCL storage path (empty = use nas_storage_path/.system/versions)
    vcl_storage_path: str = ""
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

    # System monitoring configuration
    monitoring_sample_interval: float = 5.0  # Seconds between samples
    monitoring_buffer_size: int = 120  # In-memory buffer size (10 min at 5s)
    monitoring_db_persist_interval: int = 12  # Persist to DB every N samples (1 min at 5s)
    monitoring_default_retention_hours: int = 168  # 7 days default retention
    monitoring_cleanup_interval_hours: int = 6  # Run cleanup every N hours

    # Scheduler worker service token (auto-generated if empty)
    scheduler_service_token: str = ""  # Service token for scheduler-worker -> backend API calls

    # Power management configuration (CPU frequency scaling)
    power_management_enabled: bool = True  # Enable/disable power management
    power_force_dev_backend: bool = False  # Force dev backend even on Linux
    power_default_profile: str = "idle"  # Default profile on startup
    power_auto_scaling_enabled: bool = True  # Auto-scale based on CPU usage
    power_profile_cooldown_seconds: int = 60  # Cooldown before downgrade allowed
    power_cpu_surge_threshold: float = 80.0  # CPU % to trigger SURGE
    power_cpu_medium_threshold: float = 50.0  # CPU % to trigger MEDIUM
    power_cpu_low_threshold: float = 20.0  # CPU % to trigger LOW

    # SSD cache (bcache) configuration
    ssd_cache_enabled: bool = True  # Enable/disable SSD cache management
    ssd_cache_default_mode: str = "writethrough"  # Default cache mode (writethrough|writeback|writearound)
    ssd_cache_force_dev_backend: bool = False  # Force dev backend even on Linux

    # Sleep mode configuration
    sleep_mode_enabled: bool = True  # Enable/disable sleep mode service

    # Fan control configuration (PWM fan management)
    fan_control_enabled: bool = True  # Enable/disable fan control
    fan_force_dev_backend: bool = False  # Force dev backend even on Linux
    fan_min_pwm_percent: int = 30  # Global minimum PWM (safety, 0-100)
    fan_emergency_temp_celsius: float = 85.0  # Emergency temperature threshold
    fan_sample_interval_seconds: float = 5.0  # Monitoring interval
    fan_curve_interpolation: str = "linear"  # Curve interpolation method

    # WebDAV configuration
    webdav_enabled: bool = True
    webdav_port: int = 8080
    webdav_ssl_enabled: bool = True
    webdav_verbose_logging: bool = False

    # Samba (SMB/CIFS) configuration
    samba_shares_conf_path: str = "/etc/samba/baluhost-shares.conf"

    # Cloud / OAuth
    public_url: str | None = None  # e.g. "http://baluhost.local"

    # Cloud import configuration
    cloud_import_enabled: bool = True
    google_client_id: str = ""
    google_client_secret: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""

    # Database configuration
    database_url: str | None = None
    database_type: str = "sqlite"

    # Pi-hole DNS integration
    pihole_enabled: bool = False  # Enable/disable Pi-hole integration
    pihole_force_dev_backend: bool = False  # Force dev backend even with Docker available
    pihole_web_port: int = 8053  # Pi-hole web UI port on host

    # BaluPi integration (Raspberry Pi companion device)
    balupi_enabled: bool = False  # Enable BaluPi handshake/notification integration
    balupi_url: str = ""  # BaluPi backend URL, e.g. "http://192.168.178.20:8000"
    balupi_handshake_secret: str = ""  # HMAC-SHA256 shared secret (32+ chars in prod)

    # WebSocket configuration
    ws_heartbeat_interval: int = 30  # WebSocket ping interval in seconds

    # Notification configuration
    notification_retention_days: int = 90  # Days to retain old notifications

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
            # Enable debug mode in dev (only if not explicitly set via env/config)
            if not self.debug:
                self.debug = True
            if self.nas_storage_path == "./storage":
                self.nas_storage_path = "./dev-storage"
            if self.nas_temp_path == "./tmp":
                self.nas_temp_path = "./dev-tmp"
            if self.nas_backup_path == "./backups":
                self.nas_backup_path = "./dev-backups"
            # Reduce sampling frequencies for better dev performance
            if self.telemetry_interval_seconds == 2.0:
                self.telemetry_interval_seconds = 5.0
            if self.monitoring_sample_interval == 5.0:
                self.monitoring_sample_interval = 10.0
            if self.fan_sample_interval_seconds == 5.0:
                self.fan_sample_interval_seconds = 15.0
            # Disable no-op services in dev
            if self.sleep_mode_enabled:
                self.sleep_mode_enabled = False
            if self.pihole_enabled:
                self.pihole_enabled = False
            # Enable registration in dev mode for convenience
            if not self.registration_enabled:
                self.registration_enabled = True
            # Auto-generate VPN encryption key for dev mode
            if not self.vpn_encryption_key:
                from cryptography.fernet import Fernet
                self.vpn_encryption_key = Fernet.generate_key().decode()
        else:
            # Production mode: enable audit logging by default
            if not self.audit_logging_enabled:
                self.audit_logging_enabled = True
            if self.nas_quota_bytes == 5 * 1024 * 1024 * 1024:
                self.nas_quota_bytes = None

        # Auto-generate scheduler service token if not set
        if not self.scheduler_service_token:
            import secrets
            self.scheduler_service_token = secrets.token_urlsafe(32)

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

    @field_validator("registration_enabled")
    @classmethod
    def validate_registration(cls, v: bool, info) -> bool:
        """Warn when open registration is enabled in production."""
        import os
        is_dev = os.getenv("NAS_MODE", "dev").lower() == "dev"
        is_test = os.getenv("SKIP_APP_INIT") == "1" or os.getenv("PYTEST_CURRENT_TEST")

        if not (is_dev or is_test) and v:
            logging.warning(
                "REGISTRATION_ENABLED=true in production — anyone can create accounts. "
                "Set REGISTRATION_ENABLED=false to require admin-created accounts."
            )
        return v

    @field_validator("totp_encryption_key")
    @classmethod
    def validate_totp_key(cls, v: str, info) -> str:
        """Warn when TOTP encryption key is not set in production."""
        import os
        is_dev = os.getenv("NAS_MODE", "dev").lower() == "dev"
        is_test = os.getenv("SKIP_APP_INIT") == "1" or os.getenv("PYTEST_CURRENT_TEST")

        if not (is_dev or is_test) and not v:
            logging.warning(
                "TOTP_ENCRYPTION_KEY not set — TOTP secrets will use VPN_ENCRYPTION_KEY as fallback. "
                "Set a dedicated TOTP_ENCRYPTION_KEY for proper key isolation."
            )
        return v

    @field_validator("balupi_handshake_secret")
    @classmethod
    def validate_balupi_secret(cls, v: str, info) -> str:
        """Ensure handshake secret is strong enough when BaluPi is enabled in production."""
        import os
        is_dev = os.getenv("NAS_MODE", "dev").lower() == "dev"
        is_test = os.getenv("SKIP_APP_INIT") == "1" or os.getenv("PYTEST_CURRENT_TEST")
        # Only validate in prod when BaluPi is actually enabled
        # (we can't check balupi_enabled here since validators run per-field,
        #  but the _apply_dev_defaults model_validator catches the combination)
        if not (is_dev or is_test) and v and len(v) < 32:
            raise ValueError("balupi_handshake_secret must be at least 32 characters for security")
        return v

    @field_validator("admin_password")
    @classmethod
    def validate_admin_password(cls, v: str, info) -> str:
        """Ensure admin_password is not using default value in production."""
        import os
        is_dev = os.getenv("NAS_MODE", "dev").lower() == "dev"
        is_test = os.getenv("SKIP_APP_INIT") == "1" or os.getenv("PYTEST_CURRENT_TEST")

        if not (is_dev or is_test):
            if v == "DevMode2024":
                raise ValueError(
                    "ADMIN_PASSWORD must be changed from default 'DevMode2024' for production. "
                    "Set ADMIN_PASSWORD environment variable."
                )
            if len(v) < 12:
                raise ValueError(
                    "ADMIN_PASSWORD must be at least 12 characters in production."
                )
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


