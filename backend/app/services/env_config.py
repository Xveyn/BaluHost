"""Service for reading and writing .env configuration files.

Provides a curated registry of known environment variables, grouped by category,
with sensitive value detection and atomic file writes.
"""

import os
import re
import tempfile
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SENSITIVE_PATTERN = re.compile(
    r"password|secret|token|private_key|api_key|encryption_key|client_secret",
    re.IGNORECASE,
)

MASKED_VALUE = "••••••••"


@dataclass
class EnvVarDefinition:
    """Definition of a curated environment variable."""
    key: str
    category: str
    input_type: str  # text | number | boolean | secret
    default: Optional[str] = None
    file: str = "backend"  # backend | client


# ---------------------------------------------------------------------------
# Variable Registry
# ---------------------------------------------------------------------------

_BACKEND_VARS: list[EnvVarDefinition] = [
    # Application & Mode
    EnvVarDefinition("NAS_MODE", "application", "text", "dev"),
    EnvVarDefinition("DEBUG", "application", "boolean", "false"),
    EnvVarDefinition("LOG_LEVEL", "application", "text", "INFO"),
    EnvVarDefinition("LOG_FORMAT", "application", "text", "text"),
    EnvVarDefinition("VCL_STORAGE_PATH", "application", "text", ""),

    # Security
    EnvVarDefinition("SECRET_KEY", "security", "secret", "change-me-in-prod"),
    EnvVarDefinition("TOKEN_SECRET", "security", "secret", "change-me-in-prod"),
    EnvVarDefinition("ACCESS_TOKEN_EXPIRE_MINUTES", "security", "number", "15"),
    EnvVarDefinition("REFRESH_TOKEN_EXPIRE_DAYS", "security", "number", "7"),
    EnvVarDefinition("REGISTRATION_ENABLED", "security", "boolean", "true"),

    # Database
    EnvVarDefinition("DATABASE_URL", "database", "text"),
    EnvVarDefinition("DATABASE_TYPE", "database", "text", "sqlite"),
    EnvVarDefinition("POSTGRES_DB", "database", "text"),
    EnvVarDefinition("POSTGRES_USER", "database", "text"),
    EnvVarDefinition("POSTGRES_PASSWORD", "database", "secret"),

    # Admin User
    EnvVarDefinition("ADMIN_USERNAME", "admin_user", "text", "admin"),
    EnvVarDefinition("ADMIN_EMAIL", "admin_user", "text", "admin@example.com"),
    EnvVarDefinition("ADMIN_PASSWORD", "admin_user", "secret", "DevMode2024"),

    # CORS & Server
    EnvVarDefinition("CORS_ORIGINS", "server", "text"),
    EnvVarDefinition("FRONTEND_PORT", "server", "number"),
    EnvVarDefinition("ENFORCE_LOCAL_ONLY", "server", "boolean", "false"),
    EnvVarDefinition("ALLOW_PUBLIC_PROFILE_LIST", "server", "boolean", "true"),
    EnvVarDefinition("PUBLIC_URL", "server", "text"),

    # Storage & Backup
    EnvVarDefinition("NAS_STORAGE_PATH", "storage", "text", "./storage"),
    EnvVarDefinition("NAS_QUOTA_BYTES", "storage", "number"),
    EnvVarDefinition("NAS_BACKUP_PATH", "storage", "text", "./backups"),
    EnvVarDefinition("NAS_BACKUP_RETENTION_DAYS", "storage", "number", "30"),
    EnvVarDefinition("NAS_BACKUP_MAX_COUNT", "storage", "number", "10"),
    EnvVarDefinition("BACKUP_AUTO_ENABLED", "storage", "boolean", "false"),
    EnvVarDefinition("BACKUP_AUTO_INTERVAL_HOURS", "storage", "number", "24"),
    EnvVarDefinition("BACKUP_AUTO_TYPE", "storage", "text", "full"),

    # VPN
    EnvVarDefinition("VPN_ENCRYPTION_KEY", "vpn", "secret"),
    EnvVarDefinition("VPN_LAN_NETWORK", "vpn", "text", "192.168.178.0/24"),
    EnvVarDefinition("VPN_LAN_INTERFACE", "vpn", "text"),
    EnvVarDefinition("VPN_INCLUDE_LAN", "vpn", "boolean", "true"),
    EnvVarDefinition("VPN_CONFIG_PATH", "vpn", "text", "/etc/wireguard/wg0.conf"),

    # Monitoring
    EnvVarDefinition("MONITORING_SAMPLE_INTERVAL", "monitoring", "number", "5.0"),
    EnvVarDefinition("MONITORING_BUFFER_SIZE", "monitoring", "number", "120"),
    EnvVarDefinition("MONITORING_DB_PERSIST_INTERVAL", "monitoring", "number", "12"),
    EnvVarDefinition("MONITORING_DEFAULT_RETENTION_HOURS", "monitoring", "number", "168"),

    # Power
    EnvVarDefinition("POWER_MANAGEMENT_ENABLED", "power", "boolean", "true"),
    EnvVarDefinition("POWER_DEFAULT_PROFILE", "power", "text", "idle"),
    EnvVarDefinition("POWER_AUTO_SCALING_ENABLED", "power", "boolean", "true"),
    EnvVarDefinition("POWER_CPU_SURGE_THRESHOLD", "power", "number", "80.0"),
    EnvVarDefinition("POWER_CPU_MEDIUM_THRESHOLD", "power", "number", "50.0"),
    EnvVarDefinition("POWER_CPU_LOW_THRESHOLD", "power", "number", "20.0"),

    # Fan
    EnvVarDefinition("FAN_CONTROL_ENABLED", "fan", "boolean", "true"),
    EnvVarDefinition("FAN_MIN_PWM_PERCENT", "fan", "number", "30"),
    EnvVarDefinition("FAN_EMERGENCY_TEMP_CELSIUS", "fan", "number", "85.0"),
    EnvVarDefinition("FAN_SAMPLE_INTERVAL_SECONDS", "fan", "number", "5.0"),

    # RAID
    EnvVarDefinition("RAID_FORCE_DEV_BACKEND", "raid", "boolean", "false"),
    EnvVarDefinition("RAID_ASSUME_CLEAN_BY_DEFAULT", "raid", "boolean", "false"),
    EnvVarDefinition("RAID_DRY_RUN", "raid", "boolean", "false"),
    EnvVarDefinition("RAID_SCRUB_ENABLED", "raid", "boolean", "true"),
    EnvVarDefinition("RAID_SCRUB_INTERVAL_HOURS", "raid", "number", "168"),
    EnvVarDefinition("SMART_SCAN_ENABLED", "raid", "boolean", "true"),
    EnvVarDefinition("SMART_SCAN_INTERVAL_MINUTES", "raid", "number", "60"),

    # WebDAV
    EnvVarDefinition("WEBDAV_ENABLED", "webdav", "boolean", "true"),
    EnvVarDefinition("WEBDAV_PORT", "webdav", "number", "8080"),
    EnvVarDefinition("WEBDAV_SSL_ENABLED", "webdav", "boolean", "true"),

    # Samba
    EnvVarDefinition("SAMBA_SHARES_CONF_PATH", "samba", "text", "/etc/samba/baluhost-shares.conf"),

    # Email
    EnvVarDefinition("EMAIL_ENABLED", "email", "boolean", "false"),
    EnvVarDefinition("SMTP_HOST", "email", "text"),
    EnvVarDefinition("SMTP_PORT", "email", "number", "587"),
    EnvVarDefinition("SMTP_USE_TLS", "email", "boolean", "true"),
    EnvVarDefinition("SMTP_USERNAME", "email", "text"),
    EnvVarDefinition("SMTP_PASSWORD", "email", "secret"),
    EnvVarDefinition("EMAIL_FROM_ADDRESS", "email", "text", "baluhost@example.com"),
    EnvVarDefinition("EMAIL_FROM_NAME", "email", "text", "BaluHost"),

    # Mobile
    EnvVarDefinition("MOBILE_SERVER_URL", "mobile", "text"),
    EnvVarDefinition("MOBILE_PAIRING_ALLOW_LAN", "mobile", "boolean", "true"),

    # Cloud
    EnvVarDefinition("CLOUD_IMPORT_ENABLED", "cloud", "boolean", "true"),
    EnvVarDefinition("GOOGLE_CLIENT_ID", "cloud", "text"),
    EnvVarDefinition("GOOGLE_CLIENT_SECRET", "cloud", "secret"),
    EnvVarDefinition("MICROSOFT_CLIENT_ID", "cloud", "text"),
    EnvVarDefinition("MICROSOFT_CLIENT_SECRET", "cloud", "secret"),

    # Network
    EnvVarDefinition("MDNS_HOSTNAME", "network", "text", "baluhost"),

    # Pi-hole
    EnvVarDefinition("PIHOLE_ENABLED", "pihole", "boolean", "false"),
    EnvVarDefinition("PIHOLE_WEB_PORT", "pihole", "number", "8053"),

    # BaluPi
    EnvVarDefinition("BALUPI_ENABLED", "balupi", "boolean", "false"),
    EnvVarDefinition("BALUPI_URL", "balupi", "text"),
    EnvVarDefinition("BALUPI_HANDSHAKE_SECRET", "balupi", "secret"),

    # Notifications & WebSocket
    EnvVarDefinition("NOTIFICATION_RETENTION_DAYS", "notifications", "number", "90"),
    EnvVarDefinition("WS_HEARTBEAT_INTERVAL", "notifications", "number", "30"),

    # Sleep
    EnvVarDefinition("SLEEP_MODE_ENABLED", "sleep", "boolean", "true"),

    # SSD Cache
    EnvVarDefinition("SSD_CACHE_ENABLED", "ssd_cache", "boolean", "true"),
    EnvVarDefinition("SSD_CACHE_DEFAULT_MODE", "ssd_cache", "text", "writethrough"),
]

_CLIENT_VARS: list[EnvVarDefinition] = [
    EnvVarDefinition("VITE_API_BASE_URL", "client", "text", "", file="client"),
    EnvVarDefinition("VITE_BUILD_TYPE", "client", "text", "dev", file="client"),
]

# Build lookup tables
REGISTRY: dict[str, EnvVarDefinition] = {}
for _v in _BACKEND_VARS:
    _v.file = "backend"
    REGISTRY[_v.key] = _v
for _v in _CLIENT_VARS:
    REGISTRY[_v.key] = _v

ALLOWED_KEYS = set(REGISTRY.keys())

ALL_CATEGORIES: list[str] = sorted(set(v.category for v in REGISTRY.values()))


# ---------------------------------------------------------------------------
# .env File Parsing & Writing
# ---------------------------------------------------------------------------

@dataclass
class _EnvLine:
    """Represents a single line in a .env file."""
    raw: str
    key: Optional[str] = None
    value: Optional[str] = None
    is_kv: bool = False


def _parse_env_file(path: Path) -> list[_EnvLine]:
    """Parse a .env file preserving comments, blanks, and order."""
    lines: list[_EnvLine] = []
    if not path.exists():
        return lines

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.rstrip("\n").rstrip("\r")
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                lines.append(_EnvLine(raw=raw))
                continue
            if "=" in stripped:
                key, _, val = stripped.partition("=")
                key = key.strip()
                # Remove surrounding quotes from value
                val = val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                    val = val[1:-1]
                lines.append(_EnvLine(raw=raw, key=key, value=val, is_kv=True))
            else:
                lines.append(_EnvLine(raw=raw))
    return lines


def _write_env_file(path: Path, lines: list[_EnvLine]) -> None:
    """Atomically write .env file, preserving structure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), prefix=".env.tmp.", suffix=""
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for line in lines:
                if line.is_kv and line.key is not None:
                    f.write(f"{line.key}={line.value}\n")
                else:
                    f.write(line.raw + "\n")
        os.replace(tmp_path, str(path))
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _is_sensitive(key: str) -> bool:
    """Check if a key name indicates a sensitive value."""
    return bool(SENSITIVE_PATTERN.search(key))


# ---------------------------------------------------------------------------
# Public Service Functions
# ---------------------------------------------------------------------------

def _resolve_env_path(file_type: str) -> Path:
    """Resolve the .env file path for the given file type.

    For backend: checks backend/.env, then project root .env.production
    For client: checks client/.env.development, then client/.env
    """
    project_root = Path(__file__).resolve().parent.parent.parent.parent  # up from services/ to project root

    if file_type == "backend":
        backend_env = project_root / "backend" / ".env"
        if backend_env.exists():
            return backend_env
        prod_env = project_root / ".env.production"
        if prod_env.exists():
            return prod_env
        # Default: create in backend/
        return backend_env
    else:
        client_dev = project_root / "client" / ".env.development"
        if client_dev.exists():
            return client_dev
        client_env = project_root / "client" / ".env"
        if client_env.exists():
            return client_env
        # Default
        return client_dev


def read_all_vars() -> dict:
    """Read all curated env vars from both files.

    Returns dict with keys: backend, client, categories.
    Sensitive values are masked.
    """
    result_backend: list[dict] = []
    result_client: list[dict] = []

    # Parse both files
    backend_path = _resolve_env_path("backend")
    client_path = _resolve_env_path("client")

    backend_lines = _parse_env_file(backend_path)
    client_lines = _parse_env_file(client_path)

    # Build lookup: key -> value from parsed lines
    backend_values: dict[str, str] = {}
    for line in backend_lines:
        if line.is_kv and line.key:
            backend_values[line.key] = line.value or ""

    client_values: dict[str, str] = {}
    for line in client_lines:
        if line.is_kv and line.key:
            client_values[line.key] = line.value or ""

    for defn in _BACKEND_VARS:
        raw_value = backend_values.get(defn.key, "")
        sensitive = _is_sensitive(defn.key)
        display_value = MASKED_VALUE if (sensitive and raw_value) else raw_value
        result_backend.append({
            "key": defn.key,
            "value": display_value,
            "is_sensitive": sensitive,
            "category": defn.category,
            "description_key": f"envConfig.descriptions.{defn.key}",
            "input_type": "secret" if sensitive else defn.input_type,
            "default": defn.default,
            "file": "backend",
        })

    for defn in _CLIENT_VARS:
        raw_value = client_values.get(defn.key, "")
        sensitive = _is_sensitive(defn.key)
        display_value = MASKED_VALUE if (sensitive and raw_value) else raw_value
        result_client.append({
            "key": defn.key,
            "value": display_value,
            "is_sensitive": sensitive,
            "category": defn.category,
            "description_key": f"envConfig.descriptions.{defn.key}",
            "input_type": "secret" if sensitive else defn.input_type,
            "default": defn.default,
            "file": "client",
        })

    return {
        "backend": result_backend,
        "client": result_client,
        "categories": ALL_CATEGORIES,
    }


def reveal_var(key: str) -> str:
    """Reveal the actual value of a sensitive variable.

    Raises ValueError if key is not in the registry.
    """
    if key not in REGISTRY:
        raise ValueError(f"Unknown variable: {key}")

    defn = REGISTRY[key]
    env_path = _resolve_env_path(defn.file)
    lines = _parse_env_file(env_path)

    for line in lines:
        if line.is_kv and line.key == key:
            return line.value or ""

    return ""


def update_vars(file_type: str, updates: list[dict[str, str]]) -> list[str]:
    """Update env vars in the specified file.

    Args:
        file_type: "backend" or "client"
        updates: list of {"key": ..., "value": ...} dicts

    Returns:
        List of keys that were actually changed.

    Raises:
        ValueError: If a key is not in the whitelist.
    """
    # Validate all keys first
    for u in updates:
        key = u["key"]
        if key not in ALLOWED_KEYS:
            raise ValueError(f"Variable '{key}' is not in the allowed registry")
        defn = REGISTRY[key]
        if defn.file != file_type:
            raise ValueError(
                f"Variable '{key}' belongs to '{defn.file}', not '{file_type}'"
            )

    env_path = _resolve_env_path(file_type)
    lines = _parse_env_file(env_path)

    # Build update map
    update_map: dict[str, str] = {u["key"]: u["value"] for u in updates}
    existing_keys: set[str] = set()
    changed: list[str] = []

    # Update existing lines in-place
    for line in lines:
        if line.is_kv and line.key in update_map:
            existing_keys.add(line.key)
            new_val = update_map[line.key]
            if line.value != new_val:
                line.value = new_val
                changed.append(line.key)

    # Append new keys that weren't in the file
    for key, value in update_map.items():
        if key not in existing_keys:
            lines.append(_EnvLine(raw="", key=key, value=value, is_kv=True))
            changed.append(key)

    if changed:
        _write_env_file(env_path, lines)
        logger.info("Updated %d env vars in %s: %s", len(changed), env_path, changed)

    return changed
