"""Path jail for the Optical Drive plugin.

The plugin takes absolute filesystem paths (the UI has plain text fields), while
the file manager's ``_jail_path()`` works on storage-relative ones. This module
translates between the two so a normal user is held to the same directories as
in the file manager: own home, ``Shared/`` and (read only) shares made to them.
Admins are not restricted here; ``OpticalDriveService.validate_path`` still
applies to everybody as the second barrier.
"""
import logging
import os
from pathlib import PurePosixPath

from fastapi import HTTPException, status

from app.core.config import settings
from app.services.audit.logger_db import get_audit_logger_db
from app.services.permissions import is_privileged

logger = logging.getLogger(__name__)

_SHARED_DIR = "Shared"
_SHARED_WITH_ME_DIR = "Shared with me"


def _deny(user, db, path: str, action: str, detail: str, code: int) -> HTTPException:
    """Audit a refused path and build the response; the detail stays generic."""
    try:
        get_audit_logger_db().log_authorization_failure(
            user=user.username,
            action=action,
            resource=path,
            required_permission="path_access",
            db=db,
        )
    except Exception:  # an audit failure must not turn a 403 into a 500
        logger.warning("Could not audit refused optical_drive path", exc_info=True)
    return HTTPException(status_code=code, detail=detail)


def jail_user_path(
    path: str,
    user,
    db,
    *,
    write: bool,
    action: str = "optical_drive_path",
) -> str:
    """Return the absolute path *user* may use, or raise ``HTTPException``.

    Non-privileged users: *path* must be absolute and, after resolving ``..``
    and symlinks, lie inside the storage root and pass ``_jail_path()``. Targets
    that are written (*write*) are further limited to the own home and
    ``Shared/``; a FileShare grant is enough to read from, not to write into.
    """
    if is_privileged(user):
        return path

    if not os.path.isabs(path):
        raise _deny(user, db, path, action, "Path must be absolute", status.HTTP_400_BAD_REQUEST)

    # realpath, not abspath: a symlink inside the own home must not lead out of it.
    root = os.path.realpath(settings.nas_storage_path)
    real = os.path.realpath(path)
    if real != root and not real.startswith(root + os.sep):
        raise _deny(user, db, path, action, "Access denied", status.HTTP_403_FORBIDDEN)

    relative = PurePosixPath(os.path.relpath(real, root).replace(os.sep, "/"))
    normalized = "" if str(relative) == "." else str(relative)

    # Imported here: api.routes.files pulls in the whole route layer, which is
    # still being assembled while the plugin package is loaded.
    from app.api.routes.files import _jail_path

    try:
        jailed = _jail_path(normalized, user, db)
    except HTTPException as exc:
        raise _deny(user, db, path, action, "Access denied", exc.status_code) from exc

    if jailed == _SHARED_WITH_ME_DIR:
        raise _deny(user, db, path, action, "Access denied", status.HTTP_403_FORBIDDEN)

    if write:
        own = jailed == user.username or jailed.startswith(f"{user.username}/")
        shared = jailed == _SHARED_DIR or jailed.startswith(f"{_SHARED_DIR}/")
        if not (own or shared):
            raise _deny(user, db, path, action, "Access denied", status.HTTP_403_FORBIDDEN)

    return real
