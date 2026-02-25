"""Development backend that simulates updates without real changes."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from app.schemas.update import (
    VersionInfo,
    ChangelogEntry,
    ReleaseNotesResponse,
    ReleaseNoteCategory,
    CommitInfo,
    VersionGroup,
    CommitHistoryResponse,
    CommitDiffResponse,
    DiffFile,
    ReleaseInfo,
    ReleaseListResponse,
)
from app.services.update.backend import UpdateBackend
from app.services.update.utils import (
    ProgressCallback,
    parse_version,
    version_to_string,
)

logger = logging.getLogger(__name__)


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
        include_beta = channel == "unstable"

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

    async def get_all_releases(self) -> ReleaseListResponse:
        """Return mock releases for dev mode."""
        releases = [
            ReleaseInfo(tag="v1.9.0", version="1.9.0", date="2026-02-22T12:00:00Z", is_prerelease=False, commit_short="abc1234"),
            ReleaseInfo(tag="v1.8.2", version="1.8.2", date="2026-02-20T10:30:00Z", is_prerelease=False, commit_short="def5678"),
            ReleaseInfo(tag="v1.8.1", version="1.8.1", date="2026-02-20T09:00:00Z", is_prerelease=False, commit_short="ghi9012"),
            ReleaseInfo(tag="v1.8.0", version="1.8.0", date="2026-02-19T14:00:00Z", is_prerelease=False, commit_short="jkl3456"),
            ReleaseInfo(tag="v1.8.0-beta", version="1.8.0-beta", date="2026-02-18T16:00:00Z", is_prerelease=True, commit_short="mno7890"),
            ReleaseInfo(tag="v1.7.0", version="1.7.0", date="2026-02-15T11:00:00Z", is_prerelease=False, commit_short="pqr1234"),
            ReleaseInfo(tag="v1.6.0", version="1.6.0", date="2026-02-10T09:00:00Z", is_prerelease=False, commit_short="stu5678"),
            ReleaseInfo(tag="v1.5.0-alpha", version="1.5.0-alpha", date="2026-02-05T14:00:00Z", is_prerelease=True, commit_short="vwx9012"),
            ReleaseInfo(tag="v1.5.0", version="1.5.0", date="2026-02-01T10:00:00Z", is_prerelease=False, commit_short="yza3456"),
            ReleaseInfo(tag="v1.0.0-alpha", version="1.0.0-alpha", date="2026-01-15T08:00:00Z", is_prerelease=True, commit_short="bcd7890"),
        ]
        return ReleaseListResponse(releases=releases, total=len(releases))
