"""Tests for Dashboard Plugin Panel system."""

import pytest
from pydantic import ValidationError

from app.plugins.dashboard_panel import (
    GaugePanelData,
    StatPanelData,
    StatusPanelData,
    StatusItem,
    ChartPanelData,
)


class TestGaugePanelData:
    def test_valid_gauge(self):
        data = GaugePanelData(
            value="120.5 W",
            meta="3 devices monitored",
            progress=80.3,
        )
        assert data.value == "120.5 W"
        assert data.progress == 80.3
        assert data.delta is None
        assert data.delta_tone == "live"

    def test_gauge_with_all_fields(self):
        data = GaugePanelData(
            value="120.5 W",
            meta="3 devices monitored",
            submeta="Energy today: 2.45 kWh",
            progress=80.3,
            delta="+2.3W",
            delta_tone="increase",
        )
        assert data.submeta == "Energy today: 2.45 kWh"
        assert data.delta == "+2.3W"
        assert data.delta_tone == "increase"

    def test_gauge_missing_required(self):
        with pytest.raises(ValidationError):
            GaugePanelData(value="120 W")  # missing meta, progress


class TestStatPanelData:
    def test_valid_stat(self):
        data = StatPanelData(value="42", meta="Active connections")
        assert data.value == "42"
        assert data.submeta is None

    def test_stat_missing_meta(self):
        with pytest.raises(ValidationError):
            StatPanelData(value="42")


class TestStatusPanelData:
    def test_valid_status(self):
        data = StatusPanelData(
            items=[
                StatusItem(label="DNS", value="Running", tone="ok"),
                StatusItem(label="VPN", value="Stopped", tone="error"),
            ]
        )
        assert len(data.items) == 2
        assert data.items[0].tone == "ok"

    def test_status_empty_items(self):
        data = StatusPanelData(items=[])
        assert data.items == []


class TestChartPanelData:
    def test_valid_chart(self):
        data = ChartPanelData(
            value="45 Mbps",
            meta="Download speed",
            points=[1.0, 2.0, 3.0],
        )
        assert len(data.points) == 3

    def test_chart_missing_points(self):
        with pytest.raises(ValidationError):
            ChartPanelData(value="45", meta="Speed")
