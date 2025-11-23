from functools import lru_cache
from typing import List

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


class Settings(BaseSettings):
    app_name: str = "Baluhost NAS API"
    debug: bool = True
    environment: str = "development"
    nas_mode: str = "dev"
    api_prefix: str = "/api"
    host: str = "0.0.0.0"
    port: int = 3001

    cors_origins: List[AnyHttpUrl] | List[str] = ["http://localhost:5173"]

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

    # Storage paths
    nas_storage_path: str = "./storage"
    nas_temp_path: str = "./tmp"
    nas_quota_bytes: int | None = 10 * 1024 * 1024 * 1024  # 10 GB default in dev

    telemetry_interval_seconds: float = 2.0
    telemetry_history_size: int = 90

    # Database placeholder
    database_url: str = "sqlite+aiosqlite:///./baluhost.db"

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_dev_mode(self) -> bool:
        return self.nas_mode.lower() == "dev"

    @model_validator(mode="after")
    def _apply_dev_defaults(self):
        if self.is_dev_mode:
            if self.nas_storage_path == "./storage":
                self.nas_storage_path = "./dev-storage"
            if self.nas_temp_path == "./tmp":
                self.nas_temp_path = "./dev-tmp"
        else:
            if self.nas_quota_bytes == 10 * 1024 * 1024 * 1024:
                self.nas_quota_bytes = None
        return self

    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, value: List[str] | str) -> List[str]:
        if isinstance(value, str) and not value.startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return value
        return ["http://localhost:5173"]

    @field_validator("privileged_roles", mode="before")
    @classmethod
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
