"""Setup wizard service.

Detects whether first-time setup is needed and tracks which setup steps
have been completed. Uses an in-memory flag so that once the wizard is
completed (or skipped), subsequent requests are fast.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.models.webdav_state import WebdavState
from app.services.hardware.raid import api as raid_api
from app.services import samba_service

logger = logging.getLogger(__name__)

# In-memory flag — survives for the lifetime of the process.
# Reset on restart (which is fine: the DB check is the source of truth).
_setup_complete: bool = False


def _reset_setup_complete() -> None:
    """Reset the in-memory flag. Used by tests only."""
    global _setup_complete
    _setup_complete = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_setup_required(db: Session) -> bool:
    """Return True if the setup wizard should be shown.

    Setup is NOT required when any of the following is true:
    - ``settings.skip_setup`` is True
    - The in-memory ``_setup_complete`` flag is True
    - At least one user exists in the ``users`` table
    """
    if settings.skip_setup:
        return False

    if _setup_complete:
        return False

    user_exists = db.query(User.id).first() is not None
    if user_exists:
        return False

    return True


def get_completed_steps(db: Session) -> List[str]:
    """Check live state and return which required setup steps are done.

    Possible step names:
    - ``"admin"``       — a user with ``role='admin'`` exists
    - ``"users"``       — a user with ``role != 'admin'`` exists
    - ``"raid"``        — at least one RAID array exists
    - ``"file_access"`` — Samba or WebDAV is running
    """
    steps: List[str] = []

    # --- admin step --------------------------------------------------------
    admin_exists = (
        db.query(User.id).filter(User.role == "admin").first() is not None
    )
    if admin_exists:
        steps.append("admin")

    # --- users step --------------------------------------------------------
    regular_user_exists = (
        db.query(User.id).filter(User.role != "admin").first() is not None
    )
    if regular_user_exists:
        steps.append("users")

    # --- raid step ---------------------------------------------------------
    try:
        status = raid_api.get_status()
        if status.arrays:
            steps.append("raid")
    except Exception:
        logger.debug("RAID status check failed during setup step detection", exc_info=True)

    # --- file_access step --------------------------------------------------
    try:
        file_access_running = False

        # Check WebDAV via DB state
        try:
            webdav_state = db.query(WebdavState).filter(WebdavState.is_running == True).first()  # noqa: E712
            if webdav_state is not None:
                file_access_running = True
        except Exception:
            logger.debug("WebDAV state check failed during setup step detection", exc_info=True)

        # Check Samba (async function — run via event loop if available)
        if not file_access_running:
            try:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    # We are inside an async context — cannot use asyncio.run.
                    # Create a future and schedule it.  For the sync caller the
                    # best we can do is a synchronous fallback.
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        samba_status = pool.submit(
                            asyncio.run, samba_service.get_samba_status()
                        ).result(timeout=5)
                else:
                    samba_status = asyncio.run(samba_service.get_samba_status())

                if samba_status.get("is_running"):
                    file_access_running = True
            except Exception:
                logger.debug("Samba status check failed during setup step detection", exc_info=True)

        if file_access_running:
            steps.append("file_access")
    except Exception:
        logger.debug("file_access step detection failed", exc_info=True)

    return steps


def complete_setup(db: Session) -> None:
    """Mark the setup wizard as complete (in-memory flag)."""
    global _setup_complete
    _setup_complete = True
    logger.info("Setup wizard marked as complete")


def is_setup_complete(db: Session) -> bool:
    """Return the current value of the in-memory ``_setup_complete`` flag."""
    return _setup_complete
