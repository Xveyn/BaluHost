"""Pydantic-Schemas fuer die GPU-Luefterakustik (#516)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class GpuFanAcousticsValues(BaseModel):
    """Die vier Skalare. None heisst 'BaluHost verwaltet diesen Wert nicht'."""

    fan_target_temperature: Optional[int] = None
    acoustic_limit_rpm_threshold: Optional[int] = None
    acoustic_target_rpm_threshold: Optional[int] = None
    fan_minimum_pwm: Optional[int] = None


class GpuFanAcousticsConfig(BaseModel):
    """desired: was angewendet werden soll.

    baseline: was auf der Karte stand, bevor BaluHost sie erstmals angefasst
    hat. Zurueckgesetzt wird auf die Baseline, nicht auf den Treiber-Standard
    -- 'wie du es hattest' statt 'wie der Hersteller es vorsah' (#534).
    """

    desired: GpuFanAcousticsValues = GpuFanAcousticsValues()
    baseline: GpuFanAcousticsValues = GpuFanAcousticsValues()


class GpuFanAcousticsNode(BaseModel):
    """Ein Regler: aktueller Stand, Bereich vom Treiber, verwalteter Wert."""

    current: int
    minimum: int
    maximum: int
    desired: Optional[int] = None


class GpuFanAcousticsWrite(BaseModel):
    """Ergebnis EINES Hardware-Writes aus dem PUT.

    Der Rueckgabewert von write_acoustic wurde frueher an beiden
    Aufrufstellen weggeworfen -- samt dem Ergebnis der Ruecklese-Kontrolle,
    die eigens gebaut wurde, weil ein angenommener Write auf dieser Karte
    nichts beweist (#480). Damit blieb ein Fehlschlag fuer den Nutzer
    unsichtbar; hier steht er.
    """

    ok: bool
    value: int
    restored: bool = False


class GpuFanAcousticsStatus(BaseModel):
    """Kein zero_rpm-Feld: das Frontend hat die Luefterliste ohnehin und
    leitet es aus pwm_control und rpm ab. Serverseitig zu bestimmen hiesse,
    get_status() pro Poll ein zweites Mal zu durchlaufen -- und die beiden
    Anzeigen koennten auseinanderlaufen (#516)."""

    available: bool
    competing_manager: Optional[str] = None
    nodes: dict[str, GpuFanAcousticsNode] = {}
    # Nur der PUT fuellt das: je angefasstem Knoten, ob die Karte den Wert
    # angenommen hat. Der GET laesst es leer.
    writes: dict[str, GpuFanAcousticsWrite] = {}
