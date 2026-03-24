# BaluHost Plugin System

Das Plugin-System ermöglicht es, BaluHost modular zu erweitern — mit eigenen API-Routen, Background-Tasks, Event-Handlern, Dashboard-Panels und Frontend-UI.

## Architektur-Übersicht

```
plugins/
├── __init__.py              # Public API (re-exports)
├── base.py                  # PluginBase ABC + Datenmodelle
├── manager.py               # PluginManager (Discovery, Lifecycle, Routing)
├── hooks.py                 # Pluggy Hook-Specs (on_file_uploaded, on_user_login, …)
├── events.py                # Async EventManager (Queue-basiert, non-blocking)
├── emit.py                  # Helper: emit_hook() / emit_event() für Services
├── permissions.py           # Granulares Permission-System mit Dangerous-Flags
├── dashboard_panel.py       # Dashboard-Panel-Schemas (Gauge, Stat, Status, Chart)
├── smart_device/            # Smart-Device-Subsystem (Basisklasse + Manager + Poller)
│   ├── base.py              # SmartDevicePlugin ABC (erweitert PluginBase)
│   ├── capabilities.py      # Capability-Enums + Protocols (Switch, Dimmer, Color, …)
│   ├── manager.py           # SmartDeviceManager (CRUD, Command-Dispatch, SHM-State)
│   ├── poller.py            # SmartDevicePoller (läuft im Monitoring-Worker-Prozess)
│   └── schemas.py           # Pydantic Request/Response-Schemas
└── installed/               # Installierte Plugins (je ein Unterverzeichnis)
    ├── optical_drive/       # CD/DVD/Blu-ray lesen, rippen, brennen
    ├── storage_analytics/   # Storage-Nutzungsanalysen
    └── tapo_smart_plug/     # TP-Link Tapo P110/P115 Smart-Plug-Steuerung
```

## Plugin-Lifecycle

1. **Discovery** — `PluginManager.discover_plugins()` scannt `installed/` nach Verzeichnissen mit `__init__.py`
2. **Loading** — `load_plugin()` importiert das Modul und findet die `PluginBase`-Subklasse
3. **Permission-Check** — `PermissionManager.validate_permissions()` prüft ob alle benötigten Rechte gewährt sind
4. **Activation** — `on_startup()` wird aufgerufen, Pluggy-Hooks und Event-Handler werden registriert
5. **Running** — Routen sind unter `/api/plugins/{name}/` gemountet, Background-Tasks laufen
6. **Deactivation** — `on_shutdown()` wird aufgerufen, Tasks gestoppt, Handler deregistriert

Enabled/Disabled-Status wird in der DB-Tabelle `installed_plugins` gespeichert. Beim App-Start lädt `load_enabled_plugins()` alle aktivierten Plugins automatisch.

## Ein Plugin erstellen

### Minimales Plugin

Neues Verzeichnis unter `installed/` mit `__init__.py`:

```python
# installed/my_plugin/__init__.py
from app.plugins.base import PluginBase, PluginMetadata

class MyPlugin(PluginBase):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my_plugin",               # Muss dem Verzeichnisnamen entsprechen
            version="1.0.0",
            display_name="My Plugin",
            description="Does something useful",
            author="Your Name",
            category="general",             # general | monitoring | storage | network | security | smart_device
            required_permissions=["system:info"],
        )
```

### Mit API-Routen

```python
from fastapi import APIRouter, Depends
from app.api.deps import get_current_user

class MyPlugin(PluginBase):
    # ... metadata ...

    def get_router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/status")
        async def get_status(current_user=Depends(get_current_user)):
            return {"status": "ok"}

        return router
    # Routen werden unter /api/plugins/my_plugin/status erreichbar
```

### Mit Background-Tasks

```python
from app.plugins.base import BackgroundTaskSpec

class MyPlugin(PluginBase):
    # ... metadata ...

    def get_background_tasks(self) -> list[BackgroundTaskSpec]:
        async def check_something():
            pass  # Wird alle 60s aufgerufen

        return [
            BackgroundTaskSpec(
                name="checker",
                func=check_something,
                interval_seconds=60,
                run_on_startup=True,
            )
        ]
```

### Mit Pluggy-Hooks

Plugins können auf System-Events reagieren, indem sie Hook-Methoden aus `BaluHostHookSpec` implementieren:

```python
from app.plugins.hooks import hookimpl

class MyPlugin(PluginBase):
    # ... metadata ...

    @hookimpl
    def on_file_uploaded(self, path: str, user_id: int, size: int, content_type=None):
        print(f"File uploaded: {path}")

    @hookimpl
    def on_user_login(self, user_id: int, username: str, ip: str, user_agent=None):
        print(f"User {username} logged in")
```

Verfügbare Hooks (definiert in `hooks.py`):

| Kategorie | Hooks |
|-----------|-------|
| **Dateien** | `on_file_uploaded`, `on_file_deleted`, `on_file_moved`, `on_file_downloaded` |
| **Benutzer** | `on_user_login`, `on_user_logout`, `on_user_created`, `on_user_deleted` |
| **Backup** | `on_backup_started`, `on_backup_completed` |
| **Shares** | `on_share_created`, `on_share_accessed` |
| **System** | `on_system_startup`, `on_system_shutdown`, `on_storage_threshold` |
| **RAID** | `on_raid_degraded`, `on_raid_rebuild_started`, `on_raid_rebuild_completed` |
| **SMART** | `on_disk_health_warning` |
| **Geräte** | `on_device_registered`, `on_device_removed` |
| **Smart Devices** | `on_smart_device_state_changed`, `on_smart_device_added`, `on_smart_device_removed` |
| **VPN** | `on_vpn_client_created`, `on_vpn_client_revoked` |

### Mit Async Events

Zusätzlich zu Pluggy-Hooks gibt es ein async Event-System für lose Kopplung:

```python
class MyPlugin(PluginBase):
    # ... metadata ...

    def get_event_handlers(self) -> dict[str, list]:
        async def handle_custom_event(event):
            print(f"Event: {event.name}, Data: {event.data}")

        return {
            "my_custom_event": [handle_custom_event],
            "*": [handle_custom_event],  # Wildcard: alle Events
        }
```

Events von Services emittieren:

```python
from app.plugins.emit import emit_hook, emit_event

# Pluggy-Hook (synchron, fire-and-forget)
emit_hook("on_file_uploaded", path="/test.txt", user_id=1, size=100)

# Async Event (Queue-basiert)
await emit_event("my_custom_event", {"key": "value"}, source="my_service")
```

### Mit Dashboard-Panel

Plugins können ein Panel auf dem Dashboard beanspruchen:

```python
from app.plugins.base import DashboardPanelSpec

class MyPlugin(PluginBase):
    # ... metadata ...

    def get_dashboard_panel(self) -> DashboardPanelSpec:
        return DashboardPanelSpec(
            panel_type="gauge",   # gauge | stat | status | chart
            title="My Metric",
            icon="activity",      # Lucide-Icon
            accent="from-sky-500 to-indigo-500",  # Tailwind-Gradient
        )

    async def get_dashboard_data(self, db) -> dict:
        # Muss zum panel_type passen (siehe dashboard_panel.py)
        return {
            "value": "42 W",
            "meta": "1 device monitored",
            "progress": 28.0,
            "delta_tone": "live",
        }
```

Panel-Typen und ihre Daten-Schemas (`dashboard_panel.py`):

| Type | Schema | Beschreibung |
|------|--------|-------------|
| `gauge` | `GaugePanelData` | Wert + Fortschrittsbalken + Trend |
| `stat` | `StatPanelData` | Einfacher Wert + Meta-Text |
| `status` | `StatusPanelData` | Liste von Status-Items (label/value/tone) |
| `chart` | `ChartPanelData` | Wert + Sparkline (~30 Datenpunkte) |

### Mit Frontend-UI

```python
from app.plugins.base import PluginUIManifest, PluginNavItem

class MyPlugin(PluginBase):
    # ... metadata ...

    def get_ui_manifest(self) -> PluginUIManifest:
        return PluginUIManifest(
            enabled=True,
            nav_items=[
                PluginNavItem(
                    path="overview",
                    label="My Plugin",
                    icon="plug",          # Lucide-Icon
                    admin_only=False,
                    order=50,
                )
            ],
            bundle_path="ui/bundle.js",     # Relativ zum Plugin-Verzeichnis
            styles_path="ui/styles.css",    # Optional
            dashboard_widgets=["MyWidget"],
        )
```

### Mit i18n/Übersetzungen

```python
class MyPlugin(PluginBase):
    # ... metadata ...

    def get_translations(self) -> dict[str, dict[str, str]]:
        return {
            "en": {"display_name": "My Plugin", "description": "..."},
            "de": {"display_name": "Mein Plugin", "description": "..."},
        }
```

## Permission-System

Plugins deklarieren benötigte Permissions in `metadata.required_permissions`. Admins müssen diese beim Aktivieren gewähren.

| Permission | Beschreibung | Dangerous |
|------------|-------------|-----------|
| `file:read` | Dateien lesen | Nein |
| `file:write` | Dateien schreiben | **Ja** |
| `file:delete` | Dateien löschen | **Ja** |
| `system:info` | System-Metriken lesen | Nein |
| `system:execute` | Shell-Befehle ausführen | **Ja** |
| `network:outbound` | Ausgehende HTTP-Requests | Nein |
| `db:read` | Datenbank lesen | Nein |
| `db:write` | Datenbank schreiben | **Ja** |
| `user:read` | Benutzer-Infos lesen | Nein |
| `user:write` | Benutzer-Daten ändern | **Ja** |
| `notification:send` | Push-Benachrichtigungen senden | Nein |
| `task:background` | Background-Tasks ausführen | Nein |
| `event:subscribe` | System-Events abonnieren | Nein |
| `event:emit` | Eigene Events emittieren | Nein |
| `device:control` | Smart-Devices steuern | Nein |

Dangerous Permissions erfordern explizite Admin-Bestätigung.

## Smart-Device-Plugins

Für IoT-/Smart-Home-Geräte gibt es eine spezialisierte Basisklasse `SmartDevicePlugin`, die `PluginBase` erweitert:

```python
from app.plugins.smart_device.base import SmartDevicePlugin, DeviceTypeInfo
from app.plugins.smart_device.capabilities import DeviceCapability

class MyDevicePlugin(SmartDevicePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my_device",
            # ...
            category="smart_device",  # Pflicht für Smart-Device-Plugins
        )

    def get_device_types(self) -> list[DeviceTypeInfo]:
        return [DeviceTypeInfo(
            type_id="my_device_v1",
            display_name="My Device V1",
            manufacturer="Acme",
            capabilities=[DeviceCapability.SWITCH, DeviceCapability.POWER_MONITOR],
            config_schema={"type": "object", "properties": {"api_key": {"type": "string"}}},
        )]

    async def connect_device(self, device_id: str, config: dict) -> bool:
        # Verbindung aufbauen
        return True

    async def poll_device(self, device_id: str) -> dict:
        # Aktuellen Status abfragen
        return {"switch": SwitchState(is_on=True)}

    async def poll_device_mock(self, device_id: str) -> dict:
        # Mock-Daten für Dev-Mode (Windows-kompatibel)
        return {"switch": SwitchState(is_on=True)}
```

Verfügbare Capabilities:

| Capability | Protocol | Methoden |
|------------|----------|----------|
| `switch` | `Switch` | `turn_on()`, `turn_off()`, `get_switch_state()` |
| `power_monitor` | `PowerMonitor` | `get_power()` |
| `sensor` | `Sensor` | `get_readings()` |
| `dimmer` | `Dimmer` | `set_brightness()`, `get_dimmer_state()` |
| `color` | `ColorControl` | `set_color()`, `set_color_temp()`, `get_color_state()` |

### Capability-Verträge

Capabilities sind **Verträge**, nicht nur Labels. Wenn ein Plugin eine Capability deklariert, muss es:

1. **Das zugehörige Protocol implementieren** — geprüft beim Plugin-Start (sowohl im Web-Worker als auch im Monitoring-Worker)
2. **Das zugehörige Datenmodell von `poll_device()` zurückgeben** — geprüft bei jedem Poll-Zyklus zur Laufzeit

Dafür bekommt das Plugin automatisch: Mobile-App-Integration (BaluApp), Dashboard-Panel, Energie-Statistiken und Kostenberechnung.

| Capability | Protocol | Datenmodell | `poll_device()` Key |
|------------|----------|-------------|---------------------|
| `switch` | `Switch` | `SwitchState` | `"switch"` |
| `power_monitor` | `PowerMonitor` | `PowerReading` | `"power_monitor"` |
| `sensor` | `Sensor` | `SensorReading` | `"sensor"` |
| `dimmer` | `Dimmer` | `DimmerState` | `"dimmer"` |
| `color` | `ColorControl` | `ColorState` | `"color"` |

**Wichtig:** Stromverbrauchsdaten (und alle anderen Capability-Daten) müssen über die zentrale Pipeline fließen:

```
poll_device() → Poller → SHM → Energy-Service → Mobile API
```

Plugin-eigene API-Routen dürfen **keine** Capability-Daten in einem anderen Format exponieren. Die zentrale Pipeline ist der einzige Weg, damit die Mobile App und das Dashboard konsistente Daten erhalten.

**Validierungs-Verhalten:**

- **Startup:** Plugin wird nicht geladen, wenn ein deklariertes Protocol nicht implementiert ist
- **Runtime:** Ungültige Daten werden verworfen (Warning im Log), gültige Daten fließen normal weiter
- **Leere Rückgabe:** `poll_device()` darf `{}` zurückgeben (keine Daten in diesem Zyklus)
- **Partielle Rückgabe:** Nicht alle deklarierten Capabilities müssen in jedem Poll enthalten sein
- **Extra Keys:** Keys die nicht in den deklarierten Capabilities sind werden ignoriert (Warning im Log)

Smart-Device-Plugins haben **keine eigenen Routen** — alle Interaktion läuft über die einheitliche `/api/smart-devices/` API. Der `SmartDevicePoller` läuft im separaten Monitoring-Worker-Prozess und pollt alle aktiven Geräte periodisch. Status wird per SHM (Shared Memory Files) an den Web-Worker kommuniziert.

## Mitgelieferte Plugins

BaluHost wird mit folgenden Standard-Plugins ausgeliefert, die als Referenz-Implementierungen dienen und sofort einsatzbereit sind:

| Plugin | Kategorie | Beschreibung |
|--------|-----------|-------------|
| `optical_drive` | storage | CD/DVD/Blu-ray: Lesen, Rippen (ISO/WAV), Brennen, Blanken |
| `storage_analytics` | storage | Storage-Nutzungsanalysen pro User, Dateityp-Verteilung, Top-Files |
| `tapo_smart_plug` | smart_device | TP-Link Tapo P110/P115 mit Switch + Power Monitoring |

Diese Plugins liegen unter `installed/` und zeigen die verschiedenen Muster des Plugin-Systems:
- **optical_drive** — Eigene API-Routen, UI-Manifest, Config-Schema, async Job-Management
- **storage_analytics** — Background-Tasks, Pluggy-Hook-Implementierungen (`@hookimpl`), periodische Scans
- **tapo_smart_plug** — SmartDevicePlugin-Subklasse, Capability-Protocols, Dashboard-Panel, i18n, Dev/Prod-Mode-Trennung

## Zwei Event-Systeme

| | Pluggy Hooks | Async Events |
|---|---|---|
| **Aufruf** | `emit_hook("on_file_uploaded", ...)` | `await emit_event("custom", {...})` |
| **Ausführung** | Synchron, im selben Thread | Async, Queue-basiert |
| **Subscriber** | Klasse implementiert Hook-Methode mit `@hookimpl` | Beliebige async-Funktion per `get_event_handlers()` |
| **Wildcard** | Nein | Ja (`"*"` empfängt alle Events) |
| **Anwendung** | System-Events mit festem Vertrag | Lose Kopplung, Plugin-zu-Plugin |
