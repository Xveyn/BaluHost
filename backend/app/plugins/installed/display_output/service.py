"""Service-Schicht der Displaysteuerung.

Waehlt das Backend, haelt die Auswahl als Singleton und traegt die gesamte
Validierung. Der Aufbau spiegelt ``audio_control/service.py``.

**Die Validierung ist die eigentliche Schutzmassnahme.** Listen-Argumente
schliessen eine Shell-Injektion ohnehin aus; hier wird sichergestellt, dass
ueberhaupt nur Werte in den Argumentvektor gelangen, die zuvor in der
Live-Enumeration standen.
"""
from __future__ import annotations

import logging
import platform
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.plugins.installed.display_output.backend import (
    DevDisplayBackend,
    DisplayBackend,
    KWinDisplayBackend,
)
from app.plugins.installed.display_output.kscreen import build_apply_args
from app.plugins.installed.display_output.models import DisplayApplyRequest, DisplayLayout

logger = logging.getLogger(__name__)

_service: Optional["DisplayService"] = None


@dataclass(frozen=True)
class ApplyResult:
    """Ergebnis eines apply-Aufrufs, samt des tatsaechlich geprueften argv.

    Der Audit-Eintrag muss festhalten, was ``kscreen-doctor`` wirklich
    bekommen hat — nicht den rohen, ungeprueften Request. ``argv`` ist genau
    der Vektor aus ``kscreen.build_apply_args(wanted, layout.outputs)``, also
    bereits gegen die Live-Enumeration gepruefte Namen und IDs; ein
    Ausgang mit ``selected: false`` und mitgeschickter ``mode_id`` taucht
    darin nicht auf, weil der Service diese Kombination beim Aufbau von
    ``wanted`` ohnehin verwirft.
    """

    success: bool
    message: str
    argv: List[str]


class DisplayError(Exception):
    """Basis der Fehler, die die Route in Statuscodes uebersetzt."""


class DisplayUnavailable(DisplayError):
    """KWin ist nicht erreichbar — wird zu 502."""


class InvalidRequest(DisplayError):
    """Der Wunsch ist nicht erfuellbar — wird zu 400."""


class ModeMismatch(DisplayError):
    """Die ID meint inzwischen einen anderen Modus — wird zu 409."""


class DisplayService:
    """Duenne Huelle um das gewaehlte Backend, plus Validierung."""

    def __init__(self, backend: Optional[DisplayBackend] = None) -> None:
        if backend is not None:
            self._backend: DisplayBackend = backend
        elif getattr(settings, "is_dev_mode", False) or platform.system() != "Linux":
            # kscreen-doctor gibt es auf Windows nicht, und im Dev-Modus soll
            # nichts an einer echten Session herumstellen.
            self._backend = DevDisplayBackend()
        else:
            self._backend = KWinDisplayBackend()

    async def get_layout(self) -> DisplayLayout:
        """Liest Ausgaenge, Modi und den globalen DPMS-Zustand."""
        return await self._backend.get_layout()

    async def apply(self, request: DisplayApplyRequest) -> ApplyResult:
        """Prueft den Wunsch gegen die Live-Enumeration und wendet ihn an.

        Returns:
            ApplyResult mit dem Ergebnis des Backend-Aufrufs UND dem
            argv-Vektor, den ``kscreen.build_apply_args`` daraus gebaut hat —
            derselbe Vektor, den (bei ``KWinDisplayBackend``) auch
            tatsaechlich an ``kscreen-doctor`` ging. Der Aufbau ist eine reine
            Funktion von ``wanted`` und der Live-Enumeration, also unabhaengig
            vom gewaehlten Backend berechenbar; das Protocol selbst bleibt
            unveraendert.

        Raises:
            DisplayUnavailable: KWin antwortet nicht.
            InvalidRequest: unbekannter Ausgang, unbekannte oder fremde
                Mode-ID, doppelter Ausgang, unvollstaendige Modusangabe, oder
                ein Ergebnis ohne einen einzigen gewaehlten Ausgang.
            ModeMismatch: die ID existiert, meint aber einen anderen Modus als
                der mitgeschickte Name.
        """
        layout = await self._backend.get_layout()
        if not layout.available:
            raise DisplayUnavailable(layout.detail or "KWin nicht erreichbar")

        by_name = {o.name: o for o in layout.outputs}
        wanted: Dict[str, Tuple[bool, Optional[str]]] = {}

        for item in request.outputs:
            if item.name in wanted:
                raise InvalidRequest(f"Ausgang doppelt im Wunsch: {item.name}")
            output = by_name.get(item.name)
            if output is None:
                raise InvalidRequest(f"Unbekannter Ausgang: {item.name}")

            mode_id: Optional[str] = None
            if item.mode_id is not None or item.mode_name is not None:
                if item.mode_id is None or item.mode_name is None:
                    # Ohne beide Haelften waere die Gegenprobe abschaltbar.
                    raise InvalidRequest("mode_id und mode_name gehoeren zusammen")
                if item.selected:
                    mode = next((m for m in output.modes if m.id == item.mode_id), None)
                    if mode is None:
                        raise InvalidRequest(
                            f"Modus {item.mode_id} gehoert nicht zu {item.name}"
                        )
                    if mode.name != item.mode_name:
                        raise ModeMismatch(
                            f"Modus {item.mode_id} heisst inzwischen {mode.name}"
                        )
                    mode_id = mode.id
                # Bei selected=False bleibt mode_id None: KWin behaelt die
                # Modus-Wahl eines abgewaehlten Ausgangs ohnehin.

            wanted[item.name] = (item.selected, mode_id)

        self._assert_something_stays_selected(by_name, wanted)

        argv = build_apply_args(wanted, layout.outputs)
        logger.info("Display-Wunsch: %s", wanted)
        ok, message = await self._backend.apply(wanted, layout.outputs)
        return ApplyResult(success=ok, message=message, argv=argv)

    @staticmethod
    def _assert_something_stays_selected(by_name: dict, wanted: dict) -> None:
        """Verbietet ein apply, nach dem kein Ausgang mehr gewaehlt waere.

        "Nichts soll leuchten" ist ein legitimer Wunsch, aber der Weg dafuer
        ist der DPMS-Schalter: der ist reversibel und wirft die
        KWin-Konfiguration nicht weg. Alle Ausgaenge abzuwaehlen wuerde sie
        wegwerfen.

        Ausgaenge, die der Wunsch nicht nennt, behalten ihren Zustand und
        zaehlen deshalb mit.
        """
        for name, output in by_name.items():
            if not output.connected:
                continue
            selected = wanted[name][0] if name in wanted else output.selected
            if selected:
                return
        raise InvalidRequest("Mindestens ein verbundener Ausgang muss gewaehlt bleiben")


def get_display_service() -> DisplayService:
    """Liefert die Service-Instanz und legt sie beim ersten Aufruf an."""
    global _service
    if _service is None:
        _service = DisplayService()
    return _service
