# Dashboard Plugin Panel System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded PowerWidget with a generic Dashboard Plugin Panel system that any plugin can claim via `get_dashboard_panel()` + `get_dashboard_data()`.

**Architecture:** Backend extends `PluginBase` with two new methods and a DB flag (`dashboard_panel_enabled`). A new REST endpoint serves the active panel's spec+data, WebSocket pushes live updates via a new `broadcast_typed()` method on `WebSocketManager`. Frontend replaces `<PowerWidget />` with a generic `<PluginDashboardPanel />` that selects from four renderer types (gauge, stat, status, chart).

**Tech Stack:** Python/FastAPI, SQLAlchemy+Alembic, Pydantic, React/TypeScript, Tailwind CSS, Recharts (sparkline), WebSocket

**Spec:** `docs/superpowers/specs/2026-03-18-dashboard-plugin-panel-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `backend/app/plugins/dashboard_panel.py` | Panel data schemas (GaugePanelData, StatPanelData, StatusPanelData, ChartPanelData) |
| Create | `backend/app/api/routes/dashboard.py` | `GET /api/dashboard/plugin-panel` endpoint |
| Create | `backend/app/services/dashboard_panel_bridge.py` | SHM-to-WebSocket bridge background task |
| Create | `backend/tests/plugins/test_dashboard_panel.py` | Tests for panel schemas, toggle logic, REST endpoint, bridge |
| Create | `client/src/components/dashboard/PluginDashboardPanel.tsx` | Main component: fetches panel, renders by type, subscribes WS |
| Create | `client/src/components/dashboard/panels/GaugePanel.tsx` | Gauge renderer (value + progress bar + trend) |
| Create | `client/src/components/dashboard/panels/StatPanel.tsx` | Stat renderer (large value + meta) |
| Create | `client/src/components/dashboard/panels/StatusPanel.tsx` | Status renderer (list with colored dots) |
| Create | `client/src/components/dashboard/panels/ChartPanel.tsx` | Chart renderer (value + sparkline) |
| Create | `client/src/components/dashboard/panels/PanelPlaceholder.tsx` | Empty state when no plugin active |
| Create | `backend/alembic/versions/xxxx_add_dashboard_panel_enabled.py` | Alembic migration |
| Modify | `backend/app/plugins/base.py` | Add `DashboardPanelSpec`, `get_dashboard_panel()`, `get_dashboard_data()` |
| Modify | `backend/app/models/plugin.py` | Add `dashboard_panel_enabled` column |
| Modify | `backend/app/services/websocket_manager.py` | Add `broadcast_typed()` method |
| Modify | `backend/app/services/plugin_service.py` | Add `set_dashboard_panel_enabled()` |
| Modify | `backend/app/api/routes/plugins.py` | Add `POST /{name}/dashboard-panel` toggle route |
| Modify | `backend/app/schemas/plugin.py` | Add `DashboardPanelToggleRequest`, `DashboardPanelResponse`, `has_dashboard_panel` + `dashboard_panel_enabled` fields |
| Modify | `backend/app/core/lifespan.py` | Start `dashboard_panel_ws_bridge` task |
| Modify | `backend/app/plugins/installed/tapo_smart_plug/__init__.py` | Implement `get_dashboard_panel()` + `get_dashboard_data()` |
| Modify | `client/src/pages/Dashboard.tsx` | Replace `<PowerWidget />` with `<PluginDashboardPanel />` |
| Modify | `client/src/components/dashboard/index.ts` | Export new component |
| Modify | `client/src/i18n/locales/en/dashboard.json` | Add panel i18n keys |
| Modify | `client/src/i18n/locales/de/dashboard.json` | Add panel i18n keys (German) |
| Delete | `client/src/components/PowerWidget.tsx` | Replaced by PluginDashboardPanel |
| Delete | `client/src/hooks/usePowerMonitoring.ts` | No longer needed (only consumer was PowerWidget) |

---

## Task 1: Panel Data Schemas

**Files:**
- Create: `backend/app/plugins/dashboard_panel.py`
- Test: `backend/tests/plugins/test_dashboard_panel.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/plugins/test_dashboard_panel.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.plugins.dashboard_panel'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/plugins/dashboard_panel.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/dashboard_panel.py backend/tests/plugins/test_dashboard_panel.py
git commit -m "feat(plugins): add Dashboard panel data schemas"
```

---

## Task 2: Extend PluginBase with Dashboard Panel Methods

**Files:**
- Modify: `backend/app/plugins/base.py:1-216`
- Test: `backend/tests/plugins/test_dashboard_panel.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/plugins/test_dashboard_panel.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py::TestDashboardPanelSpec -v`
Expected: FAIL with `ImportError: cannot import name 'DashboardPanelSpec' from 'app.plugins.base'`

- [ ] **Step 3: Modify PluginBase**

In `backend/app/plugins/base.py`:

1. Add imports at top: `from typing import ..., Literal` (add `Literal` to the existing import), and add `from typing import TYPE_CHECKING` with `if TYPE_CHECKING: from sqlalchemy.orm import Session` for the type hint
2. Add `PanelType` and `DashboardPanelSpec` after `PluginUIManifest` (before `BackgroundTaskSpec`):

```python
PanelType = Literal["gauge", "stat", "status", "chart"]


class DashboardPanelSpec(BaseModel):
    """Specification for a plugin's Dashboard panel."""

    panel_type: PanelType = Field(
        ...,
        description="Panel renderer type",
    )
    title: str = Field(..., description="Panel title, e.g. 'Power Monitoring'")
    icon: str = Field(default="plug", description="Lucide icon name")
    accent: str = Field(
        default="from-sky-500 to-indigo-500",
        description="Tailwind gradient classes for icon background",
    )
```

3. Add two methods to `PluginBase` class (after `get_config_schema`):

```python
    def get_dashboard_panel(self) -> Optional["DashboardPanelSpec"]:
        """Override to claim the Dashboard plugin slot.

        Returns:
            DashboardPanelSpec or None if this plugin has no Dashboard panel.
        """
        return None

    async def get_dashboard_data(self, db: "Session") -> Optional[dict]:
        """Return current data for the Dashboard panel.

        Called by the dashboard endpoint and the SHM-to-WS bridge.
        The returned dict must conform to the schema matching the
        plugin's DashboardPanelSpec.panel_type.

        Args:
            db: SQLAlchemy session.

        Returns:
            Panel data dict or None if no data available.
        """
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py -v`
Expected: All 15 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/base.py backend/tests/plugins/test_dashboard_panel.py
git commit -m "feat(plugins): add DashboardPanelSpec and panel methods to PluginBase"
```

---

## Task 3: Database Migration — `dashboard_panel_enabled`

**Files:**
- Modify: `backend/app/models/plugin.py:12-51`
- Create: Alembic migration file

- [ ] **Step 1: Add column to model**

In `backend/app/models/plugin.py`, add after the `disabled_at` column (line ~43):

```python
    dashboard_panel_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
```

- [ ] **Step 2: Generate Alembic migration**

Run: `cd backend && alembic revision --autogenerate -m "add dashboard_panel_enabled to installed_plugins"`

- [ ] **Step 3: Review and apply migration**

Run: `cd backend && alembic upgrade head`
Expected: Migration applies successfully, column added

- [ ] **Step 4: Verify**

Run: `cd backend && python -c "from app.models.plugin import InstalledPlugin; print(InstalledPlugin.__table__.columns.keys())"`
Expected: Output includes `'dashboard_panel_enabled'`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/plugin.py backend/alembic/versions/*dashboard_panel*
git commit -m "feat(db): add dashboard_panel_enabled column to installed_plugins"
```

---

## Task 4: `broadcast_typed()` on WebSocketManager

**Files:**
- Modify: `backend/app/services/websocket_manager.py:24-277`
- Test: `backend/tests/plugins/test_dashboard_panel.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/plugins/test_dashboard_panel.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py::TestBroadcastTyped -v`
Expected: FAIL with `AttributeError: 'WebSocketManager' object has no attribute 'broadcast_typed'`

- [ ] **Step 3: Add `broadcast_typed()` to WebSocketManager**

In `backend/app/services/websocket_manager.py`, add after the `broadcast_to_all` method (after line 212):

```python
    async def broadcast_typed(self, msg_type: str, payload: dict[str, Any]) -> int:
        """Broadcast a typed message to all connected users.

        Unlike broadcast_to_all() which wraps in {"type": "notification"},
        this method sends {"type": msg_type, "payload": payload} directly.

        Args:
            msg_type: Message type string (e.g. "dashboard_panel_update").
            payload: Message payload dict.

        Returns:
            Number of connections the message was sent to.
        """
        sent_count = 0
        async with self._lock:
            for user_id, connections in list(self._user_connections.items()):
                disconnected = []

                for conn in connections:
                    try:
                        await conn.websocket.send_json({
                            "type": msg_type,
                            "payload": payload,
                        })
                        sent_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to broadcast to user {user_id}: {e}")
                        disconnected.append(conn)

                # Clean up disconnected connections
                for conn in disconnected:
                    if conn in connections:
                        connections.remove(conn)

                if not connections and user_id in self._user_connections:
                    del self._user_connections[user_id]
                    self._admin_users.discard(user_id)

        return sent_count
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py::TestBroadcastTyped -v`
Expected: Both tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/websocket_manager.py backend/tests/plugins/test_dashboard_panel.py
git commit -m "feat(ws): add broadcast_typed() to WebSocketManager"
```

---

## Task 5: Dashboard Panel Toggle Service Logic

**Files:**
- Modify: `backend/app/services/plugin_service.py:1-133`
- Modify: `backend/app/schemas/plugin.py:1-162`
- Test: `backend/tests/plugins/test_dashboard_panel.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/plugins/test_dashboard_panel.py`:

```python
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
```

Note: These tests require a `db_session` fixture. If your test suite uses a different name for the DB fixture, match it (check `backend/tests/conftest.py`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py::TestDashboardPanelToggle -v`
Expected: FAIL with `ImportError: cannot import name 'set_dashboard_panel_enabled'`

- [ ] **Step 3: Add service functions**

In `backend/app/services/plugin_service.py`, add at the end:

```python
def set_dashboard_panel_enabled(
    db: Session, plugin_name: str, enabled: bool
) -> None:
    """Enable/disable a plugin's Dashboard panel.

    When enabling, deactivates any other plugin's panel (single-slot).
    """
    if enabled:
        # Deactivate all other panels
        db.query(InstalledPlugin).filter(
            InstalledPlugin.name != plugin_name,
            InstalledPlugin.dashboard_panel_enabled == True,  # noqa: E712
        ).update({"dashboard_panel_enabled": False})

    # Set the target plugin
    db.query(InstalledPlugin).filter(
        InstalledPlugin.name == plugin_name,
    ).update({"dashboard_panel_enabled": enabled})

    db.commit()


def get_dashboard_panel_plugin(db: Session) -> Optional[InstalledPlugin]:
    """Get the plugin with dashboard panel enabled (if any)."""
    return (
        db.query(InstalledPlugin)
        .filter(
            InstalledPlugin.is_enabled == True,  # noqa: E712
            InstalledPlugin.dashboard_panel_enabled == True,  # noqa: E712
        )
        .first()
    )
```

- [ ] **Step 4: Add schemas**

In `backend/app/schemas/plugin.py`, add:

```python
class DashboardPanelToggleRequest(BaseModel):
    """Request to enable/disable a plugin's Dashboard panel."""

    enabled: bool


class DashboardPanelResponse(BaseModel):
    """Response for the active Dashboard plugin panel."""

    plugin_name: str
    panel_type: str
    title: str
    icon: str
    accent: str
    data: Optional[Dict[str, Any]] = None
```

Also add `dashboard_panel_enabled: bool = False` and `has_dashboard_panel: bool = False` to the `PluginDetailResponse` class.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/plugin_service.py backend/app/schemas/plugin.py backend/tests/plugins/test_dashboard_panel.py
git commit -m "feat(plugins): add dashboard panel toggle service and schemas"
```

---

## Task 6: REST Endpoint — `GET /api/dashboard/plugin-panel`

**Files:**
- Create: `backend/app/api/routes/dashboard.py`
- Modify: `backend/app/main.py` (register the router)
- Test: `backend/tests/plugins/test_dashboard_panel.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/plugins/test_dashboard_panel.py`:

```python
from unittest.mock import patch, MagicMock

from app.api.routes.dashboard import get_plugin_panel


class TestGetPluginPanelEndpoint:
    @pytest.mark.asyncio
    async def test_returns_null_when_no_plugin_active(self):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

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

        with patch(
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
        assert result.data["value"] == "120 W"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py::TestGetPluginPanelEndpoint -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.api.routes.dashboard'`

- [ ] **Step 3: Create the dashboard route**

```python
# backend/app/api/routes/dashboard.py
"""API routes for Dashboard plugin panel."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.models.user import User
from app.plugins.manager import PluginManager
from app.schemas.plugin import DashboardPanelResponse
from app.services.plugin_service import get_dashboard_panel_plugin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/plugin-panel", response_model=Optional[DashboardPanelResponse])
@user_limiter.limit(get_limit("default"))
async def get_plugin_panel(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Optional[DashboardPanelResponse]:
    """Get the active Dashboard plugin panel with current data.

    Returns the panel spec + data for the plugin that has
    dashboard_panel_enabled=True, or null if no plugin is active.
    """
    record = get_dashboard_panel_plugin(db)
    if record is None:
        return None

    # Get the loaded plugin instance
    pm = PluginManager.get_instance()
    plugin = pm.get_plugin(record.name)
    if plugin is None:
        return None

    spec = plugin.get_dashboard_panel()
    if spec is None:
        return None

    # Get current data
    data = None
    try:
        data = await plugin.get_dashboard_data(db)
    except Exception as exc:
        logger.warning(
            "Dashboard panel data error for plugin %s: %s",
            record.name, exc,
        )

    return DashboardPanelResponse(
        plugin_name=record.name,
        panel_type=spec.panel_type,
        title=spec.title,
        icon=spec.icon,
        accent=spec.accent,
        data=data,
    )
```

- [ ] **Step 4: Register the router**

In `backend/app/main.py`, find where other routers are included (search for `include_router`) and add:

```python
from app.api.routes.dashboard import router as dashboard_router
app.include_router(dashboard_router, prefix=settings.api_prefix)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py::TestGetPluginPanelEndpoint -v`
Expected: Both tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/dashboard.py backend/app/main.py backend/tests/plugins/test_dashboard_panel.py
git commit -m "feat(api): add GET /api/dashboard/plugin-panel endpoint"
```

---

## Task 7: Toggle Endpoint — `POST /api/plugins/{name}/dashboard-panel`

**Files:**
- Modify: `backend/app/api/routes/plugins.py:1-449`
- Test: `backend/tests/plugins/test_dashboard_panel.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/plugins/test_dashboard_panel.py`:

```python
class TestDashboardPanelToggleRoute:
    @pytest.mark.asyncio
    async def test_toggle_route_exists(self):
        """Verify the dashboard-panel toggle route is registered."""
        from app.api.routes.plugins import router
        route = None
        for r in router.routes:
            if hasattr(r, "path") and r.path == "/{name}/dashboard-panel":
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

        with patch(
            "app.api.routes.plugins.get_plugin_manager",
            return_value=mock_pm,
        ):
            with pytest.raises(HTTPException) as exc_info:
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

        with patch(
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
```

Note: These tests use `from fastapi import HTTPException` and `from app.schemas.plugin import DashboardPanelToggleRequest` — ensure these are imported at the top of the test file.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py::TestDashboardPanelToggleRoute -v`
Expected: FAIL — route not found / toggle function not found

- [ ] **Step 3: Add the toggle endpoint**

In `backend/app/api/routes/plugins.py`, add before the `@router.get("/{name}/config"...)` route (line ~268):

```python
@router.post("/{name}/dashboard-panel")
@user_limiter.limit(get_limit("admin_operations"))
async def toggle_dashboard_panel(
    request: Request,
    response: Response,
    name: str,
    body: DashboardPanelToggleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    plugin_manager: PluginManager = Depends(get_plugin_manager),
):
    """Enable or disable a plugin's Dashboard panel.

    Admin only. When enabling, any other plugin's panel is deactivated
    (single-slot constraint).
    """
    plugin = plugin_manager.get_plugin(name)
    if plugin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plugin not found or not enabled",
        )

    # Verify plugin supports dashboard panel
    if plugin.get_dashboard_panel() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plugin does not provide a Dashboard panel",
        )

    plugin_service.set_dashboard_panel_enabled(db, name, body.enabled)

    # Audit log
    from app.services.audit.logger_db import get_audit_logger_db
    audit = get_audit_logger_db()
    audit.log_event(
        event_type="PLUGIN",
        user=current_user.username,
        action="toggle_dashboard_panel",
        resource=name,
        details={"enabled": body.enabled},
        ip_address=request.client.host if request.client else None,
    )

    logger.info(
        "Dashboard panel %s for plugin %s by %s",
        "enabled" if body.enabled else "disabled",
        name,
        current_user.username,
    )
    return {
        "name": name,
        "dashboard_panel_enabled": body.enabled,
        "message": f"Dashboard panel {'enabled' if body.enabled else 'disabled'}",
    }
```

Add `DashboardPanelToggleRequest` to the imports from `app.schemas.plugin` at the top of the file.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py::TestDashboardPanelToggleRoute -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/plugins.py backend/tests/plugins/test_dashboard_panel.py
git commit -m "feat(api): add POST /api/plugins/{name}/dashboard-panel toggle endpoint"
```

---

## Task 8: SHM-to-WebSocket Bridge

**Files:**
- Create: `backend/app/services/dashboard_panel_bridge.py`
- Modify: `backend/app/core/lifespan.py:154-188,379-442`
- Test: `backend/tests/plugins/test_dashboard_panel.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/plugins/test_dashboard_panel.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py::TestDashboardPanelBridge -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create bridge service**

```python
# backend/app/services/dashboard_panel_bridge.py
"""SHM-to-WebSocket bridge for Dashboard plugin panel updates.

Runs as a background task in the web worker (primary only). Detects
changes in the smart device SHM file, calls the active dashboard
plugin's get_dashboard_data(), and broadcasts via WebSocket.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.plugins.manager import PluginManager
from app.services.plugin_service import get_dashboard_panel_plugin

logger = logging.getLogger(__name__)


async def _build_panel_update(db: Session) -> Optional[Dict[str, Any]]:
    """Build a dashboard_panel_update payload for the active plugin.

    Args:
        db: SQLAlchemy session.

    Returns:
        Payload dict or None if no plugin panel is active.
    """
    record = get_dashboard_panel_plugin(db)
    if record is None:
        return None

    pm = PluginManager.get_instance()
    plugin = pm.get_plugin(record.name)
    if plugin is None:
        return None

    spec = plugin.get_dashboard_panel()
    if spec is None:
        return None

    data = None
    try:
        data = await plugin.get_dashboard_data(db)
    except Exception as exc:
        logger.debug("Dashboard panel data error: %s", exc)

    if data is None:
        return None

    return {
        "panel_type": spec.panel_type,
        "plugin_name": record.name,
        "data": data,
    }


async def dashboard_panel_ws_bridge() -> None:
    """Background task: SHM change detection -> get_dashboard_data -> WS broadcast.

    Runs every 3 seconds. When the SHM changes file is newer than the last
    check, calls get_dashboard_data(db) for full state and broadcasts
    a dashboard_panel_update message.
    """
    import asyncio

    from app.core.database import SessionLocal
    from app.services.monitoring.shm import read_shm, SMART_DEVICES_CHANGES_FILE
    from app.services.websocket_manager import get_websocket_manager

    _last_broadcast_ts: float = 0.0

    while True:
        await asyncio.sleep(3.0)
        try:
            # Check if there are any new changes
            data = read_shm(SMART_DEVICES_CHANGES_FILE, max_age_seconds=10.0)
            if data is None:
                continue

            ts = data.get("timestamp", 0.0)
            if ts <= _last_broadcast_ts:
                continue

            _last_broadcast_ts = ts

            # Build panel update from the active plugin
            db = SessionLocal()
            try:
                payload = await _build_panel_update(db)
            finally:
                db.close()

            if payload is None:
                continue

            ws = get_websocket_manager()
            if ws:
                await ws.broadcast_typed("dashboard_panel_update", payload)

        except Exception as exc:
            logger.debug("Dashboard panel WS bridge error: %s", exc)
```

- [ ] **Step 4: Start bridge in lifespan**

In `backend/app/core/lifespan.py`, in the `_startup()` function, find the block that starts the smart device WS bridge (line ~441-442):

```python
    # Start SmartDevice WebSocket bridge (primary worker only)
    if IS_PRIMARY_WORKER:
        asyncio.create_task(_smart_device_ws_bridge())
```

Add immediately after:

```python
        # Start Dashboard panel WS bridge (primary worker only)
        from app.services.dashboard_panel_bridge import dashboard_panel_ws_bridge
        asyncio.create_task(dashboard_panel_ws_bridge())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py::TestDashboardPanelBridge -v`
Expected: Both tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/dashboard_panel_bridge.py backend/app/core/lifespan.py backend/tests/plugins/test_dashboard_panel.py
git commit -m "feat: add SHM-to-WebSocket bridge for Dashboard panel updates"
```

---

## Task 9: Tapo Plugin — Implement Dashboard Panel Methods

**Files:**
- Modify: `backend/app/plugins/installed/tapo_smart_plug/__init__.py:40-451`
- Test: `backend/tests/plugins/test_dashboard_panel.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/plugins/test_dashboard_panel.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py::TestTapoPluginDashboardPanel -v`
Expected: FAIL — `get_dashboard_panel()` returns None (default from PluginBase)

- [ ] **Step 3: Implement methods on TapoSmartPlugPlugin**

In `backend/app/plugins/installed/tapo_smart_plug/__init__.py`:

1. Add imports at top:

```python
from app.plugins.base import DashboardPanelSpec
from app.services.monitoring.shm import SMART_DEVICES_FILE, read_shm
```

2. Add after the `get_device_types()` method (before `on_startup`):

```python
    # ------------------------------------------------------------------
    # Dashboard Panel
    # ------------------------------------------------------------------

    def get_dashboard_panel(self) -> Optional[DashboardPanelSpec]:
        return DashboardPanelSpec(
            panel_type="gauge",
            title="Power Monitoring",
            icon="zap",
            accent="from-amber-500 to-orange-500",
        )

    async def get_dashboard_data(self, db: Any) -> Optional[dict]:
        """Aggregate power data from the Smart Device system (SHM/DB).

        Returns GaugePanelData-compatible dict:
        - value: total watts across all online power-monitoring devices
        - meta: "X devices monitored"
        - submeta: "Energy today: X.XX kWh"
        - progress: percentage of assumed max power (default 150W)
        - delta + delta_tone: "live" (trend from SHM)
        """
        from app.models.smart_device import SmartDevice

        shm_data = read_shm(SMART_DEVICES_FILE, max_age_seconds=30.0)
        devices_shm: Dict[str, Any] = {}
        if shm_data:
            devices_shm = shm_data.get("devices", {})

        # Get all active devices for this plugin
        all_devices = (
            db.query(SmartDevice)
            .filter(
                SmartDevice.plugin_name == "tapo_smart_plug",
                SmartDevice.is_active == True,  # noqa: E712
                SmartDevice.is_online == True,  # noqa: E712
            )
            .all()
        )

        total_watts = 0.0
        total_energy_kwh = 0.0
        device_count = 0

        for device in all_devices:
            entry = devices_shm.get(str(device.id))
            if not entry:
                continue
            state = entry.get("state", {})
            pm = state.get("power_monitor")
            if pm and isinstance(pm, dict):
                watts = float(pm.get("watts", 0.0))
                energy = float(pm.get("energy_today_kwh", 0.0))
                if watts > 0.0 or energy > 0.0:
                    total_watts += watts
                    total_energy_kwh += energy
                    device_count += 1

        if device_count == 0:
            return None

        max_power = 150.0
        progress = min((total_watts / max_power) * 100, 100.0)

        return {
            "value": f"{total_watts:.1f} W",
            "meta": f"{device_count} {'device' if device_count == 1 else 'devices'} monitored",
            "submeta": f"Energy today: {total_energy_kwh:.2f} kWh",
            "progress": round(progress, 1),
            "delta_tone": "live",
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py::TestTapoPluginDashboardPanel -v`
Expected: Both tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/installed/tapo_smart_plug/__init__.py backend/tests/plugins/test_dashboard_panel.py
git commit -m "feat(tapo): implement get_dashboard_panel() + get_dashboard_data()"
```

---

## Task 10: Frontend — Panel Renderers and Placeholder

**Files:**
- Create: `client/src/components/dashboard/panels/GaugePanel.tsx`
- Create: `client/src/components/dashboard/panels/StatPanel.tsx`
- Create: `client/src/components/dashboard/panels/StatusPanel.tsx`
- Create: `client/src/components/dashboard/panels/ChartPanel.tsx`
- Create: `client/src/components/dashboard/panels/PanelPlaceholder.tsx`

- [ ] **Step 1: Create GaugePanel**

```tsx
// client/src/components/dashboard/panels/GaugePanel.tsx
import { formatNumber } from '../../../lib/formatters';

interface GaugePanelProps {
  title: string;
  icon: React.ReactNode;
  accent: string;
  data: {
    value: string;
    meta: string;
    submeta?: string;
    progress: number;
    delta?: string;
    delta_tone?: 'increase' | 'decrease' | 'steady' | 'live';
  };
  onClick?: () => void;
}

export const GaugePanel: React.FC<GaugePanelProps> = ({ title, icon, accent, data, onClick }) => {
  const deltaToneClass = data.delta_tone === 'decrease'
    ? 'text-emerald-400'
    : data.delta_tone === 'increase'
      ? 'text-rose-300'
      : data.delta_tone === 'steady'
        ? 'text-slate-400'
        : 'text-sky-400';

  const deltaLabel = data.delta ?? 'Live';

  return (
    <div
      onClick={onClick}
      className={`card border-slate-800/40 bg-slate-900/60 transition-all duration-200 hover:border-slate-700/60 hover:bg-slate-900/80 hover:shadow-[0_14px_44px_rgba(56,189,248,0.15)] active:scale-[0.98] touch-manipulation ${onClick ? 'cursor-pointer' : ''}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{title}</p>
          <p className="mt-2 text-2xl sm:text-3xl font-semibold text-white truncate">{data.value}</p>
        </div>
        <div className={`flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${accent} text-white shadow-[0_12px_38px_rgba(59,130,246,0.35)]`}>
          {icon}
        </div>
      </div>
      <div className="mt-3 sm:mt-4 flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2 text-xs text-slate-400">
          <span className="truncate flex-1 min-w-0">{data.meta}</span>
          <span className={`${deltaToneClass} shrink-0`}>{deltaLabel}</span>
        </div>
        {data.submeta && (
          <div className="text-xs text-slate-500 truncate">{data.submeta}</div>
        )}
      </div>
      <div className="mt-4 sm:mt-5 h-2 w-full overflow-hidden rounded-full bg-slate-800">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${accent} transition-all duration-500`}
          style={{ width: `${Math.min(Math.max(data.progress, 0), 100)}%` }}
        />
      </div>
    </div>
  );
};
```

- [ ] **Step 2: Create StatPanel**

```tsx
// client/src/components/dashboard/panels/StatPanel.tsx

interface StatPanelProps {
  title: string;
  icon: React.ReactNode;
  accent: string;
  data: {
    value: string;
    meta: string;
    submeta?: string;
  };
  onClick?: () => void;
}

export const StatPanel: React.FC<StatPanelProps> = ({ title, icon, accent, data, onClick }) => {
  return (
    <div
      onClick={onClick}
      className={`card border-slate-800/40 bg-slate-900/60 transition-all duration-200 hover:border-slate-700/60 hover:bg-slate-900/80 active:scale-[0.98] touch-manipulation ${onClick ? 'cursor-pointer' : ''}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{title}</p>
          <p className="mt-2 text-2xl sm:text-3xl font-semibold text-white truncate">{data.value}</p>
        </div>
        <div className={`flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${accent} text-white shadow-[0_12px_38px_rgba(59,130,246,0.35)]`}>
          {icon}
        </div>
      </div>
      <div className="mt-3 sm:mt-4 flex flex-col gap-1">
        <div className="text-xs text-slate-400 truncate">{data.meta}</div>
        {data.submeta && (
          <div className="text-xs text-slate-500 truncate">{data.submeta}</div>
        )}
      </div>
    </div>
  );
};
```

- [ ] **Step 3: Create StatusPanel**

```tsx
// client/src/components/dashboard/panels/StatusPanel.tsx

interface StatusItem {
  label: string;
  value: string;
  tone: 'ok' | 'warning' | 'error' | 'neutral';
}

interface StatusPanelProps {
  title: string;
  icon: React.ReactNode;
  accent: string;
  data: {
    items: StatusItem[];
  };
  onClick?: () => void;
}

const toneColors: Record<string, string> = {
  ok: 'bg-emerald-400',
  warning: 'bg-amber-400',
  error: 'bg-rose-400',
  neutral: 'bg-slate-400',
};

export const StatusPanel: React.FC<StatusPanelProps> = ({ title, icon, accent, data, onClick }) => {
  return (
    <div
      onClick={onClick}
      className={`card border-slate-800/40 bg-slate-900/60 transition-all duration-200 hover:border-slate-700/60 hover:bg-slate-900/80 active:scale-[0.98] touch-manipulation ${onClick ? 'cursor-pointer' : ''}`}
    >
      <div className="flex items-center justify-between gap-3 mb-4">
        <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{title}</p>
        <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${accent} text-white`}>
          {icon}
        </div>
      </div>
      <ul className="space-y-2">
        {data.items.map((item, i) => (
          <li key={i} className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <span className={`inline-block h-2 w-2 rounded-full ${toneColors[item.tone] || toneColors.neutral}`} />
              <span className="text-slate-400">{item.label}</span>
            </div>
            <span className="text-slate-200">{item.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
};
```

- [ ] **Step 4: Create ChartPanel**

```tsx
// client/src/components/dashboard/panels/ChartPanel.tsx
import { AreaChart, Area, ResponsiveContainer } from 'recharts';

interface ChartPanelProps {
  title: string;
  icon: React.ReactNode;
  accent: string;
  data: {
    value: string;
    meta: string;
    points: number[];
  };
  onClick?: () => void;
}

export const ChartPanel: React.FC<ChartPanelProps> = ({ title, icon, accent, data, onClick }) => {
  const chartData = data.points.map((v, i) => ({ idx: i, value: v }));

  return (
    <div
      onClick={onClick}
      className={`card border-slate-800/40 bg-slate-900/60 transition-all duration-200 hover:border-slate-700/60 hover:bg-slate-900/80 active:scale-[0.98] touch-manipulation ${onClick ? 'cursor-pointer' : ''}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">{title}</p>
          <p className="mt-2 text-2xl sm:text-3xl font-semibold text-white truncate">{data.value}</p>
        </div>
        <div className={`flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br ${accent} text-white shadow-[0_12px_38px_rgba(59,130,246,0.35)]`}>
          {icon}
        </div>
      </div>
      <div className="mt-2 text-xs text-slate-400 truncate">{data.meta}</div>
      <div className="mt-3 h-16 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="panelChartGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.3} />
                <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
              </linearGradient>
            </defs>
            <Area
              type="monotone"
              dataKey="value"
              stroke="#38bdf8"
              strokeWidth={1.5}
              fill="url(#panelChartGrad)"
              dot={false}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
```

- [ ] **Step 5: Create PanelPlaceholder**

```tsx
// client/src/components/dashboard/panels/PanelPlaceholder.tsx
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { Plug } from 'lucide-react';
import { useAuth } from '../../../contexts/AuthContext';

export const PanelPlaceholder: React.FC = () => {
  const { t } = useTranslation('dashboard');
  const { isAdmin } = useAuth();
  const navigate = useNavigate();

  return (
    <div
      onClick={isAdmin ? () => navigate('/settings') : undefined}
      className={`card border-slate-800/40 bg-slate-900/60 ${isAdmin ? 'cursor-pointer hover:border-slate-700/60' : ''}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">
            {t('pluginPanel.title', 'Plugin Panel')}
          </p>
          <p className="mt-2 text-lg font-medium text-slate-500">
            {t('pluginPanel.noPlugin', 'No plugin configured')}
          </p>
        </div>
        <div className="flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-2xl bg-slate-800 text-slate-500">
          <Plug className="h-6 w-6" />
        </div>
      </div>
      {isAdmin && (
        <div className="mt-3 text-xs text-slate-500">
          {t('pluginPanel.configureHint', 'Enable a plugin\'s Dashboard panel in Settings → Plugins')}
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 6: Commit**

```bash
git add client/src/components/dashboard/panels/
git commit -m "feat(frontend): add panel renderers (gauge, stat, status, chart) and placeholder"
```

---

## Task 11: Frontend — PluginDashboardPanel Component

**Files:**
- Create: `client/src/components/dashboard/PluginDashboardPanel.tsx`
- Modify: `client/src/components/dashboard/index.ts`

- [ ] **Step 1: Create PluginDashboardPanel**

```tsx
// client/src/components/dashboard/PluginDashboardPanel.tsx
/**
 * Generic Dashboard Plugin Panel
 *
 * Fetches the active plugin's panel spec+data via REST, subscribes to
 * WebSocket updates, and renders the appropriate panel renderer.
 * Falls back to REST polling (10s) if WS disconnects.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { buildApiUrl } from '../../lib/api';
import api from '../../lib/api';
import * as LucideIcons from 'lucide-react';
import { GaugePanel } from './panels/GaugePanel';
import { StatPanel } from './panels/StatPanel';
import { StatusPanel } from './panels/StatusPanel';
import { ChartPanel } from './panels/ChartPanel';
import { PanelPlaceholder } from './panels/PanelPlaceholder';

interface PanelSpec {
  plugin_name: string;
  panel_type: 'gauge' | 'stat' | 'status' | 'chart';
  title: string;
  icon: string;
  accent: string;
  data: Record<string, unknown> | null;
}

const REST_POLL_INTERVAL = 10_000; // 10s fallback when WS is down

export const PluginDashboardPanel: React.FC = () => {
  const { token } = useAuth();
  const [panel, setPanel] = useState<PanelSpec | null>(null);
  const [loaded, setLoaded] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch panel data via REST
  const fetchPanel = useCallback(async () => {
    try {
      const res = await api.get<PanelSpec | null>('/api/dashboard/plugin-panel');
      setPanel(res.data);
    } catch {
      // Silent fail — panel slot stays empty
    } finally {
      setLoaded(true);
    }
  }, []);

  // Initial REST fetch
  useEffect(() => {
    fetchPanel();
  }, [fetchPanel]);

  // WebSocket subscription for live updates
  useEffect(() => {
    if (!token) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}${buildApiUrl('/api/notifications/ws')}?token=${token}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string) as {
          type: string;
          payload?: unknown;
        };

        if (msg.type === 'dashboard_panel_update' && msg.payload) {
          const payload = msg.payload as {
            panel_type: string;
            plugin_name: string;
            data: Record<string, unknown>;
          };

          setPanel((prev) => {
            if (!prev) return prev;
            // Only update data if it's for the same plugin
            if (prev.plugin_name !== payload.plugin_name) return prev;
            return { ...prev, data: payload.data };
          });
        }
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onopen = () => {
      // WS connected — stop REST polling fallback
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };

    ws.onclose = () => {
      // WS disconnected — start REST polling fallback
      if (!pollRef.current) {
        pollRef.current = setInterval(fetchPanel, REST_POLL_INTERVAL);
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [token, fetchPanel]);

  if (!loaded) {
    return (
      <div className="card border-slate-800/40 bg-slate-900/60">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-500">Plugin Panel</p>
          <p className="mt-2 text-2xl sm:text-3xl font-semibold text-slate-400">...</p>
        </div>
      </div>
    );
  }

  if (!panel || !panel.data) {
    return <PanelPlaceholder />;
  }

  // Resolve Lucide icon by name
  const IconComponent = (LucideIcons as Record<string, React.FC<{ className?: string }>>)[
    panel.icon.charAt(0).toUpperCase() + panel.icon.slice(1)
  ] || LucideIcons.Plug;
  const iconElement = <IconComponent className="h-6 w-6" />;

  const rendererProps = {
    title: panel.title,
    icon: iconElement,
    accent: panel.accent,
  };

  switch (panel.panel_type) {
    case 'gauge':
      return <GaugePanel {...rendererProps} data={panel.data as any} />;
    case 'stat':
      return <StatPanel {...rendererProps} data={panel.data as any} />;
    case 'status':
      return <StatusPanel {...rendererProps} data={panel.data as any} />;
    case 'chart':
      return <ChartPanel {...rendererProps} data={panel.data as any} />;
    default:
      return <PanelPlaceholder />;
  }
};
```

- [ ] **Step 2: Export from dashboard index**

In `client/src/components/dashboard/index.ts`, add:

```typescript
export { PluginDashboardPanel } from './PluginDashboardPanel';
```

- [ ] **Step 3: Commit**

```bash
git add client/src/components/dashboard/PluginDashboardPanel.tsx client/src/components/dashboard/index.ts
git commit -m "feat(frontend): add PluginDashboardPanel with WS+REST data transport"
```

---

## Task 12: i18n Keys

**Files:**
- Modify: `client/src/i18n/locales/en/dashboard.json`
- Modify: `client/src/i18n/locales/de/dashboard.json`

Note: i18n keys must be added BEFORE the frontend components that reference them (Tasks 10-11 PanelPlaceholder uses `t('pluginPanel.title')` etc.).

- [ ] **Step 1: Add English keys**

Add to `client/src/i18n/locales/en/dashboard.json` at the top level:

```json
  "pluginPanel": {
    "title": "Plugin Panel",
    "noPlugin": "No plugin configured",
    "configureHint": "Enable a plugin's Dashboard panel in Settings → Plugins"
  }
```

- [ ] **Step 2: Add German keys**

Add to `client/src/i18n/locales/de/dashboard.json` at the top level:

```json
  "pluginPanel": {
    "title": "Plugin-Panel",
    "noPlugin": "Kein Plugin konfiguriert",
    "configureHint": "Aktiviere das Dashboard-Panel eines Plugins unter Einstellungen → Plugins"
  }
```

- [ ] **Step 3: Commit**

```bash
git add client/src/i18n/locales/en/dashboard.json client/src/i18n/locales/de/dashboard.json
git commit -m "feat(i18n): add Dashboard plugin panel translations (en/de)"
```

---

## Task 13: Frontend — Replace PowerWidget in Dashboard

**Files:**
- Modify: `client/src/pages/Dashboard.tsx:1-771`
- Delete: `client/src/components/PowerWidget.tsx`
- Delete: `client/src/hooks/usePowerMonitoring.ts`

- [ ] **Step 1: Update Dashboard.tsx imports**

Replace the import:
```tsx
import PowerWidget from '../components/PowerWidget';
```

With:
```tsx
import { PluginDashboardPanel } from '../components/dashboard';
```

(Add `PluginDashboardPanel` to the existing dashboard import if it's already grouped there, or add as a separate import.)

- [ ] **Step 2: Replace PowerWidget usage**

In `Dashboard.tsx`, find (line ~479):
```tsx
            {/* Power Monitoring Widget */}
            <PowerWidget />
```

Replace with:
```tsx
            {/* Plugin Dashboard Panel */}
            <PluginDashboardPanel />
```

- [ ] **Step 3: Delete old files**

Delete:
- `client/src/components/PowerWidget.tsx`
- `client/src/hooks/usePowerMonitoring.ts`

- [ ] **Step 4: Verify build**

Run: `cd client && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 5: Commit**

```bash
git add client/src/pages/Dashboard.tsx
git rm client/src/components/PowerWidget.tsx client/src/hooks/usePowerMonitoring.ts
git commit -m "feat(dashboard): replace PowerWidget with PluginDashboardPanel"
```

---

## Task 14: Update PluginDetailResponse with Dashboard Panel Fields

**Files:**
- Modify: `backend/app/schemas/plugin.py:78-114`
- Modify: `backend/app/api/routes/plugins.py:108-173`
- Test: `backend/tests/plugins/test_dashboard_panel.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/plugins/test_dashboard_panel.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py::TestPluginDetailResponsePanelFields -v`
Expected: FAIL — fields don't exist on PluginDetailResponse

- [ ] **Step 3: Add fields to PluginDetailResponse**

In `backend/app/schemas/plugin.py`, add to `PluginDetailResponse`:

```python
    has_dashboard_panel: bool = False
    dashboard_panel_enabled: bool = False
```

- [ ] **Step 4: Populate in get_plugin_details route**

In `backend/app/api/routes/plugins.py`, in the `get_plugin_details` function, update the return `PluginDetailResponse(...)` to include:

```python
        has_dashboard_panel=plugin.get_dashboard_panel() is not None,
        dashboard_panel_enabled=db_record.dashboard_panel_enabled if db_record else False,
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py::TestPluginDetailResponsePanelFields -v`
Expected: Both tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/plugin.py backend/app/api/routes/plugins.py backend/tests/plugins/test_dashboard_panel.py
git commit -m "feat(api): expose has_dashboard_panel and dashboard_panel_enabled in plugin details"
```

---

## Task 15: Run Full Test Suite

- [ ] **Step 1: Run backend tests**

Run: `cd backend && python -m pytest tests/plugins/test_dashboard_panel.py -v`
Expected: All tests PASS

- [ ] **Step 2: Run existing test suite (smoke check)**

Run: `cd backend && python -m pytest --timeout=30 -x -q`
Expected: No regressions in existing tests

- [ ] **Step 3: Run frontend build**

Run: `cd client && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address any issues found during full test run"
```
