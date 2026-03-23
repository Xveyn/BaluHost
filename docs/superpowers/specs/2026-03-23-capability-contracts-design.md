# Design: Capability Contracts for Smart Device Plugins

**Date:** 2026-03-23
**Status:** Approved
**Scope:** Smart Device Plugin System — Capability-Vertrag-Enforcement

---

## Problem

Plugins mit `POWER_MONITOR`-Capability liefern Stromverbrauchsdaten, die von der Mobile App (BaluApp) konsumiert werden. Aktuell funktioniert das de facto über `PowerReading` + `poll_device()`, aber:

1. Es gibt keinen expliziten Vertrag — ein Plugin könnte eigene Routen mit eigenem Schema für Stromverbrauch bauen
2. Die Mobile App braucht ein garantiert stabiles Schema
3. Es gibt keine Validierung, dass ein Plugin das deklarierte Capability-Protocol tatsächlich implementiert

## Lösung

**Capabilities sind Verträge.** Wer eine Capability deklariert, muss:
- Das zugehörige Protocol implementieren (geprüft beim Start)
- Das zugehörige Datenmodell über `poll_device()` liefern (geprüft zur Laufzeit)

Dafür bekommt das Plugin automatisch: Mobile-App-Integration, Dashboard-Panel, Energie-Statistiken und Kostenberechnung.

## Philosophie

Die Plugin-Freiheit bleibt bestehen. Plugins können eigene Routen, eigene UIs und eigene Logik haben. Aber wenn ein Plugin sagt "Ich kann Strom messen" (`POWER_MONITOR`), dann muss es die Daten im vorgegebenen Format liefern. Das ist keine Einschränkung, sondern eine Spezifikation — vergleichbar mit einem Interface in einer Programmiersprache.

## Design

### 1. Capability-Contract-Mapping (`capabilities.py`)

Explizites Mapping von Capability zu (Protocol, DataModel) als Code-Konstante:

```python
CAPABILITY_CONTRACTS: dict[DeviceCapability, tuple[type, type[BaseModel]]] = {
    DeviceCapability.POWER_MONITOR: (PowerMonitor, PowerReading),
    DeviceCapability.SWITCH: (Switch, SwitchState),
    DeviceCapability.SENSOR: (Sensor, SensorReading),
    DeviceCapability.DIMMER: (Dimmer, DimmerState),
    DeviceCapability.COLOR: (ColorControl, ColorState),
}
```

Dieses Mapping ist die Single Source of Truth für alle Validierungen.

**Key-Konvention:** Der Key in der `poll_device()`-Rückgabe muss dem `.value` des `DeviceCapability`-Enums entsprechen (z.B. `"power_monitor"`, `"switch"`). Dies ist bereits die implizite Konvention im Codebase und wird hiermit explizit festgelegt.

### 2. Startup-Validierung (`manager.py` + `poller.py`)

Beim Laden eines `SmartDevicePlugin` wird geprüft:

1. Für jeden `DeviceTypeInfo` des Plugins: iteriere über die deklarierten Capabilities
2. Für jede Capability: prüfe via `isinstance(plugin, Protocol)` ob das Protocol erfüllt ist
3. Wenn nicht → Plugin wird **nicht geladen**, Fehler wird geloggt:

```
ERROR: Plugin 'shelly_plug' declares capability 'power_monitor' but does not
implement the PowerMonitor protocol. Plugin not loaded.
```

**Hinweis:** Da ein Plugin eine Klasse ist, die entweder ein Protocol implementiert oder nicht, betrifft dies den gesamten Plugin — auch wenn nur ein Device-Type die fehlende Capability deklariert. Plugin-Autoren müssen sicherstellen, dass alle deklarierten Capabilities implementiert sind.

**Zwei Ladepfade:** Der Check muss an beiden Stellen erfolgen, da der Poller in einem separaten OS-Prozess läuft und Plugins unabhängig vom `PluginManager` lädt:

1. `PluginManager.load_plugin()` in `manager.py` — nach dem Instanziieren, vor dem Registrieren der Routen
2. `SmartDevicePoller._load_plugins()` in `poller.py` — beim Laden der Plugins im Monitoring-Worker

Idealerweise wird die Validierungslogik als Utility-Funktion in `capabilities.py` implementiert, damit beide Ladepfade denselben Code nutzen:

```python
def validate_capability_contracts(plugin: SmartDevicePlugin) -> list[str]:
    """Validate that a plugin implements all protocols for its declared capabilities.

    Returns list of error messages (empty = valid).
    """
```

### 3. Runtime-Validierung (`poller.py`)

Die Validierung erfolgt direkt nach dem `poll_device()` / `poll_device_mock()`-Aufruf, **bevor** die Werte zu dicts serialisiert werden. Gilt für beide Codepfade (prod und dev/mock).

**Ablauf:**

1. Iteriere über die zurückgegebenen Key-Value-Paare
2. Matche den Key gegen die deklarierte Capability des Geräts
3. Prüfe ob der Wert eine Instanz des erwarteten Datenmodells ist. Falls der Wert ein dict ist, validiere via `Model.model_validate(value, strict=True)`
4. Ungültige Daten → dieses einzelne Capability-Sample wird verworfen, Warning geloggt:

```
WARNING: Plugin 'shelly_plug' device 42: capability 'power_monitor' returned
invalid data (expected PowerReading). Sample discarded.
```

5. Gültige Samples fließen normal weiter in SHM + DB

**Edge Cases:**

| Fall | Verhalten |
|------|-----------|
| `poll_device()` gibt leeres dict `{}` zurück | Kein Fehler — Gerät hat diesen Zyklus keine Daten |
| Nur ein Teil der deklarierten Capabilities wird zurückgegeben | Gültig — vorhandene Keys werden validiert, fehlende werden ignoriert |
| Extra Keys, die nicht in den deklarierten Capabilities sind | Warning geloggt, Key wird ignoriert (nicht an SHM/DB weitergereicht) |
| `poll_device_mock()` gibt ungültige Daten zurück | Gleiche Validierung wie `poll_device()` — Dev-Mode ist kein Freifahrtschein |

### 4. Dokumentation (`plugins/README.md`)

Neuer Abschnitt "Capability-Verträge" in der Smart-Device-Sektion:

- Capabilities sind Verträge, nicht nur Labels
- Tabelle: Capability → Protocol → Datenmodell → was man bekommt
- Key-Konvention: `poll_device()`-Keys = `DeviceCapability.value`
- Expliziter Hinweis: Stromverbrauchsdaten müssen über die zentrale Pipeline (`poll_device()` → Poller → SHM → Energy-Service) fließen, nicht über eigene Plugin-Routen
- Hinweis auf Validierung: Startup-Check (Protocol) + Runtime-Check (Datenmodell)

## Betroffene Dateien

| Datei | Änderung |
|-------|----------|
| `backend/app/plugins/smart_device/capabilities.py` | `CAPABILITY_CONTRACTS` dict + `validate_capability_contracts()` Utility |
| `backend/app/plugins/manager.py` | Startup-Check beim Laden von SmartDevicePlugins |
| `backend/app/plugins/smart_device/poller.py` | Startup-Check in `_load_plugins()` + Runtime-Check nach `poll_device()`/`poll_device_mock()` |
| `backend/app/plugins/README.md` | Neuer Abschnitt "Capability-Verträge" |

## Was sich NICHT ändert

- `PowerReading`-Modell bleibt unverändert
- Tapo-Plugin braucht keine Anpassung (erfüllt den Vertrag bereits)
- Mobile API (`/mobile/power-summary`) bleibt unverändert
- Energy-Service bleibt unverändert
- Frontend bleibt unverändert

## Tests

| Test | Erwartung |
|------|-----------|
| Plugin mit `POWER_MONITOR` ohne `get_power()` laden | Startup-Fehler, Plugin nicht geladen |
| Plugin deklariert `SWITCH` + `POWER_MONITOR`, implementiert nur `Switch` | Startup-Fehler, Plugin nicht geladen |
| `poll_device()` gibt ungültiges dict zurück | Sample verworfen, Warning geloggt |
| `poll_device()` gibt valides `PowerReading` zurück | Sample normal verarbeitet |
| `poll_device()` gibt leeres dict `{}` zurück | Kein Fehler, keine Samples gespeichert |
| `poll_device()` gibt nur 1 von 2 deklarierten Capabilities zurück | Vorhandene Keys verarbeitet, kein Fehler |
| `poll_device()` gibt extra Key zurück, der nicht deklariert ist | Warning geloggt, Key ignoriert |
| `poll_device_mock()` gibt ungültige Daten zurück | Gleiche Validierung, Sample verworfen |
| Jeder `DeviceCapability`-Wert hat Eintrag in `CAPABILITY_CONTRACTS` | Struktureller Test — Mapping ist vollständig |
| Bestehende Tapo-Tests | Müssen weiterhin grün sein |

## Nicht im Scope

- Neue Endpoints oder Schema-Änderungen für die Mobile App
- Änderungen am `PowerReading`-Modell
- Nicht-Smart-Device-Plugins als Energiequellen
- Validierung von Plugin-eigenen Routen (nur Daten-Pipeline wird validiert)
- Log-Throttling für wiederholte Validierungsfehler (kann später ergänzt werden)
