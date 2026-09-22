"""Neustart der BaluHost-systemd-Units.

Die Reihenfolge ist Teil des Vertrags: ``baluhost-backend`` steht zuletzt, weil
sein Neustart den Prozess beendet, der diese Funktion ausführt. Alles, was
danach käme, liefe nie.

``baluhost-backend-local`` ist dabei, obwohl sie socket-aktiviert ist: sie ist
``Type=simple`` mit ``Restart=on-failure`` und läuft nach dem ersten
Verbindungsaufbau dauerhaft weiter. Ohne sie liefe der Companion-Kanal nach
einem "Neustart" mit altem Code.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

BALUHOST_UNITS: tuple[str, ...] = (
    "baluhost-scheduler",
    "baluhost-monitoring",
    "baluhost-webdav",
    "baluhost-backend-local",
    "baluhost-backend",
)
SUPPORT_UNITS: tuple[str, ...] = BALUHOST_UNITS[:-1]
BACKEND_UNIT: str = BALUHOST_UNITS[-1]

RESTART_TIMEOUT = 20.0
# Die Meldung geht in eine API-Antwort. Sie ist nur für Admins sichtbar und
# hinter dem Step-up, aber ein ungekürztes systemctl-Protokoll gehört trotzdem
# nicht in einen Response-Body.
MAX_MESSAGE = 200


@dataclass(frozen=True)
class UnitResult:
    name: str
    success: bool
    message: str | None = None


def restart_unit(
    unit: str,
    runner: Callable[..., Any] = subprocess.run,
    timeout: float = RESTART_TIMEOUT,
) -> UnitResult:
    """Eine Unit neu starten. Wirft nie — jeder Fehlschlag ist ein Ergebnis."""
    try:
        completed = runner(
            ["sudo", "systemctl", "restart", unit],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.warning("restart of %s timed out after %.0fs", unit, timeout)
        return UnitResult(unit, False, f"Zeitüberschreitung nach {timeout:.0f}s")
    except OSError as exc:
        logger.warning("restart of %s failed to start: %s", unit, exc)
        return UnitResult(unit, False, str(exc)[:MAX_MESSAGE])

    if completed.returncode == 0:
        return UnitResult(unit, True)

    output = (completed.stderr or completed.stdout or "").strip()
    message = output[:MAX_MESSAGE] if output else f"exit {completed.returncode}"
    logger.warning("restart of %s failed: %s", unit, message)
    return UnitResult(unit, False, message)


def restart_support_units(
    runner: Callable[..., Any] = subprocess.run,
) -> list[UnitResult]:
    """Alle Units außer dem Backend, in der Reihenfolge von BALUHOST_UNITS.

    Ein Fehlschlag bricht nicht ab: eine kaputte Unit darf die übrigen nicht
    verhindern, und der Aufrufer bekommt jedes Ergebnis einzeln.
    """
    return [restart_unit(unit, runner=runner) for unit in SUPPORT_UNITS]
