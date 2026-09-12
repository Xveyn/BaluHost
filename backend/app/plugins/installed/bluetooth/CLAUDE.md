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
