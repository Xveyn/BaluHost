# Smart Home Device Plugin/Integration System - Research & Best Practices

## 1. Home Assistant Integration Architecture

Home Assistant is the gold standard for smart home device integrations. Its architecture is Python-based and highly relevant to BaluHost.

### 1.1 Integration Structure

Every integration lives in its own directory and contains a **`manifest.json`** file declaring:
- **domain** - unique short name (e.g., `tapo`, `hue`, `shelly`)
- **name** - human-readable display name
- **version** - semver version string
- **integration_type** - the main focus (device, service, hub, etc.)
- **iot_class** - communication method: `local_polling`, `local_push`, `cloud_polling`, `cloud_push`, `assumed_state`, `calculated`
- **dependencies** - other integrations that must load first
- **after_dependencies** - optional integrations to load before this one if present
- **requirements** - Python pip packages the integration needs (auto-installed)
- **codeowners** - GitHub usernames responsible for maintenance
- **config_flow** - boolean: whether UI-based setup is supported
- **documentation** - URL to docs
- **loggers** - Python logger names the integration uses
- **quality_scale** - integration quality tier

### 1.2 Config Flow (UI-Based Setup)

Config flows provide a step-by-step wizard for setting up integrations via the UI. Key concepts:

- **Steps**: Each step is a method like `async_step_user()`, `async_step_zeroconf()`, etc.
- **Forms**: `self.async_show_form(step_id="user", data_schema=vol.Schema({...}))` renders a form
- **Schema**: Uses **Voluptuous** library for schema definitions (similar to Pydantic but for form data)
- **Discovery steps**: When a device is discovered via mDNS/SSDP, the corresponding step (e.g., `async_step_zeroconf`) is invoked automatically with discovery info
- **Validation**: Each step validates input, can show errors, and transitions to the next step
- **Result**: Final step calls `self.async_create_entry(title=..., data=...)` which creates a **ConfigEntry**

**Relevance to BaluHost**: This pattern maps directly to a multi-step device setup wizard. BaluHost could implement something similar with Pydantic schemas instead of Voluptuous.

### 1.3 Entity Model & Platform Architecture

The Entity Platform System is HA's core abstraction for standardizing device interactions:

- **Entity**: The fundamental abstraction. Each entity has:
  - `entity_id` in format `<domain>.<object_id>` (e.g., `switch.kitchen_outlet`)
  - `unique_id` for persistent identification across reboots
  - `device_info` linking it to a physical device
  - State + attributes (standardized per domain)
  - Properties set via `_attr_` prefixed class attributes or `EntityDescription` dataclass

- **Entity Domains** (capability categories):
  - **Read-only**: `sensor`, `binary_sensor`, `camera`, `image`
  - **Controllable**: `switch`, `light`, `climate`, `cover`, `fan`, `media_player`, `number`, `select`, `humidifier`, `valve`, `lock`, `siren`, `vacuum`
  - Each domain defines a base class with standardized properties and service calls

- **EntityDescription**: A dataclass pattern for declaratively describing entity metadata (name, icon, device_class, unit, etc.) without subclassing

- **CoordinatorEntity**: A mixin that integrates with DataUpdateCoordinator for automatic state updates

### 1.4 Device Registry

The Device Registry tracks physical devices:

- **Identifiers**: Tuples of `(domain, unique_id)` - e.g., `("tapo", "AA:BB:CC:DD:EE:FF")`
- **Connections**: MAC addresses, serial numbers, etc. used to match devices
- **Hierarchy**: Devices can have parent-child relationships (e.g., power strip -> individual outlets)
- **Device Info**: manufacturer, model, sw_version, hw_version, suggested_area
- Entities link to devices via `device_info` property; multiple entities can belong to one device

### 1.5 DataUpdateCoordinator (Data Fetching)

Two paradigms, unified by one coordinator pattern:

- **Polling**: Pass `update_method` and `update_interval` to constructor. Coordinator calls the method periodically and notifies all entities.
- **Push**: Don't pass polling params. Call `coordinator.async_set_updated_data(data)` when new data arrives via callback/websocket.
- **Hybrid**: Some integrations use both - polling as fallback, push for real-time.

This is the recommended pattern because it ensures a single coordinated API call across all entities of an integration.

---

## 2. OpenHAB Binding Architecture

OpenHAB uses a Java/OSGi-based architecture. While the technology differs, the conceptual model is instructive.

### 2.1 Core Concepts (Thing / Channel / Item)

- **Thing**: Represents a physical device or external service. Has a ThingType defined in XML.
- **Bridge**: A special Thing that acts as a gateway/hub for other Things (e.g., a Hue Bridge).
- **Channel**: Represents a specific capability of a Thing (e.g., brightness, temperature, on/off state). Has a ChannelType defined in XML.
- **Item**: The user-facing abstraction linked to a Channel. Items have types: `Switch`, `Dimmer`, `Number`, `String`, `Color`, `Contact`, `DateTime`, `Location`, `Player`, `Rollershutter`, `Image`.
- **Link**: Connects a Channel to an Item, enabling data flow.

### 2.2 Binding Structure

- **ThingHandlerFactory** (OSGi service): Creates ThingHandler instances for specific ThingTypes
- **ThingHandler**: Implements communication with the actual device. Handles:
  - `initialize()` - connect to device
  - `handleCommand()` - process commands from the framework
  - `updateState()` - push state changes back to the framework
  - `dispose()` - cleanup
- **DiscoveryService** (OSGi service): Scans for devices and creates DiscoveryResults
- **XML Descriptors**: `thing-types.xml` and `channel-types.xml` declaratively define the device model

### 2.3 Key Takeaway

OpenHAB's strict separation of **Thing** (physical device), **Channel** (capability), and **Item** (user-facing state) is a clean three-layer abstraction. The XML descriptors serve as a machine-readable device manifest.

---

## 3. NAS Platforms and Smart Home

### 3.1 Current State

NAS platforms (Synology, TrueNAS, Unraid) do **not** natively implement smart home plugin systems. Instead, they:
- Run Home Assistant as a Docker container or VM
- Provide monitoring integrations (e.g., Unraid custom component for HA)
- Synology's DSM Package Center supports third-party packages but these are general-purpose apps, not smart-device-specific

### 3.2 Synology Package Architecture

Synology's approach to third-party extensions is relevant as a NAS plugin model:
- **INFO file**: Package metadata (name, version, dependencies, maintainer, architecture)
- **conf/ folder**: Dependency declarations (PKG_DEPS, PKG_CONX)
- **Lifecycle hooks**: install, upgrade, uninstall, start, stop scripts
- **Multi-language support**: C/C++, Java, Python, Perl, Node.js
- **Package Center**: Centralized distribution with verification process
- **Cross-platform**: Packages can target platform families

### 3.3 Opportunity for BaluHost

No NAS platform currently offers a native smart home device plugin system. BaluHost could differentiate by providing a lightweight, built-in smart device integration layer rather than requiring users to run a full Home Assistant instance. This is especially compelling for simple use cases (smart plugs for NAS power management, temperature sensors for fan control, etc.).

---

## 4. Device Discovery Protocols

### 4.1 mDNS / Zeroconf / Bonjour
- **Port**: UDP 5353, multicast 224.0.0.251
- **How it works**: Devices advertise services via DNS-SD (DNS Service Discovery) records on the local network
- **Use case**: Most modern smart home devices (ESPHome, Shelly, Apple HomeKit, Chromecast)
- **Python library**: `zeroconf` (pure Python, async-capable)
- **BaluHost already uses**: mDNS via `network_discovery.py` service

### 4.2 SSDP / UPnP
- **Port**: UDP 1900, multicast 239.255.255.250
- **How it works**: Devices send NOTIFY announcements and respond to M-SEARCH queries over HTTP-over-UDP
- **Use case**: Network devices, media servers, routers, some smart home devices
- **Python library**: `async_upnp_client`

### 4.3 Bluetooth / BLE
- **How it works**: BLE advertisement packets broadcast device presence
- **Use case**: Sensors, locks, some lights
- **Less relevant**: NAS devices typically lack Bluetooth hardware

### 4.4 Implementation Pattern

Home Assistant's approach is the best reference:
1. Integration declares supported discovery methods in `manifest.json` (e.g., `"zeroconf": [{"type": "_http._tcp.local.", "name": "shelly*"}]`)
2. Core discovery services (Zeroconf, SSDP, DHCP watchers) run continuously
3. When a matching device is found, the integration's discovery config flow step is triggered
4. User confirms/configures the discovered device via UI

---

## 5. Device Capability Abstractions

### 5.1 Common Capability Types

Based on Home Assistant and OpenHAB, the standard capability categories are:

| Capability | State Type | Commands | Examples |
|-----------|-----------|----------|----------|
| **Switch** | on/off (bool) | turn_on, turn_off, toggle | Smart plugs, relays |
| **Dimmer/Light** | brightness (0-255), color | turn_on(brightness), set_color | Smart bulbs, LED strips |
| **Sensor** | numeric/string (read-only) | none | Temperature, humidity, power meter |
| **Binary Sensor** | on/off (read-only) | none | Door sensors, motion detectors |
| **Climate** | temperature, mode, hvac_action | set_temperature, set_mode | Thermostats, AC units |
| **Cover** | position (0-100), state | open, close, set_position | Blinds, garage doors |
| **Fan** | speed, direction, oscillating | set_speed, turn_on/off | Fans |
| **Lock** | locked/unlocked | lock, unlock | Smart locks |
| **Media Player** | playing/paused, volume, source | play, pause, volume_set | Speakers, TVs |
| **Number** | numeric value | set_value | Any adjustable parameter |
| **Select** | string from options list | select_option | Mode selectors |

### 5.2 Device Classes (Sub-types)

Within each capability, **device_class** further categorizes the entity:
- Sensor: `temperature`, `humidity`, `power`, `energy`, `voltage`, `current`, `battery`, `pressure`, `illuminance`, `gas`, `co2`
- Binary Sensor: `motion`, `door`, `window`, `smoke`, `moisture`, `vibration`, `connectivity`
- Switch: `outlet`, `switch`
- Cover: `blind`, `garage`, `shutter`, `awning`

### 5.3 Units and State Classes

Each device_class implies default units and state classes:
- `temperature` -> `TEMP_CELSIUS` or `TEMP_FAHRENHEIT`, state_class `measurement`
- `energy` -> `kWh`, state_class `total_increasing`
- `power` -> `W`, state_class `measurement`

---

## 6. Plugin Manifest / Descriptor Patterns

### 6.1 Home Assistant Pattern (`manifest.json`)

```json
{
  "domain": "tapo",
  "name": "TP-Link Tapo",
  "version": "1.0.0",
  "integration_type": "device",
  "iot_class": "local_polling",
  "config_flow": true,
  "documentation": "https://...",
  "requirements": ["pytapo==3.0.0"],
  "dependencies": [],
  "codeowners": ["@user"],
  "zeroconf": [{"type": "_http._tcp.local."}],
  "ssdp": [],
  "dhcp": [{"macaddress": "1C:61:B4:*"}]
}
```

### 6.2 OpenHAB Pattern (`binding.xml` + `thing-types.xml`)

```xml
<!-- binding.xml -->
<binding:binding id="tapo">
  <name>TP-Link Tapo Binding</name>
  <description>Controls Tapo smart devices</description>
  <author>Developer Name</author>
</binding:binding>

<!-- thing-types.xml -->
<thing-type id="smartplug">
  <label>Tapo Smart Plug</label>
  <channels>
    <channel id="power" typeId="switch"/>
    <channel id="energy" typeId="energy-consumption"/>
  </channels>
  <config-description>
    <parameter name="hostname" type="text" required="true"/>
    <parameter name="pollingInterval" type="integer" min="5" max="300"/>
  </config-description>
</thing-type>
```

### 6.3 Recommended Pattern for BaluHost

A JSON/YAML manifest combining the best of both:

```json
{
  "plugin_id": "tapo",
  "name": "TP-Link Tapo",
  "version": "1.0.0",
  "author": "...",
  "description": "TP-Link Tapo smart plug integration",
  "min_baluhost_version": "1.17.0",
  "requirements": ["pytapo>=3.0.0"],
  "discovery": {
    "mdns": [{"type": "_http._tcp.local.", "name_prefix": "Tapo*"}],
    "ssdp": []
  },
  "devices": {
    "smart_plug": {
      "label": "Tapo Smart Plug",
      "capabilities": ["switch", "sensor.power", "sensor.energy"],
      "config_schema": {
        "host": {"type": "string", "required": true},
        "username": {"type": "string", "required": true},
        "password": {"type": "string", "required": true, "secret": true},
        "poll_interval": {"type": "integer", "default": 30, "min": 5, "max": 300}
      }
    }
  }
}
```

---

## 7. Event/State Change Notification Patterns

### 7.1 Polling
- Simple: periodically fetch device state
- HA uses DataUpdateCoordinator with configurable `update_interval`
- Best for: devices with no push capability (most cheap smart devices)

### 7.2 Push/Callback
- Device notifies the platform when state changes (via WebSocket, HTTP callback, event subscription)
- HA uses `coordinator.async_set_updated_data(data)` to push into the coordinator pattern
- Best for: devices with real-time APIs (Hue, Z-Wave, Zigbee hubs)

### 7.3 Hybrid
- Poll at long intervals as heartbeat/fallback, but accept push updates in real-time
- Most robust approach for production systems

### 7.4 Internal Event Bus
- Home Assistant has a central event bus where all state changes are broadcast
- Automations, scripts, and other integrations subscribe to events
- Pattern: `hass.bus.async_fire("state_changed", {"entity_id": ..., "old_state": ..., "new_state": ...})`

**For BaluHost**: FastAPI + WebSocket manager already exists. The pattern would be:
1. Plugin updates device state via a standard method
2. Core fires an internal event
3. WebSocket manager broadcasts to connected clients
4. Other services (fan control, power management) can subscribe to device state changes

---

## 8. Python-Specific Plugin System Patterns

### 8.1 Approach Comparison

| Approach | Pros | Cons | Best For |
|----------|------|------|----------|
| **ABC (Abstract Base Classes)** | Clear interface contract, IDE support, enforced at instantiation | Requires inheritance, tightly coupled | Internal plugins, small ecosystems |
| **Protocol (PEP 544)** | Structural subtyping, no inheritance required, duck-typing compatible | No runtime enforcement by default, newer concept | External/third-party plugins |
| **Entry Points (setuptools)** | Standard Python packaging, distributable via pip, well-understood | Requires packaging, more complex setup | Distributable plugins |
| **Stevedore** | Higher-level API over entry points, driver/hook/extension patterns | OpenStack dependency, can be heavy | Large plugin ecosystems |
| **pluggy** | Hook-based, used by pytest, flexible | Unusual API, learning curve | Hook/event-driven plugins |
| **importlib + convention** | Simplest, no dependencies, file-system based | No validation, no packaging | Small, controlled ecosystems |

### 8.2 Recommended Approach for BaluHost

A **hybrid of Protocol classes + importlib discovery + Pydantic validation**:

```python
# 1. Define the plugin protocol (structural typing)
from typing import Protocol, runtime_checkable

@runtime_checkable
class SmartDevicePlugin(Protocol):
    """Interface every smart device plugin must satisfy."""

    @property
    def plugin_id(self) -> str: ...

    @property
    def manifest(self) -> PluginManifest: ...

    async def setup(self, config: dict) -> None: ...

    async def teardown(self) -> None: ...

    async def discover_devices(self) -> list[DiscoveredDevice]: ...

    async def get_device_state(self, device_id: str) -> DeviceState: ...

    async def execute_command(self, device_id: str, command: str, params: dict) -> None: ...


# 2. Define capability protocols
class SwitchCapability(Protocol):
    async def turn_on(self, device_id: str) -> None: ...
    async def turn_off(self, device_id: str) -> None: ...
    async def get_is_on(self, device_id: str) -> bool: ...

class SensorCapability(Protocol):
    async def get_sensor_value(self, device_id: str, sensor_type: str) -> float: ...
    async def get_sensor_unit(self, sensor_type: str) -> str: ...


# 3. Plugin manifest via Pydantic
from pydantic import BaseModel

class PluginManifest(BaseModel):
    plugin_id: str
    name: str
    version: str
    author: str
    description: str
    min_baluhost_version: str
    requirements: list[str] = []
    capabilities: list[str] = []  # ["switch", "sensor.power", ...]
    discovery_methods: dict = {}


# 4. Plugin manager with importlib discovery
class PluginManager:
    def __init__(self, plugin_dir: Path):
        self.plugin_dir = plugin_dir
        self._plugins: dict[str, SmartDevicePlugin] = {}

    async def discover_plugins(self) -> list[PluginManifest]:
        """Scan plugin directory for manifest.json files."""
        ...

    async def load_plugin(self, plugin_id: str) -> SmartDevicePlugin:
        """Import and instantiate a plugin."""
        ...

    async def unload_plugin(self, plugin_id: str) -> None:
        """Teardown and unload a plugin."""
        ...
```

### 8.3 Plugin Directory Layout

```
plugins/
├── tapo/
│   ├── manifest.json          # Plugin descriptor
│   ├── __init__.py            # Plugin entry point (exports plugin class)
│   ├── plugin.py              # SmartDevicePlugin implementation
│   ├── device_types.py        # Device type definitions
│   ├── api_client.py          # Device communication
│   └── requirements.txt       # Optional: pip dependencies
├── shelly/
│   ├── manifest.json
│   ├── __init__.py
│   └── plugin.py
└── _template/                 # Template for new plugin development
    ├── manifest.json
    ├── __init__.py
    └── plugin.py
```

### 8.4 Key Design Decisions

1. **Protocol over ABC**: Use `@runtime_checkable` Protocol classes so plugins don't need to inherit from a base class. This allows third-party plugins to be completely decoupled.

2. **Pydantic for manifests and config**: Leverage BaluHost's existing Pydantic usage for manifest validation and device configuration schemas. This provides automatic JSON serialization, type validation, and OpenAPI documentation.

3. **importlib for discovery**: Scan a `plugins/` directory for subdirectories containing `manifest.json`. Use `importlib.import_module()` to load them. No need for setuptools entry points unless distributing plugins via pip.

4. **Capability composition**: A plugin can implement multiple capability protocols (SwitchCapability + SensorCapability). Use `isinstance()` checks with `@runtime_checkable` protocols to discover what a plugin supports.

5. **Async-first**: All plugin methods should be async, matching BaluHost's FastAPI/asyncio architecture.

6. **Sandboxed execution**: Plugins should run within the main process but with controlled access to BaluHost internals. Expose a limited "Plugin API" object rather than giving direct access to the database or internal services.

---

## 9. Key Architectural Recommendations for BaluHost

### 9.1 Three-Layer Device Model (inspired by OpenHAB + HA)

1. **Plugin** = the integration code (e.g., "tapo", "shelly")
2. **Device** = a physical device managed by a plugin (identified by MAC/serial/IP)
3. **Entity** = a specific capability of a device (e.g., the on/off switch, the power sensor)

### 9.2 Unified State Store

All device entities should have their state in a central store (DB table + in-memory cache) with a standardized schema:
- `entity_id` (e.g., `tapo.kitchen_plug.switch`)
- `state` (string: "on", "off", "23.5", "unavailable")
- `attributes` (JSON: device_class, unit, etc.)
- `last_updated` (timestamp)
- `last_changed` (timestamp: only when state value actually changed)

### 9.3 Event-Driven Architecture

When any entity state changes:
1. Plugin calls `self.update_state(entity_id, new_state)`
2. Core compares with previous state, updates store
3. Core fires event on internal bus: `{"event": "state_changed", "entity_id": ..., "old": ..., "new": ...}`
4. WebSocket manager pushes to frontend clients
5. Other services (automations, fan control, monitoring) can subscribe

### 9.4 Configuration Flow

1. **Discovery**: Background service scans for devices (mDNS, SSDP)
2. **Notification**: Found devices shown in admin UI (similar to HA's discovery notifications)
3. **Setup**: User clicks to configure, sees a form generated from the plugin's config schema
4. **Validation**: Plugin validates the configuration (e.g., tries to connect to device)
5. **Creation**: Device + entities created in registry, polling/push starts

### 9.5 Leverage Existing BaluHost Infrastructure

- **WebSocket manager** (`websocket_manager.py`) -> device state push to frontend
- **Scheduler service** (`scheduler/service.py`) -> periodic polling coordination
- **Network discovery** (`network_discovery.py`) -> mDNS foundation already exists
- **Existing Tapo integration** (`api/routes/` with Tapo endpoints) -> first migration candidate
- **Plugin system** (`api/routes/plugins/`) -> existing plugin infrastructure to build upon
- **Pydantic schemas** -> config schema validation
- **SQLAlchemy models** -> device/entity state persistence
- **Audit logging** -> device command audit trail

---

## 10. Summary of Key Patterns

| Pattern | Source | Relevance |
|---------|--------|-----------|
| **manifest.json descriptor** | Home Assistant | Declare plugin metadata, dependencies, discovery methods |
| **Config Flow (step-based wizard)** | Home Assistant | UI-guided device setup with validation |
| **Entity model with domains** | Home Assistant | Standardized capability types (switch, sensor, etc.) |
| **Device Registry with identifiers** | Home Assistant | Track physical devices by MAC/serial, link entities |
| **DataUpdateCoordinator** | Home Assistant | Unified polling/push data fetching pattern |
| **Thing/Channel/Item hierarchy** | OpenHAB | Clean separation of device, capability, user-facing state |
| **XML/JSON type descriptors** | OpenHAB | Declarative device type definitions |
| **Protocol classes (PEP 544)** | Python typing | Structural subtyping for plugin interfaces |
| **importlib discovery** | Python stdlib | File-system based plugin discovery |
| **Pydantic for schemas** | FastAPI ecosystem | Config validation, serialization, OpenAPI docs |
| **mDNS/Zeroconf + SSDP** | Industry standard | Automatic device discovery on local network |
| **Event bus for state changes** | Home Assistant/OpenHAB | Decoupled notification of device state changes |

---

## Sources

- [Home Assistant Config Flow Developer Docs](https://developers.home-assistant.io/docs/config_entries_config_flow_handler/)
- [Home Assistant Integration Architecture](https://developers.home-assistant.io/docs/architecture_components/)
- [Home Assistant Entity Developer Docs](https://developers.home-assistant.io/docs/core/entity/)
- [Home Assistant Entity Platform System (DeepWiki)](https://deepwiki.com/home-assistant/home-assistant.io/7-entity-platform-system)
- [Home Assistant Device Registry Developer Docs](https://developers.home-assistant.io/docs/device_registry_index/)
- [Home Assistant Data Entry Flow](https://developers.home-assistant.io/docs/data_entry_flow_index/)
- [Home Assistant Fetching Data / DataUpdateCoordinator](https://developers.home-assistant.io/docs/integration_fetching_data/)
- [Home Assistant Integration Manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/)
- [Home Assistant Networking and Discovery](https://developers.home-assistant.io/docs/network_discovery/)
- [Home Assistant Discovery and Communication Protocols (DeepWiki)](https://deepwiki.com/home-assistant/core/5.2-discovery-and-communication-protocols)
- [OpenHAB Binding Developer Guide](https://www.openhab.org/docs/developer/bindings/)
- [OpenHAB Thing Descriptions](https://www.openhab.org/docs/developer/bindings/thing-xml.html)
- [Synology Package Developer Guide](https://help.synology.com/developer-guide/)
- [Synology DSM 3rd-Party Apps Developer Guide](https://global.download.synology.com/download/Document/Software/DeveloperGuide/Firmware/DSM/All/enu/Synology_NAS_Server_3rd_Party_Apps_Integration_Guide.pdf)
- [PEP 544 - Protocols: Structural Subtyping](https://peps.python.org/pep-0544/)
- [Python Protocol Classes for Type Safety](https://oneuptime.com/blog/post/2026-02-02-python-protocol-classes-type-safety/view)
- [How to Build Plugin Systems in Python](https://oneuptime.com/blog/post/2026-01-30-python-plugin-systems/view)
- [Stevedore - Creating Plugins](https://docs.openstack.org/stevedore/latest/user/tutorial/creating_plugins.html)
- [Creating and Discovering Plugins - Python Packaging Guide](https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/)
- [Writing Home Assistant Integrations (Sam Rambles)](https://samrambles.com/guides/writing-home-assistant-integrations/index.html)
- [Building a Home Assistant Custom Component (Automate The Things)](https://aarongodfrey.dev/home%20automation/building_a_home_assistant_custom_component_part_1/)
- [Zero-configuration networking (Wikipedia)](https://en.wikipedia.org/wiki/Zero-configuration_networking)
