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
