"""Record the current version in the database when the service starts."""
import logging
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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


def _count_start(
    db: Session,
    version: str,
    commit: str,
    branch: Optional[str],
    py_version: str,
) -> bool:
    """Count one more start on the existing row. False if there is no row.

    One UPDATE that raises the counter in the database (`times_started + 1`),
    not a value read earlier and written back: two processes starting at once
    would otherwise both read N and both store N + 1.
    """
    values: dict[str, object] = {
        "last_seen": datetime.now(timezone.utc),
        "times_started": VersionHistory.times_started + 1,
        # Refreshed in case it changed under the same commit (Python upgrade).
        "python_version": py_version,
    }
    if branch:
        values["git_branch"] = branch
    result: Any = db.execute(
        update(VersionHistory)
        .where(
            VersionHistory.version == version,
            VersionHistory.git_commit == commit,
        )
        .values(values)
        .execution_options(synchronize_session=False)
    )
    return bool(result.rowcount)


def record_version_on_startup(db: Session) -> None:
    """Record the current version+commit in the database.

    If the same (version, git_commit) row already exists, update last_seen
    and increment times_started.  Otherwise insert a new row.

    Safe to run in several processes at once (#715): the count is a single
    UPDATE, and losing the race for the first INSERT of a new commit — the
    other process' row trips `uq_version_commit` — turns into a count on that
    row instead of an error. The lifespan calls this in the primary worker
    only, so that `times_started` counts service starts rather than workers;
    correctness here does not depend on that.

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
        branch: Optional[str]
        ok, branch = _run_git("rev-parse", "--abbrev-ref", "HEAD")
        if not ok:
            branch = None

        # Python version
        py_version = platform.python_version()

        if _count_start(db, version, commit, branch, py_version):
            db.commit()
            logger.info("Version %s (%s) seen again", version, commit_short)
            return

        try:
            db.add(
                VersionHistory(
                    version=version,
                    git_commit=commit,
                    git_commit_short=commit_short,
                    git_branch=branch,
                    python_version=py_version,
                )
            )
            db.commit()
        except IntegrityError:
            # Another process inserted the row between our UPDATE and our
            # INSERT. Its row is the one; ours becomes a count on it.
            db.rollback()
            _count_start(db, version, commit, branch, py_version)
            db.commit()
            logger.info(
                "Version %s (%s) recorded by another process first — counted this start",
                version,
                commit_short,
            )
            return

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
