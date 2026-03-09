"""Abstract base class for update backends."""
from abc import ABC, abstractmethod
from typing import Optional

from app.schemas.update import (
    VersionInfo,
    ChangelogEntry,
    CommitInfo,
    ReleaseNotesResponse,
    CommitHistoryResponse,
    CommitDiffResponse,
    ReleaseListResponse,
)
from app.services.update.utils import ProgressCallback


class UpdateBackend(ABC):
    """Abstract backend for update operations."""

    @abstractmethod
    async def get_current_version(self) -> VersionInfo:
        """Get the current installed version."""
        pass

    @abstractmethod
    async def check_for_updates(self, channel: str) -> tuple[bool, Optional[VersionInfo], list[ChangelogEntry]]:
        """Check if updates are available."""
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

    async def install_dependencies(self, callback: Optional[ProgressCallback] = None) -> tuple[bool, Optional[str]]:
        """Install Python/Node dependencies. Returns (success, error_message).

        Only used by DevUpdateBackend (in-process simulation).
        ProdUpdateBackend delegates to shell modules.
        """
        return True, None

    async def run_migrations(self, callback: Optional[ProgressCallback] = None) -> tuple[bool, Optional[str]]:
        """Run database migrations. Returns (success, error_message).

        Only used by DevUpdateBackend (in-process simulation).
        ProdUpdateBackend delegates to shell modules.
        """
        return True, None

    async def restart_services(self, callback: Optional[ProgressCallback] = None) -> tuple[bool, Optional[str]]:
        """Restart services. Returns (success, error_message).

        Only used by DevUpdateBackend (in-process simulation).
        ProdUpdateBackend delegates to shell modules.
        """
        return True, None

    async def health_check(self) -> tuple[bool, list[str]]:
        """Check if services are healthy. Returns (healthy, issues).

        Only used by DevUpdateBackend.
        ProdUpdateBackend uses shell module 12 for health checks.
        """
        return True, []

    @abstractmethod
    async def rollback(self, commit: str) -> tuple[bool, Optional[str]]:
        """Rollback to a specific commit. Returns (success, error_message)."""
        pass

    @abstractmethod
    async def get_release_notes(self) -> ReleaseNotesResponse:
        """Get release notes for the current version (commits since previous tag)."""
        pass

    @abstractmethod
    async def get_commit_history(self) -> CommitHistoryResponse:
        """Get full commit history grouped by version tags."""
        pass

    @abstractmethod
    async def get_commit_diff(self, commit_hash: str) -> CommitDiffResponse:
        """Get diff details for a specific commit."""
        pass

    @abstractmethod
    async def get_all_releases(self) -> ReleaseListResponse:
        """Get list of all releases (git tags)."""
        pass

    async def check_dev_branch(self) -> tuple[bool, Optional[VersionInfo], Optional[int], list[CommitInfo]]:
        """Check if the development branch has unreleased commits ahead of latest tag.

        Returns:
            Tuple of (dev_available, dev_version_info, commits_ahead, commits).
            Default implementation returns no dev version.
        """
        return False, None, None, []
