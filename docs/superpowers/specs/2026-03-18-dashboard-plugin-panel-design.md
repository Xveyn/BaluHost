# Dashboard Plugin Panel System

**Date:** 2026-03-18
**Status:** Draft
**Branch:** `feat/smart-device-plugins`

## Problem

The Dashboard PowerWidget is hardcoded to the legacy Tapo power monitoring system (`/api/tapo/power/history`). New smart device plugins with `POWER_MONITOR` capability (or any other data-providing plugin) cannot contribute to the Dashboard. The recently rebuilt Tapo smart plug plugin (`tapo_smart_plug`) already has power data available through the Smart Device Plugin system but cannot surface it on the Dashboard.

## Solution

A generic **Dashboard Plugin Panel** system that allows any plugin to claim a single Dashboard slot and render structured data using a predefined panel-type library. Data flows via REST (initial load/fallback) and WebSocket (live updates).

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Panel rendering | Panel-type library (`gauge`, `stat`, `status`, `chart`) | Consistent with BaluHost design system, flexible enough for most plugins |
| Configuration | Toggle in Plugin Settings | Minimal new UI, fits existing Plugin management UX |
| Empty state | Placeholder with link to Settings | Guides admin to configure a plugin |
| Slot count | One plugin slot (for now) | Simple, extendable to multiple later |
| Data transport | REST + WebSocket push | REST for initial load/fallback, WS for real-time updates. Matches SmartDevicesPage pattern |
| Conflict resolution | Last activation wins | Admin enables Plugin B's panel -> Plugin A's panel auto-deactivates. No error dialogs. |
| Data method | Python method call (not HTTP) | Plugin implements `get_dashboard_data(db)` directly; avoids internal HTTP round-trip and SSRF risk |
| Supersedes `dashboard_widgets` | Yes | Existing `PluginUIManifest.dashboard_widgets` field is unused and unimplemented; the new `get_dashboard_panel()` system replaces it |
| Plugin disable behavior | Panel hidden, flag preserved | When an admin disables a plugin entirely, `dashboard_panel_enabled` stays `True` in DB but the panel is hidden (plugin not loaded). On re-enable, the panel reappears automatically. |

## Architecture

### Backend

#### 1. New Method on `PluginBase`

```python
# backend/app/plugins/base.py

from typing import Literal

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

class PluginBase(ABC):
    # ... existing methods ...

    def get_dashboard_panel(self) -> Optional[DashboardPanelSpec]:
        """Override to claim the Dashboard plugin slot.

        Returns:
            DashboardPanelSpec or None if this plugin has no Dashboard panel.
        """
        return None

    async def get_dashboard_data(self, db: Session) -> Optional[dict]:
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

Note: The previous `data_endpoint: str` design (internal HTTP call) is replaced by `get_dashboard_data(db)` — a direct Python method call. This avoids internal HTTP round-trips, removes an SSRF vector from plugin-controlled URL strings, and follows the existing pattern where plugin logic lives in Python methods.

#### 2. Panel Data Schemas

```python
# backend/app/plugins/dashboard_panel.py
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
    value: str              # "120.5 W"
    meta: str               # "3 devices monitored"
    submeta: Optional[str] = None  # "Energy today: 2.45 kWh"
    progress: float         # 0-100
    delta: Optional[str] = None    # "+2.3W"
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

    ``points`` should contain the most recent 30 data points
    representing the last ~2.5 minutes at a 5-second poll interval.
    The frontend renders them as a sparkline with no explicit x-axis.
    """
    value: str
    meta: str
    points: List[float] = Field(
        ...,
        description="Sparkline data points (last ~30 values, newest last)",
    )
```

#### 3. Database: New Column on `InstalledPlugin`

```python
# Alembic migration — uses Mapped[] style consistent with existing model
dashboard_panel_enabled: Mapped[bool] = mapped_column(
    Boolean, nullable=False, default=False, server_default="0"
)
```

When a plugin with `get_dashboard_panel() != None` is enabled, the admin can toggle `dashboard_panel_enabled` in Plugin Settings. When activated, any other plugin's `dashboard_panel_enabled` is set to `False` (single-slot constraint).

#### 4. New API Endpoint

```
GET /api/dashboard/plugin-panel
```

Auth: `Depends(get_current_user)` (all authenticated users can see the Dashboard).
Rate limiting: `@limiter.limit(get_limit("default"))`.

Response (200):
```json
{
  "plugin_name": "tapo_smart_plug",
  "panel_type": "gauge",
  "title": "Power Monitoring",
  "icon": "zap",
  "accent": "from-amber-500 to-orange-500",
  "data": {
    "value": "120.5 W",
    "meta": "3 devices monitored",
    "submeta": "Energy today: 2.45 kWh",
    "progress": 80.3,
    "delta": "+2.3W",
    "delta_tone": "increase"
  }
}
```

Response when no plugin is active (200):
```json
null
```

Logic:
1. Find the plugin with `dashboard_panel_enabled = True` and plugin loaded
2. Call `get_dashboard_panel()` for the spec
3. Call `get_dashboard_data(db)` on the plugin instance for current data
4. Merge spec + data into response

#### 5. Toggle Endpoint & Conflict Resolution

```
POST /api/plugins/{name}/dashboard-panel
Body: {"enabled": true}
```

Auth: `Depends(get_current_admin)`.
Rate limiting: `@limiter.limit(get_limit("admin_operations"))`.
Audit logging: logs `PLUGIN` / `toggle_dashboard_panel` via `AuditLoggerDB`.

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
            InstalledPlugin.dashboard_panel_enabled == True,
        ).update({"dashboard_panel_enabled": False})

    # Set the target plugin
    db.query(InstalledPlugin).filter(
        InstalledPlugin.name == plugin_name,
    ).update({"dashboard_panel_enabled": enabled})

    db.commit()
```

#### 6. WebSocket Push

##### Message Format

The existing `WebSocketManager.broadcast_to_all()` wraps all messages as `{"type": "notification", "payload": message}`. To support custom message types (including the existing `smart_device_update`), a new method is added:

```python
# backend/app/services/websocket_manager.py

async def broadcast_typed(self, msg_type: str, payload: dict[str, Any]) -> int:
    """Broadcast a typed message to all connected users.

    Unlike broadcast_to_all() which wraps in {"type": "notification"},
    this method sends {"type": msg_type, "payload": payload} directly.
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
            for conn in disconnected:
                if conn in connections:
                    connections.remove(conn)
            if not connections and user_id in self._user_connections:
                del self._user_connections[user_id]
                self._admin_users.discard(user_id)
    return sent_count
```

##### Dashboard Panel Update Message

```json
{
  "type": "dashboard_panel_update",
  "payload": {
    "panel_type": "gauge",
    "plugin_name": "tapo_smart_plug",
    "data": {
      "value": "120.5 W",
      "meta": "3 devices monitored",
      "submeta": "Energy today: 2.45 kWh",
      "progress": 80.3,
      "delta": "+2.3W",
      "delta_tone": "increase"
    }
  }
}
```

##### SHM-to-WebSocket Bridge

The `SmartDevicePoller` runs in a separate OS process (MonitoringWorker) and cannot call `WebSocketManager` directly. It writes state changes to `smart_devices_changes.json` in SHM.

A new **bridge task** in the web worker process reads the SHM changes file and broadcasts via WebSocket:

```python
# backend/app/services/dashboard_panel_bridge.py

async def dashboard_panel_ws_bridge() -> None:
    """Background task in the web worker that bridges SHM -> WebSocket.

    Runs every 3 seconds:
    1. Read smart_devices_changes.json from SHM to detect any changes
    2. If changes detected for the active dashboard plugin, call
       get_dashboard_data(db) for full current state (not deltas)
    3. Broadcast dashboard_panel_update via WebSocketManager.broadcast_typed()

    Creates its own SessionLocal() per cycle for the get_dashboard_data(db)
    call, following the same pattern as other background tasks.

    Note: The SHM changes file is overwritten (not appended) by the poller,
    so intermediate change batches may be missed. This is acceptable because
    the bridge calls get_dashboard_data() for full state — it only needs to
    know THAT something changed, not WHAT changed.

    Started during FastAPI lifespan alongside existing background tasks.
    """
```

This follows the same SHM-read pattern used by existing telemetry REST endpoints. The bridge task is started in the FastAPI lifespan events and stopped on shutdown.

Non-SmartDevice plugins that have their own background tasks can call `WebSocketManager.broadcast_typed("dashboard_panel_update", ...)` directly from the web worker process.

### Frontend

#### 1. New Component: `PluginDashboardPanel`

Replaces the hardcoded `<PowerWidget />` in `Dashboard.tsx`.

```
Dashboard.tsx grid:
  CPU | Memory | Storage | Uptime
  PluginDashboardPanel | Network | Services | Plugins
```

Logic:
1. On mount: `GET /api/dashboard/plugin-panel`
2. If `null` -> render `<PanelPlaceholder />`
3. If data -> select renderer by `panel_type`
4. Subscribe to WS `dashboard_panel_update` -> merge into state
5. Fallback: if WS disconnects, poll REST every 10s (intentionally slower than the 5s poll of the old PowerWidget since WS is the primary transport)

#### 2. Panel Renderers

Four components, all following the existing Dashboard card design (same height, spacing, Tailwind classes as CPU/Memory/Storage cards):

- **`GaugePanel`** -- Value, meta, submeta, delta badge, progress bar. Visually identical to current PowerWidget but driven by generic data.
- **`StatPanel`** -- Large value + meta text. No progress bar.
- **`StatusPanel`** -- List of items with colored status dots (emerald/amber/rose).
- **`ChartPanel`** -- Value + mini sparkline using Recharts (already a project dependency). Renders ~30 data points as an area chart.

All renderers receive `icon`, `accent`, and `title` from the `DashboardPanelSpec` so each plugin can customize its appearance within the design system.

#### 3. Placeholder

When no plugin has claimed the slot:

```tsx
<PanelPlaceholder />
// Shows: muted card with "No plugin configured"
// For admins: link to /settings -> Plugins
// For regular users: just the muted card (no link, as they cannot configure plugins)
```

#### 4. Internationalization

Panel titles from `DashboardPanelSpec` are backend-provided strings (not i18n keys). The placeholder text and any Chrome around the panel (e.g., "No plugin configured") must use i18n keys added to `client/src/i18n/locales/{en,de}/dashboard.json`.

#### 5. Files Removed

- `client/src/components/PowerWidget.tsx` -- replaced by `PluginDashboardPanel`
- `client/src/hooks/usePowerMonitoring.ts` -- no longer needed (verified: no other consumers; `client/src/api/power.ts` stays since it is used by the Energy page)
- Import in `Dashboard.tsx` updated

### Tapo Plugin Integration

The `TapoSmartPlugPlugin` gets:

#### `get_dashboard_panel()`

```python
def get_dashboard_panel(self) -> Optional[DashboardPanelSpec]:
    return DashboardPanelSpec(
        panel_type="gauge",
        title="Power Monitoring",
        icon="zap",
        accent="from-amber-500 to-orange-500",
    )
```

#### `get_dashboard_data(db)`

```python
async def get_dashboard_data(self, db: Session) -> Optional[dict]:
    """Aggregate power data from the Smart Device system (SHM/DB).

    Returns GaugePanelData-compatible dict:
    - value: total watts across all online power-monitoring devices
    - meta: "X devices monitored"
    - submeta: "Energy today: X.XX kWh"
    - progress: percentage of assumed max power (default 150W)
    - delta + delta_tone: trend from recent samples
    """
```

This replaces the data previously served by `usePowerMonitoring` -> `/api/tapo/power/history`.

## What Is NOT Built

- Multiple plugin slots (future: `dashboard_panel_enabled` -> `dashboard_slot: Optional[str]`)
- Drag & drop Dashboard layout
- Custom JS bundles for panels
- Changes to `/api/tapo/power/history` (still used by Energy page)
- Changes to SmartDevicesPage

## Migration Path

1. Alembic migration adds `dashboard_panel_enabled` column
2. Add `broadcast_typed()` to `WebSocketManager`
3. Add `get_dashboard_panel()` and `get_dashboard_data()` to `PluginBase`
4. Create panel data schemas (`dashboard_panel.py`)
5. Create `GET /api/dashboard/plugin-panel` endpoint
6. Create `POST /api/plugins/{name}/dashboard-panel` toggle endpoint with audit logging
7. Create SHM-to-WS bridge background task (`dashboard_panel_bridge.py`)
8. Tapo Plugin implements `get_dashboard_panel()` + `get_dashboard_data()`
9. Frontend: create `PluginDashboardPanel` + 4 renderers + placeholder
10. Frontend: replace `<PowerWidget />` with `<PluginDashboardPanel />` in Dashboard
11. Remove `PowerWidget.tsx` and `usePowerMonitoring.ts`
12. Admins enable "Dashboard Panel" in Tapo Plugin settings to activate

## Future Extensibility

- **Multiple slots:** Change `dashboard_panel_enabled: bool` to `dashboard_slot: Optional[str]` (e.g., `"slot_1"`, `"slot_2"`). Frontend renders multiple `PluginDashboardPanel` components.
- **New panel types:** Add new data schema + renderer component. Plugins can use them immediately.
- **Non-SmartDevice plugins:** Any plugin (e.g., PiHole) can implement `get_dashboard_panel()` and push updates via `WebSocketManager.broadcast_typed()`.
- **Deprecate `PluginUIManifest.dashboard_widgets`:** The existing `dashboard_widgets: List[str]` field on `PluginUIManifest` is unused and superseded by this system. It can be removed in a future cleanup.
