"""Panel data schemas for the Dashboard Plugin Panel system.

Each schema corresponds to one panel_type in DashboardPanelSpec.
Plugins return one of these from get_dashboard_data() and the
frontend selects the matching renderer.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

DeltaTone = Literal["increase", "decrease", "steady", "live"]
StatusTone = Literal["ok", "warning", "error", "neutral"]


class StatusItem(BaseModel):
    """Single item in a status panel."""

    label: str
    value: str
    tone: StatusTone


class GaugePanelData(BaseModel):
    """Data for gauge-type panel (value + progress bar + trend)."""

    value: str
    meta: str
    submeta: Optional[str] = None
    progress: float
    delta: Optional[str] = None
    delta_tone: DeltaTone = "live"


class StatPanelData(BaseModel):
    """Data for stat-type panel (simple value + meta text)."""

    value: str
    meta: str
    submeta: Optional[str] = None


class StatusPanelData(BaseModel):
    """Data for status-type panel (list of key-value items)."""

    items: List[StatusItem]


class ChartPanelData(BaseModel):
    """Data for chart-type panel (value + sparkline).

    ``points`` should contain the most recent ~30 data points.
    The frontend renders them as a sparkline with no explicit x-axis.
    """

    value: str
    meta: str
    points: List[float] = Field(
        ...,
        description="Sparkline data points (last ~30 values, newest last)",
    )
