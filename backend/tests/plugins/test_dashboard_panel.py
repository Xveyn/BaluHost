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


from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

from app.plugins.base import DashboardPanelSpec, PluginBase, PluginMetadata


class ConcretePlugin(PluginBase):
    """Minimal concrete plugin for testing default methods."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="test_plugin",
            version="1.0.0",
            display_name="Test",
            description="Test plugin",
            author="Test",
        )


class PanelPlugin(ConcretePlugin):
    """Plugin that provides a dashboard panel."""

    def get_dashboard_panel(self) -> Optional[DashboardPanelSpec]:
        return DashboardPanelSpec(
            panel_type="gauge",
            title="Power Monitoring",
            icon="zap",
            accent="from-amber-500 to-orange-500",
        )

    async def get_dashboard_data(self, db) -> Optional[dict]:
        return {"value": "100 W", "meta": "2 devices", "progress": 66.7}


class TestDashboardPanelSpec:
    def test_spec_defaults(self):
        spec = DashboardPanelSpec(panel_type="stat", title="My Panel")
        assert spec.icon == "plug"
        assert spec.accent == "from-sky-500 to-indigo-500"

    def test_spec_custom(self):
        spec = DashboardPanelSpec(
            panel_type="gauge",
            title="Power",
            icon="zap",
            accent="from-amber-500 to-orange-500",
        )
        assert spec.panel_type == "gauge"
        assert spec.icon == "zap"

    def test_spec_invalid_panel_type(self):
        with pytest.raises(ValidationError):
            DashboardPanelSpec(panel_type="sparkle", title="Bad")


class TestPluginBaseDashboardDefaults:
    def test_default_get_dashboard_panel_returns_none(self):
        plugin = ConcretePlugin()
        assert plugin.get_dashboard_panel() is None

    @pytest.mark.asyncio
    async def test_default_get_dashboard_data_returns_none(self):
        plugin = ConcretePlugin()
        result = await plugin.get_dashboard_data(db=None)
        assert result is None

    def test_panel_plugin_returns_spec(self):
        plugin = PanelPlugin()
        spec = plugin.get_dashboard_panel()
        assert spec is not None
        assert spec.panel_type == "gauge"

    @pytest.mark.asyncio
    async def test_panel_plugin_returns_data(self):
        plugin = PanelPlugin()
        data = await plugin.get_dashboard_data(db=None)
        assert data is not None
        assert data["value"] == "100 W"


import asyncio
from unittest.mock import MagicMock, AsyncMock

from app.services.websocket_manager import WebSocketManager


class TestBroadcastTyped:
    @pytest.mark.asyncio
    async def test_broadcast_typed_sends_correct_format(self):
        manager = WebSocketManager()

        mock_ws = AsyncMock()
        mock_ws.send_json = AsyncMock()
        await manager.connect(mock_ws, user_id=1, is_admin=False)

        count = await manager.broadcast_typed(
            "dashboard_panel_update",
            {"panel_type": "gauge", "data": {"value": "120 W"}},
        )

        assert count == 1
        mock_ws.send_json.assert_called_once_with({
            "type": "dashboard_panel_update",
            "payload": {"panel_type": "gauge", "data": {"value": "120 W"}},
        })

    @pytest.mark.asyncio
    async def test_broadcast_typed_cleans_up_dead_connections(self):
        manager = WebSocketManager()

        mock_ws = AsyncMock()
        mock_ws.send_json = AsyncMock(side_effect=Exception("disconnected"))
        await manager.connect(mock_ws, user_id=1, is_admin=False)

        count = await manager.broadcast_typed("test", {"key": "val"})

        assert count == 0
        # Connection should be cleaned up
        assert manager.get_connection_count() == 0
