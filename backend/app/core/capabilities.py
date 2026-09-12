"""Uniform handling for optional external tools.

RAID (mdadm), VPN (wireguard-tools) and cloud import (rclone) are optional in
the installer -- the ENABLE_* switches default to false and the package is only
installed when the feature is selected. A box that deselected a feature must
say so in plain words instead of failing with an opaque 500 or a raw
``FileNotFoundError`` (#543).
"""
from __future__ import annotations

import shutil

from app.core.exceptions import ServiceUnavailableError


class ToolUnavailableError(ServiceUnavailableError):
    """A required external tool is not installed on this host (-> HTTP 503)."""


def require_tool(binary: str, feature: str, package: str | None = None) -> str:
    """Return the absolute path of ``binary``, or raise ToolUnavailableError.

    The message names the feature *and* the package to install: whoever reads
    it sees a 503 in the UI or an error string on a failed job, never the
    traceback that would say which binary was missing.
    """
    path = shutil.which(binary)
    if path is None:
        hint = f" -- install {package}" if package else ""
        raise ToolUnavailableError(f"{feature} is not available on this system{hint}")
    return path
