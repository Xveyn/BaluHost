"""
Update Service for BaluHost.

Provides self-update functionality with:
- Version checking via Git tags
- Update installation with progress tracking
- Rollback capability
- Dev/Prod backend abstraction
"""
import asyncio
import logging
import os
import re
import subprocess
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Any

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.update_history import UpdateHistory, UpdateConfig, UpdateStatus, UpdateChannel
from app.schemas.update import (
    VersionInfo,
    ChangelogEntry,
    UpdateCheckResponse,
    UpdateStartResponse,
    UpdateProgressResponse,
    UpdateHistoryEntry,
    UpdateHistoryResponse,
    RollbackRequest,
    RollbackResponse,
    UpdateConfigResponse,
    UpdateConfigUpdate,
    ReleaseNoteCategory,
    ReleaseNotesResponse,
    CommitInfo,
    VersionGroup,
    CommitHistoryResponse,
    DiffFile,
    CommitDiffResponse,
)
from app.services.service_status import register_service

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


class UpdateBackend(ABC):
    """Abstract backend for update operations."""

    @abstractmethod
    async def get_current_version(self) -> VersionInfo:
        """Get the current installed version."""
        pass

    @abstractmethod
    async def check_for_updates(self, channel: str) -> tuple[bool, Optional[VersionInfo], list[ChangelogEntry]]:
        """
        Check if updates are available.

        Returns:
            Tuple of (update_available, latest_version, changelog)
        """
        pass

    @abstractmethod
    async def fetch_updates(self, callback: Optional[ProgressCallback] = None) -> bool:
        """Fetch updates from remote (git fetch)."""
        pass

    @abstractmethod
    async def apply_updates(
        self, target_commit: str, callback: Optional[ProgressCallback] = None
    ) -> tuple[bool, Optional[str]]:
        """Apply updates (git checkout/pull). Returns (success, error_message)."""
        pass

    @abstractmethod
    async def install_dependencies(self, callback: Optional[ProgressCallback] = None) -> tuple[bool, Optional[str]]:
        """Install Python/Node dependencies. Returns (success, error_message)."""
        pass

    @abstractmethod
    async def run_migrations(self, callback: Optional[ProgressCallback] = None) -> tuple[bool, Optional[str]]:
        """Run database migrations. Returns (success, error_message)."""
        pass

    @abstractmethod
    async def restart_services(self, callback: Optional[ProgressCallback] = None) -> tuple[bool, Optional[str]]:
        """Restart the backend service. Returns (success, error_message)."""
        pass

    @abstractmethod
    async def rollback(self, commit: str) -> tuple[bool, Optional[str]]:
        """Rollback to a specific commit. Returns (success, error_message)."""
        pass

    @abstractmethod
    async def get_release_notes(self) -> ReleaseNotesResponse:
        """Get release notes for the current version (commits since previous tag)."""
        pass

    @abstractmethod
    async def health_check(self) -> tuple[bool, list[str]]:
        """Check if services are healthy. Returns (healthy, issues)."""
        pass

    @abstractmethod
    async def get_commit_history(self) -> CommitHistoryResponse:
        """Get full commit history grouped by version tags."""
        pass

    @abstractmethod
    async def get_commit_diff(self, commit_hash: str) -> CommitDiffResponse:
        """Get diff details for a specific commit."""
        pass


class DevUpdateBackend(UpdateBackend):
    """Development backend that simulates updates without real changes."""

    def __init__(self):
        self._simulated_version = parse_version("1.4.2")
        self._latest_version = parse_version("1.5.0")
        self._current_commit = "abc1234567890abcdef1234567890abcdef12"
        self._latest_commit = "def7890123456789abcdef1234567890abcd56"

    async def get_current_version(self) -> VersionInfo:
        return VersionInfo(
            version=version_to_string(self._simulated_version),
            commit=self._current_commit,
            commit_short=self._current_commit[:7],
            tag=f"v{version_to_string(self._simulated_version)}",
            date=datetime.now(timezone.utc),
        )

    async def check_for_updates(self, channel: str) -> tuple[bool, Optional[VersionInfo], list[ChangelogEntry]]:
        # Simulate that an update is available
        include_beta = channel == "beta"

        changelog = [
            ChangelogEntry(
                version="1.5.0",
                date=datetime.now(timezone.utc),
                changes=[
                    "Added self-update functionality",
                    "Improved performance for large file operations",
                    "Fixed WebSocket reconnection issues",
                ],
                breaking_changes=[],
                is_prerelease=False,
            ),
        ]

        if include_beta:
            changelog.insert(0, ChangelogEntry(
                version="1.6.0-beta",
                date=datetime.now(timezone.utc),
                changes=["Early preview of new dashboard widgets"],
                breaking_changes=["API endpoint changes for monitoring"],
                is_prerelease=True,
            ))
            return True, VersionInfo(
                version="1.6.0-beta",
                commit="beta123456789abcdef1234567890abcdef12",
                commit_short="beta123",
                tag="v1.6.0-beta",
                date=datetime.now(timezone.utc),
            ), changelog

        return True, VersionInfo(
            version=version_to_string(self._latest_version),
            commit=self._latest_commit,
            commit_short=self._latest_commit[:7],
            tag=f"v{version_to_string(self._latest_version)}",
            date=datetime.now(timezone.utc),
        ), changelog

    async def get_release_notes(self) -> ReleaseNotesResponse:
        """Return mock release notes for dev mode."""
        return ReleaseNotesResponse(
            version=version_to_string(self._simulated_version),
            previous_version="1.1.0-alpha",
            date=datetime.now(timezone.utc),
            categories=[
                ReleaseNoteCategory(
                    name="Features",
                    icon="sparkles",
                    changes=[
                        "Add SSD cache management with bcache support",
                        "Add SMB and WebDAV service discovery",
                        "Add WSDD deployment script for Windows network discovery",
                    ],
                ),
                ReleaseNoteCategory(
                    name="Bug Fixes",
                    icon="bug",
                    changes=[
                        "Skip create_all for PostgreSQL (managed by Alembic)",
                        "Fix storage aggregation for RAID fallback path",
                    ],
                ),
                ReleaseNoteCategory(
                    name="Performance",
                    icon="zap",
                    changes=[
                        "Optimize Samba config for small-file transfers",
                    ],
                ),
            ],
        )

    async def fetch_updates(self, callback: Optional[ProgressCallback] = None) -> bool:
        """Simulate fetching updates."""
        steps = [
            (10, "Fetching remote tags..."),
            (30, "Downloading objects..."),
            (60, "Resolving deltas..."),
            (100, "Fetch complete"),
        ]
        for progress, step in steps:
            if callback:
                callback(progress, step)
            await asyncio.sleep(0.5)  # Simulate network delay
        return True

    async def apply_updates(
        self, target_commit: str, callback: Optional[ProgressCallback] = None
    ) -> tuple[bool, Optional[str]]:
        """Simulate applying updates."""
        steps = [
            (20, "Checking out target version..."),
            (50, "Updating working directory..."),
            (80, "Verifying file integrity..."),
            (100, "Update applied"),
        ]
        for progress, step in steps:
            if callback:
                callback(progress, step)
            await asyncio.sleep(0.3)
        self._current_commit = target_commit
        return True, None

    async def install_dependencies(self, callback: Optional[ProgressCallback] = None) -> tuple[bool, Optional[str]]:
        """Simulate installing dependencies."""
        steps = [
            (10, "Installing Python dependencies..."),
            (40, "Installing Node dependencies..."),
            (70, "Building frontend..."),
            (100, "Dependencies installed"),
        ]
        for progress, step in steps:
            if callback:
                callback(progress, step)
            await asyncio.sleep(0.8)
        return True, None

    async def run_migrations(self, callback: Optional[ProgressCallback] = None) -> tuple[bool, Optional[str]]:
        """Simulate running migrations."""
        steps = [
            (30, "Running alembic upgrade..."),
            (70, "Applying schema changes..."),
            (100, "Migrations complete"),
        ]
        for progress, step in steps:
            if callback:
                callback(progress, step)
            await asyncio.sleep(0.4)
        return True, None

    async def restart_services(self, callback: Optional[ProgressCallback] = None) -> tuple[bool, Optional[str]]:
        """Simulate service restart (dev mode doesn't actually restart)."""
        if callback:
            callback(50, "Simulating service restart (dev mode)...")
        await asyncio.sleep(1)
        if callback:
            callback(100, "Service restart simulated")
        return True, None

    async def rollback(self, commit: str) -> tuple[bool, Optional[str]]:
        """Simulate rollback."""
        logger.info(f"[DEV] Simulating rollback to {commit}")
        self._current_commit = commit
        return True, None

    async def health_check(self) -> tuple[bool, list[str]]:
        """Simulate health check."""
        return True, []

    async def get_commit_history(self) -> CommitHistoryResponse:
        """Return mock commit history for dev mode."""
        now = datetime.now(timezone.utc).isoformat()
        commits_v2 = [
            CommitInfo(hash="aaa1111111111111111111111111111111111111", hash_short="aaa1111", message="feat(dashboard): add real-time CPU chart", date=now, author="Dev User", type="feat", scope="dashboard"),
            CommitInfo(hash="bbb2222222222222222222222222222222222222", hash_short="bbb2222", message="fix(auth): resolve token refresh race condition", date=now, author="Dev User", type="fix", scope="auth"),
            CommitInfo(hash="ccc3333333333333333333333333333333333333", hash_short="ccc3333", message="chore: bump dependencies", date=now, author="Dev User", type="chore", scope=None),
        ]
        commits_v1 = [
            CommitInfo(hash="ddd4444444444444444444444444444444444444", hash_short="ddd4444", message="feat: initial project setup", date=now, author="Dev User", type="feat", scope=None),
            CommitInfo(hash="eee5555555555555555555555555555555555555", hash_short="eee5555", message="docs: add README", date=now, author="Dev User", type="docs", scope=None),
        ]
        commits_unreleased = [
            CommitInfo(hash="fff6666666666666666666666666666666666666", hash_short="fff6666", message="feat(updates): add versions tab with commit history", date=now, author="Dev User", type="feat", scope="updates"),
            CommitInfo(hash="ggg7777777777777777777777777777777777777", hash_short="ggg7777", message="refactor(api): consolidate error handling", date=now, author="Dev User", type="refactor", scope="api"),
        ]
        return CommitHistoryResponse(
            total_commits=7,
            groups=[
                VersionGroup(tag=None, version="Unreleased", date=None, commit_count=2, commits=commits_unreleased),
                VersionGroup(tag="v1.5.0-alpha", version="1.5.0-alpha", date=now, commit_count=3, commits=commits_v2),
                VersionGroup(tag="v1.0.0-alpha", version="1.0.0-alpha", date=now, commit_count=2, commits=commits_v1),
            ],
        )

    async def get_commit_diff(self, commit_hash: str) -> CommitDiffResponse:
        """Return mock diff for dev mode."""
        now = datetime.now(timezone.utc).isoformat()
        return CommitDiffResponse(
            hash=commit_hash,
            hash_short=commit_hash[:7],
            message="feat(dashboard): add real-time CPU chart",
            date=now,
            author="Dev User",
            stats="2 files changed, 45 insertions(+), 3 deletions(-)",
            files=[
                DiffFile(path="client/src/pages/Dashboard.tsx", status="modified", additions=40, deletions=3),
                DiffFile(path="client/src/components/CpuChart.tsx", status="added", additions=5, deletions=0),
            ],
            diff="diff --git a/client/src/pages/Dashboard.tsx b/client/src/pages/Dashboard.tsx\n--- a/client/src/pages/Dashboard.tsx\n+++ b/client/src/pages/Dashboard.tsx\n@@ -1,5 +1,10 @@\n import React from 'react';\n+import { CpuChart } from '../components/CpuChart';\n \n export default function Dashboard() {\n-  return <div>Dashboard</div>;\n+  return (\n+    <div>\n+      <CpuChart />\n+    </div>\n+  );\n }\n",
        )


class ProdUpdateBackend(UpdateBackend):
    """Production backend using Git and systemctl."""

    def __init__(self, repo_path: Optional[Path] = None):
        # Default to the project root
        self.repo_path = repo_path or Path(__file__).parent.parent.parent.parent
        self.backend_path = self.repo_path / "backend"
        self.client_path = self.repo_path / "client"

    def _run_git(self, *args: str) -> tuple[bool, str, str]:
        """Run a git command and return (success, stdout, stderr)."""
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=300,
            )
            return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "", "Command timed out"
        except Exception as e:
            return False, "", str(e)

    async def get_current_version(self) -> VersionInfo:
        """Get version from git describe or latest tag."""
        # Get current commit
        success, commit, _ = self._run_git("rev-parse", "HEAD")
        if not success:
            commit = "unknown"

        # Try git describe for version
        success, describe, _ = self._run_git("describe", "--tags", "--abbrev=0")
        if success:
            tag = describe
            version = tag.lstrip("v")
        else:
            # Fallback to checking package version
            version = "1.0.0"
            tag = None

        # Get commit date
        success, date_str, _ = self._run_git("log", "-1", "--format=%cI")
        date = datetime.fromisoformat(date_str) if success and date_str else None

        return VersionInfo(
            version=version,
            commit=commit,
            commit_short=commit[:7] if commit != "unknown" else "unknown",
            tag=tag,
            date=date,
        )

    async def check_for_updates(self, channel: str) -> tuple[bool, Optional[VersionInfo], list[ChangelogEntry]]:
        """Check for updates by fetching tags and comparing versions."""
        # Fetch tags
        success, _, err = self._run_git("fetch", "--tags", "--force")
        if not success:
            logger.warning(f"Failed to fetch tags: {err}")
            return False, None, []

        # Get current version
        current = await self.get_current_version()
        current_version = parse_version(current.version)

        # Get all tags
        success, tags_output, _ = self._run_git("tag", "-l", "--sort=-version:refname")
        if not success or not tags_output:
            return False, None, []

        tags = [t.strip() for t in tags_output.split("\n") if t.strip()]

        # Filter tags based on channel
        include_prerelease = channel == "beta"
        latest_tag = None
        latest_version = current_version

        for tag in tags:
            version = parse_version(tag)
            is_prerelease = bool(version[3])

            if not include_prerelease and is_prerelease:
                continue

            if version > latest_version:
                latest_version = version
                latest_tag = tag

        if latest_tag is None:
            return False, None, []

        # Get commit for latest tag
        success, commit, _ = self._run_git("rev-parse", latest_tag)
        if not success:
            return False, None, []

        # Get tag date
        success, date_str, _ = self._run_git("log", "-1", "--format=%cI", latest_tag)
        date = datetime.fromisoformat(date_str) if success and date_str else None

        latest = VersionInfo(
            version=version_to_string(latest_version),
            commit=commit,
            commit_short=commit[:7],
            tag=latest_tag,
            date=date,
        )

        # Build changelog from commit messages between versions
        changelog = await self._build_changelog(current.commit, commit)

        return True, latest, changelog

    async def _build_changelog(self, from_commit: str, to_commit: str) -> list[ChangelogEntry]:
        """Build changelog from git log between commits."""
        success, log_output, _ = self._run_git(
            "log", f"{from_commit}..{to_commit}",
            "--pretty=format:%s", "--no-merges"
        )

        if not success or not log_output:
            return []

        changes = [line.strip() for line in log_output.split("\n") if line.strip()]

        # Parse conventional commits for breaking changes
        breaking = [c for c in changes if "BREAKING" in c.upper() or c.startswith("!")]
        regular = [c for c in changes if c not in breaking]

        return [
            ChangelogEntry(
                version="latest",
                date=datetime.now(timezone.utc),
                changes=regular[:20],  # Limit to 20 changes
                breaking_changes=breaking,
                is_prerelease=False,
            )
        ]

    async def get_release_notes(self) -> ReleaseNotesResponse:
        """Get release notes by comparing current tag with the previous tag."""
        # Get all tags sorted by semver
        success, tags_output, _ = self._run_git("tag", "-l", "--sort=-version:refname")
        if not success or not tags_output:
            return ReleaseNotesResponse(version="unknown", categories=[])

        tags = [t.strip() for t in tags_output.split("\n") if t.strip()]
        if not tags:
            return ReleaseNotesResponse(version="unknown", categories=[])

        # Sort tags by semver properly
        sorted_tags = sorted(tags, key=lambda t: parse_version(t), reverse=True)

        # Get current version info
        current = await self.get_current_version()
        current_version = parse_version(current.version)

        # Find current tag and the one before it
        current_tag: Optional[str] = None
        previous_tag: Optional[str] = None

        for i, tag in enumerate(sorted_tags):
            if parse_version(tag) <= current_version:
                current_tag = tag
                if i + 1 < len(sorted_tags):
                    previous_tag = sorted_tags[i + 1]
                break

        if not current_tag:
            return ReleaseNotesResponse(version=current.version, categories=[])

        # Get tag date
        success, date_str, _ = self._run_git("log", "-1", "--format=%cI", current_tag)
        tag_date = datetime.fromisoformat(date_str) if success and date_str else None

        if not previous_tag:
            # No previous tag — list all commits up to current tag
            success, log_output, _ = self._run_git(
                "log", current_tag, "--pretty=format:%s", "--no-merges"
            )
        else:
            success, log_output, _ = self._run_git(
                "log", f"{previous_tag}..{current_tag}",
                "--pretty=format:%s", "--no-merges"
            )

        if not success or not log_output:
            return ReleaseNotesResponse(
                version=current.version,
                previous_version=previous_tag.lstrip("v") if previous_tag else None,
                date=tag_date,
                categories=[],
            )

        messages = [line.strip() for line in log_output.split("\n") if line.strip()]
        categories = _parse_conventional_commits(messages)

        return ReleaseNotesResponse(
            version=current.version,
            previous_version=previous_tag.lstrip("v") if previous_tag else None,
            date=tag_date,
            categories=categories,
        )

    async def fetch_updates(self, callback: Optional[ProgressCallback] = None) -> bool:
        if callback:
            callback(10, "Fetching from remote...")

        success, _, err = self._run_git("fetch", "--all", "--tags", "--prune")

        if callback:
            callback(100, "Fetch complete" if success else f"Fetch failed: {err}")

        return success

    async def apply_updates(
        self, target_commit: str, callback: Optional[ProgressCallback] = None
    ) -> tuple[bool, Optional[str]]:
        if callback:
            callback(10, "Stashing local changes...")

        # Stash any local changes
        self._run_git("stash", "push", "-m", "pre-update-stash")

        if callback:
            callback(30, f"Checking out {target_commit[:8]}...")

        # Checkout the target
        success, _, err = self._run_git("checkout", target_commit)
        if not success:
            # Try to restore
            self._run_git("stash", "pop")
            return False, f"Failed to checkout: {err}"

        if callback:
            callback(70, "Pulling latest changes...")

        # If on a branch, pull to ensure we're up to date
        success, branch, _ = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        if success and branch not in ("HEAD", ""):
            self._run_git("pull", "--rebase")

        if callback:
            callback(100, "Update applied")

        return True, None

    async def install_dependencies(self, callback: Optional[ProgressCallback] = None) -> tuple[bool, Optional[str]]:
        errors = []

        # Install Python dependencies
        if callback:
            callback(10, "Installing Python dependencies...")

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", ".[dev]"],
                cwd=self.backend_path,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                errors.append(f"pip install failed: {result.stderr}")
        except Exception as e:
            errors.append(f"pip install error: {e}")

        # Install Node dependencies and build frontend
        if callback:
            callback(40, "Installing Node dependencies...")

        try:
            result = subprocess.run(
                ["npm", "install"],
                cwd=self.client_path,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                errors.append(f"npm install failed: {result.stderr}")
        except Exception as e:
            errors.append(f"npm install error: {e}")

        if callback:
            callback(70, "Building frontend...")

        try:
            result = subprocess.run(
                ["npm", "run", "build"],
                cwd=self.client_path,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                errors.append(f"npm build failed: {result.stderr}")
        except Exception as e:
            errors.append(f"npm build error: {e}")

        if callback:
            callback(100, "Dependencies installed" if not errors else "Some errors occurred")

        return len(errors) == 0, "; ".join(errors) if errors else None

    async def run_migrations(self, callback: Optional[ProgressCallback] = None) -> tuple[bool, Optional[str]]:
        if callback:
            callback(20, "Running database migrations...")

        try:
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=self.backend_path,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if callback:
                callback(100, "Migrations complete" if result.returncode == 0 else "Migration failed")

            if result.returncode != 0:
                return False, f"Migration failed: {result.stderr}"

            return True, None
        except Exception as e:
            if callback:
                callback(100, f"Migration error: {e}")
            return False, str(e)

    async def restart_services(self, callback: Optional[ProgressCallback] = None) -> tuple[bool, Optional[str]]:
        if callback:
            callback(20, "Restarting baluhost-backend service...")

        try:
            result = subprocess.run(
                ["sudo", "systemctl", "restart", "baluhost-backend"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if callback:
                callback(100, "Service restarted" if result.returncode == 0 else "Restart failed")

            if result.returncode != 0:
                return False, f"Service restart failed: {result.stderr}"

            return True, None
        except Exception as e:
            if callback:
                callback(100, f"Restart error: {e}")
            return False, str(e)

    async def rollback(self, commit: str) -> tuple[bool, Optional[str]]:
        """Rollback to a specific commit."""
        logger.info(f"Rolling back to {commit}")

        success, _, err = self._run_git("checkout", commit)
        if not success:
            return False, f"Rollback failed: {err}"

        # Re-run migrations (downgrade if needed)
        success, err = await self.run_migrations()
        if not success:
            logger.warning(f"Migration after rollback had issues: {err}")

        return True, None

    async def health_check(self) -> tuple[bool, list[str]]:
        """Check service health via API."""
        issues = []

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://localhost:3001/api/health",
                    timeout=10,
                )
                if response.status_code != 200:
                    issues.append(f"Health endpoint returned {response.status_code}")
        except Exception as e:
            issues.append(f"Health check failed: {e}")

        return len(issues) == 0, issues

    # --- Commit History ---

    _SCOPE_RE = re.compile(r"^(\w+)\(([^)]*)\):\s*(.+)$")

    def _parse_commit_lines(self, output: str) -> list[CommitInfo]:
        """Parse git log output (pipe-separated) into CommitInfo objects."""
        commits: list[CommitInfo] = []
        for line in output.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("|", 4)
            if len(parts) < 5:
                continue
            full_hash, short_hash, subject, date_str, author = parts

            # Extract conventional commit type and scope
            commit_type: Optional[str] = None
            scope: Optional[str] = None
            scope_match = self._SCOPE_RE.match(subject)
            if scope_match:
                commit_type = scope_match.group(1).lower()
                scope = scope_match.group(2) or None
            else:
                conv_match = _CONVENTIONAL_RE.match(subject)
                if conv_match:
                    commit_type = conv_match.group(1).lower()

            commits.append(CommitInfo(
                hash=full_hash,
                hash_short=short_hash,
                message=subject,
                date=date_str,
                author=author,
                type=commit_type,
                scope=scope,
            ))
        return commits

    async def get_commit_history(self) -> CommitHistoryResponse:
        """Get full commit history grouped by version tags."""
        # Get all tags sorted by semver
        success, tags_output, _ = self._run_git("tag", "-l", "--sort=version:refname")
        if not success:
            return CommitHistoryResponse(total_commits=0, groups=[])

        tags = [t.strip() for t in tags_output.strip().split("\n") if t.strip()]

        groups: list[VersionGroup] = []
        total = 0
        log_format = "%H|%h|%s|%aI|%an"

        # Build groups for each tag pair
        prev_ref: Optional[str] = None
        for tag in tags:
            if prev_ref is None:
                # First tag: all commits up to this tag
                success, log_output, _ = self._run_git(
                    "log", tag, f"--pretty=format:{log_format}", "--no-merges"
                )
            else:
                success, log_output, _ = self._run_git(
                    "log", f"{prev_ref}..{tag}", f"--pretty=format:{log_format}", "--no-merges"
                )

            if success and log_output.strip():
                commits = self._parse_commit_lines(log_output)
            else:
                commits = []

            # Get tag date
            ok, date_str, _ = self._run_git("log", "-1", "--format=%aI", tag)
            tag_date = date_str if ok and date_str else None

            total += len(commits)
            groups.append(VersionGroup(
                tag=tag,
                version=tag.lstrip("v"),
                date=tag_date,
                commit_count=len(commits),
                commits=commits,
            ))
            prev_ref = tag

        # Check for unreleased commits (last tag → HEAD)
        if tags:
            success, log_output, _ = self._run_git(
                "log", f"{tags[-1]}..HEAD", f"--pretty=format:{log_format}", "--no-merges"
            )
            if success and log_output.strip():
                commits = self._parse_commit_lines(log_output)
                if commits:
                    total += len(commits)
                    groups.append(VersionGroup(
                        tag=None,
                        version="Unreleased",
                        date=None,
                        commit_count=len(commits),
                        commits=commits,
                    ))

        # Reverse so newest group is first
        groups.reverse()

        return CommitHistoryResponse(total_commits=total, groups=groups)

    async def get_commit_diff(self, commit_hash: str) -> CommitDiffResponse:
        """Get diff details for a specific commit."""
        # Validate hash format
        if not re.match(r"^[0-9a-fA-F]{7,40}$", commit_hash):
            raise ValueError(f"Invalid commit hash format: {commit_hash}")

        # Get commit info
        success, info_output, _ = self._run_git(
            "log", "-1", "--pretty=format:%H|%h|%s|%aI|%an", commit_hash
        )
        if not success or not info_output.strip():
            raise ValueError(f"Commit not found: {commit_hash}")

        parts = info_output.split("|", 4)
        if len(parts) < 5:
            raise ValueError(f"Failed to parse commit info: {commit_hash}")

        full_hash, short_hash, subject, date_str, author = parts

        # Get diff stat
        success, stat_output, _ = self._run_git("diff", "--stat", f"{commit_hash}~1", commit_hash)
        stats = stat_output.strip().split("\n")[-1].strip() if success and stat_output.strip() else ""

        # Get changed files with status
        success, ns_output, _ = self._run_git("diff", "--name-status", f"{commit_hash}~1", commit_hash)
        files: list[DiffFile] = []
        if success and ns_output.strip():
            # Also get numstat for additions/deletions
            ok_num, numstat_output, _ = self._run_git("diff", "--numstat", f"{commit_hash}~1", commit_hash)
            numstat_map: dict[str, tuple[int, int]] = {}
            if ok_num and numstat_output.strip():
                for ns_line in numstat_output.strip().split("\n"):
                    ns_parts = ns_line.split("\t")
                    if len(ns_parts) >= 3:
                        adds = int(ns_parts[0]) if ns_parts[0] != "-" else 0
                        dels = int(ns_parts[1]) if ns_parts[1] != "-" else 0
                        numstat_map[ns_parts[2]] = (adds, dels)

            status_map = {"A": "added", "M": "modified", "D": "deleted", "R": "renamed"}
            for line in ns_output.strip().split("\n"):
                if not line.strip():
                    continue
                line_parts = line.split("\t")
                if len(line_parts) < 2:
                    continue
                raw_status = line_parts[0][0]  # First char (R100 → R)
                file_path = line_parts[-1]  # Last part (handles renames)
                adds, dels = numstat_map.get(file_path, (0, 0))
                files.append(DiffFile(
                    path=file_path,
                    status=status_map.get(raw_status, "modified"),
                    additions=adds,
                    deletions=dels,
                ))

        # Get raw diff (truncated to 500KB)
        success, diff_output, _ = self._run_git("diff", f"{commit_hash}~1", commit_hash)
        diff_text = diff_output if success else ""
        max_diff_size = 500 * 1024
        if len(diff_text) > max_diff_size:
            diff_text = diff_text[:max_diff_size] + "\n\n... (diff truncated at 500KB)"

        return CommitDiffResponse(
            hash=full_hash,
            hash_short=short_hash,
            message=subject,
            date=date_str,
            author=author,
            stats=stats,
            files=files,
            diff=diff_text,
        )


# Global singleton for the update service
_update_service: Optional["UpdateService"] = None


def get_update_backend() -> UpdateBackend:
    """Get the appropriate backend based on settings."""
    if settings.is_dev_mode:
        return DevUpdateBackend()
    return ProdUpdateBackend()


class UpdateService:
    """Main update service coordinating update operations."""

    def __init__(self, db: Session, backend: Optional[UpdateBackend] = None):
        self.db = db
        self.backend = backend or get_update_backend()
        self._current_update: Optional[UpdateHistory] = None
        self._progress_callbacks: list[ProgressCallback] = []

    def add_progress_callback(self, callback: ProgressCallback) -> None:
        """Register a callback to receive progress updates."""
        self._progress_callbacks.append(callback)

    def remove_progress_callback(self, callback: ProgressCallback) -> None:
        """Unregister a progress callback."""
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)

    def _notify_progress(self, percent: int, step: str) -> None:
        """Notify all registered callbacks of progress."""
        for callback in self._progress_callbacks:
            try:
                callback(percent, step)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")

        # Also update the current update record if we have one
        if self._current_update:
            self._current_update.set_progress(percent, step)
            self.db.commit()

    def get_config(self) -> UpdateConfigResponse:
        """Get current update configuration."""
        config = self.db.query(UpdateConfig).first()
        if not config:
            # Create default config
            config = UpdateConfig(
                auto_check_enabled=True,
                check_interval_hours=24,
                channel=UpdateChannel.STABLE.value,
                auto_backup_before_update=True,
                require_healthy_services=True,
                auto_update_enabled=False,
            )
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)

        return UpdateConfigResponse.model_validate(config)

    def update_config(self, updates: UpdateConfigUpdate, user_id: int) -> UpdateConfigResponse:
        """Update configuration."""
        config = self.db.query(UpdateConfig).first()
        if not config:
            config = UpdateConfig()
            self.db.add(config)

        update_data = updates.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                setattr(config, key, value)

        config.updated_by = user_id
        self.db.commit()
        self.db.refresh(config)

        return UpdateConfigResponse.model_validate(config)

    async def check_for_updates(self) -> UpdateCheckResponse:
        """Check if updates are available."""
        config = self.get_config()

        # Get current version
        current = await self.backend.get_current_version()

        # Check for blockers
        blockers = await self._check_blockers()

        # Check for updates
        available, latest, changelog = await self.backend.check_for_updates(config.channel)

        # Update last check time
        db_config = self.db.query(UpdateConfig).first()
        if db_config:
            db_config.last_check_at = datetime.now(timezone.utc)
            if latest:
                db_config.last_available_version = latest.version
            self.db.commit()

        return UpdateCheckResponse(
            update_available=available,
            current_version=current,
            latest_version=latest,
            changelog=changelog,
            channel=config.channel,
            last_checked=datetime.now(timezone.utc),
            blockers=blockers,
            can_update=available and len(blockers) == 0,
        )

    async def get_release_notes(self) -> ReleaseNotesResponse:
        """Get release notes for the current version."""
        return await self.backend.get_release_notes()

    async def _check_blockers(self) -> list[str]:
        """Check for conditions that block updates."""
        blockers = []
        config = self.get_config()

        # Check for running update
        running = (
            self.db.query(UpdateHistory)
            .filter(UpdateHistory.status.in_([
                UpdateStatus.DOWNLOADING.value,
                UpdateStatus.INSTALLING.value,
                UpdateStatus.MIGRATING.value,
                UpdateStatus.RESTARTING.value,
            ]))
            .first()
        )
        if running:
            blockers.append(f"Update already in progress (ID: {running.id})")

        # Check service health if required (skip in dev mode - always healthy)
        if config.require_healthy_services and not settings.is_dev_mode:
            healthy, issues = await self.backend.health_check()
            if not healthy:
                blockers.extend([f"Service unhealthy: {issue}" for issue in issues])

        return blockers

    async def start_update(
        self,
        user_id: int,
        target_version: Optional[str] = None,
        skip_backup: bool = False,
        force: bool = False,
    ) -> UpdateStartResponse:
        """Start the update process."""
        # Check for blockers
        blockers = await self._check_blockers()
        if blockers and not force:
            return UpdateStartResponse(
                success=False,
                message="Update blocked",
                blockers=blockers,
            )

        # Get current and target versions
        current = await self.backend.get_current_version()
        check_result = await self.check_for_updates()

        if not check_result.update_available:
            return UpdateStartResponse(
                success=False,
                message="No update available",
            )

        target = check_result.latest_version
        if target_version:
            # User specified a version - we'd need to look it up
            # For now, use latest
            pass

        # Create update record
        update = UpdateHistory(
            from_version=current.version,
            to_version=target.version,
            channel=check_result.channel,
            from_commit=current.commit,
            to_commit=target.commit,
            user_id=user_id,
            status=UpdateStatus.PENDING.value,
            changelog="\n".join(
                f"- {change}" for entry in check_result.changelog for change in entry.changes
            ),
        )
        self.db.add(update)
        self.db.commit()
        self.db.refresh(update)

        self._current_update = update

        # Start update in background
        asyncio.create_task(self._run_update(update.id, skip_backup))

        return UpdateStartResponse(
            success=True,
            update_id=update.id,
            message=f"Update to {target.version} started",
        )

    async def _run_update(self, update_id: int, skip_backup: bool) -> None:
        """Run the actual update process."""
        # Get fresh session for async context
        db = SessionLocal()
        try:
            update = db.query(UpdateHistory).filter(UpdateHistory.id == update_id).first()
            if not update:
                return

            config = db.query(UpdateConfig).first()

            def progress(percent: int, step: str):
                update.set_progress(percent, step)
                db.commit()
                self._notify_progress(percent, step)

            try:
                # Step 1: Backup (if enabled)
                if config and config.auto_backup_before_update and not skip_backup:
                    update.status = UpdateStatus.BACKING_UP.value
                    progress(5, "Creating backup...")

                    try:
                        from app.services.backup import BackupService
                        from app.schemas.backup import BackupCreate

                        backup_service = BackupService(db)
                        backup_data = BackupCreate(
                            backup_type="full",
                            includes_database=True,
                            includes_files=False,  # Just DB for speed
                            includes_config=True,
                        )
                        backup = backup_service.create_backup(
                            backup_data,
                            update.user_id or 0,
                            "update_service",
                        )
                        update.backup_id = backup.id
                        db.commit()
                        progress(10, "Backup complete")
                    except Exception as e:
                        logger.warning(f"Backup failed during update: {e}")
                        progress(10, f"Backup skipped: {e}")

                # Step 2: Fetch
                update.status = UpdateStatus.DOWNLOADING.value
                progress(15, "Fetching updates...")

                success = await self.backend.fetch_updates(
                    lambda p, s: progress(15 + int(p * 0.15), s)
                )
                if not success:
                    raise Exception("Failed to fetch updates")

                # Step 3: Apply
                update.status = UpdateStatus.INSTALLING.value
                progress(30, "Applying updates...")

                success, error = await self.backend.apply_updates(
                    update.to_commit,
                    lambda p, s: progress(30 + int(p * 0.20), s),
                )
                if not success:
                    raise Exception(f"Failed to apply updates: {error}")

                # Step 4: Dependencies
                progress(50, "Installing dependencies...")

                success, error = await self.backend.install_dependencies(
                    lambda p, s: progress(50 + int(p * 0.20), s),
                )
                if not success:
                    raise Exception(f"Failed to install dependencies: {error}")

                # Step 5: Migrations
                update.status = UpdateStatus.MIGRATING.value
                progress(70, "Running migrations...")

                success, error = await self.backend.run_migrations(
                    lambda p, s: progress(70 + int(p * 0.10), s),
                )
                if not success:
                    raise Exception(f"Migration failed: {error}")

                # Step 6: Health check before restart
                update.status = UpdateStatus.HEALTH_CHECK.value
                progress(80, "Pre-restart health check...")

                healthy, issues = await self.backend.health_check()
                if not healthy and config and config.require_healthy_services:
                    raise Exception(f"Health check failed: {', '.join(issues)}")

                # Step 7: Restart
                update.status = UpdateStatus.RESTARTING.value
                progress(85, "Restarting services...")

                success, error = await self.backend.restart_services(
                    lambda p, s: progress(85 + int(p * 0.10), s),
                )
                if not success:
                    logger.warning(f"Service restart may have failed: {error}")

                # Step 8: Final health check
                progress(95, "Post-restart health check...")
                await asyncio.sleep(5)  # Give service time to start

                healthy, issues = await self.backend.health_check()
                if not healthy:
                    logger.warning(f"Post-restart health issues: {issues}")

                # Complete
                update.complete()
                db.commit()
                progress(100, "Update completed successfully")

            except Exception as e:
                logger.exception(f"Update failed: {e}")
                update.fail(str(e))
                update.rollback_commit = update.from_commit
                db.commit()

                # Attempt automatic rollback
                if update.from_commit:
                    try:
                        await self.backend.rollback(update.from_commit)
                        update.mark_rolled_back(update.from_commit)
                        db.commit()
                    except Exception as rollback_error:
                        logger.error(f"Rollback also failed: {rollback_error}")

        finally:
            db.close()
            self._current_update = None

    def get_update_progress(self, update_id: int) -> Optional[UpdateProgressResponse]:
        """Get progress of an update."""
        update = self.db.query(UpdateHistory).filter(UpdateHistory.id == update_id).first()
        if not update:
            return None

        return UpdateProgressResponse(
            update_id=update.id,
            status=update.status,
            progress_percent=update.progress_percent,
            current_step=update.current_step,
            started_at=update.started_at,
            from_version=update.from_version,
            to_version=update.to_version,
            error_message=update.error_message,
            can_rollback=update.from_commit is not None and update.status in [
                UpdateStatus.FAILED.value,
                UpdateStatus.COMPLETED.value,
            ],
        )

    async def rollback(self, request: RollbackRequest, user_id: int) -> RollbackResponse:
        """Rollback to a previous version."""
        target_commit = request.target_commit

        if not target_commit and request.target_update_id:
            # Get commit from update history
            update = (
                self.db.query(UpdateHistory)
                .filter(UpdateHistory.id == request.target_update_id)
                .first()
            )
            if update:
                target_commit = update.from_commit

        if not target_commit:
            # Get last successful update's from_commit
            last_update = (
                self.db.query(UpdateHistory)
                .filter(UpdateHistory.status == UpdateStatus.COMPLETED.value)
                .order_by(desc(UpdateHistory.completed_at))
                .first()
            )
            if last_update:
                target_commit = last_update.from_commit

        if not target_commit:
            return RollbackResponse(
                success=False,
                message="No rollback target found",
            )

        # Perform rollback
        success, error = await self.backend.rollback(target_commit)

        if not success:
            return RollbackResponse(
                success=False,
                message=f"Rollback failed: {error}",
            )

        # Restore backup if requested
        if request.restore_backup:
            # Find the backup associated with the update
            update = (
                self.db.query(UpdateHistory)
                .filter(UpdateHistory.to_commit == target_commit)
                .first()
            )
            if update and update.backup_id:
                try:
                    from app.services.backup import BackupService
                    backup_service = BackupService(self.db)
                    # Note: Would need to implement restore functionality
                    logger.info(f"Would restore backup {update.backup_id}")
                except Exception as e:
                    logger.warning(f"Backup restore failed: {e}")

        return RollbackResponse(
            success=True,
            message="Rollback completed",
            rolled_back_to=target_commit[:8],
        )

    def get_history(
        self, page: int = 1, page_size: int = 20
    ) -> UpdateHistoryResponse:
        """Get paginated update history."""
        query = self.db.query(UpdateHistory)
        total = query.count()

        updates = (
            query.order_by(desc(UpdateHistory.started_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return UpdateHistoryResponse(
            updates=[
                UpdateHistoryEntry(
                    id=u.id,
                    from_version=u.from_version,
                    to_version=u.to_version,
                    channel=u.channel,
                    from_commit=u.from_commit,
                    to_commit=u.to_commit,
                    started_at=u.started_at,
                    completed_at=u.completed_at,
                    duration_seconds=u.duration_seconds,
                    status=u.status,
                    error_message=u.error_message,
                    rollback_commit=u.rollback_commit,
                    user_id=u.user_id,
                    can_rollback=u.from_commit is not None,
                )
                for u in updates
            ],
            total=total,
            page=page,
            page_size=page_size,
        )


def get_update_service(db: Session) -> UpdateService:
    """Factory function to get update service instance."""
    return UpdateService(db)


def _get_service_status() -> dict:
    """Get status for service registry."""
    try:
        db = SessionLocal()
        service = UpdateService(db)
        config = service.get_config()

        # Check for running update
        running = (
            db.query(UpdateHistory)
            .filter(UpdateHistory.status.in_([
                UpdateStatus.DOWNLOADING.value,
                UpdateStatus.INSTALLING.value,
                UpdateStatus.MIGRATING.value,
                UpdateStatus.RESTARTING.value,
            ]))
            .first()
        )

        db.close()

        return {
            "state": "running" if running else "idle",
            "auto_check_enabled": config.auto_check_enabled,
            "channel": config.channel,
            "last_check": config.last_check_at.isoformat() if config.last_check_at else None,
            "current_update_id": running.id if running else None,
        }
    except Exception as e:
        return {"state": "error", "error": str(e)}


def register_update_service() -> None:
    """Register update service with service status collector."""
    register_service(
        name="update_service",
        display_name="Update Service",
        get_status_fn=_get_service_status,
    )
