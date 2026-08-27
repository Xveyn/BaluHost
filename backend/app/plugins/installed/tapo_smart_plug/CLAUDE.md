# Tapo Smart Plug Plugin

Bundled (in-process, fully trusted) plugin for TP-Link Tapo **P110 / P115** smart
plugs: on/off switching, live power monitoring, a dashboard gauge, and an
admin-triggered import of the device's own energy history.

**No router.** This plugin extends `SmartDevicePlugin` (not `PluginBase`
directly), so all interaction goes through the unified `/api/smart-devices/` API.
Nothing here is reachable at `/api/plugins/tapo_smart_plug/*`, and no restart is
needed to enable/disable it.

Trust tier and lifecycle: `../../CLAUDE.md`. The SmartDevice framework it plugs
into: `../../smart_device/` (`base.py`, `manager.py`, `poller.py`,
`capabilities.py`, `schemas.py`).

## Layout

| File | Contents |
|---|---|
| `__init__.py` | `TapoSmartPlugPlugin` — device types, capabilities, dashboard panel, config schema, credential resolution |
| `service.py` | `TapoService` — real device I/O via **plugp100**, with a per-device client cache |
| `mock.py` | `TapoMockService` — dev-mode live data (60–180 W, 230 V ± 5, 1.5–3.5 kWh/day) |
| `history.py` | `TapoHistoryFetcher` — historical energy buckets via the **tapo** library |
| `history_mock.py` | Deterministic dev-mode history fetcher |
| `import_service.py` | `TapoHistoryImportService` — buckets → `SmartDeviceSample` rows with conflict handling |
| `plugin.json` | Marketplace manifest (see below) |

## Two Tapo libraries, deliberately

- **plugp100** (`>=5.0.0,<6.0.0`) — live polling and switching (`service.py`).
- **tapo** (mihai-dinculescu) — history import only (`history.py`). It exposes a
  typed `get_energy_data` with hourly/daily/monthly intervals that plugp100 v5.x
  does not surface.

Do not "consolidate" these without checking that the replacement covers both
paths. Only plugp100 is declared in `plugin.json`'s `python_requirements`; the
`tapo` import is lazy, so a box without it fails at import time, not at startup.

`_patch_plugp100_bugs()` monkey-patches plugp100 v5.1.5's
`InvalidAuthentication.__init__`, which calls `super(f"...")` instead of
`super().__init__(f"...")` and therefore raises `TypeError` instead of the real
auth error. The patch is guarded: it first *tries* to construct the exception and
only patches if the bug is still present, so a fixed upstream version is left
alone. Delete it once the floor moves past the fix.

## Credentials

Tapo credentials (account email + password) live **encrypted** in
`SmartDevice.config_secret` (Fernet, via `services/vpn/encryption.py`, keyed by
`VPN_ENCRYPTION_KEY`). Two paths reach them:

- `connect_device()` — the manager passes an already-decrypted config dict; the
  plugin caches it in `self._device_info` as `_DeviceInfo(ip, email, password)`.
- `_ensure_device_info()` — the **fallback**. The poller runs in a separate
  process with its own plugin instance where `connect_device()` was never called,
  so it re-reads the row and decrypts it itself. If `vpn_encryption_key` is unset
  it falls back to parsing `config_secret` as plain JSON.

Credentials are held in memory as plaintext for the lifetime of the process and
are passed to every service call. They must never reach a log line, a response
model, or an exception message — `logger.warning` calls in this file deliberately
log only the device id.

## Live path

`poll_device()` / `poll_device_mock()` are picked by the framework; the switch and
power capability methods pick for themselves via `_is_dev_mode()`. Poll interval
is **5 s** (`get_poll_interval_seconds`). `TapoService` caches one connected
plugp100 client per `device_id:ip` and evicts it on timeout or error so the next
call reconnects from scratch; `_DEVICE_TIMEOUT = 10 s` per operation.

The dashboard panel (`gauge`) does **not** poll — it reads the SHM snapshot
`SMART_DEVICES_FILE` (`max_age_seconds=30`) written by the monitoring worker and
joins it against active+online `SmartDevice` rows. `progress` is against a
hard-coded `max_power = 150.0 W`. Returns `None` (panel hidden) when no device
reported a non-zero reading. `TapoPluginConfig.panel_devices` narrows which
devices count; it is read straight off `InstalledPlugin.config`.

## History import

Admin-only; the API route enforces authorization, `import_history()` assumes it.
Flow: resolve cached credentials → `fetch_buckets()` (real or mock) →
`TapoHistoryImportService.write_buckets()` → `ImportHistoryResponse`.

- Long ranges are split into several API calls to respect the library's
  constraints (hourly ≤ 8 days, daily per quarter, monthly per year).
- Watts are **synthesized** from bucket energy using `_BUCKET_HOURS`; monthly uses
  an average month (30.4375 d). Acceptable because aggregation divides by the
  actual observed `period_hours` at query time (`energy.py`).
- `_DEFAULT_VOLTAGE = 230.0`, consistent with the live extraction.
- Idempotency and the live-sample conflict strategy live in `import_service.py`,
  keyed on a marker in `data_json` that live samples never contain.
- `_fetcher_override` is a test seam — set it to inject a stub fetcher rather
  than monkeypatching the `tapo` import.

## Dev mode

`_is_dev_mode()` swallows exceptions and defaults to **False** (prod). Every
service getter (`_get_service`, `_build_fetcher`, each capability method) branches
on it separately; there is no single switch. `TapoMockService` and
`TapoHistoryMockFetcher` need no hardware and run on Windows.

## Operator note

Each device needs **"Third-Party Compatibility"** enabled in the Tapo app or it
may not respond — that is why `settings_third_party_hint` exists in
`get_translations()`.

`TapoPluginConfig` exposes `panel_devices` (dashboard filter) and `retention_days`
(0 = unlimited) with `x-options-source` / `x-presets` hints the settings UI reads.

## plugin.json vs. metadata

`plugin.json` is the **marketplace** manifest and its `homepage` points at the
external `BaluHost-Plugin-Market` repo. Bundled discovery does not read it — the
manager finds the `SmartDevicePlugin` subclass in `__init__.py`. `version`,
`description` and `required_permissions` therefore exist twice; when editing one,
check the other.

## Tests

- `backend/tests/plugins/tapo_smart_plug/` — `test_history_fetcher.py`,
  `test_history_mock.py`, `test_import_service.py`, `test_plugin_import_history.py`
- `backend/tests/plugins/test_tapo_plugin_config.py`
- Framework-level coverage that exercises this plugin:
  `test_smart_device_{base,manager,poller,retention,routes,schemas}.py`
