from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, field_validator, model_validator
import logging

class Settings(BaseSettings):
    app_name: str = "Baluhost NAS API"
    debug: bool = True
    environment: str = "development"
    nas_mode: str = "dev"
    is_dev_mode: bool = True  # Added as a field for Pydantic compatibility
    api_prefix: str = "/api"
    host: str = "0.0.0.0"
    port: int = 3001

    cors_origins: list[AnyHttpUrl] | list[str] = [
        "http://localhost:5173",
        "https://localhost:5173",
        "http://localhost:8000",
        "https://localhost:8000"
    ]

    # Auth configuration
    token_secret: str = "change-me-in-prod"
    token_algorithm: str = "HS256"
    token_expire_minutes: int = 60 * 12
    privileged_roles: list[str] = ["admin"]

    # Admin seed
    admin_username: str = "admin"
    admin_email: str = "admin@example.com"
    admin_password: str = "changeme"
    admin_role: str = "admin"

    # Mobile device registration
    mobile_server_url: str | None = None  # Optional: Override server URL for mobile QR codes

    # VPN Configuration
    vpn_encryption_key: str = ""  # Fernet key for encrypting VPN private/preshared keys

    # Storage paths
    nas_storage_path: str = "./storage"
    nas_temp_path: str = "./tmp"
    nas_quota_bytes: int | None = 5 * 1024 * 1024 * 1024
    nas_backup_path: str = "./backups"
    nas_backup_retention_days: int = 30
    nas_backup_max_count: int = 10

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
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, field_validator, model_validator
import logging

class Settings(BaseSettings):
    app_name: str = "Baluhost NAS API"
    debug: bool = True
    environment: str = "development"
    nas_mode: str = "dev"
    api_prefix: str = "/api"
    host: str = "0.0.0.0"
    port: int = 3001

    cors_origins: list[AnyHttpUrl] | list[str] = [
        "http://localhost:5173",
        "https://localhost:5173",
        "http://localhost:8000",
        "https://localhost:8000"
    ]
    admin_username: str = "admin"
    admin_email: str = "admin@example.com"
    admin_password: str = "changeme"

