# Bluetooth-Plugin (bundled Plugin `bluetooth`) — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein bundled Plugin, mit dem sich aus einem Topbar-Popover Bluetooth-Geräte verbinden, trennen, entfernen und — mit Code-Anzeige im Web-UI — neu koppeln lassen.

**Architecture:** Das Plugin spricht über `dbus-next` (bereits Abhängigkeit) direkt mit `org.bluez` auf dem System-Bus. Zustandslose Aktionen laufen in jedem der vier Uvicorn-Worker; ein Scan gehört dem annehmenden Worker; eine Kopplung gehört genau einem Besitzer-Worker, der einen eigenen (Nicht-Standard-)Agenten anmeldet und den Stand über SHM-Dateien an die UI übergibt, gesperrt per `flock`. Neues Recht `can_manage_bluetooth`, Koppeln nur aus privaten Netzen.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, dbus-next, pytest (asyncio_mode=auto) — React 18, TypeScript, Tailwind, lucide-react, i18next, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-11-bluetooth-plugin-design.md`

## Global Constraints

- **Nur `dbus-next`**, kein `bluetoothctl`, kein `busctl`, kein Subprozess im Produktionscode.
- **`agent.py` und `__init__.py` des Plugins ohne `from __future__ import annotations`.** In `agent.py` liest dbus-next die D-Bus-Signaturen aus den Annotationen (PEP 563 macht aus `'o'` die Zeichenkette `"'o'"`); in `__init__.py` bricht es die Body-Erkennung von FastAPI hinter `@user_limiter.limit` (jedes POST → 422).
- **dbus-nexts `@method()` verwirft den Rückgabewert bei direktem Aufruf.** Agent-Logik steckt in `handle_*`-Methoden; die dekorierten Methoden sind dünne Hüllen. Tests rufen nur `handle_*`.
- **D-Bus-Typen als Modulkonstanten** (`OBJ = "o"` usw.), nie als String-Literal in der Annotation — pyflakes meldet `'o'` sonst als F821.
- **Code und PIN** werden nie geloggt, nie auditiert, nur an den Initiator ausgeliefert.
- **Jede Route**: `Depends(require_power_manage_bluetooth)` (auch die lesenden) und `@user_limiter.limit(get_limit("bluetooth"))`; Rumpf immer als Pydantic-Modell.
- **Koppeln und Bestätigen nur bei `is_private_or_local_ip(client_host)`**, für alle Rollen (VPN zählt mit — bewusst).
- **Das Plugin schreibt nie** `Discoverable`, `Pairable`, `main.conf` oder Kernel-Parameter und ruft nie `RequestDefaultAgent`.
- **502 immer als `BadGatewayError`**, nie `HTTPException(502)` (der 5xx-Scrubber überschreibt dessen `detail`).
- **Migration kettet an den echten Head.** Stand 2026-09-11: `c3a7f0d51b64` — vor dem Anlegen mit `python -m alembic heads` erneut prüfen.
- **Kommentare/Doku deutsch** im Repo-Stil (ASCII-Umlaute `ae/oe/ue` in Python-Kommentaren wie in den Geschwister-Plugins), Bezeichner englisch. Type Hints überall, Docstrings an Services. Dateien < 500 Zeilen.
- **Volle Backend-Suite gehört der CI** (hängt auf Windows). Lokal nur die im Task genannten Testdateien mit `--no-cov`.
- Commit-Nachrichten enden mit:
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01HbQVSEmXaZU6ZV1CjhCee6
  ```
  Unter PowerShell mehrere `-m`-Argumente statt Here-Strings verwenden.

## Dateiübersicht

| Datei | Verantwortung | Task |
|---|---|---|
| `backend/scripts/debug/bluez_probe.py` | Mess-Skript: Fixture-Mitschnitt + Agent-Probe auf BaluNode | 1 |
| `backend/tests/plugins/fixtures/bluez_balunode.json` | gemessene, anonymisierte `GetManagedObjects`-Ausgabe | 1 |
| Recht: `models/power_permissions.py`, Migration, `schemas/power_permissions.py`, `services/power_permissions.py`, `api/deps.py`, `api/routes/sleep.py` | `can_manage_bluetooth` | 2 |
| `backend/app/core/config.py` | `bluetooth_adapter_address` + Validator | 3 |
| `plugins/installed/bluetooth/models.py` | Pydantic-API-Modelle | 3 |
| `plugins/installed/bluetooth/bluez.py` | Parser, Adapterwahl, `BlueZClient`, `BlueZError` | 3, 4 |
| `plugins/installed/bluetooth/pairing.py` | Sperre, SHM-Übergabe, `ActivePairing`, `PairingCoordinator` | 5 |
| `plugins/installed/bluetooth/agent.py` | `BluezAgent` (`org.bluez.Agent1`) | 6 |
| `plugins/installed/bluetooth/backend.py` | `BluetoothBackend`, `DevBluetoothBackend`, `BlueZBackend` | 7 |
| `plugins/installed/bluetooth/service.py` | Backend-Wahl, Validierung, Fehlerabbildung, Scan-Fenster | 8 |
| `plugins/installed/bluetooth/__init__.py` | `BluetoothPlugin`, Router, Audit; `core/rate_limiter.py` | 9 |
| `client/src/api/bluetooth.ts`, `bluetooth.json` (de/en), `i18n/index.ts`, Recht im Frontend | API-Client, Texte, Schalter | 10 |
| `client/src/components/topbar/BluetoothMenu.tsx`, `BluetoothPairingDialog.tsx`, `LayoutHeader.tsx` | UI | 11 |
| Doku, `deploy/install/modules/10-systemd-services.sh`, `backend/.env.example` | Betrieb + Doku | 12 |

---

## Task 1: Spike und Fixture auf BaluNode

**Braucht den Betreiber (Sven) an BaluNode.** Ohne diesen Task gibt es keine Fixture für Task 3. Ergebnis wird in der Spec festgehalten, bevor weitergebaut wird.

**Files:**
- Create: `backend/scripts/debug/bluez_probe.py`
- Create: `backend/tests/plugins/fixtures/bluez_balunode.json` (vom Betreiber erzeugt)
- Modify: `docs/superpowers/specs/2026-09-11-bluetooth-plugin-design.md` (neuer Abschnitt „Spike-Ergebnis")

**Interfaces:**
- Produces: Fixture im Format *entpacktes* `GetManagedObjects` — `{objektpfad: {interface: {property: wert}}}`, Variants aufgelöst, `ay` als Hex-String, nur Adapter und **gekoppelte** Geräte, MACs anonymisiert: Adapter → `AA:AA:AA:AA:AA:01`, Geräte nach Pfad sortiert ab `…:02` (in Pfaden als `AA_AA_…`).

- [ ] **Step 1: Mess-Skript anlegen**

`backend/scripts/debug/bluez_probe.py`:

```python
"""Mess-Skript fuer BlueZ auf BaluNode — KEIN Produktionscode.

Befehle:

  dump [--anonymize]
      GetManagedObjects als JSON auf stdout: Adapter plus GEKOPPELTE Geraete
      (fremde Geraete in Funkreichweite bleiben draussen). Mit --anonymize
      werden MAC-Adressen konsistent ersetzt; genau diese Ausgabe ist
      backend/tests/plugins/fixtures/bluez_balunode.json. Neu messen statt
      von Hand editieren.

  probe-pair MAC
      Sucht das Geraet (bis 30 s Discovery), meldet einen Agenten mit
      KeyboardDisplay an (NICHT als Standard-Agent), ruft Device1.Pair() und
      protokolliert JEDEN Agent-Aufruf. Rueckfragen werden im Terminal
      beantwortet. Nach Erfolg: Trusted=true und Connect().

Aufruf auf BaluNode mit dem venv des Backends, z. B.:
  /opt/baluhost/backend/.venv/bin/python ~/bluez_probe.py dump --anonymize
"""
import argparse
import asyncio
import json
import re
import sys
import time

from dbus_next import BusType, Message, MessageType, Variant
from dbus_next.aio import MessageBus
from dbus_next.errors import DBusError
from dbus_next.service import ServiceInterface, method

BLUEZ = "org.bluez"
ADAPTER_PATH = "/org/bluez/hci0"
AGENT_PATH = "/org/baluhost/bluetooth/probe_agent"
MAC_RE = re.compile(r"(?:[0-9A-F]{2}([:_])){5}[0-9A-F]{2}")

# D-Bus-Typen als Konstanten: als String-Literal in der Annotation meldet
# pyflakes sie als undefinierte Namen (F821).
OBJ = "o"
STR = "s"
U32 = "u"
U16 = "q"


def log(text: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


def unwrap(value):
    """Loest Variants rekursiv auf; ay wird zu Hex, Dict-Schluessel zu str."""
    if isinstance(value, Variant):
        return unwrap(value.value)
    if isinstance(value, dict):
        return {str(k): unwrap(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [unwrap(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return value


async def call(bus, path, interface, member, signature="", body=None):
    reply = await bus.call(Message(
        destination=BLUEZ, path=path, interface=interface, member=member,
        signature=signature, body=list(body or []),
    ))
    if reply.message_type == MessageType.ERROR:
        raise DBusError(reply.error_name, reply.body[0] if reply.body else "")
    return reply.body


async def managed_objects(bus) -> dict:
    body = await call(bus, "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")
    return unwrap(body[0])


def only_adapter_and_paired(objects: dict) -> dict:
    kept = {}
    for path, ifaces in objects.items():
        device = ifaces.get("org.bluez.Device1")
        if device is not None and not device.get("Paired"):
            continue
        kept[path] = ifaces
    return kept


def anonymize(objects: dict) -> dict:
    mapping: dict[str, str] = {}

    def assign(address: str) -> None:
        if address not in mapping:
            mapping[address] = f"AA:AA:AA:AA:AA:{len(mapping) + 1:02d}"

    for path in sorted(objects):
        adapter = objects[path].get("org.bluez.Adapter1")
        if adapter:
            assign(str(adapter["Address"]).upper())
    for path in sorted(objects):
        device = objects[path].get("org.bluez.Device1")
        if device:
            assign(str(device["Address"]).upper())

    text = json.dumps(objects, sort_keys=True)

    def replace(match: re.Match) -> str:
        sep = match.group(1)
        normalized = match.group(0).replace("_", ":")
        fake = mapping.get(normalized)
        if fake is None:
            return match.group(0)
        return fake.replace(":", sep)

    return json.loads(MAC_RE.sub(replace, text))


class ProbeAgent(ServiceInterface):
    def __init__(self) -> None:
        super().__init__("org.bluez.Agent1")

    @method()
    def Release(self):
        log("Agent: Release()")

    @method()
    async def RequestPinCode(self, device: OBJ) -> STR:
        log(f"Agent: RequestPinCode({device})")
        return (await asyncio.to_thread(input, "PIN fuer das Geraet: ")).strip()

    @method()
    def DisplayPinCode(self, device: OBJ, pincode: STR):
        log(f"Agent: DisplayPinCode({device}, {pincode})")

    @method()
    async def RequestPasskey(self, device: OBJ) -> U32:
        log(f"Agent: RequestPasskey({device})")
        return int(await asyncio.to_thread(input, "Passkey: "))

    @method()
    def DisplayPasskey(self, device: OBJ, passkey: U32, entered: U16):
        log(f"Agent: DisplayPasskey({device}, {passkey:06d}, entered={entered})")

    @method()
    async def RequestConfirmation(self, device: OBJ, passkey: U32):
        log(f"Agent: RequestConfirmation({device}, {passkey:06d})")
        answer = await asyncio.to_thread(input, "Stimmt der Code? [j/n] ")
        if answer.strip().lower() != "j":
            raise DBusError("org.bluez.Error.Rejected", "abgelehnt")

    @method()
    async def RequestAuthorization(self, device: OBJ):
        log(f"Agent: RequestAuthorization({device})")
        answer = await asyncio.to_thread(input, "Kopplung erlauben? [j/n] ")
        if answer.strip().lower() != "j":
            raise DBusError("org.bluez.Error.Rejected", "abgelehnt")

    @method()
    def AuthorizeService(self, device: OBJ, uuid: STR):
        log(f"Agent: AuthorizeService({device}, {uuid}) -> Rejected")
        raise DBusError("org.bluez.Error.Rejected", "Probe lehnt Dienste ab")

    @method()
    def Cancel(self):
        log("Agent: Cancel()")


async def wait_for_device(bus, device_path: str, seconds: float) -> bool:
    await call(bus, ADAPTER_PATH, "org.bluez.Adapter1", "StartDiscovery")
    log("Discovery gestartet")
    try:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if device_path in await managed_objects(bus):
                return True
            await asyncio.sleep(1)
        return False
    finally:
        await call(bus, ADAPTER_PATH, "org.bluez.Adapter1", "StopDiscovery")
        log("Discovery beendet")


async def probe_pair(mac: str) -> int:
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    device_path = f"{ADAPTER_PATH}/dev_{mac.upper().replace(':', '_')}"
    if not await wait_for_device(bus, device_path, 30):
        log("Geraet nicht gefunden — Kopplungsmodus aktiv?")
        return 1
    agent = ProbeAgent()
    bus.export(AGENT_PATH, agent)
    await call(bus, "/org/bluez", "org.bluez.AgentManager1", "RegisterAgent", "os",
               [AGENT_PATH, "KeyboardDisplay"])
    log("Agent registriert (KeyboardDisplay, nicht Standard)")
    try:
        await asyncio.wait_for(call(bus, device_path, "org.bluez.Device1", "Pair"), 90)
        log("Pair() -> OK")
        await call(bus, device_path, "org.freedesktop.DBus.Properties", "Set", "ssv",
                   ["org.bluez.Device1", "Trusted", Variant("b", True)])
        log("Trusted=true")
        await call(bus, device_path, "org.bluez.Device1", "Connect")
        log("Connect() -> OK")
        return 0
    except DBusError as exc:
        log(f"FEHLER {exc.type}: {exc.text}")
        return 1
    finally:
        try:
            await call(bus, "/org/bluez", "org.bluez.AgentManager1", "UnregisterAgent", "o",
                       [AGENT_PATH])
        except DBusError as exc:
            log(f"UnregisterAgent: {exc.type}")
        bus.unexport(AGENT_PATH)


async def dump(anonymized: bool) -> int:
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    objects = only_adapter_and_paired(await managed_objects(bus))
    if anonymized:
        objects = anonymize(objects)
    json.dump(objects, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    dump_parser = sub.add_parser("dump")
    dump_parser.add_argument("--anonymize", action="store_true")
    pair_parser = sub.add_parser("probe-pair")
    pair_parser.add_argument("mac")
    args = parser.parse_args()
    if args.command == "dump":
        return asyncio.run(dump(args.anonymize))
    return asyncio.run(probe_pair(args.mac))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Lint prüfen**

Run: `cd backend ; python -m ruff check scripts/debug/bluez_probe.py`
Expected: `All checks passed!`

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/debug/bluez_probe.py
git commit -m "chore(bluetooth): Mess-Skript fuer BlueZ-Fixture und Agent-Probe" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01HbQVSEmXaZU6ZV1CjhCee6"
```

- [ ] **Step 4: Betreiber — Fixture messen**

Auf dem Windows-Rechner im Repo: `scp backend/scripts/debug/bluez_probe.py sven@BaluNode:~/`

Auf BaluNode, **Xbox-Controller und JBL eingeschaltet und verbunden**:

```
/opt/baluhost/backend/.venv/bin/python ~/bluez_probe.py dump --anonymize > ~/bluez-fixture.json
```

Zurück auf Windows: `scp sven@BaluNode:~/bluez-fixture.json backend/tests/plugins/fixtures/bluez_balunode.json`

Prüfen (Implementer): Datei enthält `/org/bluez/hci0` mit `org.bluez.Adapter1.Address == "AA:AA:AA:AA:AA:01"`, zwei Geräte mit `Name` „Xbox Wireless Controller" und „JBL TUNE510BT", **keine** echte MAC (`40:8E`, `C8:2B`, `A0:AD` dürfen nicht vorkommen).

- [ ] **Step 5: Betreiber — JBL neu koppeln (Probe)**

Auf BaluNode: `bluetoothctl remove C8:2B:6B:35:0D:B3`, JBL in den Kopplungsmodus, dann:

```
/opt/baluhost/backend/.venv/bin/python ~/bluez_probe.py probe-pair C8:2B:6B:35:0D:B3
```

Festhalten: jede `Agent:`-Zeile, das Endergebnis, und **ob auf dem Fernseher ein KDE-Dialog erschien** (Soll: nein).

- [ ] **Step 6: Betreiber — Xbox-Controller neu koppeln (nur wenn gerade nicht gespielt wird)**

`bluetoothctl remove 40:8E:2C:4B:16:92`, Controller-Pair-Taste 3 s halten, dann `… probe-pair 40:8E:2C:4B:16:92`. Dasselbe festhalten. Danach muss der Controller wie vorher funktionieren (Trusted + verbunden).

- [ ] **Step 7: Entscheidungsregel anwenden**

| Beobachtung | Folge |
|---|---|
| Kein Agent-Aufruf oder nur `RequestAuthorization` bei Just Works | Design gilt wie geschrieben |
| KDE-Dialog erschien parallel | **STOP** — mit dem Betreiber das Design neu besprechen |
| `Pair()` scheitert mit `KeyboardDisplay`, obwohl `bluetoothctl` es kann | **STOP** — Befund melden |

- [ ] **Step 8: Ergebnis in die Spec, Fixture committen**

Am Ende des Abschnitts „Spike (erste Umsetzungsaufgabe, auf BaluNode)" der Spec einen Unterabschnitt `### Spike-Ergebnis (Datum)` anhängen: die Agent-Zeilen je Gerät (ohne Codes), KDE-Dialog ja/nein, welche Interfaces die verbundenen Geräte tragen (`Battery1`? `Input1`?).

```bash
git add backend/tests/plugins/fixtures/bluez_balunode.json docs/superpowers/specs/2026-09-11-bluetooth-plugin-design.md
git commit -m "test(bluetooth): gemessene BlueZ-Fixture und Spike-Ergebnis" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01HbQVSEmXaZU6ZV1CjhCee6"
```

---

## Task 2: Recht `can_manage_bluetooth` im Backend

**Files:**
- Modify: `backend/app/models/power_permissions.py:30` (nach `can_manage_displays`)
- Create: `backend/alembic/versions/e7c2a9d41f86_add_can_manage_bluetooth_permission.py`
- Modify: `backend/app/schemas/power_permissions.py` (drei Klassen)
- Modify: `backend/app/services/power_permissions.py` (`_ACTION_FIELD_MAP`, `get_permissions`, `update_permissions`, Docstring `check_permission`)
- Modify: `backend/app/api/deps.py:405`
- Modify: `backend/app/api/routes/sleep.py:360-378`
- Test: `backend/tests/test_power_permissions_manage_bluetooth.py`

**Interfaces:**
- Produces: Spalte `UserPowerPermission.can_manage_bluetooth`; Feld `can_manage_bluetooth` in `UserPowerPermissionsResponse` (bool, False), `UserPowerPermissionsUpdate` (Optional[bool], None), `MyPowerPermissionsResponse` (bool, False); Aktion `"manage_bluetooth"`; Abhängigkeit `app.api.deps.require_power_manage_bluetooth` (liefert `UserPublic`, 403 sonst).

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`backend/tests/test_power_permissions_manage_bluetooth.py`:

```python
"""Das Bluetooth-Recht: Standard aus, Admin implizit, keine Implikation."""
from app.schemas.power_permissions import (
    MyPowerPermissionsResponse,
    UserPowerPermissionsResponse,
    UserPowerPermissionsUpdate,
)
from app.services.power_permissions import _ACTION_FIELD_MAP


class TestWiring:
    def test_the_action_maps_to_the_column(self):
        assert _ACTION_FIELD_MAP["manage_bluetooth"] == "can_manage_bluetooth"

    def test_the_dependency_exists(self):
        from app.api import deps
        assert hasattr(deps, "require_power_manage_bluetooth")

    def test_the_model_has_the_column(self):
        from app.models.power_permissions import UserPowerPermission
        assert hasattr(UserPowerPermission, "can_manage_bluetooth")


class TestSchemas:
    def test_it_defaults_to_denied(self):
        assert UserPowerPermissionsResponse(user_id=1).can_manage_bluetooth is False
        assert MyPowerPermissionsResponse().can_manage_bluetooth is False

    def test_the_update_schema_leaves_it_untouched_by_default(self):
        assert UserPowerPermissionsUpdate().can_manage_bluetooth is None


class TestGrantAndRevoke:
    def test_granting_and_revoking_round_trip(self, db_session, test_user, admin_user):
        from app.services.power_permissions import check_permission, update_permissions

        assert check_permission(db_session, test_user.id, "manage_bluetooth") is False
        update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_manage_bluetooth=True),
            granted_by=admin_user.id,
        )
        assert check_permission(db_session, test_user.id, "manage_bluetooth") is True
        update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_manage_bluetooth=False),
            granted_by=admin_user.id,
        )
        assert check_permission(db_session, test_user.id, "manage_bluetooth") is False

    def test_it_does_not_drag_other_permissions_along(self, db_session, test_user, admin_user):
        from app.services.power_permissions import get_permissions, update_permissions

        update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_manage_bluetooth=True),
            granted_by=admin_user.id,
        )
        perms = get_permissions(db_session, test_user.id)
        assert perms.can_manage_bluetooth is True
        assert perms.can_control_audio is False
        assert perms.can_suspend is False

    def test_the_audit_values_carry_the_field(self, db_session, test_user, admin_user, monkeypatch):
        import app.services.power_permissions as svc

        captured: list[dict] = []

        class _Recorder:
            def log_security_event(self, **kwargs):
                captured.append(kwargs)

        monkeypatch.setattr(svc, "get_audit_logger_db", lambda: _Recorder())
        svc.update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_manage_bluetooth=True),
            granted_by=admin_user.id,
        )
        assert captured[0]["details"]["old"]["can_manage_bluetooth"] is False
        assert captured[0]["details"]["new"]["can_manage_bluetooth"] is True
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_power_permissions_manage_bluetooth.py -v --no-cov`
Expected: FAIL — `KeyError: 'manage_bluetooth'` bzw. `AttributeError`.

- [ ] **Step 3: Modell, Schemas, Dienst, deps, my-permissions**

`backend/app/models/power_permissions.py` — nach Zeile 30:
```python
    can_manage_bluetooth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
```

`backend/app/schemas/power_permissions.py` — in `UserPowerPermissionsResponse` und `MyPowerPermissionsResponse` jeweils nach `can_manage_displays: bool = False`:
```python
    can_manage_bluetooth: bool = False
```
In `UserPowerPermissionsUpdate` nach der `can_manage_displays`-Zeile:
```python
    can_manage_bluetooth: Optional[bool] = Field(default=None, description="Allow connecting, removing and pairing Bluetooth devices")
```

`backend/app/services/power_permissions.py`:
- `_ACTION_FIELD_MAP`: nach `"manage_displays": "can_manage_displays",` → `"manage_bluetooth": "can_manage_bluetooth",`
- `get_permissions`: nach `can_manage_displays=perm.can_manage_displays,` → `can_manage_bluetooth=perm.can_manage_bluetooth,`
- `update_permissions`: in **beiden** Dicts `old_values` und `new_values` nach der `can_manage_displays`-Zeile → `"can_manage_bluetooth": perm.can_manage_bluetooth,`; nach dem `can_manage_displays`-Block:
  ```python
      if update.can_manage_bluetooth is not None:
          perm.can_manage_bluetooth = update.can_manage_bluetooth
  ```
- Docstring von `check_permission`: `'manage_displays'` → `'manage_displays', 'manage_bluetooth'`.
- **Nicht** in `_apply_implications` aufnehmen.

`backend/app/api/deps.py` — nach Zeile 405:
```python
require_power_manage_bluetooth = _make_power_dependency("manage_bluetooth")
```

`backend/app/api/routes/sleep.py` — im Admin-Zweig nach `can_manage_displays=True,` → `can_manage_bluetooth=True,`; im Nicht-Admin-Rückgabewert nach `can_manage_displays=perms.can_manage_displays,` → `can_manage_bluetooth=perms.can_manage_bluetooth,`.

- [ ] **Step 4: Migration anlegen**

Zuerst `cd backend ; python -m alembic heads` — muss genau `c3a7f0d51b64 (head)` liefern; sonst den tatsächlichen Head als `down_revision` eintragen.

`backend/alembic/versions/e7c2a9d41f86_add_can_manage_bluetooth_permission.py`:
```python
"""add can_manage_bluetooth permission

Revision ID: e7c2a9d41f86
Revises: c3a7f0d51b64
Create Date: 2026-09-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7c2a9d41f86'
down_revision: Union[str, Sequence[str], None] = 'c3a7f0d51b64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fuegt can_manage_bluetooth zu user_power_permissions hinzu (standardmaessig aus)."""
    op.add_column(
        'user_power_permissions',
        sa.Column('can_manage_bluetooth', sa.Boolean(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    """Entfernt can_manage_bluetooth."""
    op.drop_column('user_power_permissions', 'can_manage_bluetooth')
```

- [ ] **Step 5: Migration anwenden, einzelnen Head bestätigen**

Run: `cd backend ; python -m alembic upgrade head ; python -m alembic heads`
Expected: Upgrade ohne Fehler, `heads` gibt genau `e7c2a9d41f86 (head)` aus.

- [ ] **Step 6: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/test_power_permissions_manage_bluetooth.py tests/test_power_permissions_manage_displays.py -v --no-cov`
Expected: PASS (alle).

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/power_permissions.py backend/alembic/versions/e7c2a9d41f86_add_can_manage_bluetooth_permission.py backend/app/schemas/power_permissions.py backend/app/services/power_permissions.py backend/app/api/deps.py backend/app/api/routes/sleep.py backend/tests/test_power_permissions_manage_bluetooth.py
git commit -m "feat(bluetooth): delegierbares Recht can_manage_bluetooth" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01HbQVSEmXaZU6ZV1CjhCee6"
```

---

## Task 3: Adapter-Einstellung, API-Modelle, reine BlueZ-Parser

**Voraussetzung:** Task 1 hat `backend/tests/plugins/fixtures/bluez_balunode.json` geliefert.

**Files:**
- Modify: `backend/app/core/config.py` (Feld nach Zeile 257, Validator nach `parse_marketplace_public_keys`)
- Create: `backend/app/plugins/installed/bluetooth/__init__.py` (vorläufig nur Docstring)
- Create: `backend/app/plugins/installed/bluetooth/models.py`
- Create: `backend/app/plugins/installed/bluetooth/bluez.py` (Parser-Teil)
- Test: `backend/tests/plugins/test_bluetooth_parser.py`

**Interfaces:**
- Produces (`models.py`): `DeviceKind`, `PairingStage`, `BluetoothAdapter`, `BluetoothDevice`, `BluetoothState`, `PairingSession`, `PowerRequest`, `ConfirmRequest`, `ScanResponse`, `PairStartResponse` — Felder wie unten.
- Produces (`bluez.py`): Konstanten `BLUEZ`, `ADAPTER_IFACE`, `DEVICE_IFACE`, `BATTERY_IFACE`; Dataclasses `AdapterInfo(path, address, name, powered, discovering)`, `DeviceInfo(path, adapter_path, address, name, icon, paired, trusted, connected, battery_percent, rssi)`, `Snapshot(adapters: tuple, devices: tuple)`; Funktionen `unwrap(value) -> Any`, `normalize_address(raw: str) -> Optional[str]`, `device_path(adapter_path: str, address: str) -> str`, `kind_for_icon(icon: Optional[str]) -> str`, `parse_objects(objects: dict) -> Snapshot`, `select_adapter(adapters, configured: str) -> tuple[Optional[AdapterInfo], Optional[str], Optional[str]]` (Adapter, detail, warning).
- Produces (`config.py`): `settings.bluetooth_adapter_address: str` — leer oder großgeschriebene MAC.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

`backend/tests/plugins/test_bluetooth_parser.py`:

```python
"""Parser-Tests gegen die auf BaluNode gemessene GetManagedObjects-Ausgabe.

Die Fixture ist ein Mitschnitt (scripts/debug/bluez_probe.py dump --anonymize),
kein erfundener Payload — neu messen statt von Hand editieren. Die Randfaelle
weiter unten sind bewusst kleine, synthetische Dicts.
"""
import json
from pathlib import Path

import pytest

from app.plugins.installed.bluetooth.bluez import (
    AdapterInfo,
    device_path,
    kind_for_icon,
    normalize_address,
    parse_objects,
    select_adapter,
)

FIXTURE = Path(__file__).parent / "fixtures" / "bluez_balunode.json"


def _snapshot():
    return parse_objects(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _by_name(snapshot, name):
    return next(d for d in snapshot.devices if d.name == name)


class TestMeasuredFixture:
    def test_exactly_one_adapter_the_dongle(self):
        snap = _snapshot()
        assert len(snap.adapters) == 1
        assert snap.adapters[0].path == "/org/bluez/hci0"
        assert snap.adapters[0].address == "AA:AA:AA:AA:AA:01"

    def test_the_xbox_controller_is_a_paired_controller(self):
        xbox = _by_name(_snapshot(), "Xbox Wireless Controller")
        assert kind_for_icon(xbox.icon) == "controller"
        assert xbox.paired is True

    def test_the_jbl_is_paired_audio(self):
        jbl = _by_name(_snapshot(), "JBL TUNE510BT")
        assert kind_for_icon(jbl.icon) == "audio"
        assert jbl.paired is True

    def test_every_device_hangs_off_the_adapter(self):
        snap = _snapshot()
        assert snap.devices
        assert all(d.adapter_path == "/org/bluez/hci0" for d in snap.devices)

    def test_no_real_mac_survived_anonymization(self):
        text = FIXTURE.read_text(encoding="utf-8").upper()
        for real in ("40:8E:2C", "C8:2B:6B", "A0:AD:9F", "40_8E_2C", "C8_2B_6B"):
            assert real not in text


class TestSyntheticEdgeCases:
    def _objects(self, **device_props):
        props = {"Address": "AA:AA:AA:AA:AA:02", "Adapter": "/org/bluez/hci0", "Paired": False}
        props.update(device_props)
        return {
            "/org/bluez/hci0": {"org.bluez.Adapter1": {
                "Address": "AA:AA:AA:AA:AA:01", "Alias": "BaluNode",
                "Powered": True, "Discovering": False,
            }},
            "/org/bluez/hci0/dev_AA_AA_AA_AA_AA_02": {"org.bluez.Device1": props},
        }

    def test_name_falls_back_alias_then_name_then_address(self):
        assert parse_objects(self._objects(Alias="A", Name="N")).devices[0].name == "A"
        assert parse_objects(self._objects(Name="N")).devices[0].name == "N"
        assert parse_objects(self._objects()).devices[0].name == "AA:AA:AA:AA:AA:02"

    def test_battery_comes_from_battery1(self):
        objects = self._objects()
        objects["/org/bluez/hci0/dev_AA_AA_AA_AA_AA_02"]["org.bluez.Battery1"] = {"Percentage": 80}
        assert parse_objects(objects).devices[0].battery_percent == 80

    def test_missing_battery_is_none_not_zero(self):
        assert parse_objects(self._objects()).devices[0].battery_percent is None

    def test_raw_types_are_ignored(self):
        snap = parse_objects(self._objects(ManufacturerData={"6": "0a0b"}, RSSI=-60))
        assert snap.devices[0].rssi == -60
        assert not hasattr(snap.devices[0], "manufacturer_data")

    def test_a_device_with_a_malformed_address_is_skipped(self):
        assert parse_objects(self._objects(Address="nonsense")).devices == ()


@pytest.mark.parametrize("icon,kind", [
    ("input-gaming", "controller"),
    ("audio-headphones", "audio"),
    ("audio-headset", "audio"),
    ("audio-card", "audio"),
    ("input-keyboard", "input"),
    ("input-mouse", "input"),
    ("input-tablet", "input"),
    ("phone", "other"),
    (None, "other"),
])
def test_kind_for_icon(icon, kind):
    assert kind_for_icon(icon) == kind


class TestAddresses:
    def test_normalize_uppercases_and_validates(self):
        assert normalize_address(" aa:bb:cc:dd:ee:0f ") == "AA:BB:CC:DD:EE:0F"
        assert normalize_address("AA-BB-CC-DD-EE-0F") is None
        assert normalize_address("/org/bluez/hci0") is None
        assert normalize_address("") is None

    def test_device_path_is_built_from_the_address(self):
        assert device_path("/org/bluez/hci0", "AA:BB:CC:DD:EE:0F") == \
            "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_0F"


def _adapter(address, path="/org/bluez/hci0"):
    return AdapterInfo(path=path, address=address, name="x", powered=True, discovering=False)


class TestSelectAdapter:
    def test_unset_and_exactly_one_uses_it(self):
        a = _adapter("AA:AA:AA:AA:AA:01")
        assert select_adapter((a,), "") == (a, None, None)

    def test_unset_and_several_refuses_to_guess(self):
        chosen, detail, _ = select_adapter(
            (_adapter("AA:AA:AA:AA:AA:01"), _adapter("AA:AA:AA:AA:AA:09", "/org/bluez/hci1")), "",
        )
        assert chosen is None
        assert "BLUETOOTH_ADAPTER_ADDRESS" in detail

    def test_set_and_present_uses_it_and_warns_about_the_other(self):
        b = _adapter("AA:AA:AA:AA:AA:09", "/org/bluez/hci1")
        chosen, detail, warning = select_adapter((_adapter("AA:AA:AA:AA:AA:01"), b), "AA:AA:AA:AA:AA:09")
        assert chosen == b and detail is None and warning

    def test_set_and_missing_never_falls_back(self):
        chosen, detail, _ = select_adapter((_adapter("AA:AA:AA:AA:AA:01"),), "AA:AA:AA:AA:AA:09")
        assert chosen is None
        assert "AA:AA:AA:AA:AA:09" in detail

    def test_no_adapter_at_all(self):
        chosen, detail, _ = select_adapter((), "")
        assert chosen is None and detail


class TestAdapterSetting:
    def test_empty_is_allowed(self):
        from app.core.config import Settings
        assert Settings(bluetooth_adapter_address="").bluetooth_adapter_address == ""

    def test_a_mac_is_uppercased(self):
        from app.core.config import Settings
        value = Settings(bluetooth_adapter_address="a0:ad:9f:6f:43:f1").bluetooth_adapter_address
        assert value == "A0:AD:9F:6F:43:F1"

    def test_garbage_is_rejected(self):
        from app.core.config import Settings
        with pytest.raises(ValueError):
            Settings(bluetooth_adapter_address="hci0")
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/plugins/test_bluetooth_parser.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.plugins.installed.bluetooth'`.

- [ ] **Step 3: Einstellung in `config.py`**

Nach Zeile 257 (`plugins_marketplace_signature_url …`):
```python
    # Bluetooth-Plugin — MAC des zu benutzenden Adapters. Leer = der einzige
    # vorhandene Adapter; bei mehreren ohne diese Einstellung verweigert das
    # Plugin, statt zu raten (Bonds haengen an der Adapter-MAC).
    bluetooth_adapter_address: str = ""
```

Nach dem Validator `parse_marketplace_public_keys`:
```python
    @field_validator("bluetooth_adapter_address", mode="before")
    def parse_bluetooth_adapter_address(cls, value: object) -> str:
        text = str(value or "").strip().upper()
        if text and not re.fullmatch(r"([0-9A-F]{2}:){5}[0-9A-F]{2}", text):
            raise ValueError("BLUETOOTH_ADAPTER_ADDRESS muss eine MAC-Adresse sein")
        return text
```
Falls `re` in `config.py` noch nicht importiert ist, `import re` zu den Importen oben ergänzen.

- [ ] **Step 4: Paket, Modelle, Parser anlegen**

`backend/app/plugins/installed/bluetooth/__init__.py` (vorläufig — Task 9 füllt die Datei):
```python
"""Bluetooth — bundled Plugin (Router und Plugin-Klasse folgen in Task 9)."""
```
> Ohne `PluginBase`-Unterklasse überspringt der `PluginManager` das Verzeichnis. Beabsichtigt: bis Task 9 verändert nichts die laufende App.

`backend/app/plugins/installed/bluetooth/models.py`:
```python
"""Pydantic-Modelle der Bluetooth-Steuerung.

Die Feldnamen sind der API-Vertrag zum Frontend (``client/src/api/bluetooth.ts``).
Kein BlueZ-Rohtyp (ManufacturerData, AdvertisingData, UUIDs) erscheint hier —
die Modelle uebernehmen nur, was die UI braucht.
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

DeviceKind = Literal["controller", "audio", "input", "other"]

PairingStage = Literal[
    "connecting",
    "display_passkey",
    "display_pin",
    "confirm",
    "succeeded",
    "failed",
    "cancelled",
]


class BluetoothAdapter(BaseModel):
    address: str
    name: str
    powered: bool
    discovering: bool  # auch True, wenn KDE gerade scannt


class BluetoothDevice(BaseModel):
    address: str
    name: str
    kind: DeviceKind
    icon: Optional[str] = None
    paired: bool
    trusted: bool
    connected: bool
    battery_percent: Optional[int] = None
    rssi: Optional[int] = None


class BluetoothState(BaseModel):
    available: bool
    detail: Optional[str] = None
    warning: Optional[str] = None
    adapter: Optional[BluetoothAdapter] = None
    devices: List[BluetoothDevice] = Field(default_factory=list)
    can_pair_here: bool = False
    pairing_active: bool = False


class PairingSession(BaseModel):
    """Stand einer Kopplung — nur fuer den Initiator ausgeliefert."""

    session_id: str
    address: str
    device_name: str
    stage: PairingStage
    code: Optional[str] = None
    entered: Optional[int] = None
    error: Optional[str] = None  # kuratierter Schluessel, nie BlueZ-Rohtext


class PowerRequest(BaseModel):
    powered: bool


class ConfirmRequest(BaseModel):
    accept: bool


class ScanResponse(BaseModel):
    until: datetime


class PairStartResponse(BaseModel):
    session_id: str
```

`backend/app/plugins/installed/bluetooth/bluez.py` (Parser-Teil; Task 4 ergänzt den Client darunter):
```python
"""Die EINZIGE Stelle, die ``org.bluez`` kennt.

Oben reine Funktionen (ohne Bus testbar), darunter ab Task 4 der duenne
Client ueber dem System-Bus. ``parse_objects`` erwartet die bereits per
``unwrap`` entpackte Ausgabe von ``GetManagedObjects``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional, Sequence

try:
    from dbus_next import Variant
except ImportError:  # pragma: no cover — dbus-next ist Abhaengigkeit, nur Rueckfall
    Variant = None  # type: ignore[assignment,misc]

BLUEZ = "org.bluez"
ADAPTER_IFACE = "org.bluez.Adapter1"
DEVICE_IFACE = "org.bluez.Device1"
BATTERY_IFACE = "org.bluez.Battery1"

_MAC = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")
_INPUT_ICONS = frozenset({"input-keyboard", "input-mouse", "input-tablet"})


@dataclass(frozen=True)
class AdapterInfo:
    path: str
    address: str
    name: str
    powered: bool
    discovering: bool


@dataclass(frozen=True)
class DeviceInfo:
    path: str
    adapter_path: str
    address: str
    name: str
    icon: Optional[str]
    paired: bool
    trusted: bool
    connected: bool
    battery_percent: Optional[int]
    rssi: Optional[int]


@dataclass(frozen=True)
class Snapshot:
    adapters: tuple[AdapterInfo, ...]
    devices: tuple[DeviceInfo, ...]


def unwrap(value: Any) -> Any:
    """Loest dbus-next-Variants rekursiv auf; ``ay`` wird zu Hex."""
    if Variant is not None and isinstance(value, Variant):
        return unwrap(value.value)
    if isinstance(value, dict):
        return {str(k): unwrap(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [unwrap(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    return value


def normalize_address(raw: str) -> Optional[str]:
    """Liefert die MAC grossgeschrieben oder ``None``, wenn sie keine ist."""
    text = (raw or "").strip().upper()
    return text if _MAC.match(text) else None


def device_path(adapter_path: str, address: str) -> str:
    """Baut den Objektpfad aus einer bereits GEPRUEFTEN Adresse."""
    return f"{adapter_path}/dev_{address.replace(':', '_')}"


def kind_for_icon(icon: Optional[str]) -> str:
    """Ordnet das von BlueZ gemeldete Icon einer UI-Gruppe zu.

    ``Icon`` meldet das Geraet selbst — die Gruppe ist Anzeige, keine
    Sicherheitsaussage (siehe Spec, Sicherheit Punkt 7).
    """
    if not icon:
        return "other"
    if icon == "input-gaming":
        return "controller"
    if icon.startswith("audio-"):
        return "audio"
    if icon in _INPUT_ICONS:
        return "input"
    return "other"


def _opt_int(value: Any) -> Optional[int]:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def parse_objects(objects: dict) -> Snapshot:
    """Macht aus dem entpackten Objektbaum Adapter- und Geraeteliste."""
    adapters: list[AdapterInfo] = []
    devices: list[DeviceInfo] = []
    for path in sorted(objects):
        ifaces = objects[path] or {}
        adapter = ifaces.get(ADAPTER_IFACE)
        if adapter is not None:
            adapters.append(AdapterInfo(
                path=path,
                address=str(adapter.get("Address", "")).upper(),
                name=str(adapter.get("Alias") or adapter.get("Name") or ""),
                powered=bool(adapter.get("Powered", False)),
                discovering=bool(adapter.get("Discovering", False)),
            ))
        device = ifaces.get(DEVICE_IFACE)
        if device is None:
            continue
        address = normalize_address(str(device.get("Address", "")))
        if address is None:
            continue
        battery = ifaces.get(BATTERY_IFACE) or {}
        devices.append(DeviceInfo(
            path=path,
            adapter_path=str(device.get("Adapter", "")),
            address=address,
            name=str(device.get("Alias") or device.get("Name") or address),
            icon=device.get("Icon") or None,
            paired=bool(device.get("Paired", False)),
            trusted=bool(device.get("Trusted", False)),
            connected=bool(device.get("Connected", False)),
            battery_percent=_opt_int(battery.get("Percentage")),
            rssi=_opt_int(device.get("RSSI")),
        ))
    return Snapshot(adapters=tuple(adapters), devices=tuple(devices))


def select_adapter(
    adapters: Sequence[AdapterInfo], configured: str,
) -> tuple[Optional[AdapterInfo], Optional[str], Optional[str]]:
    """Waehlt den Adapter — nie stilles Umschwenken.

    Returns:
        (adapter, detail, warning). ``adapter`` ist ``None``, wenn nicht
        eindeutig entschieden werden kann; ``detail`` sagt dann, warum.
    """
    wanted = (configured or "").strip().upper()
    if wanted:
        match = next((a for a in adapters if a.address.upper() == wanted), None)
        if match is None:
            return None, f"Adapter {wanted} nicht vorhanden", None
        warning = "Mehrere Bluetooth-Adapter erkannt" if len(adapters) > 1 else None
        return match, None, warning
    if not adapters:
        return None, "Kein Bluetooth-Adapter gefunden", None
    if len(adapters) > 1:
        return None, "Mehrere Bluetooth-Adapter — BLUETOOTH_ADAPTER_ADDRESS setzen", None
    return adapters[0], None, None
```

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/plugins/test_bluetooth_parser.py -v --no-cov`
Expected: PASS. Scheitert ein Fixture-Test, weil die Messung anders aussieht als erwartet (etwa ein anderer Name), **die Annahme im Test prüfen, nicht die Fixture editieren** — und den Befund melden.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py backend/app/plugins/installed/bluetooth/__init__.py backend/app/plugins/installed/bluetooth/models.py backend/app/plugins/installed/bluetooth/bluez.py backend/tests/plugins/test_bluetooth_parser.py
git commit -m "feat(bluetooth): API-Modelle, BlueZ-Parser und feste Adapterwahl" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01HbQVSEmXaZU6ZV1CjhCee6"
```

---

## Task 4: `BlueZClient` — dünne Schicht über dem System-Bus

**Files:**
- Modify: `backend/app/plugins/installed/bluetooth/bluez.py` (Client-Teil unten anhängen, Importe oben ergänzen)
- Test: `backend/tests/plugins/test_bluetooth_client.py`

**Interfaces:**
- Consumes: `BLUEZ`, `unwrap` (Task 3).
- Produces: `BlueZError(name: str, text: str = "")` mit Attributen `.name`, `.text`; Konstanten `TIMEOUT_ERROR = "org.baluhost.Error.Timeout"`, `BUS_ERROR = "org.baluhost.Error.BusUnavailable"`, `CALL_TIMEOUT_SECONDS = 10.0`, `PROPERTIES_IFACE`; Klasse `BlueZClient(bus_factory: Optional[Callable[[], Awaitable[Any]]] = None)` mit
  - `async call(path, interface, member, signature="", body=None, timeout: Optional[float]=CALL_TIMEOUT_SECONDS) -> list`
  - `async get_managed_objects() -> dict` (entpackt)
  - `async set_property(path, interface, name, signature, value) -> None`
  - `async export(path, interface_obj) -> None`, `unexport(path) -> None`

> Low-Level-API von dbus-next (`Message` + `bus.call`) statt Proxy-Objekten: keine Introspektion pro Aufruf, keine Proxy-Lebensdauer, und im Test genügt ein Objekt mit einer `call()`-Methode. `bus.call` kennt kein Timeout — deshalb `asyncio.wait_for`. `Pair()` wird mit `timeout=None` gerufen; dort begrenzt der Koordinator (Task 5).

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

`backend/tests/plugins/test_bluetooth_client.py`:

```python
"""BlueZClient gegen einen Fake-Bus: Nachrichtenform, Fehler, Timeout, Neuaufbau."""
import asyncio

import pytest
from dbus_next import MessageType, Variant

from app.plugins.installed.bluetooth.bluez import (
    ADAPTER_IFACE,
    DEVICE_IFACE,
    TIMEOUT_ERROR,
    BlueZClient,
    BlueZError,
)


class _Reply:
    def __init__(self, message_type, body=(), error_name=None):
        self.message_type = message_type
        self.body = list(body)
        self.error_name = error_name


def _ok(*body):
    return _Reply(MessageType.METHOD_RETURN, body)


class _FakeBus:
    connected = True

    def __init__(self, replies):
        self.sent = []
        self.exported = {}
        self._replies = list(replies)

    async def call(self, msg):
        self.sent.append(msg)
        reply = self._replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        if reply == "hang":
            await asyncio.sleep(10)
        return reply

    def export(self, path, interface):
        self.exported[path] = interface

    def unexport(self, path, interface=None):
        self.exported.pop(path, None)


def _client(bus):
    async def factory():
        return bus
    return BlueZClient(bus_factory=factory)


async def test_managed_objects_are_unwrapped():
    bus = _FakeBus([_ok({"/org/bluez/hci0": {ADAPTER_IFACE: {"Powered": Variant("b", True)}}})])
    objects = await _client(bus).get_managed_objects()
    assert objects["/org/bluez/hci0"][ADAPTER_IFACE]["Powered"] is True
    assert bus.sent[0].member == "GetManagedObjects"
    assert bus.sent[0].destination == "org.bluez"


async def test_an_error_reply_becomes_a_named_bluez_error():
    bus = _FakeBus([_Reply(MessageType.ERROR, ["br-connection-page-timeout"], "org.bluez.Error.Failed")])
    with pytest.raises(BlueZError) as info:
        await _client(bus).call("/org/bluez/hci0/dev_AA_AA_AA_AA_AA_02", DEVICE_IFACE, "Connect")
    assert info.value.name == "org.bluez.Error.Failed"
    assert info.value.text == "br-connection-page-timeout"


async def test_set_property_sends_a_typed_variant():
    bus = _FakeBus([_ok()])
    await _client(bus).set_property("/org/bluez/hci0", ADAPTER_IFACE, "Powered", "b", False)
    msg = bus.sent[0]
    assert (msg.interface, msg.member, msg.signature) == (
        "org.freedesktop.DBus.Properties", "Set", "ssv",
    )
    assert msg.body[0] == ADAPTER_IFACE and msg.body[1] == "Powered"
    assert msg.body[2].signature == "b" and msg.body[2].value is False


async def test_a_hanging_call_times_out_with_a_named_error():
    bus = _FakeBus(["hang"])
    with pytest.raises(BlueZError) as info:
        await _client(bus).call("/org/bluez/hci0", ADAPTER_IFACE, "StartDiscovery", timeout=0.01)
    assert info.value.name == TIMEOUT_ERROR


async def test_a_broken_bus_is_rebuilt_on_the_next_call():
    buses = [_FakeBus([EOFError()]), _FakeBus([_ok({})])]
    built = []

    async def factory():
        built.append(1)
        return buses.pop(0)

    client = BlueZClient(bus_factory=factory)
    with pytest.raises(BlueZError):
        await client.get_managed_objects()
    assert await client.get_managed_objects() == {}
    assert len(built) == 2


async def test_export_and_unexport_use_the_bus():
    bus = _FakeBus([])
    client = _client(bus)
    marker = object()
    await client.export("/org/baluhost/bluetooth/agent", marker)
    assert bus.exported["/org/baluhost/bluetooth/agent"] is marker
    client.unexport("/org/baluhost/bluetooth/agent")
    assert bus.exported == {}
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/plugins/test_bluetooth_client.py -v --no-cov`
Expected: FAIL — `ImportError: cannot import name 'BlueZClient'`.

- [ ] **Step 3: Client implementieren**

Importblock von `bluez.py` ersetzen durch:
```python
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Sequence

try:
    from dbus_next import BusType, Message, MessageType, Variant
    from dbus_next.aio import MessageBus
    _DBUS_AVAILABLE = True
except ImportError:  # pragma: no cover — dbus-next ist Abhaengigkeit, nur Rueckfall
    BusType = Message = MessageType = Variant = MessageBus = None  # type: ignore[assignment,misc]
    _DBUS_AVAILABLE = False

logger = logging.getLogger(__name__)
```

Ans Dateiende anhängen:
```python
# --- Bus-Client --------------------------------------------------------------

CALL_TIMEOUT_SECONDS = 10.0
PROPERTIES_IFACE = "org.freedesktop.DBus.Properties"
OBJECT_MANAGER_IFACE = "org.freedesktop.DBus.ObjectManager"
TIMEOUT_ERROR = "org.baluhost.Error.Timeout"
BUS_ERROR = "org.baluhost.Error.BusUnavailable"


class BlueZError(Exception):
    """Ein Fehler von BlueZ oder vom Bus, mit dem D-Bus-Fehlernamen.

    ``text`` stammt roh von BlueZ. Er wird geloggt, aber NIE an einen Client
    ausgeliefert — die Route bildet ``name`` auf kuratierte Meldungen ab.
    """

    def __init__(self, name: str, text: str = "") -> None:
        super().__init__(f"{name}: {text}" if text else name)
        self.name = name
        self.text = text


async def _connect_system_bus() -> Any:
    if not _DBUS_AVAILABLE:
        raise BlueZError(BUS_ERROR, "dbus-next nicht verfuegbar")
    return await MessageBus(bus_type=BusType.SYSTEM).connect()


class BlueZClient:
    """Eine Bus-Verbindung pro Worker, bei Bedarf und nach Fehlern neu aufgebaut."""

    def __init__(self, bus_factory: Optional[Callable[[], Awaitable[Any]]] = None) -> None:
        self._factory = bus_factory or _connect_system_bus
        self._bus: Any = None
        self._lock = asyncio.Lock()

    async def _get_bus(self) -> Any:
        async with self._lock:
            if self._bus is None or not getattr(self._bus, "connected", True):
                try:
                    self._bus = await self._factory()
                except BlueZError:
                    raise
                except Exception as exc:
                    raise BlueZError(BUS_ERROR, type(exc).__name__) from exc
            return self._bus

    async def call(
        self,
        path: str,
        interface: str,
        member: str,
        signature: str = "",
        body: Optional[Sequence[Any]] = None,
        timeout: Optional[float] = CALL_TIMEOUT_SECONDS,
    ) -> list:
        """Ruft eine Methode an ``org.bluez`` und liefert den Antwort-Rumpf."""
        bus = await self._get_bus()
        msg = Message(
            destination=BLUEZ, path=path, interface=interface, member=member,
            signature=signature, body=list(body or []),
        )
        try:
            pending = bus.call(msg)
            reply = await (asyncio.wait_for(pending, timeout) if timeout is not None else pending)
        except asyncio.TimeoutError as exc:
            raise BlueZError(TIMEOUT_ERROR, member) from exc
        except (OSError, EOFError) as exc:
            self._bus = None
            raise BlueZError(BUS_ERROR, type(exc).__name__) from exc
        if reply.message_type == MessageType.ERROR:
            text = reply.body[0] if reply.body else ""
            raise BlueZError(reply.error_name or "org.bluez.Error.Failed", str(text))
        return list(reply.body or [])

    async def get_managed_objects(self) -> dict:
        body = await self.call("/", OBJECT_MANAGER_IFACE, "GetManagedObjects")
        return unwrap(body[0]) if body else {}

    async def set_property(
        self, path: str, interface: str, name: str, signature: str, value: Any,
    ) -> None:
        await self.call(
            path, PROPERTIES_IFACE, "Set", "ssv", [interface, name, Variant(signature, value)],
        )

    async def export(self, path: str, interface_obj: Any) -> None:
        bus = await self._get_bus()
        bus.export(path, interface_obj)

    def unexport(self, path: str) -> None:
        if self._bus is not None:
            self._bus.unexport(path)
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/plugins/test_bluetooth_client.py tests/plugins/test_bluetooth_parser.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/installed/bluetooth/bluez.py backend/tests/plugins/test_bluetooth_client.py
git commit -m "feat(bluetooth): BlueZClient ueber die Low-Level-API von dbus-next" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01HbQVSEmXaZU6ZV1CjhCee6"
```

---

## Task 5: `pairing.py` — Sperre, SHM-Übergabe, Koordinator

Der eigentliche Kern. Kein D-Bus hier: der Koordinator spricht nur mit einem Backend-Protokoll und dem Prompter; das macht ihn ohne Bus testbar.

**Files:**
- Create: `backend/app/plugins/installed/bluetooth/pairing.py`
- Test: `backend/tests/plugins/test_bluetooth_pairing.py`

**Interfaces:**
- Consumes: `BlueZError`, `DeviceInfo` (Tasks 3/4); `PairingSession` (Task 3); `app.services.monitoring.shm` (`write_shm`, `read_shm`, `SHM_DIR`).
- Produces:
  - Konstanten `STATUS_FILE`, `ANSWER_FILE`, `LOCK_PATH`, `PAIR_TIMEOUT_SECONDS = 60.0`, `HEARTBEAT_SECONDS = 5.0`, `STALE_AFTER_SECONDS = 15.0`, `ANSWER_POLL_SECONDS = 0.25`, `RESULT_DISPLAY_SECONDS = 10.0`, `TERMINAL_STAGES`.
  - `class PairingPrompter(Protocol)`: Attribute `device_path: str`, `device_icon: Optional[str]`; Methoden `show_passkey(passkey: int, entered: int) -> None`, `show_pin(pin: str) -> None`, `async ask_confirmation(passkey: int) -> bool`, `cancelled() -> None`.
  - `class PairBackend(Protocol)`: `async pair(device_path, prompter)`, `async set_trusted(device_path, trusted)`, `async connect(device_path)`, `async cancel_pairing(device_path)`.
  - `OnFinished = Callable[[str, Optional[str]], None]` — `(stage, error)`.
  - `class PairingBusy(Exception)`; `class PairingLock` (`acquire() -> bool`, `release() -> None`).
  - `outcome_for_error(exc: BlueZError) -> tuple[str, Optional[str]]`.
  - `read_session_for(user_id: int) -> Optional[PairingSession]`, `pairing_active() -> bool`, `write_answer(session_id: str, user_id: int, action: str) -> bool` (`action` ∈ `accept`/`reject`/`cancel`).
  - `class PairingCoordinator`: `start(backend, device: DeviceInfo, user_id: int, on_finished: OnFinished) -> str` (wirft `PairingBusy`), `async wait_idle()`, `async aclose()`.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

`backend/tests/plugins/test_bluetooth_pairing.py`:

```python
"""Koppel-Sitzung: Sperre, Uebergabe per SHM, Ablauf — ohne D-Bus."""
import asyncio
import os
import time

import pytest

from app.plugins.installed.bluetooth import pairing
from app.plugins.installed.bluetooth.bluez import BlueZError, DeviceInfo
from app.services.monitoring import shm

DEVICE = DeviceInfo(
    path="/org/bluez/hci0/dev_AA_AA_AA_AA_AA_04", adapter_path="/org/bluez/hci0",
    address="AA:AA:AA:AA:AA:04", name="Dev-Tastatur", icon="input-keyboard",
    paired=False, trusted=False, connected=False, battery_percent=None, rssi=None,
)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(shm, "SHM_DIR", tmp_path / "shm")
    monkeypatch.setattr(pairing, "LOCK_PATH", tmp_path / "pairing.lock")
    monkeypatch.setattr(pairing, "ANSWER_POLL_SECONDS", 0.01)
    monkeypatch.setattr(pairing, "HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr(pairing, "RESULT_DISPLAY_SECONDS", 60.0)


@pytest.fixture
async def coord():
    coordinator = pairing.PairingCoordinator()
    yield coordinator
    await coordinator.aclose()


class _FakeBackend:
    def __init__(self, script):
        self.script = script
        self.trusted = []
        self.connected = []
        self.cancelled = []
        self.cancel_event = asyncio.Event()

    async def pair(self, device_path, prompter):
        await self.script(prompter, self)

    async def set_trusted(self, device_path, trusted):
        self.trusted.append((device_path, trusted))

    async def connect(self, device_path):
        self.connected.append(device_path)

    async def cancel_pairing(self, device_path):
        self.cancelled.append(device_path)
        self.cancel_event.set()


class _Finished:
    def __init__(self):
        self.calls = []

    def __call__(self, stage, error):
        self.calls.append((stage, error))


async def _succeed(prompter, backend):
    return None


async def _until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Bedingung nicht erreicht")


def _stage(user_id=1):
    session = pairing.read_session_for(user_id)
    return session.stage if session else None


def test_the_lock_is_exclusive_and_released():
    first, second = pairing.PairingLock(), pairing.PairingLock()
    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    assert second.acquire() is True
    second.release()


async def test_start_publishes_connecting_for_the_initiator_only(coord):
    release = asyncio.Event()

    async def hold(prompter, backend):
        await release.wait()

    session_id = coord.start(_FakeBackend(hold), DEVICE, 1, _Finished())
    session = pairing.read_session_for(1)
    assert session.session_id == session_id
    assert session.stage == "connecting"
    assert session.address == "AA:AA:AA:AA:AA:04"
    assert pairing.read_session_for(2) is None
    assert pairing.pairing_active() is True
    release.set()
    await coord.wait_idle()


async def test_a_passkey_is_shown_with_progress(coord):
    release = asyncio.Event()

    async def script(prompter, backend):
        prompter.show_passkey(4821, 2)
        await release.wait()

    coord.start(_FakeBackend(script), DEVICE, 1, _Finished())
    await _until(lambda: _stage() == "display_passkey")
    session = pairing.read_session_for(1)
    assert session.code == "004821"
    assert session.entered == 2
    release.set()
    await coord.wait_idle()


async def test_success_trusts_and_connects_and_clears_the_code(coord):
    async def script(prompter, backend):
        prompter.show_passkey(123456, 6)

    backend = _FakeBackend(script)
    finished = _Finished()
    coord.start(backend, DEVICE, 1, finished)
    await coord.wait_idle()
    assert finished.calls == [("succeeded", None)]
    assert backend.trusted == [(DEVICE.path, True)]
    assert backend.connected == [DEVICE.path]
    session = pairing.read_session_for(1)
    assert session.stage == "succeeded"
    assert session.code is None and session.entered is None
    assert pairing.pairing_active() is False


async def test_confirmation_accept_succeeds(coord):
    async def script(prompter, backend):
        if not await prompter.ask_confirmation(654321):
            raise BlueZError("org.bluez.Error.AuthenticationRejected")

    finished = _Finished()
    session_id = coord.start(_FakeBackend(script), DEVICE, 1, finished)
    await _until(lambda: _stage() == "confirm")
    assert pairing.read_session_for(1).code == "654321"
    assert pairing.write_answer(session_id, 1, "accept") is True
    await coord.wait_idle()
    assert finished.calls == [("succeeded", None)]


async def test_confirmation_reject_ends_cancelled(coord):
    async def script(prompter, backend):
        if not await prompter.ask_confirmation(654321):
            raise BlueZError("org.bluez.Error.AuthenticationRejected")

    finished = _Finished()
    session_id = coord.start(_FakeBackend(script), DEVICE, 1, finished)
    await _until(lambda: _stage() == "confirm")
    pairing.write_answer(session_id, 1, "reject")
    await coord.wait_idle()
    assert finished.calls == [("cancelled", None)]


async def test_an_answer_from_another_user_is_refused(coord):
    release = asyncio.Event()

    async def hold(prompter, backend):
        await release.wait()

    session_id = coord.start(_FakeBackend(hold), DEVICE, 1, _Finished())
    assert pairing.write_answer(session_id, 2, "accept") is False
    assert pairing.write_answer("fremde-id", 1, "accept") is False
    release.set()
    await coord.wait_idle()


async def test_cancel_calls_cancel_pairing_and_ends_cancelled(coord):
    async def script(prompter, backend):
        await backend.cancel_event.wait()
        raise BlueZError("org.bluez.Error.AuthenticationCanceled")

    backend = _FakeBackend(script)
    finished = _Finished()
    session_id = coord.start(backend, DEVICE, 1, finished)
    assert pairing.write_answer(session_id, 1, "cancel") is True
    await coord.wait_idle()
    assert backend.cancelled == [DEVICE.path]
    assert finished.calls == [("cancelled", None)]


async def test_a_timeout_cancels_and_fails(coord, monkeypatch):
    monkeypatch.setattr(pairing, "PAIR_TIMEOUT_SECONDS", 0.05)

    async def forever(prompter, backend):
        await asyncio.sleep(10)

    backend = _FakeBackend(forever)
    finished = _Finished()
    coord.start(backend, DEVICE, 1, finished)
    await coord.wait_idle()
    assert finished.calls == [("failed", "timeout")]
    assert backend.cancelled == [DEVICE.path]


async def test_a_second_pairing_is_busy_until_the_first_ends(coord):
    release = asyncio.Event()

    async def hold(prompter, backend):
        await release.wait()

    coord.start(_FakeBackend(hold), DEVICE, 1, _Finished())
    with pytest.raises(pairing.PairingBusy):
        coord.start(_FakeBackend(_succeed), DEVICE, 1, _Finished())
    release.set()
    await coord.wait_idle()
    coord.start(_FakeBackend(_succeed), DEVICE, 1, _Finished())
    await coord.wait_idle()


async def test_a_stale_status_reads_as_nothing(coord, monkeypatch):
    monkeypatch.setattr(pairing, "HEARTBEAT_SECONDS", 60.0)
    release = asyncio.Event()

    async def hold(prompter, backend):
        await release.wait()

    coord.start(_FakeBackend(hold), DEVICE, 1, _Finished())
    old = time.time() - 60
    os.utime(shm.SHM_DIR / pairing.STATUS_FILE, (old, old))
    assert pairing.read_session_for(1) is None
    assert pairing.pairing_active() is False
    release.set()
    await coord.wait_idle()


async def test_already_exists_counts_as_success(coord):
    async def script(prompter, backend):
        raise BlueZError("org.bluez.Error.AlreadyExists")

    finished = _Finished()
    coord.start(_FakeBackend(script), DEVICE, 1, finished)
    await coord.wait_idle()
    assert finished.calls == [("succeeded", None)]


@pytest.mark.parametrize("name,text,expected", [
    ("org.bluez.Error.AuthenticationFailed", "", ("failed", "auth_failed")),
    ("org.bluez.Error.AuthenticationCanceled", "", ("cancelled", None)),
    ("org.bluez.Error.AuthenticationRejected", "", ("cancelled", None)),
    ("org.bluez.Error.AuthenticationTimeout", "", ("failed", "unreachable")),
    ("org.bluez.Error.ConnectionAttemptFailed", "", ("failed", "unreachable")),
    ("org.bluez.Error.Failed", "br-connection-page-timeout", ("failed", "unreachable")),
    ("org.bluez.Error.AlreadyExists", "", ("succeeded", None)),
    ("org.bluez.Error.Failed", "irgendwas", ("failed", "unknown")),
])
def test_outcome_for_error(name, text, expected):
    assert pairing.outcome_for_error(BlueZError(name, text)) == expected
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/plugins/test_bluetooth_pairing.py -v --no-cov`
Expected: FAIL — `ImportError: cannot import name 'pairing'`.

- [ ] **Step 3: `pairing.py` implementieren**

```python
"""Koppel-Sitzung: systemweit hoechstens eine, gehalten von EINEM Worker.

Der Worker, der ``POST /pair`` annimmt, wird Besitzer: er haelt die
Dateisperre, laesst den Agenten auf SEINER Bus-Verbindung laufen und
schreibt den Stand nach ``/dev/shm/baluhost/bluetooth_pairing.json``. Die
UI-Abfragen landen auf beliebigen Workern und lesen nur diese Datei. Der
Rueckweg (Ja/Nein, Abbruch) laeuft ueber eine zweite Datei, die der Besitzer
abfragt.

Die Sperre liegt BEWUSST nicht im SHM-Verzeichnis: ``cleanup_shm()``
(``services/monitoring/shm.py``) loescht dort beim Beenden des
Monitoring-Workers alle Dateien. Eine geloeschte, aber noch gesperrte Datei
liesse einen zweiten Worker eine neue anlegen und sperren — zwei
gleichzeitige Kopplungen. ``/tmp`` ist durch ``PrivateTmp`` pro Unit privat,
aber zwischen den vier Workern derselben Unit geteilt.

Code und PIN werden hier nie geloggt.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Protocol

from app.plugins.installed.bluetooth.bluez import BlueZError, DeviceInfo
from app.plugins.installed.bluetooth.models import PairingSession
from app.services.monitoring import shm

logger = logging.getLogger(__name__)

STATUS_FILE = "bluetooth_pairing.json"
ANSWER_FILE = "bluetooth_pairing_answer.json"
LOCK_PATH = (
    Path(tempfile.gettempdir()) / "baluhost-bluetooth-pairing.lock"
    if sys.platform == "win32"
    else Path("/tmp/baluhost-bluetooth-pairing.lock")
)
PAIR_TIMEOUT_SECONDS = 60.0
HEARTBEAT_SECONDS = 5.0
STALE_AFTER_SECONDS = 15.0
ANSWER_POLL_SECONDS = 0.25
RESULT_DISPLAY_SECONDS = 10.0
TERMINAL_STAGES = frozenset({"succeeded", "failed", "cancelled"})

_UNREACHABLE = frozenset({
    "org.bluez.Error.AuthenticationTimeout",
    "org.bluez.Error.ConnectionAttemptFailed",
    "org.baluhost.Error.Timeout",
})


class PairingPrompter(Protocol):
    """Was der Agent waehrend einer Kopplung braucht."""

    device_path: str
    device_icon: Optional[str]

    def show_passkey(self, passkey: int, entered: int) -> None: ...
    def show_pin(self, pin: str) -> None: ...
    async def ask_confirmation(self, passkey: int) -> bool: ...
    def cancelled(self) -> None: ...


class PairBackend(Protocol):
    async def pair(self, device_path: str, prompter: PairingPrompter) -> None: ...
    async def set_trusted(self, device_path: str, trusted: bool) -> None: ...
    async def connect(self, device_path: str) -> None: ...
    async def cancel_pairing(self, device_path: str) -> None: ...


OnFinished = Callable[[str, Optional[str]], None]


class PairingBusy(Exception):
    """Eine andere Kopplung haelt die Sperre."""


class PairingLock:
    """OS-Dateisperre fuer die Dauer einer Sitzung.

    Der Kernel gibt ``flock`` frei, wenn der Prozess stirbt — die Sperre
    braucht deshalb kein Ablaufdatum und kann nicht verwaisen.
    """

    def __init__(self) -> None:
        self._fd: Optional[int] = None

    def acquire(self) -> bool:
        path = LOCK_PATH  # zur Aufrufzeit gelesen (Tests biegen den Pfad um)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if sys.platform == "win32":
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        self._fd = fd
        return True

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt
                try:
                    os.lseek(self._fd, 0, os.SEEK_SET)
                    msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None


def outcome_for_error(exc: BlueZError) -> tuple[str, Optional[str]]:
    """Bildet einen BlueZ-Fehler auf (stage, kuratierter Fehlerschluessel) ab."""
    if exc.name == "org.bluez.Error.AlreadyExists":
        return "succeeded", None
    if exc.name == "org.bluez.Error.AuthenticationFailed":
        return "failed", "auth_failed"
    if exc.name in ("org.bluez.Error.AuthenticationCanceled", "org.bluez.Error.AuthenticationRejected"):
        return "cancelled", None
    if exc.name in _UNREACHABLE or (exc.name == "org.bluez.Error.Failed" and "timeout" in exc.text):
        return "failed", "unreachable"
    return "failed", "unknown"


def _read_status() -> Optional[dict]:
    return shm.read_shm(STATUS_FILE, max_age_seconds=STALE_AFTER_SECONDS)


def _delete(filename: str) -> None:
    try:
        (shm.SHM_DIR / filename).unlink()
    except OSError:
        pass


def read_session_for(user_id: int) -> Optional[PairingSession]:
    """Liefert die Sitzung NUR dem Initiator; allen anderen ``None``."""
    raw = _read_status()
    if not raw or raw.get("user_id") != user_id:
        return None
    return PairingSession(**{key: raw.get(key) for key in PairingSession.model_fields})


def pairing_active() -> bool:
    raw = _read_status()
    return bool(raw) and raw.get("stage") not in TERMINAL_STAGES


def write_answer(session_id: str, user_id: int, action: str) -> bool:
    """Legt eine Antwort fuer den Besitzer ab — nur fuer die eigene Sitzung."""
    raw = _read_status()
    if not raw or raw.get("session_id") != session_id or raw.get("user_id") != user_id:
        return False
    shm.write_shm(ANSWER_FILE, {
        "session_id": session_id, "user_id": user_id, "action": action, "at": time.time(),
    })
    return True


def _take_answer(session_id: str) -> Optional[str]:
    target = shm.SHM_DIR / ANSWER_FILE
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    _delete(ANSWER_FILE)
    if data.get("session_id") != session_id:
        return None
    return data.get("action")


class ActivePairing:
    """Laufzeit-Zustand im Besitzer-Worker; zugleich der Prompter des Agenten."""

    def __init__(self, session_id: str, user_id: int, device: DeviceInfo) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.device = device
        self.device_path = device.path
        self.device_icon = device.icon
        self.stage = "connecting"
        self.code: Optional[str] = None
        self.entered: Optional[int] = None
        self.error: Optional[str] = None
        self.cancel_requested = False
        self._confirm: Optional[asyncio.Future] = None

    def publish(self) -> None:
        shm.write_shm(STATUS_FILE, {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "address": self.device.address,
            "device_name": self.device.name,
            "stage": self.stage,
            "code": self.code,
            "entered": self.entered,
            "error": self.error,
            "updated_at": time.time(),
        })

    def show_passkey(self, passkey: int, entered: int) -> None:
        self.stage, self.code, self.entered = "display_passkey", f"{passkey:06d}", entered
        self.publish()

    def show_pin(self, pin: str) -> None:
        self.stage, self.code, self.entered = "display_pin", pin, None
        self.publish()

    async def ask_confirmation(self, passkey: int) -> bool:
        self.stage, self.code, self.entered = "confirm", f"{passkey:06d}", None
        self.publish()
        self._confirm = asyncio.get_running_loop().create_future()
        try:
            return await asyncio.wait_for(asyncio.shield(self._confirm), PAIR_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            return False
        finally:
            self._confirm = None

    def resolve_confirmation(self, accept: bool) -> None:
        if self._confirm is not None and not self._confirm.done():
            self._confirm.set_result(accept)

    def cancelled(self) -> None:
        self.resolve_confirmation(False)

    def finish(self, stage: str, error: Optional[str]) -> None:
        # Code und Fortschritt verschwinden mit dem Ende — sie sollen nicht
        # noch zehn Sekunden in der Datei stehen.
        self.stage, self.code, self.entered, self.error = stage, None, None, error
        self.publish()


async def _quietly(action: Awaitable[Any], what: str) -> None:
    try:
        await action
    except BlueZError as exc:
        logger.warning("Bluetooth: %s fehlgeschlagen (%s)", what, exc.name)


class PairingCoordinator:
    """Startet und begleitet Kopplungen dieses Workers."""

    def __init__(self) -> None:
        self._runs: set[asyncio.Task] = set()
        self._cleanups: set[asyncio.Task] = set()

    def start(self, backend: PairBackend, device: DeviceInfo, user_id: int,
              on_finished: OnFinished) -> str:
        lock = PairingLock()
        if not lock.acquire():
            raise PairingBusy()
        session_id = secrets.token_urlsafe(16)
        active = ActivePairing(session_id, user_id, device)
        _delete(ANSWER_FILE)
        active.publish()
        task = asyncio.create_task(self._run(backend, active, lock, on_finished))
        self._runs.add(task)
        task.add_done_callback(self._runs.discard)
        return session_id

    async def _run(self, backend: PairBackend, active: ActivePairing, lock: PairingLock,
                   on_finished: OnFinished) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(active))
        answers = asyncio.create_task(self._watch_answers(backend, active))
        stage, error = "failed", "unknown"
        try:
            try:
                await asyncio.wait_for(backend.pair(active.device_path, active), PAIR_TIMEOUT_SECONDS)
                stage, error = "succeeded", None
            except asyncio.TimeoutError:
                await _quietly(backend.cancel_pairing(active.device_path), "CancelPairing")
                stage, error = "failed", "timeout"
            except BlueZError as exc:
                logger.info("Bluetooth: Kopplung mit %s endete mit %s", active.device.address, exc.name)
                stage, error = outcome_for_error(exc)
            if active.cancel_requested and stage != "succeeded":
                stage, error = "cancelled", None
            if stage == "succeeded":
                # Trusted ist noetig, damit Controller und Eingabegeraete nach
                # dem Aufwachen selbst wieder verbinden.
                await _quietly(backend.set_trusted(active.device_path, True), "Trusted")
                await _quietly(backend.connect(active.device_path), "Connect")
        except Exception:
            logger.exception("Bluetooth: unerwarteter Fehler in der Kopplung")
            stage, error = "failed", "unknown"
        finally:
            heartbeat.cancel()
            answers.cancel()
            active.finish(stage, error)
            lock.release()
            try:
                on_finished(stage, error)
            except Exception:
                logger.exception("Bluetooth: on_finished fehlgeschlagen")
            cleanup = asyncio.create_task(self._expire(active.session_id))
            self._cleanups.add(cleanup)
            cleanup.add_done_callback(self._cleanups.discard)

    async def _heartbeat(self, active: ActivePairing) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            active.publish()

    async def _watch_answers(self, backend: PairBackend, active: ActivePairing) -> None:
        while True:
            await asyncio.sleep(ANSWER_POLL_SECONDS)
            action = _take_answer(active.session_id)
            if action == "cancel":
                active.cancel_requested = True
                active.resolve_confirmation(False)
                await _quietly(backend.cancel_pairing(active.device_path), "CancelPairing")
            elif action in ("accept", "reject"):
                active.resolve_confirmation(action == "accept")

    async def _expire(self, session_id: str) -> None:
        await asyncio.sleep(RESULT_DISPLAY_SECONDS)
        raw = shm.read_shm(STATUS_FILE, max_age_seconds=3600)
        if raw and raw.get("session_id") == session_id:
            _delete(STATUS_FILE)

    async def wait_idle(self) -> None:
        """Wartet, bis alle laufenden Kopplungen dieses Workers beendet sind."""
        if self._runs:
            await asyncio.gather(*list(self._runs), return_exceptions=True)

    async def aclose(self) -> None:
        """Bricht Aufraeum-Tasks ab (Shutdown und Tests)."""
        for task in list(self._runs) + list(self._cleanups):
            task.cancel()
        await asyncio.gather(*list(self._runs), *list(self._cleanups), return_exceptions=True)
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/plugins/test_bluetooth_pairing.py -v --no-cov`
Expected: PASS (auf Windows über `msvcrt`, in der CI über `fcntl`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/installed/bluetooth/pairing.py backend/tests/plugins/test_bluetooth_pairing.py
git commit -m "feat(bluetooth): Koppel-Sitzung mit flock-Sperre und SHM-Uebergabe" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01HbQVSEmXaZU6ZV1CjhCee6"
```

---

## Task 6: `agent.py` — `org.bluez.Agent1`

**Files:**
- Create: `backend/app/plugins/installed/bluetooth/agent.py`
- Test: `backend/tests/plugins/test_bluetooth_agent.py`

**Interfaces:**
- Consumes: `PairingPrompter` (Task 5).
- Produces: `AGENT_PATH = "/org/baluhost/bluetooth/agent"`, `AGENT_CAPABILITY = "KeyboardDisplay"`, `REJECTED = "org.bluez.Error.Rejected"`, Klasse `BluezAgent(prompter: PairingPrompter)` (ein `dbus_next.service.ServiceInterface`) mit den Logikmethoden `handle_display_passkey(device, passkey, entered)`, `handle_display_pin_code(device, pincode)`, `handle_request_pin_code(device) -> str`, `async handle_request_confirmation(device, passkey)`, `handle_request_authorization(device)`, `handle_request_passkey(device) -> int`, `handle_authorize_service(device, uuid)`, `handle_cancel()`.

> **Zwei Fallen, beide an der dbus-next-Quelle belegt:** (1) `@method()` wickelt die Funktion in `def wrapped(*a, **kw): fn(*a, **kw)` — ein direkter Aufruf liefert immer `None`, bei `async` sogar eine nie erwartete Coroutine. Deshalb Logik in `handle_*`, Tests nur dort. (2) dbus-next liest die Signatur per `inspect.signature` aus den Annotationen; mit `from __future__ import annotations` stünde dort `"'o'"`. Deshalb **kein** Future-Import und Typen als Konstanten.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

`backend/tests/plugins/test_bluetooth_agent.py`:

```python
"""Agent-Logik: nur das Sitzungsgeraet, nur erlaubte Ablaeufe."""
import pytest
from dbus_next.errors import DBusError
from dbus_next.service import ServiceInterface

from app.plugins.installed.bluetooth.agent import REJECTED, BluezAgent

SESSION = "/org/bluez/hci0/dev_AA_AA_AA_AA_AA_04"
FOREIGN = "/org/bluez/hci0/dev_AA_AA_AA_AA_AA_09"


class _Prompter:
    def __init__(self, icon="input-keyboard", confirm=True):
        self.device_path = SESSION
        self.device_icon = icon
        self.confirm = confirm
        self.passkeys = []
        self.pins = []
        self.cancel_count = 0

    def show_passkey(self, passkey, entered):
        self.passkeys.append((passkey, entered))

    def show_pin(self, pin):
        self.pins.append(pin)

    async def ask_confirmation(self, passkey):
        return self.confirm

    def cancelled(self):
        self.cancel_count += 1


def _rejected(call):
    with pytest.raises(DBusError) as info:
        call()
    assert info.value.type == REJECTED


class TestOnlyTheSessionDevice:
    def test_display_passkey_for_a_foreign_device_is_rejected(self):
        prompter = _Prompter()
        _rejected(lambda: BluezAgent(prompter).handle_display_passkey(FOREIGN, 1, 0))
        assert prompter.passkeys == []

    def test_authorization_for_a_foreign_device_is_rejected(self):
        _rejected(lambda: BluezAgent(_Prompter()).handle_request_authorization(FOREIGN))

    async def test_confirmation_for_a_foreign_device_is_rejected(self):
        with pytest.raises(DBusError):
            await BluezAgent(_Prompter()).handle_request_confirmation(FOREIGN, 1)


class TestFlows:
    def test_display_passkey_reaches_the_prompter(self):
        prompter = _Prompter()
        BluezAgent(prompter).handle_display_passkey(SESSION, 4821, 3)
        assert prompter.passkeys == [(4821, 3)]

    def test_request_pin_code_generates_a_six_digit_pin_for_a_keyboard(self):
        prompter = _Prompter(icon="input-keyboard")
        pin = BluezAgent(prompter).handle_request_pin_code(SESSION)
        assert len(pin) == 6 and pin.isdigit()
        assert prompter.pins == [pin]

    def test_request_pin_code_is_rejected_for_anything_but_a_keyboard(self):
        _rejected(lambda: BluezAgent(_Prompter(icon="audio-headphones")).handle_request_pin_code(SESSION))

    def test_the_pin_comes_from_secrets(self, monkeypatch):
        import app.plugins.installed.bluetooth.agent as agent_module
        monkeypatch.setattr(agent_module.secrets, "randbelow", lambda n: 42)
        assert BluezAgent(_Prompter()).handle_request_pin_code(SESSION) == "000042"

    async def test_an_accepted_confirmation_returns_normally(self):
        await BluezAgent(_Prompter(confirm=True)).handle_request_confirmation(SESSION, 123456)

    async def test_a_refused_confirmation_is_rejected(self):
        with pytest.raises(DBusError) as info:
            await BluezAgent(_Prompter(confirm=False)).handle_request_confirmation(SESSION, 123456)
        assert info.value.type == REJECTED

    def test_authorization_for_the_session_device_is_accepted(self):
        BluezAgent(_Prompter()).handle_request_authorization(SESSION)

    def test_request_passkey_is_always_rejected(self):
        _rejected(lambda: BluezAgent(_Prompter()).handle_request_passkey(SESSION))

    def test_authorize_service_is_always_rejected(self):
        _rejected(lambda: BluezAgent(_Prompter()).handle_authorize_service(SESSION, "0000110b"))

    def test_cancel_reaches_the_prompter(self):
        prompter = _Prompter()
        BluezAgent(prompter).handle_cancel()
        assert prompter.cancel_count == 1


class TestExportedSignatures:
    """Faengt den Future-Import und falsche Annotationen ab, bevor BlueZ es tut."""

    def test_the_dbus_methods_carry_the_bluez_signatures(self):
        methods = {m.name: m for m in ServiceInterface._get_methods(BluezAgent(_Prompter()))}
        assert (methods["RequestPinCode"].in_signature, methods["RequestPinCode"].out_signature) == ("o", "s")
        assert methods["DisplayPasskey"].in_signature == "ouq"
        assert (methods["RequestPasskey"].in_signature, methods["RequestPasskey"].out_signature) == ("o", "u")
        assert methods["RequestConfirmation"].in_signature == "ou"
        assert methods["AuthorizeService"].in_signature == "os"
        assert methods["DisplayPinCode"].in_signature == "os"
        assert {"Release", "Cancel", "RequestAuthorization"} <= set(methods)
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/plugins/test_bluetooth_agent.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: … agent`.

- [ ] **Step 3: `agent.py` implementieren**

```python
"""org.bluez.Agent1 — beantwortet Rueckfragen von BlueZ waehrend EINER Kopplung.

Der Agent wird pro Kopplung angemeldet (``RegisterAgent`` mit
``KeyboardDisplay``, NIE ``RequestDefaultAgent``) und danach wieder
abgemeldet. BlueZ fragt einen solchen Agenten nur zu Kopplungen, die dieselbe
Bus-Verbindung per ``Pair()`` angestossen hat; eingehende Anfragen bleiben
bei KDE (BlueDevil).

NB 1: kein ``from __future__ import annotations``. dbus-next liest die
D-Bus-Signaturen aus den Annotationen; PEP 563 machte aus ``'o'`` die
Zeichenkette ``"'o'"``. Die Typen stehen als Konstanten da, weil pyflakes ein
String-Literal wie ``'o'`` als undefinierten Namen meldet.

NB 2: dbus-nexts ``@method()`` verwirft den Rueckgabewert, wenn man die
dekorierte Methode direkt aufruft. Die Logik steckt in ``handle_*``; die
dekorierten Methoden sind nur Huellen.
"""
import logging
import secrets

from dbus_next.errors import DBusError
from dbus_next.service import ServiceInterface, method

from app.plugins.installed.bluetooth.pairing import PairingPrompter

logger = logging.getLogger(__name__)

AGENT_PATH = "/org/baluhost/bluetooth/agent"
AGENT_CAPABILITY = "KeyboardDisplay"
REJECTED = "org.bluez.Error.Rejected"

OBJ = "o"
STR = "s"
U32 = "u"
U16 = "q"


class BluezAgent(ServiceInterface):
    """Antwortet ausschliesslich zum Geraet der laufenden Sitzung."""

    def __init__(self, prompter: PairingPrompter) -> None:
        super().__init__("org.bluez.Agent1")
        self._prompter = prompter

    def _require_session_device(self, device: str) -> None:
        if device != self._prompter.device_path:
            logger.warning("Bluetooth-Agent: Anfrage fuer fremdes Geraet abgelehnt")
            raise DBusError(REJECTED, "Nicht Teil dieser Kopplung")

    # --- Logik -----------------------------------------------------------

    def handle_display_passkey(self, device: str, passkey: int, entered: int) -> None:
        self._require_session_device(device)
        self._prompter.show_passkey(int(passkey), int(entered))

    def handle_display_pin_code(self, device: str, pincode: str) -> None:
        self._require_session_device(device)
        self._prompter.show_pin(str(pincode))

    def handle_request_pin_code(self, device: str) -> str:
        self._require_session_device(device)
        if self._prompter.device_icon != "input-keyboard":
            # Legacy-Geraete mit fester PIN ("0000") gehoeren nicht zu v1.
            raise DBusError(REJECTED, "Legacy-Geraet mit fester PIN nicht unterstuetzt")
        pin = f"{secrets.randbelow(10**6):06d}"
        self._prompter.show_pin(pin)
        return pin

    async def handle_request_confirmation(self, device: str, passkey: int) -> None:
        self._require_session_device(device)
        if not await self._prompter.ask_confirmation(int(passkey)):
            raise DBusError(REJECTED, "Abgelehnt")

    def handle_request_authorization(self, device: str) -> None:
        # Der Klick auf genau dieses Geraet ist die Zustimmung.
        self._require_session_device(device)

    def handle_request_passkey(self, device: str) -> int:
        raise DBusError(REJECTED, "Passkey-Eingabe am Rechner nicht unterstuetzt")

    def handle_authorize_service(self, device: str, uuid: str) -> None:
        raise DBusError(REJECTED, "Dienstfreigaben entscheidet dieser Agent nicht")

    def handle_cancel(self) -> None:
        self._prompter.cancelled()

    # --- D-Bus-Huellen ---------------------------------------------------

    @method()
    def Release(self):
        pass

    @method()
    def RequestPinCode(self, device: OBJ) -> STR:
        return self.handle_request_pin_code(device)

    @method()
    def DisplayPinCode(self, device: OBJ, pincode: STR):
        self.handle_display_pin_code(device, pincode)

    @method()
    def RequestPasskey(self, device: OBJ) -> U32:
        return self.handle_request_passkey(device)

    @method()
    def DisplayPasskey(self, device: OBJ, passkey: U32, entered: U16):
        self.handle_display_passkey(device, passkey, entered)

    @method()
    async def RequestConfirmation(self, device: OBJ, passkey: U32):
        await self.handle_request_confirmation(device, passkey)

    @method()
    def RequestAuthorization(self, device: OBJ):
        self.handle_request_authorization(device)

    @method()
    def AuthorizeService(self, device: OBJ, uuid: STR):
        self.handle_authorize_service(device, uuid)

    @method()
    def Cancel(self):
        self.handle_cancel()
```

- [ ] **Step 4: Tests und Lint**

Run: `cd backend ; python -m pytest tests/plugins/test_bluetooth_agent.py -v --no-cov ; python -m ruff check app/plugins/installed/bluetooth/agent.py`
Expected: PASS, `All checks passed!`

> `ServiceInterface._get_methods` ist private API von dbus-next. Heißt sie in der installierten Version anders (`python -c "import dbus_next.service as s; print([n for n in dir(s.ServiceInterface) if 'method' in n.lower()])"`), den Test auf den dortigen Namen umstellen — **nicht** streichen: er ist die einzige Stelle, die einen versehentlichen Future-Import in `agent.py` vor dem ersten echten Export bemerkt.

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/installed/bluetooth/agent.py backend/tests/plugins/test_bluetooth_agent.py
git commit -m "feat(bluetooth): Agent, der nur zum Geraet der eigenen Kopplung antwortet" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01HbQVSEmXaZU6ZV1CjhCee6"
```

---

## Task 7: `backend.py` — Protokoll, Dev-Backend, BlueZ-Backend

**Files:**
- Create: `backend/app/plugins/installed/bluetooth/backend.py`
- Test: `backend/tests/plugins/test_bluetooth_backend.py`

**Interfaces:**
- Consumes: `AdapterInfo`, `DeviceInfo`, `Snapshot`, `BlueZClient`, `BlueZError`, `device_path`, `ADAPTER_IFACE`, `DEVICE_IFACE` (Tasks 3/4); `PairingPrompter` (Task 5); `BluezAgent`, `AGENT_PATH`, `AGENT_CAPABILITY` (Task 6).
- Produces: `class BluetoothBackend(Protocol)` mit `async snapshot() -> Snapshot`, `async set_powered(adapter_path, powered)`, `async start_scan(adapter_path)`, `async stop_scan(adapter_path)`, `async connect(device_path)`, `async disconnect(device_path)`, `async remove(adapter_path, device_path)`, `async pair(device_path, prompter)`, `async set_trusted(device_path, trusted)`, `async cancel_pairing(device_path)`; `DEV_ADAPTER_PATH = "/org/bluez/hci0"`; `DevBluetoothBackend(step_seconds: float = 1.0, passkey: Optional[int] = None)`; `BlueZBackend(client: Optional[BlueZClient] = None)`. Fehler werden als `BlueZError` mit echten BlueZ-Namen geworfen — auch im Dev-Backend, damit die Fehlerabbildung in beiden gleich greift.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

`backend/tests/plugins/test_bluetooth_backend.py`:

```python
"""Dev-Backend (Zustand im Speicher) und BlueZ-Backend (Aufrufreihenfolge)."""
import pytest

from app.plugins.installed.bluetooth.backend import (
    DEV_ADAPTER_PATH,
    BlueZBackend,
    DevBluetoothBackend,
)
from app.plugins.installed.bluetooth.bluez import BlueZError, device_path

KEYBOARD = device_path(DEV_ADAPTER_PATH, "AA:AA:AA:AA:AA:04")
MOUSE = device_path(DEV_ADAPTER_PATH, "AA:AA:AA:AA:AA:05")
PHONE = device_path(DEV_ADAPTER_PATH, "AA:AA:AA:AA:AA:06")
XBOX = device_path(DEV_ADAPTER_PATH, "AA:AA:AA:AA:AA:02")


class _Prompter:
    def __init__(self, confirm=True):
        self.device_path = ""
        self.device_icon = None
        self.confirm = confirm
        self.passkeys = []

    def show_passkey(self, passkey, entered):
        self.passkeys.append((passkey, entered))

    def show_pin(self, pin):
        pass

    async def ask_confirmation(self, passkey):
        return self.confirm

    def cancelled(self):
        pass


def _names(snapshot):
    return {d.name for d in snapshot.devices}


class TestDevBackend:
    async def test_it_starts_with_the_two_paired_devices(self):
        snap = await DevBluetoothBackend(step_seconds=0).snapshot()
        assert len(snap.adapters) == 1
        assert all(d.paired for d in snap.devices)
        assert len(snap.devices) == 2

    async def test_a_scan_reveals_three_unpaired_devices_and_stop_drops_them(self):
        backend = DevBluetoothBackend(step_seconds=0)
        await backend.start_scan(DEV_ADAPTER_PATH)
        snap = await backend.snapshot()
        assert {"Dev-Tastatur", "Dev-Maus", "Dev-Telefon"} <= _names(snap)
        assert snap.adapters[0].discovering is True
        await backend.stop_scan(DEV_ADAPTER_PATH)
        assert "Dev-Maus" not in _names(await backend.snapshot())

    async def test_the_keyboard_shows_a_passkey_with_rising_progress(self):
        backend = DevBluetoothBackend(step_seconds=0, passkey=482913)
        await backend.start_scan(DEV_ADAPTER_PATH)
        prompter = _Prompter()
        await backend.pair(KEYBOARD, prompter)
        assert prompter.passkeys[0] == (482913, 0)
        assert prompter.passkeys[-1] == (482913, 6)
        paired = next(d for d in (await backend.snapshot()).devices if d.path == KEYBOARD)
        assert paired.paired is True

    async def test_a_refused_confirmation_raises_rejected(self):
        backend = DevBluetoothBackend(step_seconds=0)
        await backend.start_scan(DEV_ADAPTER_PATH)
        with pytest.raises(BlueZError) as info:
            await backend.pair(PHONE, _Prompter(confirm=False))
        assert info.value.name == "org.bluez.Error.AuthenticationRejected"

    async def test_pairing_a_paired_device_is_already_exists(self):
        with pytest.raises(BlueZError) as info:
            await DevBluetoothBackend(step_seconds=0).pair(XBOX, _Prompter())
        assert info.value.name == "org.bluez.Error.AlreadyExists"

    async def test_scanning_with_the_adapter_off_is_not_ready(self):
        backend = DevBluetoothBackend(step_seconds=0)
        await backend.set_powered(DEV_ADAPTER_PATH, False)
        with pytest.raises(BlueZError) as info:
            await backend.start_scan(DEV_ADAPTER_PATH)
        assert info.value.name == "org.bluez.Error.NotReady"

    async def test_connect_disconnect_remove(self):
        backend = DevBluetoothBackend(step_seconds=0)
        await backend.disconnect(XBOX)
        assert not next(d for d in (await backend.snapshot()).devices if d.path == XBOX).connected
        await backend.connect(XBOX)
        await backend.remove(DEV_ADAPTER_PATH, XBOX)
        assert XBOX not in {d.path for d in (await backend.snapshot()).devices}
        with pytest.raises(BlueZError) as info:
            await backend.remove(DEV_ADAPTER_PATH, XBOX)
        assert info.value.name == "org.bluez.Error.DoesNotExist"


class _RecordingClient:
    def __init__(self, fail_pair=None):
        self.calls = []
        self.fail_pair = fail_pair

    async def call(self, path, interface, member, signature="", body=None, timeout=10.0):
        self.calls.append((path, member, list(body or []), timeout))
        if member == "Pair" and self.fail_pair:
            raise BlueZError(self.fail_pair)
        return []

    async def set_property(self, path, interface, name, signature, value):
        self.calls.append((path, f"Set:{name}", [signature, value], None))

    async def export(self, path, interface_obj):
        self.calls.append((path, "export", [], None))

    def unexport(self, path):
        self.calls.append((path, "unexport", [], None))

    async def get_managed_objects(self):
        return {}


class TestBlueZBackend:
    async def test_pair_registers_the_agent_first_and_always_cleans_up(self):
        client = _RecordingClient(fail_pair="org.bluez.Error.AuthenticationFailed")
        with pytest.raises(BlueZError):
            await BlueZBackend(client).pair(KEYBOARD, _Prompter())
        members = [c[1] for c in client.calls]
        assert members == ["export", "RegisterAgent", "Pair", "UnregisterAgent", "unexport"]
        register = next(c for c in client.calls if c[1] == "RegisterAgent")
        assert register[2] == ["/org/baluhost/bluetooth/agent", "KeyboardDisplay"]
        pair = next(c for c in client.calls if c[1] == "Pair")
        assert pair[3] is None  # das Zeitlimit setzt der Koordinator

    async def test_no_default_agent_is_ever_requested(self):
        client = _RecordingClient()
        await BlueZBackend(client).pair(KEYBOARD, _Prompter())
        assert "RequestDefaultAgent" not in [c[1] for c in client.calls]

    async def test_scan_sets_the_filter_before_starting(self):
        client = _RecordingClient()
        await BlueZBackend(client).start_scan(DEV_ADAPTER_PATH)
        assert [c[1] for c in client.calls] == ["SetDiscoveryFilter", "StartDiscovery"]
        assert client.calls[0][2][0]["Transport"].value == "auto"

    async def test_power_and_trust_are_property_writes(self):
        client = _RecordingClient()
        backend = BlueZBackend(client)
        await backend.set_powered(DEV_ADAPTER_PATH, False)
        await backend.set_trusted(KEYBOARD, True)
        assert client.calls[0][1] == "Set:Powered" and client.calls[0][2] == ["b", False]
        assert client.calls[1][1] == "Set:Trusted" and client.calls[1][2] == ["b", True]

    async def test_remove_goes_through_the_adapter(self):
        client = _RecordingClient()
        await BlueZBackend(client).remove(DEV_ADAPTER_PATH, KEYBOARD)
        assert client.calls == [(DEV_ADAPTER_PATH, "RemoveDevice", [KEYBOARD], 10.0)]
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/plugins/test_bluetooth_backend.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: … backend`.

- [ ] **Step 3: `backend.py` implementieren**

```python
"""Bluetooth-Backends: ein Protokoll, eine Attrappe, eine echte Umsetzung.

Aufbau wie ``audio_control/backend.py``. Beide Backends werfen ``BlueZError``
mit echten BlueZ-Fehlernamen, damit die Fehlerabbildung im Service fuer Dev
und Produktion dieselbe ist.
"""
from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass
from typing import Dict, Optional, Protocol

from app.plugins.installed.bluetooth.agent import AGENT_CAPABILITY, AGENT_PATH, BluezAgent
from app.plugins.installed.bluetooth.bluez import (
    ADAPTER_IFACE,
    CALL_TIMEOUT_SECONDS,
    DEVICE_IFACE,
    AdapterInfo,
    BlueZClient,
    BlueZError,
    DeviceInfo,
    Snapshot,
    device_path,
    parse_objects,
)
from app.plugins.installed.bluetooth.pairing import PairingPrompter

try:
    from dbus_next import Variant
except ImportError:  # pragma: no cover
    Variant = None  # type: ignore[assignment,misc]

CONNECT_TIMEOUT_SECONDS = 30.0
AGENT_MANAGER_PATH = "/org/bluez"
AGENT_MANAGER_IFACE = "org.bluez.AgentManager1"
DEV_ADAPTER_PATH = "/org/bluez/hci0"


class BluetoothBackend(Protocol):
    async def snapshot(self) -> Snapshot: ...
    async def set_powered(self, adapter_path: str, powered: bool) -> None: ...
    async def start_scan(self, adapter_path: str) -> None: ...
    async def stop_scan(self, adapter_path: str) -> None: ...
    async def connect(self, device_path: str) -> None: ...
    async def disconnect(self, device_path: str) -> None: ...
    async def remove(self, adapter_path: str, device_path: str) -> None: ...
    async def pair(self, device_path: str, prompter: PairingPrompter) -> None: ...
    async def set_trusted(self, device_path: str, trusted: bool) -> None: ...
    async def cancel_pairing(self, device_path: str) -> None: ...


@dataclass
class _DevDevice:
    address: str
    name: str
    icon: str
    flow: str  # "none" | "passkey" | "confirm"
    paired: bool = False
    trusted: bool = False
    connected: bool = False
    battery: Optional[int] = None


def _dev_paired() -> list[_DevDevice]:
    return [
        _DevDevice("AA:AA:AA:AA:AA:02", "Xbox Wireless Controller", "input-gaming", "none",
                   paired=True, trusted=True, connected=True, battery=80),
        _DevDevice("AA:AA:AA:AA:AA:03", "JBL TUNE510BT", "audio-headphones", "none",
                   paired=True, trusted=True),
    ]


def _dev_found() -> list[_DevDevice]:
    return [
        _DevDevice("AA:AA:AA:AA:AA:04", "Dev-Tastatur", "input-keyboard", "passkey"),
        _DevDevice("AA:AA:AA:AA:AA:05", "Dev-Maus", "input-mouse", "none"),
        _DevDevice("AA:AA:AA:AA:AA:06", "Dev-Telefon", "phone", "confirm"),
    ]


class DevBluetoothBackend:
    """Zustand im Speicher, damit jeder UI-Pfad auf Windows bedienbar ist."""

    def __init__(self, step_seconds: float = 1.0, passkey: Optional[int] = None) -> None:
        self._step = step_seconds
        self._passkey = passkey
        self._powered = True
        self._discovering = False
        self._devices: Dict[str, _DevDevice] = {
            device_path(DEV_ADAPTER_PATH, d.address): d for d in _dev_paired()
        }
        self._cancelled: set[str] = set()

    def _get(self, path: str) -> _DevDevice:
        device = self._devices.get(path)
        if device is None:
            raise BlueZError("org.bluez.Error.DoesNotExist", "Dev: unbekanntes Geraet")
        return device

    def _require_powered(self) -> None:
        if not self._powered:
            raise BlueZError("org.bluez.Error.NotReady", "Dev: Adapter aus")

    async def snapshot(self) -> Snapshot:
        adapter = AdapterInfo(
            path=DEV_ADAPTER_PATH, address="AA:AA:AA:AA:AA:01", name="BaluNode (Dev)",
            powered=self._powered, discovering=self._discovering,
        )
        devices = tuple(
            DeviceInfo(
                path=path, adapter_path=DEV_ADAPTER_PATH, address=d.address, name=d.name,
                icon=d.icon, paired=d.paired, trusted=d.trusted, connected=d.connected,
                battery_percent=d.battery if d.connected else None,
                rssi=None if d.paired else -55,
            )
            for path, d in sorted(self._devices.items())
        )
        return Snapshot(adapters=(adapter,), devices=devices)

    async def set_powered(self, adapter_path: str, powered: bool) -> None:
        self._powered = powered
        if not powered:
            self._discovering = False
            for device in self._devices.values():
                device.connected = False

    async def start_scan(self, adapter_path: str) -> None:
        self._require_powered()
        self._discovering = True
        for device in _dev_found():
            self._devices.setdefault(device_path(DEV_ADAPTER_PATH, device.address), device)

    async def stop_scan(self, adapter_path: str) -> None:
        self._discovering = False
        self._devices = {p: d for p, d in self._devices.items() if d.paired}

    async def connect(self, device_path: str) -> None:
        self._require_powered()
        device = self._get(device_path)
        if not device.paired:
            raise BlueZError("org.bluez.Error.Failed", "Dev: nicht gekoppelt")
        device.connected = True

    async def disconnect(self, device_path: str) -> None:
        self._get(device_path).connected = False

    async def remove(self, adapter_path: str, device_path: str) -> None:
        self._get(device_path)
        del self._devices[device_path]

    async def pair(self, device_path: str, prompter: PairingPrompter) -> None:
        self._require_powered()
        device = self._get(device_path)
        if device.paired:
            raise BlueZError("org.bluez.Error.AlreadyExists", "Dev: schon gekoppelt")
        self._cancelled.discard(device_path)
        key = self._passkey if self._passkey is not None else secrets.randbelow(10**6)
        if device.flow == "passkey":
            for entered in range(7):
                self._raise_if_cancelled(device_path)
                prompter.show_passkey(key, entered)
                await asyncio.sleep(self._step)
        elif device.flow == "confirm":
            accepted = await prompter.ask_confirmation(key)
            self._raise_if_cancelled(device_path)
            if not accepted:
                raise BlueZError("org.bluez.Error.AuthenticationRejected", "Dev: abgelehnt")
        else:
            await asyncio.sleep(self._step)
        self._raise_if_cancelled(device_path)
        device.paired = True

    def _raise_if_cancelled(self, device_path: str) -> None:
        if device_path in self._cancelled:
            raise BlueZError("org.bluez.Error.AuthenticationCanceled", "Dev: abgebrochen")

    async def set_trusted(self, device_path: str, trusted: bool) -> None:
        self._get(device_path).trusted = trusted

    async def cancel_pairing(self, device_path: str) -> None:
        self._cancelled.add(device_path)


class BlueZBackend:
    """Spricht ueber ``BlueZClient`` mit dem echten BlueZ auf dem System-Bus.

    Der Dienst-User muss in der Gruppe ``bluetooth`` sein (D-Bus-Policy von
    BlueZ); auf BaluNode gemessen, kein sudo.
    """

    def __init__(self, client: Optional[BlueZClient] = None) -> None:
        self._client = client or BlueZClient()

    async def snapshot(self) -> Snapshot:
        return parse_objects(await self._client.get_managed_objects())

    async def set_powered(self, adapter_path: str, powered: bool) -> None:
        await self._client.set_property(adapter_path, ADAPTER_IFACE, "Powered", "b", powered)

    async def start_scan(self, adapter_path: str) -> None:
        await self._client.call(
            adapter_path, ADAPTER_IFACE, "SetDiscoveryFilter", "a{sv}",
            [{"Transport": Variant("s", "auto")}],
        )
        await self._client.call(adapter_path, ADAPTER_IFACE, "StartDiscovery")

    async def stop_scan(self, adapter_path: str) -> None:
        await self._client.call(adapter_path, ADAPTER_IFACE, "StopDiscovery")

    async def connect(self, device_path: str) -> None:
        await self._client.call(device_path, DEVICE_IFACE, "Connect", timeout=CONNECT_TIMEOUT_SECONDS)

    async def disconnect(self, device_path: str) -> None:
        await self._client.call(device_path, DEVICE_IFACE, "Disconnect", timeout=CONNECT_TIMEOUT_SECONDS)

    async def remove(self, adapter_path: str, device_path: str) -> None:
        await self._client.call(
            adapter_path, ADAPTER_IFACE, "RemoveDevice", "o", [device_path],
            timeout=CALL_TIMEOUT_SECONDS,
        )

    async def pair(self, device_path: str, prompter: PairingPrompter) -> None:
        """Meldet den Agenten an, koppelt und meldet ihn in JEDEM Fall wieder ab.

        Kein ``RequestDefaultAgent``: dieser Agent bedient nur Kopplungen,
        die diese Verbindung selbst anstoesst. Das Zeitlimit setzt der
        Koordinator (``timeout=None`` hier).
        """
        await self._client.export(AGENT_PATH, BluezAgent(prompter))
        try:
            await self._client.call(
                AGENT_MANAGER_PATH, AGENT_MANAGER_IFACE, "RegisterAgent", "os",
                [AGENT_PATH, AGENT_CAPABILITY],
            )
            try:
                await self._client.call(device_path, DEVICE_IFACE, "Pair", timeout=None)
            finally:
                try:
                    await self._client.call(
                        AGENT_MANAGER_PATH, AGENT_MANAGER_IFACE, "UnregisterAgent", "o", [AGENT_PATH],
                    )
                except BlueZError:
                    pass
        finally:
            self._client.unexport(AGENT_PATH)

    async def set_trusted(self, device_path: str, trusted: bool) -> None:
        await self._client.set_property(device_path, DEVICE_IFACE, "Trusted", "b", trusted)

    async def cancel_pairing(self, device_path: str) -> None:
        await self._client.call(device_path, DEVICE_IFACE, "CancelPairing")
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/plugins/test_bluetooth_backend.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/installed/bluetooth/backend.py backend/tests/plugins/test_bluetooth_backend.py
git commit -m "feat(bluetooth): Dev- und BlueZ-Backend" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01HbQVSEmXaZU6ZV1CjhCee6"
```

---

## Task 8: `service.py` — Validierung, LAN-Prüfung, Fehlerabbildung, Scan-Fenster

**Files:**
- Create: `backend/app/plugins/installed/bluetooth/service.py`
- Test: `backend/tests/plugins/test_bluetooth_service.py`

**Interfaces:**
- Consumes: alles aus Tasks 3–7; `settings.bluetooth_adapter_address`; `is_private_or_local_ip`; `ServiceError`-Unterklassen aus `app.core.exceptions`.
- Produces:
  - `SCAN_SECONDS = 30.0`; `DeviceFinished = Callable[[DeviceInfo, str, Optional[str]], None]`
  - `action_error(exc: BlueZError) -> ServiceError`
  - `class BluetoothService(backend=None, coordinator=None, scan_seconds=SCAN_SECONDS)` mit
    `async get_state(client_host: Optional[str]) -> BluetoothState`,
    `async set_powered(powered: bool) -> None`,
    `async start_scan() -> datetime`,
    `async connect(address: str) -> None`, `async disconnect(address: str) -> None`,
    `async remove(address: str) -> DeviceInfo`,
    `async start_pairing(address: str, user_id: int, client_host: Optional[str], on_finished: DeviceFinished) -> str`,
    `pairing_status(user_id: int) -> Optional[PairingSession]`,
    `answer(session_id: str, user_id: int, action: str, client_host: Optional[str]) -> None`,
    `async wait_pairings()`, `async aclose()`.
  - `get_bluetooth_service() -> BluetoothService` (Modul-Singleton, pro Worker).
- **Alle Fehler als `ServiceError`-Unterklassen** mit deutschen, kuratierten Meldungen; BlueZ-Rohtext geht nur ins Log.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

`backend/tests/plugins/test_bluetooth_service.py`:

```python
"""Service: Adapterwahl, LAN-Pruefung, Validierung vor jedem Backend-Aufruf."""
import asyncio

import pytest

from app.core.config import settings
from app.core.exceptions import (
    BadGatewayError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.plugins.installed.bluetooth import pairing
from app.plugins.installed.bluetooth import service as service_module
from app.plugins.installed.bluetooth.backend import DevBluetoothBackend
from app.plugins.installed.bluetooth.bluez import BlueZError
from app.plugins.installed.bluetooth.service import BluetoothService
from app.services.monitoring import shm

LAN = "192.168.1.10"
PUBLIC = "203.0.113.7"
KEYBOARD = "AA:AA:AA:AA:AA:04"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(shm, "SHM_DIR", tmp_path / "shm")
    monkeypatch.setattr(pairing, "LOCK_PATH", tmp_path / "pairing.lock")
    monkeypatch.setattr(pairing, "ANSWER_POLL_SECONDS", 0.01)
    monkeypatch.setattr(pairing, "RESULT_DISPLAY_SECONDS", 60.0)
    monkeypatch.setattr(service_module, "is_private_or_local_ip", lambda host: host == LAN)
    monkeypatch.setattr(settings, "bluetooth_adapter_address", "")


@pytest.fixture
async def backend():
    return DevBluetoothBackend(step_seconds=0, passkey=482913)


@pytest.fixture
async def svc(backend):
    # Langes Scan-Fenster: ein kurzes wuerde ungekoppelte Funde mitten in einer
    # laufenden Kopplung wieder entfernen. TestScan baut sich ein eigenes.
    service = BluetoothService(backend=backend, scan_seconds=300)
    yield service
    await service.aclose()


def _spy_pair(backend):
    calls = []
    original = backend.pair

    async def spy(path, prompter):
        calls.append(path)
        await original(path, prompter)

    backend.pair = spy
    return calls


class TestState:
    async def test_it_lists_the_paired_devices_with_their_kinds(self, svc):
        state = await svc.get_state(LAN)
        assert state.available is True
        assert state.adapter.address == "AA:AA:AA:AA:AA:01"
        kinds = {d.name: d.kind for d in state.devices}
        assert kinds == {"Xbox Wireless Controller": "controller", "JBL TUNE510BT": "audio"}

    async def test_can_pair_here_follows_the_client_ip(self, svc):
        assert (await svc.get_state(LAN)).can_pair_here is True
        assert (await svc.get_state(PUBLIC)).can_pair_here is False
        assert (await svc.get_state(None)).can_pair_here is False

    async def test_a_missing_configured_adapter_is_unavailable_not_a_fallback(self, svc, monkeypatch):
        monkeypatch.setattr(settings, "bluetooth_adapter_address", "AA:AA:AA:AA:AA:09")
        state = await svc.get_state(LAN)
        assert state.available is False
        assert "AA:AA:AA:AA:AA:09" in state.detail
        assert state.devices == []

    async def test_a_dead_bluez_reads_as_unavailable(self, backend, svc):
        async def broken():
            raise BlueZError("org.baluhost.Error.BusUnavailable", "EOFError")
        backend.snapshot = broken
        state = await svc.get_state(LAN)
        assert state.available is False
        assert state.detail


class TestPairingGate:
    async def test_pairing_from_outside_the_lan_is_forbidden_before_any_backend_call(self, backend, svc):
        await svc.start_scan()
        calls = _spy_pair(backend)
        with pytest.raises(ForbiddenError):
            await svc.start_pairing(KEYBOARD, 1, PUBLIC, lambda *a: None)
        assert calls == []

    async def test_a_malformed_address_is_400(self, svc):
        with pytest.raises(BadRequestError):
            await svc.start_pairing("/org/bluez/hci0", 1, LAN, lambda *a: None)

    async def test_an_unknown_address_is_404_without_a_backend_call(self, backend, svc):
        calls = _spy_pair(backend)
        with pytest.raises(NotFoundError):
            await svc.start_pairing("AA:AA:AA:AA:AA:77", 1, LAN, lambda *a: None)
        assert calls == []

    async def test_an_already_paired_device_is_409(self, svc):
        with pytest.raises(ConflictError):
            await svc.start_pairing("AA:AA:AA:AA:AA:02", 1, LAN, lambda *a: None)

    async def test_a_second_pairing_is_409(self, backend, svc):
        await svc.start_scan()
        release = asyncio.Event()

        async def hold(path, prompter):
            await release.wait()

        backend.pair = hold
        await svc.start_pairing(KEYBOARD, 1, LAN, lambda *a: None)
        with pytest.raises(ConflictError):
            await svc.start_pairing("AA:AA:AA:AA:AA:05", 1, LAN, lambda *a: None)
        release.set()
        await svc.wait_pairings()


class TestPairingFlow:
    async def test_a_keyboard_pairs_trusts_and_connects(self, svc):
        await svc.start_scan()
        finished = []
        session_id = await svc.start_pairing(
            KEYBOARD.lower(), 1, LAN, lambda device, stage, error: finished.append((device.address, stage, error)),
        )
        await svc.wait_pairings()
        assert finished == [(KEYBOARD, "succeeded", None)]
        status = svc.pairing_status(1)
        assert status.session_id == session_id and status.stage == "succeeded"
        keyboard = next(d for d in (await svc.get_state(LAN)).devices if d.address == KEYBOARD)
        assert keyboard.paired and keyboard.trusted and keyboard.connected

    async def test_the_status_is_invisible_to_other_users(self, svc):
        await svc.start_scan()
        await svc.start_pairing(KEYBOARD, 1, LAN, lambda *a: None)
        assert svc.pairing_status(2) is None
        await svc.wait_pairings()

    async def test_confirming_from_outside_the_lan_is_forbidden_but_cancelling_is_not(self, backend, svc):
        await svc.start_scan()
        release = asyncio.Event()

        async def hold(path, prompter):
            await release.wait()

        backend.pair = hold
        session_id = await svc.start_pairing(KEYBOARD, 1, LAN, lambda *a: None)
        with pytest.raises(ForbiddenError):
            svc.answer(session_id, 1, "accept", PUBLIC)
        svc.answer(session_id, 1, "cancel", PUBLIC)
        release.set()
        await svc.wait_pairings()

    async def test_answering_an_unknown_session_is_404(self, svc):
        with pytest.raises(NotFoundError):
            svc.answer("gibt-es-nicht", 1, "cancel", LAN)


class TestScan:
    async def test_the_window_is_reused_and_closes_by_itself(self, backend):
        short = BluetoothService(backend=backend, scan_seconds=0.05)
        try:
            first = await short.start_scan()
            assert await short.start_scan() == first
            names = {d.name for d in (await short.get_state(LAN)).devices}
            assert "Dev-Maus" in names
            await asyncio.sleep(0.15)
            assert "Dev-Maus" not in {d.name for d in (await short.get_state(LAN)).devices}
        finally:
            await short.aclose()

    async def test_scanning_with_the_adapter_off_is_409(self, svc):
        await svc.set_powered(False)
        with pytest.raises(ConflictError):
            await svc.start_scan()


class TestActions:
    async def test_connect_when_already_connected_is_fine(self, backend, svc):
        async def already(path):
            raise BlueZError("org.bluez.Error.AlreadyConnected", "")
        backend.connect = already
        await svc.connect("AA:AA:AA:AA:AA:02")

    async def test_raw_bluez_text_never_reaches_the_error_message(self, backend, svc):
        async def chatty(path):
            raise BlueZError("org.bluez.Error.Failed", "/var/lib/bluetooth/geheim")
        backend.connect = chatty
        with pytest.raises(BadGatewayError) as info:
            await svc.connect("AA:AA:AA:AA:AA:03")
        assert "geheim" not in info.value.public_message

    async def test_remove_returns_the_removed_device(self, svc):
        device = await svc.remove("AA:AA:AA:AA:AA:03")
        assert device.name == "JBL TUNE510BT"
        assert "JBL TUNE510BT" not in {d.name for d in (await svc.get_state(LAN)).devices}
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/plugins/test_bluetooth_service.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: … service`.

- [ ] **Step 3: `service.py` implementieren**

```python
"""Service-Schicht der Bluetooth-Steuerung.

Waehlt das Backend, haelt es als Singleton pro Worker und traegt die gesamte
Validierung: Keine Client-Zeichenkette erreicht BlueZ, bevor sie als MAC
geprueft und im aktuellen Objektbaum unter dem gebundenen Adapter gefunden
wurde. Objektpfade entstehen nur aus geprueften Adressen.

Fehler verlassen den Service ausschliesslich als ``ServiceError`` mit
kuratierter Meldung; BlueZ-Rohtext landet nur im Log.
"""
from __future__ import annotations

import asyncio
import logging
import platform
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from app.core.config import settings
from app.core.exceptions import (
    BadGatewayError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceError,
)
from app.core.network_utils import is_private_or_local_ip
from app.plugins.installed.bluetooth import pairing
from app.plugins.installed.bluetooth.backend import (
    BluetoothBackend,
    BlueZBackend,
    DevBluetoothBackend,
)
from app.plugins.installed.bluetooth.bluez import (
    AdapterInfo,
    BlueZError,
    DeviceInfo,
    Snapshot,
    kind_for_icon,
    normalize_address,
    select_adapter,
)
from app.plugins.installed.bluetooth.models import (
    BluetoothAdapter,
    BluetoothDevice,
    BluetoothState,
    PairingSession,
)

logger = logging.getLogger(__name__)

SCAN_SECONDS = 30.0
DeviceFinished = Callable[[DeviceInfo, str, Optional[str]], None]

_service: Optional["BluetoothService"] = None


def action_error(exc: BlueZError) -> ServiceError:
    """Uebersetzt einen BlueZ-Fehler in eine kuratierte Antwort."""
    logger.warning("Bluetooth-Aktion fehlgeschlagen: %s %s", exc.name, exc.text)
    if exc.name in ("org.bluez.Error.DoesNotExist", "org.freedesktop.DBus.Error.UnknownObject"):
        return NotFoundError("Geraet nicht gefunden")
    if exc.name == "org.bluez.Error.InProgress":
        return ConflictError("Vorgang laeuft bereits")
    if exc.name == "org.bluez.Error.NotReady":
        return ConflictError("Adapter ist aus")
    if "timeout" in exc.text or exc.name == "org.baluhost.Error.Timeout":
        return BadGatewayError("Geraet nicht erreichbar — eingeschaltet?")
    return BadGatewayError("Bluetooth-Aktion fehlgeschlagen")


def _to_model(device: DeviceInfo) -> BluetoothDevice:
    return BluetoothDevice(
        address=device.address,
        name=device.name,
        kind=kind_for_icon(device.icon),
        icon=device.icon,
        paired=device.paired,
        trusted=device.trusted,
        connected=device.connected,
        battery_percent=device.battery_percent,
        rssi=device.rssi,
    )


class BluetoothService:
    """Duenne Huelle um das Backend, plus Validierung und Scan-Fenster."""

    def __init__(
        self,
        backend: Optional[BluetoothBackend] = None,
        coordinator: Optional[pairing.PairingCoordinator] = None,
        scan_seconds: float = SCAN_SECONDS,
    ) -> None:
        if backend is not None:
            self._backend: BluetoothBackend = backend
        elif getattr(settings, "is_dev_mode", False) or platform.system() != "Linux":
            # BlueZ gibt es auf Windows nicht, und im Dev-Modus soll nichts an
            # echten Funkgeraeten herumstellen.
            self._backend = DevBluetoothBackend()
        else:
            self._backend = BlueZBackend()
        self._coordinator = coordinator or pairing.PairingCoordinator()
        self._scan_seconds = scan_seconds
        self._scan_task: Optional[asyncio.Task] = None
        self._scan_until: Optional[datetime] = None

    # --- Lesen -----------------------------------------------------------

    async def get_state(self, client_host: Optional[str]) -> BluetoothState:
        """Liest den Zustand. Ein unerreichbares BlueZ ist kein Fehler, sondern
        ``available=false`` — die UI soll das anzeigen koennen."""
        common = {
            "can_pair_here": is_private_or_local_ip(client_host),
            "pairing_active": pairing.pairing_active(),
        }
        try:
            snapshot = await self._backend.snapshot()
        except BlueZError as exc:
            logger.warning("BlueZ nicht erreichbar: %s", exc.name)
            return BluetoothState(available=False, detail="Bluetooth-Dienst nicht erreichbar", **common)
        adapter, detail, warning = select_adapter(snapshot.adapters, settings.bluetooth_adapter_address)
        if adapter is None:
            return BluetoothState(available=False, detail=detail, **common)
        devices = [_to_model(d) for d in snapshot.devices if d.adapter_path == adapter.path]
        devices.sort(key=lambda d: (not d.paired, d.kind, d.name.lower()))
        return BluetoothState(
            available=True,
            warning=warning,
            adapter=BluetoothAdapter(
                address=adapter.address, name=adapter.name,
                powered=adapter.powered, discovering=adapter.discovering,
            ),
            devices=devices,
            **common,
        )

    async def _adapter(self) -> tuple[Snapshot, AdapterInfo]:
        try:
            snapshot = await self._backend.snapshot()
        except BlueZError as exc:
            raise BadGatewayError("Bluetooth nicht erreichbar") from exc
        adapter, detail, _ = select_adapter(snapshot.adapters, settings.bluetooth_adapter_address)
        if adapter is None:
            raise ConflictError(detail or "Kein Bluetooth-Adapter")
        return snapshot, adapter

    async def _device(self, address: str) -> tuple[AdapterInfo, DeviceInfo]:
        normalized = normalize_address(address)
        if normalized is None:
            raise BadRequestError("Ungueltige Geraeteadresse")
        snapshot, adapter = await self._adapter()
        device = next(
            (d for d in snapshot.devices if d.adapter_path == adapter.path and d.address == normalized),
            None,
        )
        if device is None:
            raise NotFoundError("Geraet nicht gefunden")
        return adapter, device

    async def _act(self, action: Awaitable[Any], ok_errors: frozenset = frozenset()) -> None:
        try:
            await action
        except BlueZError as exc:
            if exc.name in ok_errors:
                return
            raise action_error(exc) from exc

    # --- Aktionen --------------------------------------------------------

    async def set_powered(self, powered: bool) -> None:
        _, adapter = await self._adapter()
        await self._act(self._backend.set_powered(adapter.path, powered))

    async def start_scan(self) -> datetime:
        if self._scan_task is not None and not self._scan_task.done() and self._scan_until:
            return self._scan_until
        _, adapter = await self._adapter()
        if not adapter.powered:
            raise ConflictError("Adapter ist aus")
        await self._act(self._backend.start_scan(adapter.path))
        self._scan_until = datetime.now(timezone.utc) + timedelta(seconds=self._scan_seconds)
        self._scan_task = asyncio.create_task(self._stop_scan_later(adapter.path))
        return self._scan_until

    async def _stop_scan_later(self, adapter_path: str) -> None:
        await asyncio.sleep(self._scan_seconds)
        try:
            await self._backend.stop_scan(adapter_path)
        except BlueZError as exc:
            logger.info("Bluetooth: StopDiscovery ergab %s", exc.name)

    async def connect(self, address: str) -> None:
        _, device = await self._device(address)
        await self._act(self._backend.connect(device.path), frozenset({"org.bluez.Error.AlreadyConnected"}))

    async def disconnect(self, address: str) -> None:
        _, device = await self._device(address)
        await self._act(self._backend.disconnect(device.path), frozenset({"org.bluez.Error.NotConnected"}))

    async def remove(self, address: str) -> DeviceInfo:
        adapter, device = await self._device(address)
        await self._act(self._backend.remove(adapter.path, device.path))
        return device

    async def start_pairing(
        self, address: str, user_id: int, client_host: Optional[str], on_finished: DeviceFinished,
    ) -> str:
        """Prueft LAN, Adresse, Zustand — erst dann startet die Kopplung."""
        if not is_private_or_local_ip(client_host):
            raise ForbiddenError("Koppeln nur im lokalen Netz")
        adapter, device = await self._device(address)
        if device.paired:
            raise ConflictError("Geraet ist bereits gekoppelt")
        if not adapter.powered:
            raise ConflictError("Adapter ist aus")
        try:
            return self._coordinator.start(
                self._backend, device, user_id,
                lambda stage, error: on_finished(device, stage, error),
            )
        except pairing.PairingBusy as exc:
            raise ConflictError("Es wird bereits ein Geraet gekoppelt") from exc

    def pairing_status(self, user_id: int) -> Optional[PairingSession]:
        return pairing.read_session_for(user_id)

    def answer(self, session_id: str, user_id: int, action: str, client_host: Optional[str]) -> None:
        """Ja/Nein braucht das LAN (es schliesst eine Vertrauensentscheidung ab),
        Abbrechen nicht."""
        if action in ("accept", "reject") and not is_private_or_local_ip(client_host):
            raise ForbiddenError("Bestaetigen nur im lokalen Netz")
        if not pairing.write_answer(session_id, user_id, action):
            raise NotFoundError("Keine laufende Kopplung")

    async def wait_pairings(self) -> None:
        await self._coordinator.wait_idle()

    async def aclose(self) -> None:
        if self._scan_task is not None:
            self._scan_task.cancel()
        await self._coordinator.aclose()


def get_bluetooth_service() -> BluetoothService:
    """Liefert die Service-Instanz dieses Workers und legt sie beim ersten Aufruf an."""
    global _service
    if _service is None:
        _service = BluetoothService()
    return _service
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/plugins/test_bluetooth_service.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugins/installed/bluetooth/service.py backend/tests/plugins/test_bluetooth_service.py
git commit -m "feat(bluetooth): Service mit LAN-Pruefung, Validierung und Scan-Fenster" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01HbQVSEmXaZU6ZV1CjhCee6"
```

---

## Task 9: Router, Plugin-Klasse, Audit, Rate-Limit

**Files:**
- Modify: `backend/app/core/rate_limiter.py:193` (neuer Eintrag nach `display_output`)
- Modify: `backend/app/plugins/installed/bluetooth/__init__.py` (ersetzt den Platzhalter aus Task 3)
- Test: `backend/tests/plugins/test_bluetooth_routes.py`, `backend/tests/plugins/test_bluetooth_ui_manifest.py`

**Interfaces:**
- Consumes: `get_bluetooth_service()`, `BluetoothService` (Task 8); Modelle (Task 3); `require_power_manage_bluetooth` (Task 2); `kind_for_icon` (Task 3).
- Produces: `BluetoothPlugin(PluginBase)` mit `metadata.name == "bluetooth"`, `get_router()`, `get_ui_manifest() -> PluginUIManifest(enabled=True)`; Routen unter `/api/plugins/bluetooth/` exakt wie in der Tabelle der Spec.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

`backend/tests/plugins/test_bluetooth_ui_manifest.py`:
```python
"""Ohne diese Ueberschreibung ist das Plugin im Frontend unsichtbar."""
from app.plugins.installed.bluetooth import BluetoothPlugin


class TestUiManifest:
    def test_the_manifest_is_present_and_enabled(self):
        manifest = BluetoothPlugin().get_ui_manifest()
        assert manifest is not None and manifest.enabled is True

    def test_it_contributes_no_nav_item(self):
        assert BluetoothPlugin().get_ui_manifest().nav_items == []

    def test_the_metadata_name_matches_the_route_prefix(self):
        assert BluetoothPlugin().metadata.name == "bluetooth"
```

`backend/tests/plugins/test_bluetooth_routes.py`:
```python
"""Routen: Recht, LAN-Pruefung, Statuscodes, Audit, keine Interna, kein Code im Log."""
import asyncio
import logging
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.plugins.installed.bluetooth as plugin_module
from app.api.deps import require_power_manage_bluetooth
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.plugins.installed.bluetooth import BluetoothPlugin, pairing
from app.plugins.installed.bluetooth import service as service_module
from app.plugins.installed.bluetooth.backend import DEV_ADAPTER_PATH, DevBluetoothBackend
from app.plugins.installed.bluetooth.bluez import BlueZError
from app.plugins.installed.bluetooth.service import BluetoothService
from app.services.monitoring import shm

BASE = "/api/plugins/bluetooth"
KEYBOARD = "AA:AA:AA:AA:AA:04"
PASSKEY = 482913


class _Admin:
    id = 1
    username = "admin"
    role = "admin"


class _Other:
    id = 2
    username = "someone"
    role = "user"


class _Lan:
    value = True


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(shm, "SHM_DIR", tmp_path / "shm")
    monkeypatch.setattr(pairing, "LOCK_PATH", tmp_path / "pairing.lock")
    monkeypatch.setattr(pairing, "ANSWER_POLL_SECONDS", 0.01)
    monkeypatch.setattr(pairing, "RESULT_DISPLAY_SECONDS", 60.0)
    monkeypatch.setattr(settings, "bluetooth_adapter_address", "")
    _Lan.value = True
    monkeypatch.setattr(service_module, "is_private_or_local_ip", lambda host: _Lan.value)


@pytest.fixture
def audit(monkeypatch):
    events: list[dict] = []
    security: list[dict] = []

    class _Recorder:
        def log_event(self, **kwargs):
            events.append(kwargs)

        def log_security_event(self, **kwargs):
            security.append(kwargs)

    monkeypatch.setattr(plugin_module, "get_audit_logger_db", lambda: _Recorder())
    return events, security


def _make(monkeypatch, backend=None, user=_Admin):
    backend = backend or DevBluetoothBackend(step_seconds=0.01, passkey=PASSKEY)
    service = BluetoothService(backend=backend, scan_seconds=300)
    monkeypatch.setattr(service_module, "get_bluetooth_service", lambda: service)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(BluetoothPlugin().get_router(), prefix=BASE)
    app.dependency_overrides[require_power_manage_bluetooth] = lambda: user()
    return app, service, backend


def _poll(client, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"{BASE}/pairing").json()
        if predicate(body):
            return body
        time.sleep(0.02)
    raise AssertionError("Zustand nicht erreicht")


class TestPermission:
    def test_the_read_route_is_gated(self):
        app = FastAPI()
        app.include_router(BluetoothPlugin().get_router(), prefix=BASE)
        assert TestClient(app).get(f"{BASE}/state").status_code in (401, 403)

    def test_the_pair_route_is_gated(self):
        app = FastAPI()
        app.include_router(BluetoothPlugin().get_router(), prefix=BASE)
        resp = TestClient(app).post(f"{BASE}/devices/{KEYBOARD}/pair")
        assert resp.status_code in (401, 403)


class TestState:
    def test_state_lists_the_dev_devices(self, monkeypatch):
        app, _, _ = _make(monkeypatch)
        body = TestClient(app).get(f"{BASE}/state").json()
        assert body["available"] is True
        assert {d["kind"] for d in body["devices"]} == {"controller", "audio"}
        assert body["can_pair_here"] is True


class TestPairRoute:
    def test_outside_the_lan_is_403_even_for_an_admin_and_is_audited(self, monkeypatch, audit):
        events, _ = audit
        _Lan.value = False
        app, _, _ = _make(monkeypatch)
        resp = TestClient(app).post(f"{BASE}/devices/{KEYBOARD}/pair")
        assert resp.status_code == 403
        assert events[-1]["action"] == "bluetooth_pair_denied"
        assert events[-1]["success"] is False

    def test_a_malformed_address_is_400(self, monkeypatch):
        app, _, _ = _make(monkeypatch)
        assert TestClient(app).post(f"{BASE}/devices/nonsense/pair").status_code == 400

    def test_an_unknown_address_is_404(self, monkeypatch):
        app, _, _ = _make(monkeypatch)
        assert TestClient(app).post(f"{BASE}/devices/AA:AA:AA:AA:AA:77/pair").status_code == 404

    def test_an_already_paired_device_is_409(self, monkeypatch):
        app, _, _ = _make(monkeypatch)
        assert TestClient(app).post(f"{BASE}/devices/AA:AA:AA:AA:AA:02/pair").status_code == 409

    def test_a_keyboard_pairs_and_the_code_never_reaches_log_or_audit(self, monkeypatch, audit, caplog):
        caplog.set_level(logging.DEBUG)
        events, _ = audit
        # 0,2 s pro Ziffer: die Code-Anzeige steht ~1,4 s — lang genug, dass
        # die HTTP-Abfrage sie sicher sieht, bevor der Erfolg kommt.
        app, service, _ = _make(monkeypatch, backend=DevBluetoothBackend(step_seconds=0.2, passkey=PASSKEY))
        with TestClient(app) as client:
            assert client.post(f"{BASE}/scan").status_code == 200
            resp = client.post(f"{BASE}/devices/{KEYBOARD}/pair")
            assert resp.status_code == 202
            session_id = resp.json()["session_id"]
            shown = _poll(client, lambda b: b and b["stage"] == "display_passkey")
            assert shown["code"] == f"{PASSKEY:06d}"
            assert shown["session_id"] == session_id
            done = _poll(client, lambda b: b and b["stage"] == "succeeded")
            assert done["code"] is None
            client.portal.call(service.aclose)
        pair_events = [e for e in events if e["action"] == "bluetooth_pair"]
        assert pair_events and pair_events[0]["success"] is True
        assert pair_events[0]["details"]["kind"] == "input"
        assert str(PASSKEY) not in caplog.text
        assert str(PASSKEY) not in repr(events)

    def test_another_user_sees_nothing_and_cannot_answer(self, monkeypatch):
        backend = DevBluetoothBackend(step_seconds=0.01, passkey=PASSKEY)

        async def hold(path, prompter):
            prompter.show_passkey(PASSKEY, 0)
            while path not in backend._cancelled:
                await asyncio.sleep(0.01)
            raise BlueZError("org.bluez.Error.AuthenticationCanceled")

        backend.pair = hold
        app, service, _ = _make(monkeypatch, backend=backend)
        asyncio.run(backend.start_scan(DEV_ADAPTER_PATH))
        with TestClient(app) as client:
            session_id = client.post(f"{BASE}/devices/{KEYBOARD}/pair").json()["session_id"]
            _poll(client, lambda b: b and b["stage"] == "display_passkey")
            app.dependency_overrides[require_power_manage_bluetooth] = lambda: _Other()
            assert client.get(f"{BASE}/pairing").json() is None
            assert client.post(f"{BASE}/pairing/{session_id}/cancel").status_code == 404
            app.dependency_overrides[require_power_manage_bluetooth] = lambda: _Admin()
            assert client.post(f"{BASE}/pairing/{session_id}/cancel").status_code == 200
            _poll(client, lambda b: b and b["stage"] == "cancelled")
            client.portal.call(service.aclose)


class TestOtherRoutes:
    def test_raw_bluez_text_never_reaches_the_client(self, monkeypatch):
        backend = DevBluetoothBackend(step_seconds=0)

        async def chatty(path):
            raise BlueZError("org.bluez.Error.Failed", "/var/lib/bluetooth/geheim")

        backend.connect = chatty
        app, _, _ = _make(monkeypatch, backend=backend)
        resp = TestClient(app).post(f"{BASE}/devices/AA:AA:AA:AA:AA:03/connect")
        assert resp.status_code == 502
        assert "geheim" not in resp.text

    def test_remove_is_audited_with_address_and_kind(self, monkeypatch, audit):
        events, _ = audit
        app, _, _ = _make(monkeypatch)
        assert TestClient(app).delete(f"{BASE}/devices/AA:AA:AA:AA:AA:03").status_code == 200
        entry = next(e for e in events if e["action"] == "bluetooth_remove")
        assert entry["details"] == {"address": "AA:AA:AA:AA:AA:03", "kind": "audio"}

    def test_adapter_power_is_audited_and_a_non_admin_gets_the_delegated_entry(self, monkeypatch, audit):
        events, security = audit
        app, _, _ = _make(monkeypatch, user=_Other)
        assert TestClient(app).post(f"{BASE}/adapter/power", json={"powered": False}).status_code == 200
        assert any(e["action"] == "bluetooth_adapter_power" for e in events)
        assert security and security[0]["resource"] == "manage_bluetooth"

    def test_a_raw_dict_body_is_422(self, monkeypatch):
        app, _, _ = _make(monkeypatch)
        assert TestClient(app).post(f"{BASE}/adapter/power", json={"nonsense": 1}).status_code == 422
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/plugins/test_bluetooth_routes.py tests/plugins/test_bluetooth_ui_manifest.py -v --no-cov`
Expected: FAIL — `ImportError: cannot import name 'BluetoothPlugin'`.

- [ ] **Step 3: Rate-Limit-Kategorie**

`backend/app/core/rate_limiter.py` — nach dem `display_output`-Eintrag (Zeile 193):
```python
    # Bluetooth — Popover-Abfrage alle 3 s, waehrend einer Kopplung jede
    # Sekunde. admin_operations (30/Minute) waere schon von der
    # Kopplungs-Abfrage allein aufgebraucht.
    "bluetooth": "120/minute",
```

- [ ] **Step 4: `__init__.py` schreiben**

`backend/app/plugins/installed/bluetooth/__init__.py` vollständig ersetzen:
```python
"""Bluetooth — bundled Plugin.

Verbindet, trennt, entfernt und koppelt Bluetooth-Geraete ueber BlueZ auf
dem System-Bus. Laeuft im Host-Prozess als Dienst-User, der in der Gruppe
``bluetooth`` ist; ein Sandbox-Plugin kaeme nicht an ``org.bluez``.
"""
# NB: kein ``from __future__ import annotations`` hier (vgl. audio_control).
# Zusammen mit Pydantic v2 + FastAPIs Body-Erkennung durch slowapis
# ``@user_limiter.limit``-Wrapper werden aufgeschobene Annotationen zu
# ForwardRefs, die FastAPI nicht mehr als Pydantic-Modell aufloest — jedes
# POST liefert dann 422.
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import require_power_manage_bluetooth
from app.core.exceptions import ForbiddenError
from app.core.rate_limiter import get_limit, user_limiter
from app.plugins.base import PluginBase, PluginMetadata, PluginUIManifest
from app.plugins.installed.bluetooth import service as service_module
from app.plugins.installed.bluetooth.bluez import DeviceInfo, kind_for_icon
from app.plugins.installed.bluetooth.models import (
    BluetoothState,
    ConfirmRequest,
    PairingSession,
    PairStartResponse,
    PowerRequest,
    ScanResponse,
)
from app.schemas.user import UserPublic
from app.services.audit.logger_db import get_audit_logger_db

logger = logging.getLogger(__name__)

router = APIRouter()

_LIMIT = get_limit("bluetooth")


def _client_host(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _audit(action: str, user: UserPublic, success: bool, details: dict) -> None:
    """Audit fuer Koppeln, Entfernen und Adapter an/aus — nie mit Code oder PIN."""
    audit_logger = get_audit_logger_db()
    audit_logger.log_event(
        event_type="POWER",
        action=action,
        user=user.username,
        resource="bluetooth",
        success=success,
        details=details,
    )
    if getattr(user, "role", None) != "admin":
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=user.username,
            resource="manage_bluetooth",
            details={"action": action},
            success=True,
        )


@router.get("/state", response_model=BluetoothState)
@user_limiter.limit(_LIMIT)
async def get_bluetooth_state(
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> BluetoothState:
    """Adapter, Geraete und ob hier gekoppelt werden darf.

    Hinter derselben Berechtigung wie die Schreibrouten: die Liste verraet
    Hardware und MAC-Adressen.
    """
    return await service_module.get_bluetooth_service().get_state(_client_host(request))


@router.post("/adapter/power")
@user_limiter.limit(_LIMIT)
async def set_adapter_power(
    body: PowerRequest,
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> dict:
    await service_module.get_bluetooth_service().set_powered(body.powered)
    _audit("bluetooth_adapter_power", current_user, True, {"powered": body.powered})
    return {"success": True}


@router.post("/scan", response_model=ScanResponse)
@user_limiter.limit(_LIMIT)
async def start_scan(
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> ScanResponse:
    until = await service_module.get_bluetooth_service().start_scan()
    return ScanResponse(until=until)


@router.post("/devices/{address}/connect")
@user_limiter.limit(_LIMIT)
async def connect_device(
    address: str,
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> dict:
    await service_module.get_bluetooth_service().connect(address)
    return {"success": True}


@router.post("/devices/{address}/disconnect")
@user_limiter.limit(_LIMIT)
async def disconnect_device(
    address: str,
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> dict:
    await service_module.get_bluetooth_service().disconnect(address)
    return {"success": True}


@router.delete("/devices/{address}")
@user_limiter.limit(_LIMIT)
async def remove_device(
    address: str,
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> dict:
    device = await service_module.get_bluetooth_service().remove(address)
    _audit("bluetooth_remove", current_user, True,
           {"address": device.address, "kind": kind_for_icon(device.icon)})
    return {"success": True}


@router.post("/devices/{address}/pair", status_code=status.HTTP_202_ACCEPTED,
             response_model=PairStartResponse)
@user_limiter.limit(_LIMIT)
async def pair_device(
    address: str,
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> PairStartResponse:
    """Startet eine Kopplung; der Ablauf laeuft im Hintergrund dieses Workers.

    Nur aus privaten Netzen — fuer ALLE Rollen. Ein abgelehnter Versuch von
    aussen wird auditiert: er ist genau das Muster, gegen das diese Pruefung
    steht (gestohlenes Konto plus Funkreichweite).
    """
    def on_finished(device: DeviceInfo, stage: str, error: Optional[str]) -> None:
        _audit("bluetooth_pair", current_user, stage == "succeeded", {
            "address": device.address, "kind": kind_for_icon(device.icon),
            "stage": stage, "error": error,
        })

    try:
        session_id = await service_module.get_bluetooth_service().start_pairing(
            address, current_user.id, _client_host(request), on_finished,
        )
    except ForbiddenError:
        _audit("bluetooth_pair_denied", current_user, False, {"reason": "not_local"})
        raise
    return PairStartResponse(session_id=session_id)


@router.get("/pairing", response_model=Optional[PairingSession])
@user_limiter.limit(_LIMIT)
async def get_pairing(
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> Optional[PairingSession]:
    """Die Sitzung des Aufrufers oder ``null`` — fremde Codes sieht niemand."""
    return service_module.get_bluetooth_service().pairing_status(current_user.id)


@router.post("/pairing/{session_id}/confirm")
@user_limiter.limit(_LIMIT)
async def confirm_pairing(
    session_id: str,
    body: ConfirmRequest,
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> dict:
    service_module.get_bluetooth_service().answer(
        session_id, current_user.id, "accept" if body.accept else "reject", _client_host(request),
    )
    return {"success": True}


@router.post("/pairing/{session_id}/cancel")
@user_limiter.limit(_LIMIT)
async def cancel_pairing(
    session_id: str,
    request: Request,
    response: Response,
    current_user=Depends(require_power_manage_bluetooth),
) -> dict:
    service_module.get_bluetooth_service().answer(
        session_id, current_user.id, "cancel", _client_host(request),
    )
    return {"success": True}


class BluetoothPlugin(PluginBase):
    """Bundled Plugin fuer Bluetooth."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="bluetooth",
            version="1.0.0",
            display_name="Bluetooth",
            description=(
                "Bluetooth-Geraete verbinden, trennen und koppeln — "
                "Controller, Kopfhoerer, Maus und Tastatur."
            ),
            author="Xveyn",
            category="system",
        )

    def get_router(self) -> APIRouter:
        return router

    def get_ui_manifest(self) -> PluginUIManifest:
        """Meldet das Plugin ans Frontend, ohne Nav-Eintrag.

        **Ohne diese Ueberschreibung ist das Feature unsichtbar**:
        ``usePluginEnabled('bluetooth')`` liest genau die Liste der Plugins
        mit aktivem Manifest. Die Bedienung sitzt in der Topbar.
        """
        return PluginUIManifest(enabled=True)
```

- [ ] **Step 5: Tests laufen lassen**

Run: `cd backend ; python -m pytest tests/plugins/test_bluetooth_routes.py tests/plugins/test_bluetooth_ui_manifest.py -v --no-cov`
Expected: PASS. Scheitert `client.portal.call(...)`, weil die installierte Starlette-Version kein `portal` am TestClient führt: stattdessen vor dem Verlassen des `with`-Blocks `_poll` bis zum Endstand abwarten und die Zeile entfernen — die Tasks werden mit dem Loop beendet.

- [ ] **Step 6: Alle Plugin-Tests plus Lint**

Run: `cd backend ; python -m pytest tests/plugins/test_bluetooth_*.py tests/test_power_permissions_manage_bluetooth.py -v --no-cov ; python -m ruff check app/plugins/installed/bluetooth tests/plugins`
Expected: alles PASS, `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/rate_limiter.py backend/app/plugins/installed/bluetooth/__init__.py backend/tests/plugins/test_bluetooth_routes.py backend/tests/plugins/test_bluetooth_ui_manifest.py
git commit -m "feat(bluetooth): Routen, Plugin-Klasse und Audit" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01HbQVSEmXaZU6ZV1CjhCee6"
```

---

## Task 10: Frontend — API-Client, Übersetzungen, Rechte-Schalter

**Files:**
- Create: `client/src/api/bluetooth.ts`
- Create: `client/src/i18n/locales/de/bluetooth.json`, `client/src/i18n/locales/en/bluetooth.json`
- Modify: `client/src/i18n/index.ts` (Import, `resources.de/en`, `ns`-Array)
- Modify: `client/src/api/powerPermissions.ts` (drei Schnittstellen)
- Modify: `client/src/components/user-management/PowerPermissionsSection.tsx`
- Modify: `client/src/i18n/locales/{de,en}/admin.json`
- Test: `client/src/__tests__/api/bluetooth.test.ts`, `client/src/__tests__/i18n/bluetooth-locale.test.ts`, `client/src/__tests__/components/user-management/PowerPermissionsSection.bluetooth.test.tsx`

**Interfaces:**
- Produces (`api/bluetooth.ts`): Typen `DeviceKind`, `PairingStage`, `BluetoothAdapter`, `BluetoothDevice`, `BluetoothState`, `PairingSession`; `TERMINAL_STAGES: ReadonlySet<PairingStage>`; Funktionen `getBluetoothState()`, `setAdapterPowered(powered)`, `startScan(): Promise<string>` (ISO-Zeit), `connectDevice(address)`, `disconnectDevice(address)`, `removeDevice(address)`, `startPairing(address): Promise<string>` (session_id), `getPairingSession(): Promise<PairingSession | null>`, `answerPairing(sessionId, accept)`, `cancelPairing(sessionId)`.
- Produces (i18n): Namespace `bluetooth` mit den Schlüsseln unten; Platzhalter `battery{{percent}}`, `removeConfirm{{name}}`, `scanning{{seconds}}`, `dialog.title{{name}}`.
- Produces: `MyPowerPermissions.can_manage_bluetooth: boolean`.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

`client/src/__tests__/api/bluetooth.test.ts`:
```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../lib/api', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

import { apiClient } from '../../lib/api';
import {
  answerPairing,
  cancelPairing,
  connectDevice,
  getBluetoothState,
  getPairingSession,
  removeDevice,
  setAdapterPowered,
  startPairing,
  startScan,
} from '../../api/bluetooth';

const BASE = '/api/plugins/bluetooth';
const get = apiClient.get as ReturnType<typeof vi.fn>;
const post = apiClient.post as ReturnType<typeof vi.fn>;
const del = apiClient.delete as ReturnType<typeof vi.fn>;

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  del.mockReset();
  post.mockResolvedValue({ data: { success: true } });
  del.mockResolvedValue({ data: { success: true } });
});

describe('bluetooth api', () => {
  it('liest den Zustand', async () => {
    get.mockResolvedValue({ data: { available: true } });
    expect(await getBluetoothState()).toEqual({ available: true });
    expect(get).toHaveBeenCalledWith(`${BASE}/state`);
  });

  it('schaltet den Adapter', async () => {
    await setAdapterPowered(false);
    expect(post).toHaveBeenCalledWith(`${BASE}/adapter/power`, { powered: false });
  });

  it('liefert das Scan-Ende', async () => {
    post.mockResolvedValue({ data: { until: '2026-09-11T12:00:30Z' } });
    expect(await startScan()).toBe('2026-09-11T12:00:30Z');
  });

  it('kodiert die Adresse im Pfad', async () => {
    await connectDevice('AA:BB:CC:DD:EE:0F');
    expect(post).toHaveBeenCalledWith(`${BASE}/devices/AA%3ABB%3ACC%3ADD%3AEE%3A0F/connect`);
    await removeDevice('AA:BB:CC:DD:EE:0F');
    expect(del).toHaveBeenCalledWith(`${BASE}/devices/AA%3ABB%3ACC%3ADD%3AEE%3A0F`);
  });

  it('startet eine Kopplung und liefert die Sitzung', async () => {
    post.mockResolvedValue({ data: { session_id: 'abc' } });
    expect(await startPairing('AA:BB:CC:DD:EE:0F')).toBe('abc');
  });

  it('liest die eigene Sitzung, auch null', async () => {
    get.mockResolvedValue({ data: null });
    expect(await getPairingSession()).toBeNull();
    expect(get).toHaveBeenCalledWith(`${BASE}/pairing`);
  });

  it('beantwortet und bricht ab', async () => {
    await answerPairing('abc', true);
    expect(post).toHaveBeenCalledWith(`${BASE}/pairing/abc/confirm`, { accept: true });
    await cancelPairing('abc');
    expect(post).toHaveBeenCalledWith(`${BASE}/pairing/abc/cancel`);
  });
});
```

`client/src/__tests__/i18n/bluetooth-locale.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import de from '../../i18n/locales/de/bluetooth.json';
import en from '../../i18n/locales/en/bluetooth.json';

function flatten(obj: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === 'object'
      ? flatten(v as Record<string, unknown>, `${prefix}${k}.`)
      : [`${prefix}${k}`],
  );
}

describe('bluetooth locale contract', () => {
  it('de und en haben dieselben Schluessel', () => {
    expect(flatten(de).sort()).toEqual(flatten(en).sort());
  });

  // Der react-i18next-Mock der Komponententests erfindet die Interpolation
  // selbst; ein fehlender {{platzhalter}} faellt nur hier auf.
  it.each([
    ['battery', '{{percent}}'],
    ['removeConfirm', '{{name}}'],
    ['scanning', '{{seconds}}'],
  ])('%s traegt %s in beiden Sprachen', (key, placeholder) => {
    // `as unknown as`: ein direkter Cast auf Record<string, string> ist wegen
    // der verschachtelten Objekte TS2352 — und `tsc -b` prueft auch Tests.
    expect((de as unknown as Record<string, string>)[key]).toContain(placeholder);
    expect((en as unknown as Record<string, string>)[key]).toContain(placeholder);
  });

  it('dialog.title traegt {{name}} in beiden Sprachen', () => {
    expect(de.dialog.title).toContain('{{name}}');
    expect(en.dialog.title).toContain('{{name}}');
  });

  it('jeder Fehlerschluessel des Backends hat einen Text', () => {
    for (const key of ['auth_failed', 'unreachable', 'timeout', 'unknown']) {
      expect(de.dialog.error).toHaveProperty(key);
      expect(en.dialog.error).toHaveProperty(key);
    }
  });
});
```

`client/src/__tests__/components/user-management/PowerPermissionsSection.bluetooth.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: (ns: string) => ({
    t: (key: string) => `${ns}:${key}`,
    i18n: { language: 'de' },
  }),
}));

vi.mock('../../../api/powerPermissions', () => ({
  getUserPowerPermissions: vi.fn(),
  updateUserPowerPermissions: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../../lib/errorHandling', () => ({
  handleApiError: vi.fn(),
}));

import { PowerPermissionsSection } from '../../../components/user-management/PowerPermissionsSection';
import { getUserPowerPermissions } from '../../../api/powerPermissions';

const PERMS = {
  user_id: 7,
  can_soft_sleep: false, can_wake: false, can_suspend: false, can_wol: false,
  can_toggle_desktop: false, can_unlock_session: false, can_control_audio: false,
  can_manage_displays: false, can_manage_bluetooth: false,
  granted_by: null, granted_by_username: null, granted_at: null,
};

beforeEach(() => {
  vi.mocked(getUserPowerPermissions).mockResolvedValue(structuredClone(PERMS) as never);
});

describe('PowerPermissionsSection — Bluetooth', () => {
  it('bietet den Schalter fuer can_manage_bluetooth an', async () => {
    render(<PowerPermissionsSection userId={7} userRole="user" />);
    await waitFor(() => expect(getUserPowerPermissions).toHaveBeenCalled());
    expect(
      await screen.findByText('admin:users.systemPermissions.items.manageBluetooth.label'),
    ).toBeTruthy();
  });
});
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd client ; npx vitest run src/__tests__/api/bluetooth.test.ts src/__tests__/i18n/bluetooth-locale.test.ts src/__tests__/components/user-management/PowerPermissionsSection.bluetooth.test.tsx`
Expected: FAIL — Module `../../api/bluetooth` bzw. `bluetooth.json` nicht gefunden, Schalter fehlt.

- [ ] **Step 3: `client/src/api/bluetooth.ts`**

```ts
/**
 * API-Client der Bluetooth-Steuerung (bundled Plugin `bluetooth`).
 *
 * Alle Routen liegen hinter dem Recht `can_manage_bluetooth` — auch die
 * lesenden, weil die Liste Hardware und MAC-Adressen verrät. Koppeln und
 * Bestätigen lehnt der Server außerhalb privater Netze ab; `can_pair_here`
 * sagt der UI das vorab.
 */

import { apiClient } from '../lib/api';

const BASE = '/api/plugins/bluetooth';

export type DeviceKind = 'controller' | 'audio' | 'input' | 'other';

export type PairingStage =
  | 'connecting'
  | 'display_passkey'
  | 'display_pin'
  | 'confirm'
  | 'succeeded'
  | 'failed'
  | 'cancelled';

export const TERMINAL_STAGES: ReadonlySet<PairingStage> = new Set<PairingStage>([
  'succeeded',
  'failed',
  'cancelled',
]);

export interface BluetoothAdapter {
  address: string;
  name: string;
  powered: boolean;
  /** Auch true, wenn KDE gerade scannt. */
  discovering: boolean;
}

export interface BluetoothDevice {
  address: string;
  name: string;
  kind: DeviceKind;
  icon: string | null;
  paired: boolean;
  trusted: boolean;
  connected: boolean;
  battery_percent: number | null;
  rssi: number | null;
}

export interface BluetoothState {
  available: boolean;
  detail: string | null;
  warning: string | null;
  adapter: BluetoothAdapter | null;
  devices: BluetoothDevice[];
  can_pair_here: boolean;
  pairing_active: boolean;
}

export interface PairingSession {
  session_id: string;
  address: string;
  device_name: string;
  stage: PairingStage;
  /** Nur für den Initiator; nach dem Ende null. */
  code: string | null;
  entered: number | null;
  /** Kuratierter Schlüssel: auth_failed | unreachable | timeout | unknown. */
  error: string | null;
}

function devicePath(address: string): string {
  return `${BASE}/devices/${encodeURIComponent(address)}`;
}

export async function getBluetoothState(): Promise<BluetoothState> {
  const { data } = await apiClient.get<BluetoothState>(`${BASE}/state`);
  return data;
}

export async function setAdapterPowered(powered: boolean): Promise<void> {
  await apiClient.post(`${BASE}/adapter/power`, { powered });
}

/** Startet das 30-s-Suchfenster; liefert dessen Ende als ISO-Zeit. */
export async function startScan(): Promise<string> {
  const { data } = await apiClient.post<{ until: string }>(`${BASE}/scan`);
  return data.until;
}

export async function connectDevice(address: string): Promise<void> {
  await apiClient.post(`${devicePath(address)}/connect`);
}

export async function disconnectDevice(address: string): Promise<void> {
  await apiClient.post(`${devicePath(address)}/disconnect`);
}

export async function removeDevice(address: string): Promise<void> {
  await apiClient.delete(devicePath(address));
}

/** Startet eine Kopplung; liefert die session_id. */
export async function startPairing(address: string): Promise<string> {
  const { data } = await apiClient.post<{ session_id: string }>(`${devicePath(address)}/pair`);
  return data.session_id;
}

/** Die eigene laufende Kopplung — oder null. */
export async function getPairingSession(): Promise<PairingSession | null> {
  const { data } = await apiClient.get<PairingSession | null>(`${BASE}/pairing`);
  return data;
}

export async function answerPairing(sessionId: string, accept: boolean): Promise<void> {
  await apiClient.post(`${BASE}/pairing/${encodeURIComponent(sessionId)}/confirm`, { accept });
}

export async function cancelPairing(sessionId: string): Promise<void> {
  await apiClient.post(`${BASE}/pairing/${encodeURIComponent(sessionId)}/cancel`);
}
```

- [ ] **Step 4: Übersetzungen**

`client/src/i18n/locales/de/bluetooth.json`:
```json
{
  "title": "Bluetooth",
  "powerOn": "Einschalten",
  "powerOff": "Ausschalten",
  "adapterOff": "Bluetooth ist ausgeschaltet.",
  "unavailable": "Bluetooth ist nicht verfügbar.",
  "kind": {
    "controller": "Controller",
    "audio": "Audio",
    "input": "Eingabegeräte",
    "other": "Weitere Geräte"
  },
  "battery": "Akku {{percent}} %",
  "connect": "Verbinden",
  "disconnect": "Trennen",
  "remove": "Entfernen",
  "removeConfirm": "{{name}} wirklich entfernen? Das Gerät muss danach neu gekoppelt werden.",
  "noDevices": "Keine gekoppelten Geräte.",
  "addDevice": "Gerät hinzufügen",
  "scanning": "Suche läuft … noch {{seconds}} s",
  "noneFound": "Noch nichts gefunden. Ist das Gerät im Kopplungsmodus?",
  "pair": "Koppeln",
  "pairOnlyLocal": "Koppeln nur im lokalen Netz",
  "pairBusy": "Es wird gerade ein Gerät gekoppelt",
  "actionError": "Aktion fehlgeschlagen",
  "loadError": "Bluetooth-Zustand konnte nicht geladen werden",
  "dialog": {
    "title": "{{name}} koppeln",
    "connecting": "Gerät in den Kopplungsmodus versetzen …",
    "displayPasskey": "Diesen Code auf der Tastatur eintippen und mit Enter bestätigen:",
    "displayPin": "Diese PIN auf dem Gerät eintippen und mit Enter bestätigen:",
    "confirm": "Zeigt das Gerät denselben Code?",
    "accept": "Ja, stimmt überein",
    "reject": "Nein",
    "succeeded": "Gekoppelt und verbunden.",
    "cancelled": "Kopplung abgebrochen.",
    "cancel": "Abbrechen",
    "close": "Schließen",
    "inputWarning": "Eingabegeräte können in die Desktop-Sitzung tippen. Nur eigene Geräte koppeln.",
    "error": {
      "auth_failed": "Code falsch oder abgelaufen.",
      "unreachable": "Gerät nicht erreichbar — ist der Kopplungsmodus aktiv?",
      "timeout": "Zeitüberschreitung — bitte erneut versuchen.",
      "unknown": "Kopplung fehlgeschlagen."
    }
  }
}
```

`client/src/i18n/locales/en/bluetooth.json`:
```json
{
  "title": "Bluetooth",
  "powerOn": "Turn on",
  "powerOff": "Turn off",
  "adapterOff": "Bluetooth is turned off.",
  "unavailable": "Bluetooth is not available.",
  "kind": {
    "controller": "Controllers",
    "audio": "Audio",
    "input": "Input devices",
    "other": "Other devices"
  },
  "battery": "Battery {{percent}} %",
  "connect": "Connect",
  "disconnect": "Disconnect",
  "remove": "Remove",
  "removeConfirm": "Really remove {{name}}? It will have to be paired again.",
  "noDevices": "No paired devices.",
  "addDevice": "Add device",
  "scanning": "Searching … {{seconds}} s left",
  "noneFound": "Nothing found yet. Is the device in pairing mode?",
  "pair": "Pair",
  "pairOnlyLocal": "Pairing only on the local network",
  "pairBusy": "Another device is being paired",
  "actionError": "Action failed",
  "loadError": "Could not load the Bluetooth state",
  "dialog": {
    "title": "Pair {{name}}",
    "connecting": "Put the device into pairing mode …",
    "displayPasskey": "Type this code on the keyboard and press Enter:",
    "displayPin": "Type this PIN on the device and press Enter:",
    "confirm": "Does the device show the same code?",
    "accept": "Yes, it matches",
    "reject": "No",
    "succeeded": "Paired and connected.",
    "cancelled": "Pairing cancelled.",
    "cancel": "Cancel",
    "close": "Close",
    "inputWarning": "Input devices can type into the desktop session. Only pair your own devices.",
    "error": {
      "auth_failed": "Wrong or expired code.",
      "unreachable": "Device not reachable — is pairing mode active?",
      "timeout": "Timed out — please try again.",
      "unknown": "Pairing failed."
    }
  }
}
```

`client/src/i18n/index.ts`: nach `import displayEn …` ergänzen
```ts
import bluetoothDe from './locales/de/bluetooth.json';
import bluetoothEn from './locales/en/bluetooth.json';
```
in `resources.de` nach `display: displayDe,` → `bluetooth: bluetoothDe,`; in `resources.en` nach `display: displayEn,` → `bluetooth: bluetoothEn,`; im `ns`-Array nach `'display'` → `, 'bluetooth'`.

- [ ] **Step 5: Recht im Frontend**

`client/src/api/powerPermissions.ts` — in `UserPowerPermissions` und `MyPowerPermissions` nach `can_manage_displays: boolean;` → `can_manage_bluetooth: boolean;`; in `UserPowerPermissionsUpdate` nach `can_manage_displays?: boolean;` → `can_manage_bluetooth?: boolean;`.

`client/src/components/user-management/PowerPermissionsSection.tsx`:
- lucide-Import um `Bluetooth` ergänzen.
- `FIELD_TO_I18N`: nach `can_manage_displays: 'manageDisplays',` → `can_manage_bluetooth: 'manageBluetooth',`
- `PERMISSION_TOGGLES`: nach dem `can_manage_displays`-Eintrag → `{ key: 'can_manage_bluetooth', icon: <Bluetooth className="h-4 w-4" /> },`

`client/src/i18n/locales/de/admin.json` — die Zeile
```json
        "manageDisplays": { "label": "Displays", "desc": "Bildschirm-Ausgang und Auflösung wählen" }
```
ersetzen durch
```json
        "manageDisplays": { "label": "Displays", "desc": "Bildschirm-Ausgang und Auflösung wählen" },
        "manageBluetooth": { "label": "Bluetooth", "desc": "Bluetooth-Geräte verbinden und koppeln (Koppeln nur im lokalen Netz)" }
```
`client/src/i18n/locales/en/admin.json` entsprechend:
```json
        "manageDisplays": { "label": "Displays", "desc": "Choose the display output and resolution" },
        "manageBluetooth": { "label": "Bluetooth", "desc": "Connect and pair Bluetooth devices (pairing on the local network only)" }
```

- [ ] **Step 6: Tests laufen lassen**

Run: `cd client ; npx vitest run src/__tests__/api/bluetooth.test.ts src/__tests__/i18n/bluetooth-locale.test.ts src/__tests__/components/user-management`
Expected: PASS (auch der vorhandene Displays-Test).

- [ ] **Step 7: Commit**

```bash
git add client/src/api/bluetooth.ts client/src/api/powerPermissions.ts client/src/i18n/index.ts client/src/i18n/locales/de/bluetooth.json client/src/i18n/locales/en/bluetooth.json client/src/i18n/locales/de/admin.json client/src/i18n/locales/en/admin.json client/src/components/user-management/PowerPermissionsSection.tsx client/src/__tests__/api/bluetooth.test.ts client/src/__tests__/i18n/bluetooth-locale.test.ts client/src/__tests__/components/user-management/PowerPermissionsSection.bluetooth.test.tsx
git commit -m "feat(bluetooth): API-Client, Uebersetzungen und Rechte-Schalter" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01HbQVSEmXaZU6ZV1CjhCee6"
```

---

## Task 11: Frontend — Topbar-Popover und Koppel-Dialog

**Files:**
- Create: `client/src/components/topbar/BluetoothPairingDialog.tsx`
- Create: `client/src/components/topbar/BluetoothMenu.tsx`
- Modify: `client/src/components/layout/LayoutHeader.tsx`
- Modify: `client/src/__tests__/components/layout/LayoutHeader.test.tsx`
- Test: `client/src/__tests__/components/topbar/BluetoothPairingDialog.test.tsx`, `client/src/__tests__/components/topbar/BluetoothMenu.test.tsx`

**Interfaces:**
- Consumes: alles aus `api/bluetooth.ts` (Task 10); `getMyPowerPermissions().can_manage_bluetooth`.
- Produces: `BluetoothPairingDialog({ sessionId, deviceName, kind, onClose, pollMs? })`, `BluetoothMenu()`.

> Muster ist `DisplayMenu.tsx`: Recht per `getMyPowerPermissions`, Abfrage nur bei offenem Popover, `refresh` mit leeren Deps (sonst baut der Poll-Effekt bei jedem Render das Intervall neu auf — unter dem Test-Mock eine Endlosschleife), Fehler als i18n-**Schlüssel** im State. Der Dialog wird **außerhalb** des `isOpen`-Blocks gerendert: schließt man das Popover mitten in der Kopplung, bleibt der Dialog stehen.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

`client/src/__tests__/components/topbar/BluetoothPairingDialog.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: (ns: string) => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const values = options ? Object.values(options).join('/') : '';
      return values ? `${ns}:${key}:${values}` : `${ns}:${key}`;
    },
  }),
}));

vi.mock('../../../api/bluetooth', async () => {
  const actual = await vi.importActual<typeof import('../../../api/bluetooth')>('../../../api/bluetooth');
  return {
    ...actual,
    getPairingSession: vi.fn(),
    answerPairing: vi.fn().mockResolvedValue(undefined),
    cancelPairing: vi.fn().mockResolvedValue(undefined),
  };
});

import { BluetoothPairingDialog } from '../../../components/topbar/BluetoothPairingDialog';
import { answerPairing, cancelPairing, getPairingSession } from '../../../api/bluetooth';

function session(overrides: Record<string, unknown>) {
  return {
    session_id: 's1', address: 'AA:AA:AA:AA:AA:04', device_name: 'Dev-Tastatur',
    stage: 'connecting', code: null, entered: null, error: null, ...overrides,
  };
}

function renderDialog(kind: 'input' | 'audio' = 'input') {
  const onClose = vi.fn();
  render(
    <BluetoothPairingDialog sessionId="s1" deviceName="Dev-Tastatur" kind={kind} onClose={onClose} pollMs={10} />,
  );
  return onClose;
}

beforeEach(() => {
  vi.mocked(getPairingSession).mockReset();
});

describe('BluetoothPairingDialog', () => {
  it('zeigt den Code mit Fortschritt', async () => {
    vi.mocked(getPairingSession).mockResolvedValue(
      session({ stage: 'display_passkey', code: '482913', entered: 2 }) as never,
    );
    renderDialog();
    expect((await screen.findByTestId('pairing-code')).textContent).toBe('482913');
    expect(screen.getByTestId('pairing-progress').textContent).toBe('●●○○○○');
  });

  it('bestaetigt einen Zahlenvergleich', async () => {
    vi.mocked(getPairingSession).mockResolvedValue(
      session({ stage: 'confirm', code: '654321' }) as never,
    );
    renderDialog('audio');
    fireEvent.click(await screen.findByText('bluetooth:dialog.accept'));
    await waitFor(() => expect(answerPairing).toHaveBeenCalledWith('s1', true));
  });

  it('bricht ab', async () => {
    vi.mocked(getPairingSession).mockResolvedValue(session({}) as never);
    renderDialog();
    fireEvent.click(await screen.findByText('bluetooth:dialog.cancel'));
    await waitFor(() => expect(cancelPairing).toHaveBeenCalledWith('s1'));
  });

  it('meldet abgebrochen, wenn die Sitzung ohne Endstand verschwindet', async () => {
    vi.mocked(getPairingSession)
      .mockResolvedValueOnce(session({}) as never)
      .mockResolvedValue(null as never);
    renderDialog();
    expect(await screen.findByText('bluetooth:dialog.cancelled')).toBeTruthy();
  });

  it('ignoriert eine fremde Sitzung', async () => {
    vi.mocked(getPairingSession).mockResolvedValue(
      session({ session_id: 'andere', stage: 'display_passkey', code: '111111', entered: 0 }) as never,
    );
    renderDialog();
    await waitFor(() => expect(getPairingSession).toHaveBeenCalled());
    expect(screen.queryByTestId('pairing-code')).toBeNull();
  });

  it('uebersetzt den Fehlerschluessel', async () => {
    vi.mocked(getPairingSession).mockResolvedValue(
      session({ stage: 'failed', error: 'auth_failed' }) as never,
    );
    const onClose = renderDialog();
    expect(await screen.findByText('bluetooth:dialog.error.auth_failed')).toBeTruthy();
    fireEvent.click(screen.getByText('bluetooth:dialog.close'));
    expect(onClose).toHaveBeenCalled();
  });

  it('warnt nur bei Eingabegeraeten', async () => {
    vi.mocked(getPairingSession).mockResolvedValue(session({}) as never);
    renderDialog('input');
    expect(await screen.findByText('bluetooth:dialog.inputWarning')).toBeTruthy();
  });
});
```

`client/src/__tests__/components/topbar/BluetoothMenu.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: (ns: string) => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const values = options ? Object.values(options).join('/') : '';
      return values ? `${ns}:${key}:${values}` : `${ns}:${key}`;
    },
  }),
}));

vi.mock('../../../api/bluetooth', async () => {
  const actual = await vi.importActual<typeof import('../../../api/bluetooth')>('../../../api/bluetooth');
  return {
    ...actual,
    getBluetoothState: vi.fn(),
    setAdapterPowered: vi.fn().mockResolvedValue(undefined),
    startScan: vi.fn().mockResolvedValue(new Date(Date.now() + 30000).toISOString()),
    connectDevice: vi.fn().mockResolvedValue(undefined),
    disconnectDevice: vi.fn().mockResolvedValue(undefined),
    removeDevice: vi.fn().mockResolvedValue(undefined),
    startPairing: vi.fn().mockResolvedValue('s1'),
    getPairingSession: vi.fn().mockResolvedValue(null),
    answerPairing: vi.fn().mockResolvedValue(undefined),
    cancelPairing: vi.fn().mockResolvedValue(undefined),
  };
});

vi.mock('../../../api/powerPermissions', () => ({
  getMyPowerPermissions: vi.fn(),
}));

import { BluetoothMenu } from '../../../components/topbar/BluetoothMenu';
import {
  disconnectDevice,
  getBluetoothState,
  getPairingSession,
  removeDevice,
  startPairing,
} from '../../../api/bluetooth';
import { getMyPowerPermissions } from '../../../api/powerPermissions';

const STATE = {
  available: true, detail: null, warning: null, can_pair_here: true, pairing_active: false,
  adapter: { address: 'AA:AA:AA:AA:AA:01', name: 'BaluNode', powered: true, discovering: false },
  devices: [
    { address: 'AA:AA:AA:AA:AA:02', name: 'Xbox Wireless Controller', kind: 'controller', icon: 'input-gaming',
      paired: true, trusted: true, connected: true, battery_percent: 80, rssi: null },
    { address: 'AA:AA:AA:AA:AA:03', name: 'JBL TUNE510BT', kind: 'audio', icon: 'audio-headphones',
      paired: true, trusted: true, connected: false, battery_percent: null, rssi: null },
    { address: 'AA:AA:AA:AA:AA:04', name: 'Dev-Tastatur', kind: 'input', icon: 'input-keyboard',
      paired: false, trusted: false, connected: false, battery_percent: null, rssi: -55 },
  ],
};

beforeEach(() => {
  vi.mocked(getMyPowerPermissions).mockResolvedValue({ can_manage_bluetooth: true } as never);
  vi.mocked(getBluetoothState).mockResolvedValue(structuredClone(STATE) as never);
});

async function open() {
  render(<BluetoothMenu />);
  fireEvent.click(await screen.findByLabelText('bluetooth:title'));
  await screen.findByText('Xbox Wireless Controller');
}

describe('BluetoothMenu', () => {
  it('bleibt unsichtbar ohne das Recht', async () => {
    vi.mocked(getMyPowerPermissions).mockResolvedValue({ can_manage_bluetooth: false } as never);
    const { container } = render(<BluetoothMenu />);
    await waitFor(() => expect(getMyPowerPermissions).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });

  it('fragt erst ab, wenn das Popover offen ist', async () => {
    vi.mocked(getBluetoothState).mockClear();
    render(<BluetoothMenu />);
    await screen.findByLabelText('bluetooth:title');
    expect(getBluetoothState).not.toHaveBeenCalled();
  });

  it('gruppiert gekoppelte Geraete nach Art und zeigt den Akku', async () => {
    await open();
    expect(screen.getByText('bluetooth:kind.controller')).toBeTruthy();
    expect(screen.getByText('bluetooth:kind.audio')).toBeTruthy();
    expect(screen.getByText('bluetooth:battery:80')).toBeTruthy();
  });

  it('trennt ein verbundenes Geraet', async () => {
    await open();
    fireEvent.click(screen.getByText('bluetooth:disconnect'));
    await waitFor(() => expect(disconnectDevice).toHaveBeenCalledWith('AA:AA:AA:AA:AA:02'));
  });

  it('entfernt nur nach Rueckfrage', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    await open();
    fireEvent.click(screen.getByLabelText('bluetooth:remove: JBL TUNE510BT'));
    expect(removeDevice).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByLabelText('bluetooth:remove: JBL TUNE510BT'));
    await waitFor(() => expect(removeDevice).toHaveBeenCalledWith('AA:AA:AA:AA:AA:03'));
    confirm.mockRestore();
  });

  it('sperrt Koppeln ausserhalb des LANs mit Hinweis', async () => {
    vi.mocked(getBluetoothState).mockResolvedValue({ ...structuredClone(STATE), can_pair_here: false } as never);
    await open();
    const pair = screen.getByText('bluetooth:pair').closest('button') as HTMLButtonElement;
    expect(pair.disabled).toBe(true);
    expect(screen.getByText('bluetooth:pairOnlyLocal')).toBeTruthy();
  });

  it('sperrt Koppeln, waehrend jemand anderes koppelt', async () => {
    vi.mocked(getBluetoothState).mockResolvedValue({ ...structuredClone(STATE), pairing_active: true } as never);
    await open();
    expect((screen.getByText('bluetooth:pair').closest('button') as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('bluetooth:pairBusy')).toBeTruthy();
  });

  it('startet eine Kopplung und oeffnet den Dialog', async () => {
    vi.mocked(getPairingSession).mockResolvedValue({
      session_id: 's1', address: 'AA:AA:AA:AA:AA:04', device_name: 'Dev-Tastatur',
      stage: 'connecting', code: null, entered: null, error: null,
    } as never);
    await open();
    fireEvent.click(screen.getByText('bluetooth:pair'));
    await waitFor(() => expect(startPairing).toHaveBeenCalledWith('AA:AA:AA:AA:AA:04'));
    expect(await screen.findByText('bluetooth:dialog.connecting')).toBeTruthy();
  });

  it('meldet ein nicht verfuegbares Bluetooth statt einer leeren Liste', async () => {
    vi.mocked(getBluetoothState).mockResolvedValue({
      ...structuredClone(STATE), available: false, adapter: null, devices: [], detail: 'Kein Adapter',
    } as never);
    render(<BluetoothMenu />);
    fireEvent.click(await screen.findByLabelText('bluetooth:title'));
    expect(await screen.findByText(/bluetooth:unavailable/)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd client ; npx vitest run src/__tests__/components/topbar/BluetoothPairingDialog.test.tsx src/__tests__/components/topbar/BluetoothMenu.test.tsx`
Expected: FAIL — Komponenten fehlen.

- [ ] **Step 3: `BluetoothPairingDialog.tsx`**

```tsx
/**
 * Koppel-Dialog: zeigt den Stand der eigenen Kopplung.
 *
 * Die Sitzung lebt im Besitzer-Worker des Backends; hier wird nur
 * `GET /pairing` abgefragt. Verschwindet die Sitzung, bevor ein Endstand kam
 * (Besitzer-Worker tot, SHM geräumt), zeigt der Dialog „abgebrochen" — nie
 * einen Code, der nicht mehr gilt.
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import {
  answerPairing,
  cancelPairing,
  getPairingSession,
  TERMINAL_STAGES,
  type DeviceKind,
  type PairingSession,
} from '../../api/bluetooth';

interface BluetoothPairingDialogProps {
  sessionId: string;
  deviceName: string;
  kind: DeviceKind;
  onClose: () => void;
  /** Nur für Tests kürzer. */
  pollMs?: number;
}

export function BluetoothPairingDialog({
  sessionId,
  deviceName,
  kind,
  onClose,
  pollMs = 1000,
}: BluetoothPairingDialogProps) {
  const { t } = useTranslation('bluetooth');
  const [session, setSession] = useState<PairingSession | null>(null);
  const [lost, setLost] = useState(false);
  const [sending, setSending] = useState(false);
  const seen = useRef(false);
  const finished = useRef(false);

  useEffect(() => {
    let active = true;
    const poll = async () => {
      if (finished.current) return;
      try {
        const next = await getPairingSession();
        if (!active) return;
        const mine = next && next.session_id === sessionId ? next : null;
        if (mine) {
          seen.current = true;
          setSession(mine);
          if (TERMINAL_STAGES.has(mine.stage)) finished.current = true;
        } else if (seen.current) {
          finished.current = true;
          setLost(true);
        }
      } catch {
        // Nächster Takt versucht es erneut.
      }
    };
    void poll();
    const id = setInterval(() => void poll(), pollMs);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [sessionId, pollMs]);

  const stage = lost ? 'cancelled' : (session?.stage ?? 'connecting');
  const done = lost || (session !== null && TERMINAL_STAGES.has(session.stage));
  const title = t('dialog.title', { name: deviceName });

  const send = async (action: () => Promise<void>) => {
    setSending(true);
    try {
      await action();
    } catch {
      // Der nächste Poll zeigt den tatsächlichen Stand.
    } finally {
      setSending(false);
    }
  };

  const code = session?.code ?? null;
  const entered = session?.entered ?? null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4"
    >
      <div className="w-full max-w-sm rounded-xl border border-slate-800 bg-slate-900 p-5 shadow-xl">
        <h2 className="mb-3 text-base font-medium text-slate-100">{title}</h2>

        {kind === 'input' && !done && (
          <p className="mb-3 text-xs text-amber-400">{t('dialog.inputWarning')}</p>
        )}

        {stage === 'connecting' && (
          <p className="flex items-center gap-2 text-sm text-slate-300">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('dialog.connecting')}
          </p>
        )}

        {(stage === 'display_passkey' || stage === 'display_pin') && code && (
          <>
            <p className="mb-2 text-sm text-slate-300">
              {stage === 'display_passkey' ? t('dialog.displayPasskey') : t('dialog.displayPin')}
            </p>
            <p data-testid="pairing-code" className="mb-2 text-center font-mono text-3xl tracking-[0.4em] text-slate-100">
              {code}
            </p>
            {stage === 'display_passkey' && entered !== null && (
              <p data-testid="pairing-progress" aria-hidden="true" className="text-center text-slate-400">
                {'●'.repeat(Math.min(entered, code.length))}
                {'○'.repeat(Math.max(0, code.length - entered))}
              </p>
            )}
          </>
        )}

        {stage === 'confirm' && code && (
          <>
            <p className="mb-2 text-sm text-slate-300">{t('dialog.confirm')}</p>
            <p data-testid="pairing-code" className="mb-3 text-center font-mono text-3xl tracking-[0.4em] text-slate-100">
              {code}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={sending}
                onClick={() => void send(() => answerPairing(sessionId, true))}
                className="flex-1 rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              >
                {t('dialog.accept')}
              </button>
              <button
                type="button"
                disabled={sending}
                onClick={() => void send(() => answerPairing(sessionId, false))}
                className="flex-1 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:border-rose-500/50 disabled:opacity-50"
              >
                {t('dialog.reject')}
              </button>
            </div>
          </>
        )}

        {stage === 'succeeded' && <p className="text-sm text-emerald-400">{t('dialog.succeeded')}</p>}
        {stage === 'cancelled' && <p className="text-sm text-slate-300">{t('dialog.cancelled')}</p>}
        {stage === 'failed' && (
          <p className="text-sm text-rose-400">{t(`dialog.error.${session?.error ?? 'unknown'}`)}</p>
        )}

        <div className="mt-4 flex justify-end">
          {done ? (
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:border-sky-500/50"
            >
              {t('dialog.close')}
            </button>
          ) : (
            <button
              type="button"
              disabled={sending}
              onClick={() => void send(() => cancelPairing(sessionId))}
              className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:border-rose-500/50 disabled:opacity-50"
            >
              {t('dialog.cancel')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: `BluetoothMenu.tsx`**

```tsx
/**
 * Bluetooth-Steuerung in der Topbar.
 *
 * Absichtliche Eigenheiten:
 * - Abgefragt wird nur bei offenem Popover (alle 3 s).
 * - „Koppeln" ist außerhalb privater Netze gesperrt; der Server prüft das
 *   ohnehin, `can_pair_here` spart nur den vergeblichen Klick.
 * - Der Koppel-Dialog hängt nicht am Popover: schließt man es mitten in der
 *   Kopplung, bleibt der Dialog stehen.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bluetooth, BluetoothOff, Gamepad2, Headphones, Keyboard, Loader2, Trash2 } from 'lucide-react';
import {
  connectDevice,
  disconnectDevice,
  getBluetoothState,
  removeDevice,
  setAdapterPowered,
  startPairing,
  startScan,
  type BluetoothDevice,
  type BluetoothState,
  type DeviceKind,
} from '../../api/bluetooth';
import { getMyPowerPermissions } from '../../api/powerPermissions';
import { BluetoothPairingDialog } from './BluetoothPairingDialog';

const POLL_MS = 3000;
const KIND_ORDER: DeviceKind[] = ['controller', 'audio', 'input', 'other'];

/** i18n-Schlüssel statt Text — übersetzt wird erst beim Rendern. */
type ErrorKey = 'loadError' | 'actionError';

interface PairingTarget {
  sessionId: string;
  name: string;
  kind: DeviceKind;
}

function KindIcon({ kind }: { kind: DeviceKind }) {
  if (kind === 'controller') return <Gamepad2 className="h-4 w-4" />;
  if (kind === 'audio') return <Headphones className="h-4 w-4" />;
  if (kind === 'input') return <Keyboard className="h-4 w-4" />;
  return <Bluetooth className="h-4 w-4" />;
}

const SMALL_BUTTON =
  'rounded-lg border border-slate-700 px-2 py-0.5 text-xs text-slate-200 transition hover:border-sky-500/50 disabled:opacity-50';

export function BluetoothMenu() {
  const { t } = useTranslation('bluetooth');
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [state, setState] = useState<BluetoothState | null>(null);
  const [error, setError] = useState<ErrorKey | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [scanUntil, setScanUntil] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [pairing, setPairing] = useState<PairingTarget | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inFlight = useRef(false);

  useEffect(() => {
    let active = true;
    getMyPowerPermissions()
      .then((perms) => active && setAllowed(perms.can_manage_bluetooth))
      .catch(() => active && setAllowed(false));
    return () => {
      active = false;
    };
  }, []);

  // Leere Deps sind Absicht (siehe DisplayMenu): eine wechselnde Identität
  // liesse den Poll-Effekt bei jedem Render neu aufsetzen.
  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      setState(await getBluetoothState());
      setError((prev) => (prev === 'loadError' ? null : prev));
    } catch {
      setError('loadError');
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    void refresh();
    const id = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(id);
  }, [isOpen, refresh]);

  useEffect(() => {
    if (scanUntil === null) return;
    const id = setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (current >= scanUntil) setScanUntil(null);
    }, 1000);
    return () => clearInterval(id);
  }, [scanUntil]);

  useEffect(() => {
    const onClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [isOpen]);

  const run = async (key: string, action: () => Promise<unknown>) => {
    setBusy(key);
    setError(null);
    try {
      await action();
      await refresh();
    } catch {
      setError('actionError');
    } finally {
      setBusy(null);
    }
  };

  const handleScan = () =>
    run('scan', async () => {
      const until = await startScan();
      setNow(Date.now());
      setScanUntil(new Date(until).getTime());
    });

  const handlePair = (device: BluetoothDevice) =>
    run(device.address, async () => {
      const sessionId = await startPairing(device.address);
      setPairing({ sessionId, name: device.name, kind: device.kind });
    });

  const handleRemove = (device: BluetoothDevice) => {
    if (!window.confirm(t('removeConfirm', { name: device.name }))) return;
    void run(device.address, () => removeDevice(device.address));
  };

  if (!allowed) return null;

  const adapter = state?.available ? state.adapter : null;
  const paired = state?.devices.filter((d) => d.paired) ?? [];
  const found = state?.devices.filter((d) => !d.paired) ?? [];
  const secondsLeft = scanUntil !== null ? Math.max(0, Math.ceil((scanUntil - now) / 1000)) : 0;
  let pairBlocked: string | null = null;
  if (state && !state.can_pair_here) pairBlocked = t('pairOnlyLocal');
  else if (state?.pairing_active && !pairing) pairBlocked = t('pairBusy');

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        aria-label={t('title')}
        onClick={() => setIsOpen((open) => !open)}
        className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 text-slate-400 transition hover:border-sky-500/50 hover:text-sky-400"
      >
        {adapter && !adapter.powered ? <BluetoothOff className="h-5 w-5" /> : <Bluetooth className="h-5 w-5" />}
      </button>

      {isOpen && (
        <div className="absolute right-0 z-50 mt-2 w-96 max-w-[calc(100vw-2rem)] rounded-xl border border-slate-800 bg-slate-900/95 p-4 shadow-xl backdrop-blur-xl">
          {state && !state.available && (
            <p className="text-sm text-slate-400">
              {t('unavailable')}
              {state.detail ? ` ${state.detail}` : ''}
            </p>
          )}

          {adapter && (
            <>
              <div className="mb-3 flex items-center justify-between">
                <span className="text-sm text-slate-200">{adapter.name}</span>
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => void run('adapter', () => setAdapterPowered(!adapter.powered))}
                  className={SMALL_BUTTON}
                >
                  {adapter.powered ? t('powerOff') : t('powerOn')}
                </button>
              </div>

              {state?.warning && <p className="mb-2 text-xs text-amber-400">{state.warning}</p>}
              {!adapter.powered && <p className="text-sm text-slate-400">{t('adapterOff')}</p>}

              {adapter.powered && (
                <>
                  {paired.length === 0 && <p className="mb-2 text-sm text-slate-400">{t('noDevices')}</p>}

                  {KIND_ORDER.map((kind) => {
                    const group = paired.filter((d) => d.kind === kind);
                    if (group.length === 0) return null;
                    return (
                      <div key={kind} className="mb-3">
                        <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">{t(`kind.${kind}`)}</p>
                        {group.map((device) => (
                          <div key={device.address} className="flex items-center gap-2 py-1">
                            <span className="text-slate-400">
                              <KindIcon kind={device.kind} />
                            </span>
                            <span className="min-w-0 flex-1 truncate text-sm text-slate-200">{device.name}</span>
                            {device.battery_percent !== null && (
                              <span className="text-xs text-slate-500">
                                {t('battery', { percent: device.battery_percent })}
                              </span>
                            )}
                            <button
                              type="button"
                              disabled={busy !== null}
                              onClick={() =>
                                void run(device.address, () =>
                                  device.connected ? disconnectDevice(device.address) : connectDevice(device.address),
                                )
                              }
                              className={SMALL_BUTTON}
                            >
                              {busy === device.address ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : device.connected ? (
                                t('disconnect')
                              ) : (
                                t('connect')
                              )}
                            </button>
                            <button
                              type="button"
                              aria-label={`${t('remove')}: ${device.name}`}
                              disabled={busy !== null}
                              onClick={() => handleRemove(device)}
                              className="text-slate-500 transition hover:text-rose-400 disabled:opacity-50"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        ))}
                      </div>
                    );
                  })}

                  <div className="border-t border-slate-800 pt-3">
                    {scanUntil !== null ? (
                      <p className="mb-2 text-xs text-slate-400">{t('scanning', { seconds: secondsLeft })}</p>
                    ) : (
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() => void handleScan()}
                        className="w-full rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-sky-500 disabled:opacity-50"
                      >
                        {t('addDevice')}
                      </button>
                    )}
                    {scanUntil !== null && found.length === 0 && (
                      <p className="text-xs text-slate-500">{t('noneFound')}</p>
                    )}
                    {found.map((device) => (
                      <div key={device.address} className="flex items-center gap-2 py-1">
                        <span className="text-slate-400">
                          <KindIcon kind={device.kind} />
                        </span>
                        <span className="min-w-0 flex-1 truncate text-sm text-slate-200">{device.name}</span>
                        <button
                          type="button"
                          disabled={busy !== null || pairBlocked !== null}
                          title={pairBlocked ?? undefined}
                          onClick={() => void handlePair(device)}
                          className={SMALL_BUTTON}
                        >
                          {t('pair')}
                        </button>
                      </div>
                    ))}
                    {pairBlocked && found.length > 0 && (
                      <p className="mt-1 text-xs text-amber-400">{pairBlocked}</p>
                    )}
                  </div>
                </>
              )}
            </>
          )}

          {error && <p className="mt-2 text-xs text-rose-400">{t(error)}</p>}
        </div>
      )}

      {pairing && (
        <BluetoothPairingDialog
          sessionId={pairing.sessionId}
          deviceName={pairing.name}
          kind={pairing.kind}
          onClose={() => {
            setPairing(null);
            void refresh();
          }}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 5: In den Header einhängen**

`client/src/components/layout/LayoutHeader.tsx`:
- Import nach `DisplayMenu`: `import { BluetoothMenu } from '../topbar/BluetoothMenu';`
- nach `const displaysEnabled = …`: `const bluetoothEnabled = usePluginEnabled('bluetooth');`
- vor `{!isPi && displaysEnabled && <DisplayMenu />}`: `{!isPi && bluetoothEnabled && <BluetoothMenu />}`

`client/src/__tests__/components/layout/LayoutHeader.test.tsx`:
- `pluginState` erweitern: `vi.hoisted(() => ({ audioEnabled: false, bluetoothEnabled: false }))`
- `usePluginEnabled`-Mock: `(name: string) => (name === 'audio_control' && pluginState.audioEnabled) || (name === 'bluetooth' && pluginState.bluetoothEnabled)`
- Mock ergänzen (nach dem `audioControl`-Mock; alle von BluetoothMenu und Dialog importierten Namen müssen darin stehen):
  ```tsx
  vi.mock('../../../api/bluetooth', () => ({
    TERMINAL_STAGES: new Set(['succeeded', 'failed', 'cancelled']),
    getBluetoothState: vi.fn().mockResolvedValue({ available: false, detail: null, warning: null, adapter: null, devices: [], can_pair_here: false, pairing_active: false }),
    setAdapterPowered: vi.fn(), startScan: vi.fn(), connectDevice: vi.fn(), disconnectDevice: vi.fn(),
    removeDevice: vi.fn(), startPairing: vi.fn(), getPairingSession: vi.fn().mockResolvedValue(null),
    answerPairing: vi.fn(), cancelPairing: vi.fn(),
  }));
  ```
- `getMyPowerPermissions`-Mock: `{ can_control_audio: true, can_manage_bluetooth: true }`
- `beforeEach`: zusätzlich `pluginState.bluetoothEnabled = false;`
- neuer Test:
  ```tsx
  it('bluetooth aktiviert: Bluetooth-Symbol erscheint', async () => {
    pluginState.bluetoothEnabled = true;
    render(<MemoryRouter><LayoutHeader {...props} /></MemoryRouter>);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'title' })).toBeInTheDocument(),
    );
  });
  ```

- [ ] **Step 6: Tests, Lint, Build**

Run: `cd client ; npx vitest run src/__tests__/components/topbar src/__tests__/components/layout ; npx eslint . ; npm run build`
Expected: Tests PASS, eslint 0 Fehler, Build ohne Fehler (`tsc -b` prüft auch die Testprojekte).

- [ ] **Step 7: Commit**

```bash
git add client/src/components/topbar/BluetoothMenu.tsx client/src/components/topbar/BluetoothPairingDialog.tsx client/src/components/layout/LayoutHeader.tsx client/src/__tests__/components/topbar/BluetoothMenu.test.tsx client/src/__tests__/components/topbar/BluetoothPairingDialog.test.tsx client/src/__tests__/components/layout/LayoutHeader.test.tsx
git commit -m "feat(bluetooth): Topbar-Popover und Koppel-Dialog" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01HbQVSEmXaZU6ZV1CjhCee6"
```

---

## Task 12: Betrieb und Doku

**Files:**
- Modify: `deploy/install/modules/10-systemd-services.sh` (nach dem `video`-Gruppenblock, Zeile 187–194)
- Modify: `backend/.env.example`
- Create: `backend/app/plugins/installed/bluetooth/CLAUDE.md`
- Modify: `backend/app/plugins/CLAUDE.md`, `CLAUDE.md` (Wurzel), `.claude/rules/architecture.md`, `.claude/rules/security-agent.md`, `client/src/i18n/CLAUDE.md`

> `deploy/` und `.claude/rules/security*` sind CODEOWNERS-Pfade — im PR-Text ausdrücklich erwähnen.

- [ ] **Step 1: Install-Modul — Gruppe `bluetooth`**

In `deploy/install/modules/10-systemd-services.sh` direkt **vor** `# --- Reload systemd ---` einfügen:
```bash
# --- Bluetooth group (bluetooth plugin) ---
log_step "Bluetooth Group"

# The BlueZ D-Bus policy grants org.bluez to the 'bluetooth' group. Only act
# when BlueZ is installed (the group exists); without it the plugin reports
# available=false and nothing else breaks.
if getent group bluetooth &>/dev/null; then
    if id -nG "$BALUHOST_USER" | tr ' ' '\n' | grep -qx bluetooth; then
        log_info "$BALUHOST_USER already in 'bluetooth' group."
    else
        usermod -aG bluetooth "$BALUHOST_USER"
        log_info "Added $BALUHOST_USER to 'bluetooth' group (takes effect on next service start)."
    fi
else
    log_warn "Group 'bluetooth' not found (BlueZ not installed) — bluetooth plugin will be unavailable."
fi
```

Run: `bash -n deploy/install/modules/10-systemd-services.sh` (Git Bash)
Expected: keine Ausgabe (Syntax OK).

- [ ] **Step 2: `backend/.env.example`**

Ans Dateiende:
```
# Bluetooth plugin — MAC of the adapter to use. Empty = the only adapter
# present. With several adapters and no value the plugin refuses instead of
# guessing: pairings are stored per adapter MAC.
BLUETOOTH_ADAPTER_ADDRESS=
```

- [ ] **Step 3: Plugin-CLAUDE.md**

`backend/app/plugins/installed/bluetooth/CLAUDE.md`:
````markdown
# Bluetooth Plugin

Bundled (in-process, fully trusted) plugin: lists, connects, disconnects,
removes and **pairs** Bluetooth devices, driven from a topbar popover. Talks to
BlueZ directly over the system D-Bus with `dbus-next`. Design:
`docs/superpowers/specs/2026-09-11-bluetooth-plugin-design.md`.

Trust tier, lifecycle and the `PluginBase` contract are in `../../CLAUDE.md`.

## Layout

| File | Contents |
|---|---|
| `bluez.py` | The **only** module that talks to `org.bluez`: pure parsers, adapter selection, `BlueZClient` (low-level `Message` + `bus.call`), `BlueZError` |
| `pairing.py` | One pairing system-wide: `flock` lock, SHM hand-over, `ActivePairing` (the prompter), `PairingCoordinator` |
| `agent.py` | `BluezAgent` — `org.bluez.Agent1`, answers only about the session device |
| `backend.py` | `BluetoothBackend` protocol, `DevBluetoothBackend`, `BlueZBackend` |
| `service.py` | Backend choice, validation, LAN gate, error mapping, scan window |
| `models.py` | Pydantic models; field names are the API contract |
| `__init__.py` | `BluetoothPlugin`, router, audit |

Frontend: `client/src/components/topbar/BluetoothMenu.tsx`,
`BluetoothPairingDialog.tsx`, `client/src/api/bluetooth.ts`,
`client/src/i18n/locales/{de,en}/bluetooth.json`.

## Why bundled, why no sudo

The service user is in group `bluetooth` (measured on BaluNode, gid 106 in
`/proc/<MainPID>/status`); the BlueZ D-Bus policy
(`/usr/share/dbus-1/system.d/`) grants that group `org.bluez`. A sandbox plugin
runs as `baluhost-plugin` without that group and would not reach BlueZ.

## Worker model

- **Stateless** (read, connect, disconnect, remove, power): any worker.
- **Scan**: the accepting worker holds discovery for 30 s on its own bus
  connection; BlueZ counts discovery per client, so parallel scans (or KDE's)
  are harmless.
- **Pairing**: the accepting worker becomes the owner. Lock =
  `flock` on `/tmp/baluhost-bluetooth-pairing.lock` (**not** in
  `/dev/shm/baluhost/` — `cleanup_shm()` deletes everything there). Status in
  `bluetooth_pairing.json` (0600, heartbeat 5 s, stale after 15 s), answers in
  `bluetooth_pairing_answer.json`. A dead owner releases the lock via the
  kernel and BlueZ aborts the pairing when its bus connection closes.

## Three dbus-next traps

1. **No `from __future__ import annotations` in `agent.py` or `__init__.py`.**
   dbus-next reads D-Bus signatures from annotations; FastAPI's body detection
   behind slowapi breaks the same way.
2. **`@method()` discards return values on direct calls** — logic lives in
   `handle_*`, tests call only those.
3. **D-Bus type strings as constants** (`OBJ = "o"`), because pyflakes reports
   a literal `'o'` annotation as F821.

## Security invariants

- Every route: `require_power_manage_bluetooth` + `get_limit("bluetooth")`.
- Pair and confirm only when `is_private_or_local_ip(client_host)` — for every
  role. VPN clients count as local (deliberate). Denied attempts are audited.
- The agent is registered **without** `RequestDefaultAgent` and answers only
  about the session device; incoming pairing stays with KDE.
- Passkeys/PINs are never logged or audited and only returned to the initiator.
- The plugin never writes `Discoverable`, `Pairable`, `main.conf` or kernel
  parameters.
- Addresses reach BlueZ only after MAC validation **and** a match in the live
  object tree; object paths are built from validated addresses.
- BlueZ error text is logged, never returned — `action_error()` /
  `outcome_for_error()` map names to curated messages.

## Tests

`backend/tests/plugins/test_bluetooth_{parser,client,pairing,agent,backend,service,routes,ui_manifest}.py`
plus `backend/tests/test_power_permissions_manage_bluetooth.py`. The fixture
`fixtures/bluez_balunode.json` is a **measured**, anonymized capture
(`backend/scripts/debug/bluez_probe.py dump --anonymize`) — re-measure, don't
hand-edit. No test touches a real bus.
````

- [ ] **Step 4: Verweise in bestehender Doku**

`backend/app/plugins/CLAUDE.md` — im Baum nach der `audio_control/`-Zeile:
```
    ├── bluetooth/          # BlueZ over D-Bus: devices, scan, pairing with an own agent
```

`CLAUDE.md` (Wurzel), Abschnitt „Quick Reference", nach der Zeile **Display outputs**:
```
**Bluetooth**: `backend/app/plugins/installed/bluetooth/` (bundled Plugin; `bluez.py` kapselt den gesamten org.bluez-Kontakt, `pairing.py` + `agent.py` die Kopplung)
```

`.claude/rules/architecture.md`, API-Liste, nach der `display_output`-Zeile:
```
- `/api/plugins/bluetooth/*` - Bluetooth (Geräte, Scan, Kopplung mit Code im Web-UI; Koppeln nur aus privaten Netzen)
```

`.claude/rules/security-agent.md`, Abschnitt „Role Model", nach dem Absatz zu `can_unlock_session`:
```
- `can_manage_bluetooth` (power permission) verbindet, entfernt und koppelt
  Bluetooth-Geräte. Koppeln und Bestätigen sind doppelt gegated: Recht **und**
  `is_private_or_local_ip(request.client.host)` — für alle Rollen, VPN zählt als
  lokal. Ein gekoppeltes Eingabegerät tippt in die Desktop-Session; ein
  gestohlenes Web-Konto plus Funkreichweite darf dafür nicht reichen.
  Durchgesetzt in `plugins/installed/bluetooth/service.py` (`start_pairing`,
  `answer`); abgelehnte Versuche von außen werden auditiert.
```

`client/src/i18n/CLAUDE.md`, Namespace-Tabelle, nach der `audio`-Zeile:
```
| `bluetooth` | Topbar Bluetooth control (`BluetoothMenu`, `BluetoothPairingDialog`) |
```

- [ ] **Step 5: Commit**

```bash
git add deploy/install/modules/10-systemd-services.sh backend/.env.example backend/app/plugins/installed/bluetooth/CLAUDE.md backend/app/plugins/CLAUDE.md CLAUDE.md .claude/rules/architecture.md .claude/rules/security-agent.md client/src/i18n/CLAUDE.md
git commit -m "docs(bluetooth): Betrieb, Plugin-Doku und Verweise" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01HbQVSEmXaZU6ZV1CjhCee6"
```

---

## Task 13: Gesamtprüfung, PR, Abnahme auf BaluNode

- [ ] **Step 1: Backend**

Run: `cd backend ; python -m pytest tests/plugins/test_bluetooth_parser.py tests/plugins/test_bluetooth_client.py tests/plugins/test_bluetooth_pairing.py tests/plugins/test_bluetooth_agent.py tests/plugins/test_bluetooth_backend.py tests/plugins/test_bluetooth_service.py tests/plugins/test_bluetooth_routes.py tests/plugins/test_bluetooth_ui_manifest.py tests/test_power_permissions_manage_bluetooth.py tests/test_power_permissions_manage_displays.py -v --no-cov`
Expected: alle PASS.

Run: `cd backend ; python -m ruff check app tests scripts/debug/bluez_probe.py ; python -m alembic heads`
Expected: `All checks passed!`; genau ein Head `e7c2a9d41f86`.

Die **volle** Backend-Suite läuft in der CI (hängt unter Windows).

- [ ] **Step 2: Frontend**

Run: `cd client ; npx vitest run ; npx eslint . ; npm run build`
Expected: Suite grün, eslint 0 Fehler, Build ohne Fehler.

- [ ] **Step 3: Dev-Rundgang (Windows, `python start_dev.py`)**

Plugin „Bluetooth" in der Plugin-Verwaltung aktivieren, Backend neu starten (Router wird nur beim Start gemountet). Als `admin` im Popover: zwei gekoppelte Geräte, „Gerät hinzufügen" → drei Funde; Dev-Tastatur koppeln → Code mit wachsenden Punkten, danach „gekoppelt"; Dev-Telefon → Ja/Nein; Dev-Maus → ohne Rückfrage. Als `user` ohne Recht: kein Symbol. Recht vergeben → Symbol erscheint.

- [ ] **Step 4: PR öffnen**

Push und PR gegen `main`. Im PR-Text: CODEOWNERS-Pfade (`deploy/install/modules/10-systemd-services.sh`, `.claude/rules/security-agent.md`), neues Recht + Migration `e7c2a9d41f86`, Spike-Ergebnis, Hinweis „nach Merge Router-Neustart nötig". PR-Text per Datei (`gh pr create --body-file`), endet mit:
```
🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01HbQVSEmXaZU6ZV1CjhCee6
```

- [ ] **Step 5: Abnahme auf BaluNode (Betreiber, nach Merge und Deploy)**

1. Plugin aktivieren, `sudo systemctl restart baluhost-backend`.
2. `GET /api/plugins/bluetooth/state` über das Popover: Adapter `A0:AD:9F:6F:43:F1`, Controller und JBL korrekt gruppiert, Akkustand wo vorhanden.
3. JBL aus dem Popover trennen/verbinden; im Audio-Popover erscheint der Ausgang (Kopplung über PipeWire, kein Code dazwischen).
4. Wenn eine BT-Tastatur verfügbar ist: koppeln, Code im Web-UI, auf der Tastatur tippen, Erfolg. Sonst die Maus.
5. Außerhalb des LANs (Mobilfunk ohne VPN): Koppeln-Knopf gesperrt; direkter `POST …/pair` → 403 und Audit-Eintrag `bluetooth_pair_denied`.
6. Kein Code im Journal: `journalctl -u baluhost-backend --since "10 min ago" | grep -c <gezeigter Code>` → `0`.
7. Nach Merge: Worktree/Branch aufräumen (`git branch -d feat/bluetooth-plugin`).

