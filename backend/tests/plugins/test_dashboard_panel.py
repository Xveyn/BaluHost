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
            GaugePanelData(value="120 W")  # type: ignore[call-arg]  # missing meta, progress


class TestStatPanelData:
    def test_valid_stat(self):
        data = StatPanelData(value="42", meta="Active connections")
        assert data.value == "42"
        assert data.submeta is None

    def test_stat_missing_meta(self):
        with pytest.raises(ValidationError):
            StatPanelData(value="42")  # type: ignore[call-arg]


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
            ChartPanelData(value="45", meta="Speed")  # type: ignore[call-arg]


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
            DashboardPanelSpec(panel_type="sparkle", title="Bad")  # type: ignore[arg-type]


class TestPluginBaseDashboardDefaults:
    def test_default_get_dashboard_panel_returns_none(self):
        plugin = ConcretePlugin()
        assert plugin.get_dashboard_panel() is None

    @pytest.mark.asyncio
    async def test_default_get_dashboard_data_returns_none(self):
        plugin = ConcretePlugin()
        result = await plugin.get_dashboard_data(db=None)  # type: ignore[arg-type]
        assert result is None

    def test_panel_plugin_returns_spec(self):
        plugin = PanelPlugin()
        spec = plugin.get_dashboard_panel()
        assert spec is not None
        assert spec.panel_type == "gauge"

    @pytest.mark.asyncio
    async def test_panel_plugin_returns_data(self):
        plugin = PanelPlugin()
        data = await plugin.get_dashboard_data(db=None)  # type: ignore[arg-type]
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


from app.services.plugin_service import (
    set_dashboard_panel_enabled,
    get_dashboard_panel_plugin,
)
from app.models.plugin import InstalledPlugin


class TestDashboardPanelToggle:
    def test_enable_deactivates_others(self, db_session):
        """When enabling plugin B's panel, plugin A's panel is auto-disabled."""
        # Create two plugins
        plugin_a = InstalledPlugin(
            name="plugin_a", version="1.0.0", display_name="A",
            is_enabled=True, dashboard_panel_enabled=True,
        )
        plugin_b = InstalledPlugin(
            name="plugin_b", version="1.0.0", display_name="B",
            is_enabled=True, dashboard_panel_enabled=False,
        )
        db_session.add_all([plugin_a, plugin_b])
        db_session.commit()

        set_dashboard_panel_enabled(db_session, "plugin_b", True)

        db_session.refresh(plugin_a)
        db_session.refresh(plugin_b)
        assert plugin_b.dashboard_panel_enabled is True
        assert plugin_a.dashboard_panel_enabled is False

    def test_disable_panel(self, db_session):
        plugin = InstalledPlugin(
            name="plugin_a", version="1.0.0", display_name="A",
            is_enabled=True, dashboard_panel_enabled=True,
        )
        db_session.add(plugin)
        db_session.commit()

        set_dashboard_panel_enabled(db_session, "plugin_a", False)

        db_session.refresh(plugin)
        assert plugin.dashboard_panel_enabled is False

    def test_get_active_panel_plugin(self, db_session):
        plugin = InstalledPlugin(
            name="plugin_a", version="1.0.0", display_name="A",
            is_enabled=True, dashboard_panel_enabled=True,
        )
        db_session.add(plugin)
        db_session.commit()

        result = get_dashboard_panel_plugin(db_session)
        assert result is not None
        assert result.name == "plugin_a"

    def test_get_active_panel_none(self, db_session):
        result = get_dashboard_panel_plugin(db_session)
        assert result is None


from unittest.mock import patch, MagicMock

from app.api.routes.dashboard import get_plugin_panel


class TestGetPluginPanelEndpoint:
    @pytest.mark.asyncio
    async def test_returns_null_when_no_plugin_active(self):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("app.api.routes.dashboard.user_limiter.enabled", False):
            result = await get_plugin_panel(
                request=MagicMock(),
                response=MagicMock(),
                db=mock_db,
                current_user=MagicMock(),
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_panel_data_when_plugin_active(self):
        """Integration-style test: mock DB record + plugin manager."""
        from app.plugins.base import DashboardPanelSpec

        mock_record = MagicMock()
        mock_record.name = "tapo_smart_plug"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        mock_spec = DashboardPanelSpec(
            panel_type="gauge",
            title="Power Monitoring",
            icon="zap",
            accent="from-amber-500 to-orange-500",
        )
        mock_plugin = MagicMock()
        mock_plugin.get_dashboard_panel.return_value = mock_spec
        mock_plugin.get_dashboard_data = AsyncMock(return_value={
            "value": "120 W", "meta": "3 devices", "progress": 80.0,
        })

        mock_pm = MagicMock()
        mock_pm.get_plugin.return_value = mock_plugin

        with patch("app.api.routes.dashboard.user_limiter.enabled", False), patch(
            "app.api.routes.dashboard.PluginManager.get_instance",
            return_value=mock_pm,
        ):
            result = await get_plugin_panel(
                request=MagicMock(),
                response=MagicMock(),
                db=mock_db,
                current_user=MagicMock(),
            )

        assert result is not None
        assert result.plugin_name == "tapo_smart_plug"
        assert result.panel_type == "gauge"
        assert result.data is not None
        assert result.data["value"] == "120 W"


from fastapi import HTTPException
from app.schemas.plugin import DashboardPanelToggleRequest


class TestDashboardPanelToggleRoute:
    @pytest.mark.asyncio
    async def test_toggle_route_exists(self):
        """Verify the dashboard-panel toggle route is registered."""
        from app.api.routes.plugins import router
        route = None
        for r in router.routes:
            if hasattr(r, "path") and "dashboard-panel" in r.path:
                route = r
                break
        assert route is not None, "Route /{name}/dashboard-panel not found"

    @pytest.mark.asyncio
    async def test_toggle_rejects_plugin_without_panel(self):
        """Plugins that don't implement get_dashboard_panel() get 400."""
        from app.api.routes.plugins import toggle_dashboard_panel

        mock_plugin = MagicMock()
        mock_plugin.get_dashboard_panel.return_value = None  # No panel support

        mock_pm = MagicMock()
        mock_pm.get_plugin.return_value = mock_plugin

        with patch("app.api.routes.plugins.user_limiter.enabled", False), \
             pytest.raises(HTTPException) as exc_info:
            await toggle_dashboard_panel(
                request=MagicMock(),
                response=MagicMock(),
                name="no_panel_plugin",
                body=DashboardPanelToggleRequest(enabled=True),
                db=MagicMock(),
                current_user=MagicMock(username="admin"),
                plugin_manager=mock_pm,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_toggle_enables_panel_with_audit(self):
        """Enabling a panel calls set_dashboard_panel_enabled and logs audit."""
        from app.api.routes.plugins import toggle_dashboard_panel

        mock_spec = DashboardPanelSpec(
            panel_type="gauge", title="Power", icon="zap",
            accent="from-amber-500 to-orange-500",
        )
        mock_plugin = MagicMock()
        mock_plugin.get_dashboard_panel.return_value = mock_spec

        mock_pm = MagicMock()
        mock_pm.get_plugin.return_value = mock_plugin

        mock_db = MagicMock()
        mock_audit = MagicMock()

        with patch("app.api.routes.plugins.user_limiter.enabled", False), patch(
            "app.api.routes.plugins.plugin_service"
        ) as mock_svc, patch(
            "app.services.audit.logger_db.get_audit_logger_db",
            return_value=mock_audit,
        ):
            result = await toggle_dashboard_panel(
                request=MagicMock(client=MagicMock(host="127.0.0.1")),
                response=MagicMock(),
                name="tapo_smart_plug",
                body=DashboardPanelToggleRequest(enabled=True),
                db=mock_db,
                current_user=MagicMock(username="admin"),
                plugin_manager=mock_pm,
            )

            mock_svc.set_dashboard_panel_enabled.assert_called_once_with(
                mock_db, "tapo_smart_plug", True
            )
            assert result["dashboard_panel_enabled"] is True


from app.services.dashboard_panel_bridge import _build_panel_update


class TestDashboardPanelBridge:
    @pytest.mark.asyncio
    async def test_build_panel_update_returns_none_when_no_active_plugin(self):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = await _build_panel_update(mock_db)
        assert result is None

    @pytest.mark.asyncio
    async def test_build_panel_update_returns_payload(self):
        from app.plugins.base import DashboardPanelSpec

        mock_record = MagicMock()
        mock_record.name = "tapo_smart_plug"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        mock_spec = DashboardPanelSpec(
            panel_type="gauge", title="Power", icon="zap",
            accent="from-amber-500 to-orange-500",
        )
        mock_plugin = MagicMock()
        mock_plugin.get_dashboard_panel.return_value = mock_spec
        mock_plugin.get_dashboard_data = AsyncMock(return_value={
            "value": "100 W", "meta": "2 devices", "progress": 66.7,
        })

        mock_pm = MagicMock()
        mock_pm.get_plugin.return_value = mock_plugin

        with patch(
            "app.services.dashboard_panel_bridge.PluginManager.get_instance",
            return_value=mock_pm,
        ):
            result = await _build_panel_update(mock_db)

        assert result is not None
        assert result["panel_type"] == "gauge"
        assert result["plugin_name"] == "tapo_smart_plug"
        assert result["data"]["value"] == "100 W"


class TestTapoPluginDashboardPanel:
    def test_get_dashboard_panel_returns_gauge_spec(self):
        from app.plugins.installed.tapo_smart_plug import TapoSmartPlugPlugin

        plugin = TapoSmartPlugPlugin()
        spec = plugin.get_dashboard_panel()

        assert spec is not None
        assert spec.panel_type == "gauge"
        assert spec.title == "Power Monitoring"
        assert spec.icon == "zap"

    @pytest.mark.asyncio
    async def test_get_dashboard_data_aggregates_power(self):
        from app.plugins.installed.tapo_smart_plug import TapoSmartPlugPlugin

        plugin = TapoSmartPlugPlugin()

        # Mock SHM data
        shm_data = {
            "devices": {
                "1": {
                    "state": {
                        "power_monitor": {"watts": 60.0, "energy_today_kwh": 1.2},
                    },
                    "is_online": True,
                    "plugin_name": "tapo_smart_plug",
                },
                "2": {
                    "state": {
                        "power_monitor": {"watts": 40.0, "energy_today_kwh": 0.8},
                    },
                    "is_online": True,
                    "plugin_name": "tapo_smart_plug",
                },
            },
        }

        mock_db = MagicMock()
        # Mock list of active devices
        mock_device_1 = MagicMock(id=1, name="Plug 1", is_active=True, is_online=True, plugin_name="tapo_smart_plug")
        mock_device_2 = MagicMock(id=2, name="Plug 2", is_active=True, is_online=True, plugin_name="tapo_smart_plug")
        mock_db.query.return_value.filter.return_value.all.return_value = [
            mock_device_1, mock_device_2,
        ]

        with patch(
            "app.plugins.installed.tapo_smart_plug.read_shm",
            return_value=shm_data,
        ):
            data = await plugin.get_dashboard_data(mock_db)

        assert data is not None
        assert data["value"] == "100.0 W"
        assert "2" in data["meta"]  # "2 devices monitored"
        assert data["progress"] == pytest.approx(66.7, abs=0.1)


from app.schemas.plugin import PluginDetailResponse


class TestPluginDetailResponsePanelFields:
    def test_detail_response_includes_panel_fields(self):
        """PluginDetailResponse should include has_dashboard_panel and dashboard_panel_enabled."""
        resp = PluginDetailResponse(
            name="test",
            version="1.0.0",
            display_name="Test",
            description="Test plugin",
            author="Test",
            has_dashboard_panel=True,
            dashboard_panel_enabled=True,
        )
        assert resp.has_dashboard_panel is True
        assert resp.dashboard_panel_enabled is True

    def test_detail_response_panel_fields_default_false(self):
        """Panel fields should default to False."""
        resp = PluginDetailResponse(
            name="test",
            version="1.0.0",
            display_name="Test",
            description="Test plugin",
            author="Test",
        )
        assert resp.has_dashboard_panel is False
        assert resp.dashboard_panel_enabled is False
