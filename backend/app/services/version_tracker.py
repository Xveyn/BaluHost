"""Record the current version in the database on every startup."""
import logging
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app import __version__
from app.models.version_history import VersionHistory

logger = logging.getLogger(__name__)

# Project root — same convention as ProdUpdateBackend.__init__
_REPO_PATH = Path(__file__).parent.parent.parent.parent


def _run_git(*args: str) -> tuple[bool, str]:
    """Run a git command and return (success, stdout)."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=_REPO_PATH,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0, result.stdout.strip()
    except Exception:
        return False, ""


def record_version_on_startup(db: Session) -> None:
    """Record the current version+commit in the database.

    If the same (version, git_commit) row already exists, update last_seen
    and increment times_started.  Otherwise insert a new row.

    This function must never prevent the application from starting.
    """
    try:
        version = __version__

        # Git commit
        ok, commit = _run_git("rev-parse", "HEAD")
        if not ok:
            commit = "unknown"
        commit_short = commit[:7] if commit != "unknown" else "unknown"

        # Git branch
        ok, branch = _run_git("rev-parse", "--abbrev-ref", "HEAD")
        if not ok:
            branch = None

        # Python version
        py_version = platform.python_version()

        # Upsert: try to find existing row
        existing = (
            db.query(VersionHistory)
            .filter(
                VersionHistory.version == version,
                VersionHistory.git_commit == commit,
            )
            .first()
        )

        if existing:
            existing.last_seen = datetime.now(timezone.utc)
            existing.times_started = existing.times_started + 1
            # Update branch/python in case they changed (e.g. Python upgrade)
            if branch:
                existing.git_branch = branch
            existing.python_version = py_version
            db.commit()
            logger.info(
                "Version %s (%s) seen again — start #%d",
                version,
                commit_short,
                existing.times_started,
            )
        else:
            entry = VersionHistory(
                version=version,
                git_commit=commit,
                git_commit_short=commit_short,
                git_branch=branch,
                python_version=py_version,
            )
            db.add(entry)
            db.commit()
            logger.info(
                "Version %s (%s) recorded for the first time",
                version,
                commit_short,
            )

    except Exception:
        logger.exception("Failed to record version on startup (non-fatal)")
        try:
            db.rollback()
        except Exception:
            pass
