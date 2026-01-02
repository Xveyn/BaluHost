"""TUI configuration and constants."""
from pathlib import Path
from typing import Optional

# Token storage location
TOKEN_DIR = Path.home() / ".baluhost"
TOKEN_FILE = TOKEN_DIR / "token"
CONFIG_FILE = TOKEN_DIR / "config.json"

# Ensure directory exists
TOKEN_DIR.mkdir(exist_ok=True)


def save_token(token: str) -> None:
    """Save authentication token to file."""
    TOKEN_FILE.write_text(token)
    TOKEN_FILE.chmod(0o600)  # Secure permissions


def load_token() -> Optional[str]:
    """Load authentication token from file."""
    if not TOKEN_FILE.exists():
        return None
    try:
        return TOKEN_FILE.read_text().strip()
    except Exception:
        return None


def clear_token() -> None:
    """Remove saved token."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()


# TUI Theme colors
THEME_PRIMARY = "#00d4ff"
THEME_SUCCESS = "#00ff88"
THEME_WARNING = "#ffaa00"
THEME_ERROR = "#ff4444"
THEME_INFO = "#6699ff"

# Update intervals (seconds)
UPDATE_INTERVAL_FAST = 2.0  # Dashboard metrics
UPDATE_INTERVAL_SLOW = 5.0  # Background updates
UPDATE_INTERVAL_LOGS = 3.0  # Log streaming
