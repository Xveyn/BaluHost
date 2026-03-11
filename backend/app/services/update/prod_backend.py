"""Production backend using Git and systemctl."""
import json
import logging
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.schemas.update import (
    VersionInfo,
    ChangelogEntry,
    ReleaseNotesResponse,
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
    _CONVENTIONAL_RE,
    _parse_conventional_commits,
)

logger = logging.getLogger(__name__)


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

        # Check if HEAD is exactly on a tag
        exact_success, _, _ = self._run_git("describe", "--tags", "--exact-match")
        is_dev_build = not exact_success

        return VersionInfo(
            version=version,
            commit=commit,
            commit_short=commit[:7] if commit != "unknown" else "unknown",
            tag=tag,
            date=date,
            is_dev_build=is_dev_build,
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
        include_prerelease = channel == "unstable"
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

    async def check_dev_branch(self) -> tuple[bool, Optional[VersionInfo], Optional[int], list[CommitInfo]]:
        """Check if origin/development has unreleased commits ahead of latest tag."""
        empty: list[CommitInfo] = []

        # Fetch all refs including tags
        success, _, err = self._run_git("fetch", "--all", "--tags", "--prune")
        if not success:
            logger.warning(f"Failed to fetch for dev branch check: {err}")
            return False, None, None, empty

        # Get latest tag by semver
        success, tags_output, _ = self._run_git("tag", "-l", "--sort=-version:refname")
        if not success or not tags_output.strip():
            return False, None, None, empty

        tags = [t.strip() for t in tags_output.split("\n") if t.strip()]
        if not tags:
            return False, None, None, empty
        latest_tag = tags[0]

        # Check if origin/development exists
        success, _, _ = self._run_git("rev-parse", "--verify", "origin/development")
        if not success:
            return False, None, None, empty

        # Count commits ahead
        success, count_str, _ = self._run_git(
            "rev-list", "--count", f"{latest_tag}..origin/development"
        )
        if not success or not count_str.strip():
            return False, None, None, empty

        commits_ahead = int(count_str.strip())
        if commits_ahead <= 0:
            return False, None, None, empty

        # Get tip commit info
        success, tip_output, _ = self._run_git(
            "log", "-1", "--format=%H|%h|%aI", "origin/development"
        )
        if not success or not tip_output.strip():
            return False, None, None, empty

        parts = tip_output.split("|", 2)
        if len(parts) < 3:
            return False, None, None, empty

        full_hash, short_hash, date_str = parts
        tip_date = datetime.fromisoformat(date_str) if date_str else None

        # Format version as X.Y.Z+dev.N
        base_version = latest_tag.lstrip("v")
        dev_version_str = f"{base_version}+dev.{commits_ahead}"

        dev_info = VersionInfo(
            version=dev_version_str,
            commit=full_hash,
            commit_short=short_hash,
            tag=None,
            date=tip_date,
        )

        # Fetch commit messages (max 50)
        commit_list: list[CommitInfo] = []
        success, log_output, _ = self._run_git(
            "log", "--format=%H|%h|%s|%aI|%an",
            f"{latest_tag}..origin/development", "--no-merges", "-50"
        )
        if success and log_output.strip():
            for line in log_output.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                log_parts = line.split("|", 4)
                if len(log_parts) < 5:
                    continue
                c_hash, c_short, c_msg, c_date, c_author = log_parts
                # Parse conventional commit type/scope
                c_type, c_scope = None, None
                if ":" in c_msg:
                    prefix = c_msg.split(":", 1)[0]
                    if "(" in prefix and prefix.endswith(")"):
                        c_type = prefix.split("(")[0]
                        c_scope = prefix.split("(")[1].rstrip(")")
                    elif prefix.isalpha() or prefix.replace("!", "").isalpha():
                        c_type = prefix.rstrip("!")
                commit_list.append(CommitInfo(
                    hash=c_hash, hash_short=c_short, message=c_msg,
                    date=c_date, author=c_author, type=c_type, scope=c_scope,
                ))

        return True, dev_info, commits_ahead, commit_list

    async def get_all_releases(self) -> ReleaseListResponse:
        """Get list of all releases from git tags."""
        # Get all tags sorted by semver (newest first)
        success, tags_output, _ = self._run_git("tag", "-l", "--sort=-version:refname")
        if not success or not tags_output.strip():
            return ReleaseListResponse(releases=[], total=0)

        tags = [t.strip() for t in tags_output.strip().split("\n") if t.strip()]

        releases: list[ReleaseInfo] = []
        for tag in tags:
            # Get commit for this tag
            ok, commit, _ = self._run_git("rev-parse", "--short=7", tag)
            commit_short = commit if ok else "unknown"

            # Get tag date
            ok, date_str, _ = self._run_git("log", "-1", "--format=%aI", tag)
            tag_date = date_str if ok and date_str else None

            # Parse version to check for prerelease
            version = tag.lstrip("v")
            is_prerelease = bool(parse_version(tag)[3])  # tuple[3] is prerelease suffix

            releases.append(ReleaseInfo(
                tag=tag,
                version=version,
                date=tag_date,
                is_prerelease=is_prerelease,
                commit_short=commit_short,
            ))

        return ReleaseListResponse(releases=releases, total=len(releases))
