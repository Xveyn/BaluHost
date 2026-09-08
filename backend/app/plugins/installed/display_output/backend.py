"""Display-Backends: ein Protokoll, eine Attrappe, eine echte Umsetzung.

Der Aufbau spiegelt ``services/power/desktop_backend.py`` und
``audio_control/backend.py``: ein Protocol, ein Dev-Backend fuer Windows und
Entwicklungsbetrieb, ein Linux-Backend, das mit der realen Session spricht.
"""
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Protocol, Tuple

from app.plugins.installed.display_output.kscreen import (
    build_apply_args,
    parse_outputs,
    run_kscreen,
    run_kscreen_json,
)
from app.plugins.installed.display_output.models import (
    DisplayLayout,
    DisplayMode,
    DisplayOutput,
)
from app.services.power.gpu.display_detector import get_connector_states


class DisplayBackend(Protocol):
    async def get_layout(self) -> DisplayLayout: ...
    async def apply(
        self, wanted: Dict[str, Tuple[bool, Optional[str]]], live_outputs: List[DisplayOutput]
    ) -> Tuple[bool, str]: ...


def _dev_modes(entries: List[tuple]) -> List[DisplayMode]:
    return [
        DisplayMode(id=i, name=n, width=w, height=h, refresh_rate=r)
        for i, n, w, h, r in entries
    ]


class DevDisplayBackend:
    """Zustand im Speicher, damit das Feature auf Windows entwickelbar ist.

    Bildet BaluNode nach: **zwei** verbundene Ausgaenge. Ein
    ``disconnected``-Ausgang gehoert bewusst nicht dazu — kscreen-doctor listet
    unverbundene Connectoren gar nicht erst, ein solcher Eintrag waere also ein
    Zustand, den das echte Backend nie liefert.

    Die namensgleichen Modus-Paare sind Absicht: an ihnen haengt die gesamte
    Begruendung fuer die ID-Adressierung, und ohne sie liesse sich die
    Beschriftung unter Windows nicht pruefen.
    """

    def __init__(self) -> None:
        self._outputs: List[DisplayOutput] = [
            DisplayOutput(
                name="HDMI-A-1", connected=True, selected=False,
                current_mode_id="1", preferred_mode_id="1", scale=1.0, priority=0,
                modes=_dev_modes([
                    ("1", "2560x1440@144", 2560, 1440, 143.99899291992188),
                    ("8", "1920x1200@144", 1920, 1200, 143.99899291992188),
                    ("9", "1920x1080@60", 1920, 1080, 60.0),
                    ("11", "1920x1080@60", 1920, 1080, 59.939998626708984),
                    ("50", "1920x1080@144", 1920, 1080, 143.8820037841797),
                ]),
            ),
            DisplayOutput(
                name="DP-3", connected=True, selected=True,
                current_mode_id="57", preferred_mode_id="56", scale=2.5, priority=1,
                modes=_dev_modes([
                    ("57", "3840x2160@120", 3840, 2160, 120.0),
                    ("58", "3840x2160@120", 3840, 2160, 119.87999725341797),
                    ("56", "3840x2160@60", 3840, 2160, 60.0),
                    ("67", "2560x1440@120", 2560, 1440, 119.99800109863281),
                    ("69", "1920x1080@120", 1920, 1080, 120.0),
                ]),
            ),
        ]

    async def get_layout(self) -> DisplayLayout:
        # lit folgt hier direkt selected: das Dev-Backend simuliert keine
        # eigene DPMS-Ebene, sondern gibt vor, dass beide Ebenen deckungsgleich sind.
        outputs = [o.model_copy(update={"lit": o.selected}) for o in self._outputs]
        return DisplayLayout(
            outputs=outputs,
            displays_powered=any(o.lit is True for o in outputs),
            available=True,
            detail="Dev-Backend (im Speicher)",
        )

    async def apply(
        self, wanted: Dict[str, Tuple[bool, Optional[str]]], live_outputs: List[DisplayOutput]
    ) -> Tuple[bool, str]:
        for output in self._outputs:
            if output.name not in wanted:
                continue
            selected, mode_id = wanted[output.name]
            output.selected = selected
            if selected and mode_id:
                output.current_mode_id = mode_id
        return True, "Angewendet (Dev)"


class KWinDisplayBackend:
    """Spricht ueber kscreen-doctor mit der KWin-Instanz der Desktop-Session.

    Das Backend laeuft unter derselben UID wie die Session, deshalb genuegt die
    Umgebung aus ``wayland_session_env()``; es wird kein Sudo benoetigt.
    """

    async def get_layout(self) -> DisplayLayout:
        payload = await asyncio.to_thread(run_kscreen_json)
        if payload is None:
            return DisplayLayout(available=False, detail="KWin nicht erreichbar")

        outputs = parse_outputs(payload)
        states = await get_connector_states()
        merged = [
            # .get() statt [] : ein Name ohne Connector ist "unbekannt",
            # nicht "aus". Eine unbekannte Antwort als aus auszugeben waere
            # eine Falschaussage.
            o.model_copy(update={"lit": states.get(o.name)})
            for o in outputs
        ]
        return DisplayLayout(
            outputs=merged,
            displays_powered=any(o.lit is True for o in merged),
            available=True,
        )

    async def apply(
        self, wanted: Dict[str, Tuple[bool, Optional[str]]], live_outputs: List[DisplayOutput]
    ) -> Tuple[bool, str]:
        args = build_apply_args(wanted, live_outputs)
        # Genau ein Aufruf: kscreen-doctor wendet alle Argumente gemeinsam an.
        return await asyncio.to_thread(run_kscreen, args[1:])
