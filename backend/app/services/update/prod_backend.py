"""Production backend using Git and systemctl."""
import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.schemas.update import (
    VersionInfo,
    ChangelogEntry,
    ReleaseNotesResponse,
    ReleaseNoteItem,
    CommitInfo,
    VersionGroup,
    CommitHistoryResponse,
    CommitDiffResponse,
    DiffFile,
    ReleaseInfo,
    ReleaseListResponse,
)
from app.services.update.backend import UpdateBackend
from app.services.update.github_releases import (
    GitHubReleasesClient,
    GitHubRelease,
    GitHubUnavailable,
    latest_for_channel,
    notes_since_last_stable,
    releases_between,
)
from app.services.update.changelog_fallback import notes_since_last_stable_from_changelog
from app.services.update.utils import (
    ProgressCallback,
    version_sort_key,
    version_to_string,
    get_installed_version,
    _CONVENTIONAL_RE,
)

logger = logging.getLogger(__name__)

# Update targets are always resolved commit SHAs (7-40 hex). Reject anything
# else before it reaches `git checkout` (blocks option-injection like --force).
_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


class ProdUpdateBackend(UpdateBackend):
    """Production backend using Git and systemctl."""

    def __init__(self, repo_path: Optional[Path] = None):
        # Default to the project root
        self.repo_path = repo_path or Path(__file__).parent.parent.parent.parent.parent
        self.backend_path = self.repo_path / "backend"
        self.client_path = self.repo_path / "client"
        self._gh = GitHubReleasesClient()

    def _changelog_path(self) -> str:
        p = Path(settings.update_changelog_path)
        return str(p if p.is_absolute() else (self.repo_path / p))

    @staticmethod
    def _to_item(r: GitHubRelease) -> ReleaseNoteItem:
        from datetime import datetime
        date = None
        if r.published_at:
            try:
                date = datetime.fromisoformat(r.published_at.replace("Z", "+00:00"))
            except ValueError:
                date = None
        return ReleaseNoteItem(version=r.tag.lstrip("v"), date=date,
                               is_prerelease=r.prerelease, url=r.url, body_markdown=r.body_markdown)

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
        """Get current version from git tag (preferred) or pyproject.toml (fallback)."""
        # Try exact tag match first — succeeds for pre-release and stable tags
        exact_ok, exact_tag, _ = self._run_git("describe", "--tags", "--exact-match")
        if exact_ok and exact_tag.strip():
            tag_name = exact_tag.strip()
            version = tag_name.lstrip("v")
            is_prerelease = any(
                marker in tag_name for marker in ("-pre.", "-rc.", "-alpha", "-beta", "-unstable")
            )
            is_dev_build = False
            tag = tag_name
        else:
            # Local build between tags — fall back to pyproject.toml
            version = version_to_string(get_installed_version())
            tag = None
            is_prerelease = False
            is_dev_build = True

        # Commit metadata
        success, commit, _ = self._run_git("rev-parse", "HEAD")
        if not success:
            commit = "unknown"

        success, date_str, _ = self._run_git("log", "-1", "--format=%cI")
        date = datetime.fromisoformat(date_str) if success and date_str else None

        return VersionInfo(
            version=version,
            commit=commit,
            commit_short=commit[:7] if commit != "unknown" else "unknown",
            tag=tag,
            date=date,
            is_dev_build=is_dev_build,
            is_prerelease=is_prerelease,
        )

    async def check_for_updates(self, channel: str) -> tuple[bool, Optional[VersionInfo], list[ChangelogEntry]]:
        current = await self.get_current_version()
        try:
            releases = await self._gh.list_releases()
        except GitHubUnavailable:
            return False, None, []

        latest = latest_for_channel(releases, channel)
        if latest is None:
            return False, None, []

        latest_v = version_sort_key(latest.tag)
        current_v = version_sort_key(current.version)
        if latest_v <= current_v:
            return False, None, []

        latest_info = VersionInfo(
            version=latest.tag.lstrip("v"), commit="", commit_short="",
            tag=latest.tag, date=None, is_prerelease=latest.prerelease,
        )
        delta = releases_between(releases, newer_than=current.version, up_to=latest.tag.lstrip("v"))
        changelog = [
            ChangelogEntry(version=r.tag.lstrip("v"), date=None, changes=[], breaking_changes=[],
                           is_prerelease=r.prerelease, body_markdown=r.body_markdown)
            for r in delta
        ]
        return True, latest_info, changelog

    async def get_release_notes(self) -> ReleaseNotesResponse:
        current = await self.get_current_version()
        try:
            releases = await self._gh.list_releases()
            slice_, since = notes_since_last_stable(releases, current.version)
            return ReleaseNotesResponse(
                current_version=current.version,
                since_version=since.lstrip("v") if since else None,
                source="github",
                releases=[self._to_item(r) for r in slice_],
            )
        except GitHubUnavailable:
            items, since = notes_since_last_stable_from_changelog(self._changelog_path(), current.version)
            return ReleaseNotesResponse(
                current_version=current.version,
                since_version=since.lstrip("v") if since else None,
                source="changelog",
                releases=items,
            )

    async def fetch_updates(self, callback: Optional[ProgressCallback] = None) -> bool:
        if callback:
            callback(10, "Fetching from remote...")

        success, _, err = self._run_git("fetch", "--all", "--tags", "--prune")

        if callback:
            callback(100, "Fetch complete" if success else f"Fetch failed: {err}")

        return success

    @staticmethod
    def _is_valid_commit(commit: str) -> bool:
        return bool(commit) and bool(_COMMIT_RE.match(commit))

    async def apply_updates(
        self, target_commit: str, callback: Optional[ProgressCallback] = None
    ) -> tuple[bool, Optional[str]]:
        if not self._is_valid_commit(target_commit):
            return False, f"Invalid commit identifier: {target_commit!r}"

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

    async def rollback(self, commit: str) -> tuple[bool, Optional[str]]:
        """Rollback to a specific commit."""
        logger.info(f"Rolling back to {commit}")

        success, _, err = self._run_git("checkout", commit)
        if not success:
            return False, f"Rollback failed: {err}"

        return True, None

    # --- Update Script Launch (replaces in-process install/migrate/restart) ---

    _STATUS_DIR = Path("/var/lib/baluhost/update-status")

    def launch_update_script(
        self,
        update_id: int,
        from_commit: str,
        to_commit: str,
        from_version: str,
        to_version: str,
    ) -> tuple[bool, Optional[str]]:
        """Launch the detached update runner as a transient systemd unit.

        The script runs as root via systemd-run and survives backend restarts.
        It writes progress to /var/lib/baluhost/update-status/<update_id>.json.
        """
        if not self._is_valid_commit(to_commit) or not self._is_valid_commit(from_commit):
            return False, "Invalid commit identifier for update"

        script_path = self.repo_path / "deploy" / "update" / "run-update.sh"
        if not script_path.exists():
            return False, f"Update script not found: {script_path}"

        # Reset any previous failed unit with the same name
        subprocess.run(
            ["sudo", "systemctl", "reset-failed", "baluhost-update.service"],
            capture_output=True, text=True, timeout=10,
        )

        try:
            result = subprocess.run(
                [
                    "sudo", "systemd-run",
                    "--unit=baluhost-update",
                    "--remain-after-exit",
                    str(script_path),
                    "--update-id", str(update_id),
                    "--from-commit", from_commit,
                    "--to-commit", to_commit,
                    "--from-version", from_version,
                    "--to-version", to_version,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return False, f"Failed to launch update: {result.stderr}"

            logger.info(
                f"Update script launched as baluhost-update.service "
                f"(update_id={update_id})"
            )
            return True, None

        except subprocess.TimeoutExpired:
            return False, "Timed out launching update script"
        except Exception as e:
            return False, str(e)

    def stop_update_service(self) -> tuple[bool, Optional[str]]:
        """Stop the running update systemd unit."""
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "stop", "baluhost-update.service"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return False, result.stderr.strip()
            return True, None
        except subprocess.TimeoutExpired:
            return False, "Timed out stopping update service"
        except Exception as e:
            return False, str(e)

    def read_update_status(self, update_id: int) -> Optional[dict]:
        """Read the JSON status file written by the update runner script.

        Returns the parsed dict or None if the file doesn't exist yet.
        """
        status_file = self._STATUS_DIR / f"{update_id}.json"
        try:
            if not status_file.exists():
                return None
            text = status_file.read_text(encoding="utf-8")
            return json.loads(text)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read update status file {status_file}: {e}")
            return None

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

    async def get_all_releases(self) -> ReleaseListResponse:
        try:
            releases = await self._gh.list_releases()
        except GitHubUnavailable:
            return ReleaseListResponse(releases=[], total=0)
        infos = [
            ReleaseInfo(
                tag=r.tag, version=r.tag.lstrip("v"), date=r.published_at,
                is_prerelease=r.prerelease, commit_short=None,
                name=r.name, html_url=r.url, body_markdown=r.body_markdown,
            )
            for r in releases
        ]
        return ReleaseListResponse(releases=infos, total=len(infos))
