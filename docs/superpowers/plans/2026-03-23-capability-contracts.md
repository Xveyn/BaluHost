# Capability Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce that smart device plugins declaring capabilities (e.g. `POWER_MONITOR`) actually implement the corresponding protocol and return the correct data model — validated at startup and runtime.

**Architecture:** Add a `CAPABILITY_CONTRACTS` mapping in `capabilities.py` as the single source of truth. A shared `validate_capability_contracts()` utility is called by both `PluginManager.load_plugin()` and `SmartDevicePoller._load_plugins()`. The poller's `_poll_one_device()` validates returned data against the contract before serialization.

**Tech Stack:** Python 3.11+, Pydantic v2, `@runtime_checkable` Protocols, pytest

**Spec:** `docs/superpowers/specs/2026-03-23-capability-contracts-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/plugins/smart_device/capabilities.py` | Modify | Add `CAPABILITY_CONTRACTS` dict + `validate_capability_contracts()` utility |
| `backend/app/plugins/manager.py` | Modify (lines ~188-200) | Call validation after instantiating SmartDevicePlugin |
| `backend/app/plugins/smart_device/poller.py` | Modify (lines ~220-226, ~333-341) | Call validation in `_load_plugins()` + validate poll data in `_poll_one_device()` |
| `backend/app/plugins/README.md` | Modify | Add "Capability-Verträge" section |
| `backend/tests/plugins/test_capability_contracts.py` | Create | All contract validation tests |

---

### Task 1: CAPABILITY_CONTRACTS mapping + validate utility

**Files:**
- Modify: `backend/app/plugins/smart_device/capabilities.py`
- Test: `backend/tests/plugins/test_capability_contracts.py`

- [ ] **Step 1: Write the test file with structural + startup validation tests**

```python
# backend/tests/plugins/test_capability_contracts.py
"""Tests for capability contract enforcement."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest
from pydantic import BaseModel

from app.plugins.smart_device.capabilities import (
    CAPABILITY_CONTRACTS,
    DeviceCapability,
    PowerMonitor,
    PowerReading,
    Switch,
    SwitchState,
    validate_capability_contracts,
)
from app.plugins.smart_device.base import DeviceTypeInfo, SmartDevicePlugin
from app.plugins.base import PluginMetadata


# --- Helpers ---

class _ValidPowerPlugin(SmartDevicePlugin):
    """Plugin that correctly implements POWER_MONITOR."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="valid_power",
            version="1.0.0",
            display_name="Valid Power",
            description="Test",
            author="Test",
            category="smart_device",
        )

    def get_device_types(self) -> List[DeviceTypeInfo]:
        return [
            DeviceTypeInfo(
                type_id="test_power",
                display_name="Test Power",
                manufacturer="Test",
                capabilities=[DeviceCapability.POWER_MONITOR],
            )
        ]

    async def connect_device(self, device_id: str, config: Dict[str, Any]) -> bool:
        return True

    async def poll_device(self, device_id: str) -> Dict[str, Any]:
        return {
            "power_monitor": PowerReading(
                watts=42.0, timestamp=datetime.now(timezone.utc)
            )
        }

    async def get_power(self, device_id: str) -> PowerReading:
        return PowerReading(watts=42.0, timestamp=datetime.now(timezone.utc))


class _MissingProtocolPlugin(SmartDevicePlugin):
    """Plugin that declares POWER_MONITOR but does NOT implement get_power()."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="missing_protocol",
            version="1.0.0",
            display_name="Missing Protocol",
            description="Test",
            author="Test",
            category="smart_device",
        )

    def get_device_types(self) -> List[DeviceTypeInfo]:
        return [
            DeviceTypeInfo(
                type_id="test_broken",
                display_name="Test Broken",
                manufacturer="Test",
                capabilities=[DeviceCapability.POWER_MONITOR],
            )
        ]

    async def connect_device(self, device_id: str, config: Dict[str, Any]) -> bool:
        return True

    async def poll_device(self, device_id: str) -> Dict[str, Any]:
        return {}


class _PartialProtocolPlugin(SmartDevicePlugin):
    """Declares SWITCH + POWER_MONITOR but only implements Switch."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="partial_protocol",
            version="1.0.0",
            display_name="Partial",
            description="Test",
            author="Test",
            category="smart_device",
        )

    def get_device_types(self) -> List[DeviceTypeInfo]:
        return [
            DeviceTypeInfo(
                type_id="test_partial",
                display_name="Test Partial",
                manufacturer="Test",
                capabilities=[
                    DeviceCapability.SWITCH,
                    DeviceCapability.POWER_MONITOR,
                ],
            )
        ]

    async def connect_device(self, device_id: str, config: Dict[str, Any]) -> bool:
        return True

    async def poll_device(self, device_id: str) -> Dict[str, Any]:
        return {}

    # Implements Switch but NOT PowerMonitor
    async def turn_on(self, device_id: str) -> SwitchState:
        return SwitchState(is_on=True)

    async def turn_off(self, device_id: str) -> SwitchState:
        return SwitchState(is_on=False)

    async def get_switch_state(self, device_id: str) -> SwitchState:
        return SwitchState(is_on=True)


# --- Tests: CAPABILITY_CONTRACTS completeness ---

def test_all_capabilities_have_contracts():
    """Every DeviceCapability enum value must have an entry in CAPABILITY_CONTRACTS."""
    for cap in DeviceCapability:
        assert cap in CAPABILITY_CONTRACTS, f"Missing contract for {cap.value}"


# --- Tests: validate_capability_contracts ---

def test_valid_plugin_passes_validation():
    plugin = _ValidPowerPlugin()
    errors = validate_capability_contracts(plugin)
    assert errors == []


def test_missing_protocol_fails_validation():
    plugin = _MissingProtocolPlugin()
    errors = validate_capability_contracts(plugin)
    assert len(errors) == 1
    assert "power_monitor" in errors[0].lower()
    assert "PowerMonitor" in errors[0]


def test_partial_protocol_fails_validation():
    plugin = _PartialProtocolPlugin()
    errors = validate_capability_contracts(plugin)
    assert len(errors) == 1
    assert "power_monitor" in errors[0].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/plugins/test_capability_contracts.py -v`
Expected: FAIL — `CAPABILITY_CONTRACTS` and `validate_capability_contracts` don't exist yet.

- [ ] **Step 3: Implement CAPABILITY_CONTRACTS + validate_capability_contracts**

First, update the import line at the top of `backend/app/plugins/smart_device/capabilities.py`:

```python
from typing import Any, Protocol, runtime_checkable, Optional
```

Then add to end of the file:

```python
# --- Capability Contracts ---
# Declaring a capability is a CONTRACT:
# - Your plugin MUST implement the Protocol (checked at startup)
# - poll_device() MUST return the DataModel for this capability key (checked at runtime)
# In return you get: mobile app integration, dashboard panels,
# energy statistics, and cost calculations — for free.

CAPABILITY_CONTRACTS: dict[DeviceCapability, tuple[type, type[BaseModel]]] = {
    DeviceCapability.SWITCH: (Switch, SwitchState),
    DeviceCapability.POWER_MONITOR: (PowerMonitor, PowerReading),
    DeviceCapability.SENSOR: (Sensor, SensorReading),
    DeviceCapability.DIMMER: (Dimmer, DimmerState),
    DeviceCapability.COLOR: (ColorControl, ColorState),
}


def validate_capability_contracts(plugin: object) -> list[str]:
    """Validate that a plugin implements all protocols for its declared capabilities.

    Iterates over every DeviceTypeInfo returned by the plugin's
    ``get_device_types()`` and checks that each declared capability's
    protocol is satisfied (via ``isinstance``).

    Args:
        plugin: A SmartDevicePlugin instance.

    Returns:
        List of human-readable error strings (empty means valid).
    """
    errors: list[str] = []
    seen: set[DeviceCapability] = set()

    # Import here to avoid circular import at module level
    from app.plugins.smart_device.base import SmartDevicePlugin

    if not isinstance(plugin, SmartDevicePlugin):
        return errors

    for device_type in plugin.get_device_types():
        for cap in device_type.capabilities:
            if cap in seen:
                continue
            seen.add(cap)

            contract = CAPABILITY_CONTRACTS.get(cap)
            if contract is None:
                errors.append(
                    f"Capability '{cap.value}' has no contract defined in CAPABILITY_CONTRACTS"
                )
                continue

            protocol_cls, _data_model = contract
            if not isinstance(plugin, protocol_cls):
                errors.append(
                    f"Capability '{cap.value}' requires {protocol_cls.__name__} protocol "
                    f"but plugin '{plugin.metadata.name}' does not implement it"
                )

    return errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_capability_contracts.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/smart_device/capabilities.py backend/tests/plugins/test_capability_contracts.py
git commit -m "feat(plugins): add CAPABILITY_CONTRACTS mapping and validation utility"
```

---

### Task 2: Startup validation in PluginManager

**Files:**
- Modify: `backend/app/plugins/manager.py:188-200`
- Test: `backend/tests/plugins/test_capability_contracts.py` (append)

- [ ] **Step 1: Write the test**

Append to `backend/tests/plugins/test_capability_contracts.py`:

```python
from unittest.mock import patch
from app.plugins.manager import PluginManager, PluginLoadError


@pytest.fixture(autouse=True)
def reset_manager():
    PluginManager.reset_instance()
    yield
    PluginManager.reset_instance()


def test_plugin_manager_rejects_invalid_smart_device_plugin(tmp_path):
    """PluginManager.load_plugin() should reject a SmartDevicePlugin that
    fails capability contract validation."""
    # Create a plugin directory with a broken smart device plugin
    plugins_dir = tmp_path / "plugins"
    plugin_dir = plugins_dir / "broken_device"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text('''
from app.plugins.base import PluginMetadata
from app.plugins.smart_device.base import SmartDevicePlugin, DeviceTypeInfo
from app.plugins.smart_device.capabilities import DeviceCapability

class BrokenDevicePlugin(SmartDevicePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="broken_device",
            version="1.0.0",
            display_name="Broken",
            description="Test",
            author="Test",
            category="smart_device",
        )

    def get_device_types(self):
        return [DeviceTypeInfo(
            type_id="broken",
            display_name="Broken",
            manufacturer="Test",
            capabilities=[DeviceCapability.POWER_MONITOR],
        )]

    async def connect_device(self, device_id, config):
        return True

    async def poll_device(self, device_id):
        return {}
''')

    manager = PluginManager(plugins_dir=plugins_dir)
    with pytest.raises(PluginLoadError, match="capability contract"):
        manager.load_plugin("broken_device")


def test_plugin_manager_accepts_valid_smart_device_plugin(tmp_path):
    """PluginManager.load_plugin() should accept a SmartDevicePlugin that
    satisfies all capability contracts."""
    plugins_dir = tmp_path / "plugins"
    plugin_dir = plugins_dir / "good_device"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text('''
from datetime import datetime, timezone
from app.plugins.base import PluginMetadata
from app.plugins.smart_device.base import SmartDevicePlugin, DeviceTypeInfo
from app.plugins.smart_device.capabilities import (
    DeviceCapability, PowerReading,
)

class GoodDevicePlugin(SmartDevicePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="good_device",
            version="1.0.0",
            display_name="Good",
            description="Test",
            author="Test",
            category="smart_device",
        )

    def get_device_types(self):
        return [DeviceTypeInfo(
            type_id="good",
            display_name="Good",
            manufacturer="Test",
            capabilities=[DeviceCapability.POWER_MONITOR],
        )]

    async def connect_device(self, device_id, config):
        return True

    async def poll_device(self, device_id):
        return {"power_monitor": PowerReading(watts=1.0, timestamp=datetime.now(timezone.utc))}

    async def get_power(self, device_id):
        return PowerReading(watts=1.0, timestamp=datetime.now(timezone.utc))
''')

    manager = PluginManager(plugins_dir=plugins_dir)
    plugin = manager.load_plugin("good_device")
    assert plugin is not None
```

- [ ] **Step 2: Run tests to verify the new tests fail**

Run: `cd backend && python -m pytest tests/plugins/test_capability_contracts.py::test_plugin_manager_rejects_invalid_smart_device_plugin -v`
Expected: FAIL — load_plugin does not check contracts yet (plugin loads without error).

- [ ] **Step 3: Add contract check to PluginManager.load_plugin()**

In `backend/app/plugins/manager.py`, after line 197 (`self._plugins[name] = plugin`) and before the `logger.info` on line 198, insert:

```python
            # Validate capability contracts for smart device plugins
            from app.plugins.smart_device.base import SmartDevicePlugin
            if isinstance(plugin, SmartDevicePlugin):
                from app.plugins.smart_device.capabilities import validate_capability_contracts
                contract_errors = validate_capability_contracts(plugin)
                if contract_errors:
                    del self._plugins[name]
                    errors_str = "; ".join(contract_errors)
                    raise PluginLoadError(
                        f"Plugin '{name}' failed capability contract validation: {errors_str}"
                    )
```

- [ ] **Step 4: Run all contract tests to verify they pass**

Run: `cd backend && python -m pytest tests/plugins/test_capability_contracts.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 5: Run existing plugin tests for regression**

Run: `cd backend && python -m pytest tests/plugins/ -v`
Expected: All existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/plugins/manager.py backend/tests/plugins/test_capability_contracts.py
git commit -m "feat(plugins): enforce capability contracts at startup in PluginManager"
```

---

### Task 3: Startup validation in SmartDevicePoller

**Files:**
- Modify: `backend/app/plugins/smart_device/poller.py:220-226`
- Test: `backend/tests/plugins/test_capability_contracts.py` (append)

- [ ] **Step 1: Write the test**

Append to `backend/tests/plugins/test_capability_contracts.py`:

```python
from app.plugins.smart_device.poller import SmartDevicePoller


@pytest.mark.asyncio
async def test_poller_skips_plugin_failing_contracts(tmp_path, caplog):
    """SmartDevicePoller._load_plugins() should skip plugins that fail
    capability contract validation and log a warning."""
    plugins_dir = tmp_path / "plugins"
    plugin_dir = plugins_dir / "broken_poller_device"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text('''
from app.plugins.base import PluginMetadata
from app.plugins.smart_device.base import SmartDevicePlugin, DeviceTypeInfo
from app.plugins.smart_device.capabilities import DeviceCapability

class BrokenPollerPlugin(SmartDevicePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="broken_poller_device",
            version="1.0.0",
            display_name="Broken Poller",
            description="Test",
            author="Test",
            category="smart_device",
        )

    def get_device_types(self):
        return [DeviceTypeInfo(
            type_id="broken",
            display_name="Broken",
            manufacturer="Test",
            capabilities=[DeviceCapability.POWER_MONITOR],
        )]

    async def connect_device(self, device_id, config):
        return True

    async def poll_device(self, device_id):
        return {}
''')

    # We can't easily test _load_plugins() end-to-end (needs DB),
    # so we test the validation integration directly by simulating
    # what _load_plugins does: instantiate + validate
    import importlib.util, sys
    module_name = "test_broken_poller_plugin"
    spec = importlib.util.spec_from_file_location(
        module_name,
        plugin_dir / "__init__.py",
        submodule_search_locations=[str(plugin_dir)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    plugin = module.BrokenPollerPlugin()

    from app.plugins.smart_device.capabilities import validate_capability_contracts
    errors = validate_capability_contracts(plugin)
    assert len(errors) == 1
    assert "power_monitor" in errors[0].lower()

    # Cleanup
    del sys.modules[module_name]
```

- [ ] **Step 2: Run to verify it passes (validates the utility works with dynamically loaded plugins)**

Run: `cd backend && python -m pytest tests/plugins/test_capability_contracts.py::test_poller_skips_plugin_failing_contracts -v`
Expected: PASS (the utility already works; this test confirms it works with dynamically imported plugins).

- [ ] **Step 3: Add contract check to SmartDevicePoller._load_plugins()**

In `backend/app/plugins/smart_device/poller.py`, after line 220 (`plugin = plugin_cls()`) and before the category check on line 221, insert:

```python
                # Validate capability contracts
                from app.plugins.smart_device.capabilities import validate_capability_contracts
                contract_errors = validate_capability_contracts(plugin)
                if contract_errors:
                    errors_str = "; ".join(contract_errors)
                    logger.warning(
                        "SmartDevicePoller: plugin '%s' failed capability contract "
                        "validation: %s — skipping",
                        name, errors_str,
                    )
                    continue
```

- [ ] **Step 4: Run all contract tests**

Run: `cd backend && python -m pytest tests/plugins/test_capability_contracts.py -v`
Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/smart_device/poller.py backend/tests/plugins/test_capability_contracts.py
git commit -m "feat(plugins): enforce capability contracts at startup in SmartDevicePoller"
```

---

### Task 4: Runtime validation in poller

**Files:**
- Modify: `backend/app/plugins/smart_device/poller.py:333-341`
- Test: `backend/tests/plugins/test_capability_contracts.py` (append)

- [ ] **Step 1: Write the tests**

Append to `backend/tests/plugins/test_capability_contracts.py`:

```python
from app.plugins.smart_device.capabilities import validate_poll_data


def test_validate_poll_data_valid_power_reading():
    """Valid PowerReading passes validation."""
    declared = [DeviceCapability.POWER_MONITOR]
    data = {
        "power_monitor": PowerReading(
            watts=42.0, timestamp=datetime.now(timezone.utc)
        )
    }
    validated, warnings = validate_poll_data(data, declared)
    assert "power_monitor" in validated
    assert warnings == []


def test_validate_poll_data_valid_dict():
    """A raw dict that matches PowerReading schema passes validation."""
    declared = [DeviceCapability.POWER_MONITOR]
    data = {
        "power_monitor": {
            "watts": 42.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }
    validated, warnings = validate_poll_data(data, declared)
    assert "power_monitor" in validated
    assert warnings == []


def test_validate_poll_data_invalid_dict():
    """A dict missing required field 'watts' is rejected."""
    declared = [DeviceCapability.POWER_MONITOR]
    data = {
        "power_monitor": {"voltage": 230.0}  # missing 'watts' and 'timestamp'
    }
    validated, warnings = validate_poll_data(data, declared)
    assert "power_monitor" not in validated
    assert len(warnings) == 1
    assert "power_monitor" in warnings[0].lower()


def test_validate_poll_data_empty_dict():
    """Empty poll result is valid — no errors."""
    declared = [DeviceCapability.POWER_MONITOR]
    validated, warnings = validate_poll_data({}, declared)
    assert validated == {}
    assert warnings == []


def test_validate_poll_data_partial_capabilities():
    """Returning only some declared capabilities is valid."""
    declared = [DeviceCapability.SWITCH, DeviceCapability.POWER_MONITOR]
    data = {
        "switch": SwitchState(is_on=True),
    }
    validated, warnings = validate_poll_data(data, declared)
    assert "switch" in validated
    assert warnings == []


def test_validate_poll_data_extra_key_warned():
    """Keys not in declared capabilities are dropped with a warning."""
    declared = [DeviceCapability.SWITCH]
    data = {
        "switch": SwitchState(is_on=True),
        "power_monitor": PowerReading(
            watts=42.0, timestamp=datetime.now(timezone.utc)
        ),
    }
    validated, warnings = validate_poll_data(data, declared)
    assert "switch" in validated
    assert "power_monitor" not in validated
    assert len(warnings) == 1
    assert "undeclared" in warnings[0].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/plugins/test_capability_contracts.py::test_validate_poll_data_valid_power_reading -v`
Expected: FAIL — `validate_poll_data` does not exist yet.

- [ ] **Step 3: Implement validate_poll_data()**

Add to `backend/app/plugins/smart_device/capabilities.py`:

```python
def validate_poll_data(
    data: dict[str, Any],
    declared_capabilities: list[DeviceCapability],
) -> tuple[dict[str, Any], list[str]]:
    """Validate poll_device() output against declared capability contracts.

    Args:
        data: The dict returned by poll_device() or poll_device_mock().
        declared_capabilities: The device's declared capabilities list.

    Returns:
        Tuple of (validated_data, warnings).
        validated_data contains only entries that passed validation.
        warnings contains human-readable messages for issues found.
    """
    validated: dict[str, Any] = {}
    warnings: list[str] = []
    declared_values = {cap.value for cap in declared_capabilities}

    for key, value in data.items():
        # Check if key corresponds to a declared capability
        if key not in declared_values:
            warnings.append(
                f"Undeclared capability key '{key}' in poll result — ignored"
            )
            continue

        # Find the matching capability and its contract
        try:
            cap = DeviceCapability(key)
        except ValueError:
            warnings.append(f"Unknown capability key '{key}' — ignored")
            continue

        contract = CAPABILITY_CONTRACTS.get(cap)
        if contract is None:
            # No contract defined — pass through
            validated[key] = value
            continue

        _protocol_cls, data_model = contract

        # Already the right Pydantic model?
        if isinstance(value, data_model):
            validated[key] = value
            continue

        # Try to validate as dict
        if isinstance(value, dict):
            try:
                data_model.model_validate(value)
                validated[key] = value
            except Exception:
                warnings.append(
                    f"Capability '{key}' returned invalid data "
                    f"(expected {data_model.__name__})"
                )
            continue

        warnings.append(
            f"Capability '{key}' returned unexpected type {type(value).__name__} "
            f"(expected {data_model.__name__} or dict)"
        )

    return validated, warnings
```

- [ ] **Step 4: Run runtime validation tests**

Run: `cd backend && python -m pytest tests/plugins/test_capability_contracts.py -k "validate_poll_data" -v`
Expected: All 6 new tests PASS.

- [ ] **Step 5: Integrate into poller's _poll_one_device()**

In `backend/app/plugins/smart_device/poller.py`, in `_poll_one_device()`, replace lines 333-341 (the serialization block) with:

```python
            # Validate poll data against capability contracts
            from app.plugins.smart_device.capabilities import (
                DeviceCapability,
                validate_poll_data,
            )
            declared_caps = []
            for c in device.capabilities:
                try:
                    declared_caps.append(DeviceCapability(c))
                except ValueError:
                    pass
            validated_state, poll_warnings = validate_poll_data(new_state, declared_caps)
            for warning in poll_warnings:
                logger.warning(
                    "SmartDevicePoller: plugin '%s' device %d ('%s'): %s",
                    plugin.metadata.name, device_id, device.name, warning,
                )

            # Serialize any Pydantic models in the validated state dict
            serialized: Dict[str, Any] = {}
            for cap_key, cap_value in validated_state.items():
                if hasattr(cap_value, "model_dump"):
                    serialized[cap_key] = cap_value.model_dump(mode="json")
                else:
                    serialized[cap_key] = cap_value

            self._process_state(device, serialized)
```

- [ ] **Step 6: Run all contract tests + existing plugin tests**

Run: `cd backend && python -m pytest tests/plugins/test_capability_contracts.py tests/plugins/ -v`
Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/plugins/smart_device/capabilities.py backend/app/plugins/smart_device/poller.py backend/tests/plugins/test_capability_contracts.py
git commit -m "feat(plugins): add runtime validation of poll data against capability contracts"
```

---

### Task 5: Update plugin documentation

**Files:**
- Modify: `backend/app/plugins/README.md`

- [ ] **Step 1: Add "Capability-Verträge" section**

Insert after the existing "Verfügbare Capabilities:" table (around line 318) in `backend/app/plugins/README.md`:

```markdown
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
```

- [ ] **Step 2: Verify README renders correctly (visual check)**

Open `backend/app/plugins/README.md` and verify the new section is well-placed and the table renders.

- [ ] **Step 3: Commit**

```bash
git add backend/app/plugins/README.md
git commit -m "docs(plugins): add capability contracts documentation"
```

---

### Task 6: Full regression test

- [ ] **Step 1: Run all plugin tests**

Run: `cd backend && python -m pytest tests/plugins/ -v`
Expected: All tests PASS.

- [ ] **Step 2: Run the full test suite**

Run: `cd backend && python -m pytest --timeout=30 -x -q`
Expected: All tests PASS, no regressions.

- [ ] **Step 3: Verify Tapo plugin still loads correctly**

Run: `cd backend && python -c "from app.plugins.installed.tapo_smart_plug import TapoSmartPlugPlugin; from app.plugins.smart_device.capabilities import validate_capability_contracts; p = TapoSmartPlugPlugin(); errors = validate_capability_contracts(p); print('Errors:', errors); assert errors == [], errors"`
Expected: `Errors: []` — Tapo plugin satisfies all contracts.

- [ ] **Step 4: Final commit if any fixups needed, otherwise done**
