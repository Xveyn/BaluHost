# TUI Companion Rebuild — Design

**Date:** 2026-06-07
**Branch:** `feat/tui-companion-rebuild`
**Status:** Approved (brainstorming), pending implementation plan

## Purpose

Rebuild the BaluHost TUI (`backend/baluhost_tui/`) so it becomes a true **alternative to the Tauri Companion app** — an SSH-friendly, terminal-based admin & recovery tool that can perform **destructive operations** on the server.

The Tauri Companion is just an HTTP→Unix-socket reverse proxy (Rust) wrapping the React web UI: its webview talks to the backend over the Unix socket `/run/baluhost/local.sock`, which makes its requests `channel=local`, which is what unlocks the destructive (`require_local_admin`-gated) operations. A browser over TCP is `channel=remote` and has those operations blocked.

For the TUI to be an equal-footing alternative it must **also speak over the local channel**. The current TUI talks over TCP/HTTP and partly via direct DB access, so it is `channel=remote` and cannot perform the gated operations. This rebuild fixes that and resolves the accumulated architecture debt.

## Background: how the local channel works (already implemented)

This trust model already exists in the codebase (see `docs/superpowers/specs/2026-05-25-tauri-local-admin-design.md`):

- **Two backend processes.** One TCP-bound (`BALUHOST_CHANNEL=remote`), one bound to the Unix socket `/run/baluhost/local.sock` via systemd socket activation (`baluhost-backend-local.service` + `.socket`, `BALUHOST_CHANNEL=local`, socket mode `0660 baluhost:baluhost`).
- **`ChannelMarkerMiddleware`** stamps every request with `request.state.channel` from the per-process `BALUHOST_CHANNEL` env var — fixed per process, **not** spoofable via headers.
- **`require_local_admin`** dependency = admin role **AND** `channel == "local"`. On a remote channel it returns `403 {"error": "local_channel_required"}` and writes an audit log entry.
- **Dev loopback fallback.** `start_dev.py` sets `BALUHOST_LOCAL_LOOPBACK_FALLBACK=true`, so the dev backend treats `127.0.0.1` TCP as `channel=local`. (Blocked in production by a settings validator.)

### Endpoints gated by `require_local_admin` (the destructive set)

| Endpoint | Handler |
|---|---|
| `POST /api/system/raid/delete-array` | `delete_array` |
| `POST /api/system/raid/create-array` | `create_array` |
| `POST /api/system/raid/format-disk` | `format_disk` |
| `POST /api/plugins/{name}/install` (marketplace) | `install_plugin` |
| `DELETE /api/plugins/{name}` (marketplace + core) | `uninstall_plugin` |
| `POST /api/vpn/sync-server-keys` | `sync_server_keys` |
| `POST /api/users/bulk-delete` | `bulk_delete_users` |
| `POST /api/setup/*` | setup wizard (uses `require_local_or_setup_secret`) |

### Adjacent admin endpoints (admin-only, any channel)

- `POST /api/system/restart` — restarts the **app** process (systemd service in prod / SIGINT in dev). Not OS reboot.
- `POST /api/system/shutdown` — stops the **app** process. Not OS poweroff.
- `POST /api/system/sleep/{soft,wake,suspend,wol}` + `GET /api/system/sleep/status` — sleep/suspend/Wake-on-LAN.

**Open item:** There is **no** OS-level `reboot`/`poweroff` endpoint. Whether to add one (`POST /api/system/reboot` + `/poweroff`, local-channel-gated, `systemctl reboot/poweroff` via sudoers) is deferred — decided "later". Tracked in Open Items below.

## Decisions (from brainstorming)

1. **Transport: Unix-socket only** (like Tauri). Drop the old `remote`-over-HTTP mode and the direct-DB mode. The interactive TUI runs on the server.
2. **Scope: admin/recovery focus.** All destructive ops + diagnostics. No full file-manager parity.
3. **Structure: rebuild the foundation, port the screens.** New client/API layer + screen base, then migrate the salvageable screens and add new ones.
4. **File-browser screen: remove for now** (code stays in git history). CLI `files-download`/`files-upload` commands stay (API-based, useful for scripted recovery).
5. **OS reboot/poweroff: deferred.** Build with the existing app-restart/shutdown + sleep/suspend/WoL.

## Architecture

### Transport — one client, two bindings

A single `BackendClient` (httpx) is bound differently per environment but speaks the identical API:

| Environment | Binding | Why `channel=local` |
|---|---|---|
| **Prod (Linux)** | Unix socket `/run/baluhost/local.sock` via `httpx.HTTPTransport(uds=...)`, `base_url="http://localhost"` | `baluhost-backend-local.service` sets `BALUHOST_CHANNEL=local` |
| **Dev (Windows)** | TCP `http://127.0.0.1:3001` | `start_dev.py` sets `BALUHOST_LOCAL_LOOPBACK_FALLBACK=true` → 127.0.0.1 counts as local |

httpx speaks UDS natively, so the TUI needs **no** Rust proxy (unlike Tauri, which needs it because a webview can only do TCP).

**Auto-detection** replaces the old `auto/local/remote` modes:
- If the socket file exists (default `/run/baluhost/local.sock`) → use UDS.
- Else → TCP loopback (`http://127.0.0.1:3001`).
- Overridable: `--socket <path>` or `--server <url>`.

### Auth — JWT still required

`require_local_admin` is admin **AND** local. The local channel alone is not enough, so the TUI must still authenticate with a JWT:
- Login screen calls `POST /api/auth/login` through the client, stores the access token in the client.
- The **direct-DB login path is removed entirely** (`login.py` no longer imports `SessionLocal`/`get_user_by_username`).

On `403 local_channel_required` (e.g. accidentally pointed at the remote process), show a clear message, not a raw error.

### New foundation layer

```
baluhost_tui/
├── client.py          # NEW: BackendClient — UDS/TCP transport, JWT, unified GET/POST/PUT/DELETE + error mapping
├── api/               # NEW: typed wrappers per domain (mirrors client/src/api/)
│   ├── auth.py        #   login(), me()
│   ├── system.py      #   raid_*, restart, shutdown, channel_status, smart, telemetry, sleep_*
│   ├── users.py       #   list, create, update, reset_password, delete, bulk_delete
│   ├── services.py    #   list, restart
│   ├── plugins.py     #   list, install, uninstall
│   ├── vpn.py         #   clients (read), sync_server_keys
│   └── network.py     #   interfaces / IPs
├── screens/
│   ├── base.py        # NEW: BaseScreen — shared bindings, error toast, refresh pattern
│   └── ...            # ported + new screens
├── widgets/           # NEW: ConfirmDialog (destructive ops), StatusBar
├── app.py             # slim: routing + global bindings only
├── config.py          # extended: settings persistence (socket path, theme)
└── main.py            # slim Click CLI
```

**Cleaned up in the process:**
- The `sys.path.insert(...)` hack repeated in every screen module → resolved once centrally (package import).
- Direct-DB imports in `login.py`, `users.py`, `dashboard.py` → removed.
- Hardcoded `v1.0.0` in the welcome screen → real version.
- Inconsistent `mode` handling → gone (single transport model).

## Screen & Feature Map

Destructive ops are **bold** (run through `require_local_admin`, require `ConfirmDialog`).

| Screen | Source | Endpoints | Notes |
|---|---|---|---|
| Login | port | `POST /api/auth/login` | DB login removed → JWT via client |
| Dashboard | port | telemetry / monitoring / raid status | direct-DB removed; show dev mock data |
| System / RAID | extend | status + **create-array / delete-array / format-disk** | destructive ops new |
| Users | port | list/create/update/reset-pw/delete + **bulk-delete** | all via API; bulk-delete new |
| Services | keep | `/api/admin/services` + restart | already API-based |
| Power | extend | sleep/wake/suspend/wol + **app-restart / app-shutdown** | restart/shutdown new |
| SMART | keep | `/api/system/smart/*` | already API-based |
| Logs | keep + extend | audit logs + (new) live system logs | live-tail new |
| Plugins | NEW | list + **install / uninstall** | destructive |
| VPN | NEW | clients (read-only) + **sync-server-keys** | no tunnel start (per constraint) |
| Network | NEW | interfaces / IPs | "is the NAS reachable?" |
| Settings | NEW | local (socket path, theme) | was missing entirely |

**Intentionally out of scope** (scope discipline; can return later as small additions): full file-manager, scheduler detail, backup, mobile devices, Pi-hole, fan-curve editor.

### Destructive-ops UX

A single `ConfirmDialog` widget:
- Names the action and the target.
- Type-to-confirm for the most dangerous ops (e.g. RAID delete: type the array name).
- Maps `403 local_channel_required` to a clear explanation rather than a cryptic error.

## CLI surface (`baluhost-tui`)

```
baluhost-tui                                     # interactive TUI (auto-detect socket→UDS, else TCP-loopback)
baluhost-tui --socket /run/baluhost/local.sock  # explicit socket
baluhost-tui --server http://127.0.0.1:3001     # explicit TCP (dev)
baluhost-tui status                             # quick status (API)
baluhost-tui users                              # user list (API)
baluhost-tui files-download / files-upload      # kept (API-based, recovery scripting)
baluhost-tui reset-password <user>              # kept CLI-only — direct-DB emergency escape hatch
```

**`reset-password`** is today the only direct-DB path and the genuine lock-out recovery anchor (backend dead, admin locked out). The *interactive* TUI becomes UDS/JWT-only as decided; `reset-password` remains a **separate CLI escape hatch with direct DB access** — it is not a "TUI talks to backend" case but an offline admin script. This is consistent with the UDS-only decision and preserves recovery value.

## Testing

There is already a `backend/tests/tui/` suite (`test_app_actions`, `test_login_token`, `test_power_screen`, `test_services_screen`, `test_smart_screen`) using a FakeClient pattern.

- **`BackendClient`**: UDS vs TCP transport selection, JWT header injection, error mapping (incl. `403 local_channel_required`).
- **Per `api/` wrapper**: request shape + response parsing against a FakeClient (existing pattern in `test_services_screen.py`).
- **Destructive screens**: ConfirmDialog gate (no action without confirmation), correct endpoint called.
- **Existing TUI tests** (power/services/smart/login/app_actions): adapt to the new foundation, do not discard.
- Runs on Windows (dev) + CI.

## Build order (incremental, always green)

1. **Foundation**: `client.py` (BackendClient, UDS+TCP) + `api/auth.py` + `screens/base.py` + tests.
2. **Login** → JWT (remove direct-DB). From here everything authenticates through the client.
3. **Dock existing API screens** (services, smart, power) onto the new foundation.
4. **Port Dashboard + Users** (remove direct-DB; add bulk-delete).
5. **RAID** destructive (create/delete/format + ConfirmDialog).
6. **New screens**: Plugins, VPN, Network, Settings, live system logs.
7. **Cleanup** `app.py`/`main.py`, centralize `sys.path`, fix welcome version, remove `files` screen.
8. **Docs**: update `TUI_FEATURE_AUDIT.md` and any TUI docs.

## Risks / Trade-offs

1. **httpx UDS on Windows**: not needed in dev (TCP loopback) → no problem. The UDS path is tested on Linux/CI.
2. **Socket permissions**: the TUI's OS user must be in group `baluhost` (socket is `0660 baluhost:baluhost`) — same condition as SSH access to the box; document it.
3. **Doubled backend process**: already running for Tauri; the TUI reuses the same socket, no new process.
4. **OS reboot/poweroff**: deferred follow-up (see Open Items).

## Open Items

- **OS reboot/poweroff endpoint** (`POST /api/system/reboot` + `/poweroff`, local-channel-gated, `systemctl` via sudoers): decision deferred. If approved later, it expands scope to backend + deploy (sudoers) and adds a TUI Power action.
- **Live system-logs source**: confirm whether to tail journald (`journalctl`) via a new backend endpoint or reuse an existing logs API — to be settled in the implementation plan when building the Logs screen.

## Out of scope (per constraints)

- VPN tunnel start from the TUI (read-only VPN, per existing user constraint).
- External reachability — the TUI stays server-local (runs over the local socket).
- Full file-manager parity, scheduler/backup/mobile/Pi-hole/fan-curve screens (possible later additions).
