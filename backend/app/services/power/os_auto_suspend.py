"""
OS Auto-Suspend — bidirectional read/write of idle-suspend across power managers.

Detects the active session-level power manager (KDE PowerDevil / GNOME
gsd-power) or falls back to systemd-logind and dispatches read/write
through a common adapter protocol. Read-through architecture: no DB copy.

Helper script (root-required for logind) lives at
/usr/local/lib/baluhost/baluhost-write-logind-idle and is invoked via
sudo with a NOPASSWD entry installed by deploy/install/modules/13-power-helpers.sh.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

ActionLiteral = Literal["suspend", "hibernate", "ignore"]


@dataclass(frozen=True)
class AutoSuspendValue:
    """Normalised auto-suspend setting, identical shape across all backends."""
    enabled: bool
    timeout_minutes: int
    action: ActionLiteral


class OsAutoSuspendBackend(Protocol):
    """
    Structural interface for auto-suspend read/write adapters.

    Implementations live in this same module: KdeAdapter, GnomeAdapter,
    LogindAdapter. The active adapter is selected at request time by the
    detector based on which power manager is currently running.
    """
    name: Literal["kde", "gnome", "logind"]
    label: str

    def is_available(self) -> bool: ...
    def read(self) -> AutoSuspendValue: ...
    def write(self, value: AutoSuspendValue) -> None: ...
