"""Utility functions and constants for the update service."""
import logging
import re
from pathlib import Path
from typing import Callable

from app.schemas.update import ReleaseNoteCategory

logger = logging.getLogger(__name__)

# Type for progress callback
ProgressCallback = Callable[[int, str], None]


def parse_version(tag: str) -> tuple[int, int, int, str]:
    """Parse semver tag (e.g., 'v1.5.0' or '1.5.0-beta') into comparable tuple."""
    # Remove leading 'v' if present
    tag = tag.lstrip("v")
    # Handle pre-release suffixes
    prerelease = ""
    if "-" in tag:
        tag, prerelease = tag.split("-", 1)
    parts = tag.split(".")
    major = int(parts[0]) if len(parts) > 0 else 0
    minor = int(parts[1]) if len(parts) > 1 else 0
    patch = int(parts[2]) if len(parts) > 2 else 0
    return (major, minor, patch, prerelease)


def version_to_string(version: tuple[int, int, int, str]) -> str:
    """Convert version tuple back to string."""
    major, minor, patch, prerelease = version
    base = f"{major}.{minor}.{patch}"
    return f"{base}-{prerelease}" if prerelease else base


def get_installed_version() -> tuple[int, int, int, str]:
    """Read the version from pyproject.toml (single source of truth)."""
    try:
        pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version") and "=" in line:
                ver = line.split("=", 1)[1].strip().strip('"').strip("'")
                return parse_version(ver)
    except Exception:
        pass
    # Fallback to importlib.metadata
    try:
        from importlib.metadata import version as pkg_version
        ver = pkg_version("baluhost-backend")
        return parse_version(ver)
    except Exception:
        logger.warning("Could not read version, falling back to 0.0.0")
        return (0, 0, 0, "")


# Mapping from conventional commit type to display name + icon
COMMIT_TYPE_MAP: dict[str, tuple[str, str]] = {
    "feat": ("Features", "sparkles"),
    "fix": ("Bug Fixes", "bug"),
    "perf": ("Performance", "zap"),
    "refactor": ("Refactoring", "wrench"),
    "chore": ("Maintenance", "cog"),
    "docs": ("Documentation", "book-open"),
    "test": ("Tests", "test-tube"),
    "style": ("Style", "paintbrush"),
    "ci": ("CI/CD", "cog"),
    "build": ("Build", "cog"),
}

# Regex for conventional commits: type(scope): description  OR  type: description
_CONVENTIONAL_RE = re.compile(r"^(\w+)(?:\([^)]*\))?:\s*(.+)$")


def _parse_conventional_commits(messages: list[str]) -> list[ReleaseNoteCategory]:
    """Parse conventional commit messages into categorized release notes.

    Groups commits by type (feat, fix, perf, etc.) and returns
    a list of ReleaseNoteCategory with cleaned-up descriptions.
    """
    grouped: dict[str, list[str]] = {}

    for msg in messages:
        match = _CONVENTIONAL_RE.match(msg)
        if match:
            commit_type = match.group(1).lower()
            description = match.group(2).strip()
        else:
            commit_type = "other"
            description = msg.strip()

        # Capitalize first letter
        if description:
            description = description[0].upper() + description[1:]

        category_name, _ = COMMIT_TYPE_MAP.get(commit_type, ("Other", "circle-dot"))

        if category_name not in grouped:
            grouped[category_name] = []
        grouped[category_name].append(description)

    # Build result in a stable order matching COMMIT_TYPE_MAP
    seen = set()
    categories: list[ReleaseNoteCategory] = []

    for _type, (name, icon) in COMMIT_TYPE_MAP.items():
        if name in grouped and name not in seen:
            seen.add(name)
            categories.append(ReleaseNoteCategory(
                name=name,
                icon=icon,
                changes=grouped[name],
            ))

    # Add "Other" at the end if present
    if "Other" in grouped:
        categories.append(ReleaseNoteCategory(
            name="Other",
            icon="circle-dot",
            changes=grouped["Other"],
        ))

    return categories
