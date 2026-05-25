# Tauri Companion App + Local-Channel Gate for Destructive Admin Operations

**Date:** 2026-05-25
**Status:** Draft — awaiting user review
**Related:** `.claude/rules/security-agent.md`, `.claude/rules/ci-cd-security.md`, `backend/app/middleware/local_only.py`, `docs/superpowers/specs/2026-04-12-dev-impersonation-design.md`

## Problem

BaluHost has ~10 admin endpoints whose effect is irreversible: deleting a RAID array, installing/uninstalling a plugin (arbitrary code execution), rotating VPN server keys, bulk-deleting users, formatting disks, and the initial setup wizard. Today these are gated only by `get_current_admin` — a stolen JWT or compromised admin session lets any remote attacker trigger them.

The defense-in-depth gap: there is no second factor that requires physical presence at the server. The existing `local_only.py` middleware accepts the whole private LAN (192.168/10.x/172.16) as "local," which is too permissive — any device on the home network would pass.

## Goal

Add a second mandatory gate on the most destructive admin endpoints: the request must arrive via a Unix-domain socket served by a dedicated backend process that only the BaluNode's `baluhost` OS user can reach. JWT authentication remains mandatory (defense-in-depth, not auto-elevation).

A small Tauri desktop app installed on the BaluNode itself is the intended consumer of this local channel. Web UI keeps working for everything else; destructive-action buttons in the Web UI render disabled with a tooltip pointing at the Companion app.

## Non-Goals

These are explicitly out of scope for V1. They can be added later without structural refactor:

1. System-tray icon in the Tauri app (quick status, notifications center)
2. OS-native notifications from Tauri (RAID failure, backup done)
3. Auto-updater for the Tauri shell (Tauri updater plugin with signing chain)
4. Auto-start on OS login (XDG autostart entry)
5. Multi-window support in Tauri (settings in second window etc.)
6. Offline mode / local-database caching in Tauri
7. Tauri-IPC `invoke()` pattern for native Rust logic (architecture diagram shows this as future option — not needed today)
8. Token-sharing Web ↔ Tauri (e.g. via SSO cookie) — user logs into each app separately
9. Moving Category-A endpoints (single user-delete, reboot, hostname-change, DB-admin, ...) onto the local channel — they stay remote-capable; can be promoted later
10. Egress firewall for ci-sandbox / production runners (already a Known Gap in CI/CD rules; not addressed here)
11. Multiple parallel Tauri instances (e.g. on BaluNode + on a backup admin laptop via SSH-forwarded UDS) — explicitly not supported
12. Compile-time Web-UI build variant without destructive buttons — buttons are runtime-disabled, never tree-shaken
13. TUI (`baluhost_tui`) integration with local channel — TUI talks to the DB directly, no HTTP, not affected

## Threat Model

| Threat | Mitigated by |
|---|---|
| Stolen JWT used from remote network | Local-channel gate: TCP-bound backend never sets `request.state.channel = "local"`, regardless of headers. |
| Attacker on local LAN with stolen JWT | Same. LAN is no longer treated as "local" — only requests via UDS qualify. |
| Privilege escalation by a non-`baluhost` OS user on the BaluNode | UDS file mode `0660 baluhost:baluhost`. Foreign OS users get `EACCES`. |
| Tauri-Webview compromise (XSS / malicious page) | Webview hits a random-port proxy on `127.0.0.1:N` which only forwards to UDS. Same JWT requirement, same role checks. Worst case: attacker can do what the logged-in admin could anyway. |
| Compromised systemd config replacing the local backend | Out of scope — root on the BaluNode bypasses everything. Defense ends at root. |
| Setup-wizard remote bypass via `BALUHOST_SETUP_SECRET` | Documented trade-off (see Risks). Secret-holder can provision remotely. |

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ Web-Browser (remote or LAN)                                  │
│   → nginx :80 → baluhost-backend.service :8000               │
│                 [TCP bind, BALUHOST_CHANNEL unset → remote]  │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│ Tauri Companion App (runs on BaluNode as OS user baluhost)   │
│                                                              │
│   Webview loads ../dist/ (same React build as the Web UI)    │
│        ↓ fetch('/api/...') → http://127.0.0.1:<rand-port>    │
│                                                              │
│   Rust HTTP-Proxy on 127.0.0.1:<rand-port>                   │
│        ↓ forwards 1:1 over Unix socket                       │
│                                                              │
│   /run/baluhost/local.sock  (0660 baluhost:baluhost)         │
│        ↓ systemd socket activation                           │
│                                                              │
│   baluhost-backend-local.service                             │
│        Uvicorn --fd 3, BALUHOST_CHANNEL=local                │
│        Same app.main:app as TCP backend                      │
└──────────────────────────────────────────────────────────────┘

In both backend processes:
  ChannelMarkerMiddleware sets request.state.channel
  from settings.channel (env BALUHOST_CHANNEL).
  Destructive endpoints use Depends(require_local_admin)
  which checks channel == "local" AND admin role.
```

**Key invariants:**

- Channel identity is decided at backend-process boot via env var. No header, no client IP, no client cert. An attacker who somehow forges `X-Channel: local` against the TCP process cannot win — the TCP process unconditionally overwrites `request.state.channel = "remote"`.
- One React build serves both Web UI and Tauri Webview. Tauri shell is ~50 lines of Rust plus a `tauri.conf.json`.
- Existing `baluhost-backend.service` is structurally unchanged. The local-channel service is a sibling unit sharing the same Python app.

## Backend Components

### New: `backend/app/middleware/channel_marker.py`

```python
"""Marks each incoming request with its trust channel (local|remote).

The channel is fixed per backend process via the BALUHOST_CHANNEL env var,
so an attacker on the TCP-bound process cannot spoof local-channel status
no matter what headers they send.
"""
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

VALID_CHANNELS = {"local", "remote"}


class ChannelMarkerMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, channel: str, loopback_fallback: bool = False):
        super().__init__(app)
        if channel not in VALID_CHANNELS:
            raise ValueError(f"Invalid channel '{channel}' — must be one of {VALID_CHANNELS}")
        self.channel = channel
        self.loopback_fallback = loopback_fallback
        logger.info(
            "ChannelMarkerMiddleware initialized: channel=%s, loopback_fallback=%s",
            channel, loopback_fallback,
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        effective = self.channel
        if effective == "remote" and self.loopback_fallback:
            host = request.client.host if request.client else None
            if host == "127.0.0.1" or host == "::1" or (host or "").startswith("::ffff:127."):
                effective = "local"
        request.state.channel = effective
        return await call_next(request)
```

### Config (`backend/app/core/config.py`) — additions

```python
class Settings(BaseSettings):
    ...
    channel: Literal["local", "remote"] = Field(
        default="remote",
        validation_alias="BALUHOST_CHANNEL",
        description="Trust channel of this backend process. Set to 'local' "
                    "only in the UDS-bound systemd unit.",
    )
    local_loopback_fallback: bool = Field(
        default=False,
        validation_alias="BALUHOST_LOCAL_LOOPBACK_FALLBACK",
        description="Dev-only: treat 127.0.0.1 TCP as local when no UDS bound. "
                    "Never set in production — startup will fail.",
    )

    @model_validator(mode="after")
    def _validate_loopback_fallback_only_in_dev(self) -> "Settings":
        if self.local_loopback_fallback and not self.is_dev_mode:
            raise ValueError(
                "BALUHOST_LOCAL_LOOPBACK_FALLBACK is dev-only — never set this in production"
            )
        return self
```

### Registration in `main.py`

One new `add_middleware` call alongside the existing security/audit middlewares:

```python
from app.middleware.channel_marker import ChannelMarkerMiddleware
app.add_middleware(
    ChannelMarkerMiddleware,
    channel=settings.channel,
    loopback_fallback=settings.local_loopback_fallback,
)
```

### New dependency: `require_local_admin` (in `backend/app/api/deps.py`)

```python
async def require_local_admin(
    request: Request,
    user: UserPublic = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> UserPublic:
    """Combined gate: admin role AND local channel.

    Returns the authenticated admin user on success. On failure:
      - 401 if no JWT (handled by get_current_admin → get_current_user chain)
      - 403 "Admin required" if non-admin (get_current_admin)
      - 403 "local_channel_required" if admin but remote channel

    Failed local-channel checks are audit-logged with the resolved username.
    """
    channel = getattr(request.state, "channel", "remote")
    if channel != "local":
        audit_logger = get_audit_logger_db()
        audit_logger.log_security_event(
            action="local_channel_required_denied",
            user=user.username,
            details={"path": request.url.path, "role": user.role},
            success=False,
            db=db,
        )
        logger.warning(
            "local_channel_required: user=%s path=%s client=%s",
            user.username, request.url.path,
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "local_channel_required",
                "message": (
                    "This operation can only be performed from the BaluHost "
                    "Companion app running on the server itself."
                ),
            },
        )
    return user
```

Order of resolution: `get_current_user` → `get_current_admin` → channel check. Unauthenticated callers get 401 (auth fails first); non-admin admins get 403 "Admin required"; remote admins get 403 with structured `local_channel_required` payload. The audit log is only written on the third case, where we have a verified admin identity.

### Setup-wizard variant: `require_local_or_setup_secret`

The setup wizard runs before any admin exists, so it cannot use `require_local_admin`. Separate weaker dep:

```python
async def require_local_or_setup_secret(
    request: Request,
    payload_setup_secret: str | None = None,
) -> None:
    channel = getattr(request.state, "channel", "remote")
    if channel == "local":
        return
    if settings.setup_secret and payload_setup_secret == settings.setup_secret:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": "local_channel_required", "message": "..."},
    )
```

Today's `/api/setup/admin` has an inline `is_private_or_local_ip(client_ip)` block at `backend/app/api/routes/setup.py:99-111`. That block is removed and replaced by `require_local_or_setup_secret` as a route dependency. The `setup_secret` env-var bypass is preserved for Ansible/provisioning use cases — documented trade-off (see Risks).

### New endpoint: `GET /api/system/channel-status`

Returns the channel of the current connection. Used by the Web UI to disable destructive-action buttons. Auth: `get_current_user` (not admin) — channel info is not sensitive and a normal user might also benefit from UI affordances.

```python
class ChannelStatusResponse(BaseModel):
    channel: Literal["local", "remote"]

@router.get("/channel-status", response_model=ChannelStatusResponse)
async def get_channel_status(
    request: Request,
    _: UserPublic = Depends(deps.get_current_user),
) -> ChannelStatusResponse:
    return ChannelStatusResponse(channel=getattr(request.state, "channel", "remote"))
```

Lives in `backend/app/api/routes/system.py` (extends the existing system router).

### Endpoints gated by `require_local_admin`

All Category-S endpoints get the new dep. The change per endpoint is one line — replace `Depends(deps.get_current_admin)` with `Depends(deps.require_local_admin)`:

| Endpoint | File:Line | Verified existing handler |
|---|---|---|
| `POST /api/system/raid/delete-array` | `system_raid.py:225` | `delete_array` |
| `POST /api/system/raid/create-array` | `system_raid.py` | `create_array` |
| `POST /api/system/raid/format-disk` | `system_raid.py` | `format_disk` |
| `POST /api/plugins/{plugin_name}/install` (marketplace) | `plugins_marketplace.py:116` | `install_plugin` |
| `DELETE /api/plugins/{plugin_name}` (marketplace) | `plugins_marketplace.py:186` | `uninstall_plugin` |
| `DELETE /api/plugins/{name}` (core) | `plugins.py:503` | `uninstall_plugin` |
| `POST /api/vpn/sync-server-keys` | `vpn.py:419` | `sync_server_keys` |
| `POST /api/users/bulk-delete` | `users.py:194` | `bulk_delete_users` |
| `POST /api/setup/admin` | `setup.py:77` | `create_admin` (uses `require_local_or_setup_secret`) |
| `POST /api/setup/users` | `setup.py:150` | `create_user` (uses `require_local_or_setup_secret`) |
| `DELETE /api/setup/users/{user_id}` | `setup.py:185` | `delete_setup_user` (uses `require_local_or_setup_secret`) |
| `POST /api/setup/file-access` | `setup.py:207` | `configure_file_access` (uses `require_local_or_setup_secret`) |
| `POST /api/setup/complete` | `setup.py:242` | `complete_setup` (uses `require_local_or_setup_secret`) |

`POST /api/vpn/clients/{id}/regenerate-config` is **not** in the list — it regenerates one client config only, and the user can already regenerate their own. Server-side key rotation (`sync-server-keys`) is the destructive operation.

## Tauri App

### Layout

In-repo, next to the React code (standard Tauri 2 layout):

```
client/
├── src/                  ← existing React code, unchanged
├── src-tauri/            ← new
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   ├── build.rs
│   ├── icons/
│   └── src/
│       ├── main.rs       ← Tauri entry; starts proxy + opens webview
│       └── proxy.rs      ← HTTP → UDS reverse proxy
├── package.json          ← adds tauri:dev / tauri:build scripts
└── vite.config.ts        ← unchanged
```

### Rust dependencies (`Cargo.toml`)

```toml
[dependencies]
tauri = { version = "2", features = [] }
hyper = "1"
hyper-util = "0.1"
hyperlocal = "0.9"
tokio = { version = "1", features = ["full"] }
```

### Proxy behavior (`proxy.rs`)

- Binds `127.0.0.1:0` (kernel picks free port); returns the port to Rust caller
- Accepts HTTP/1.1 requests from the webview
- For each request: opens a new connection to `/run/baluhost/local.sock` via hyperlocal, forwards method/URI/headers/body
- Streams response back unchanged (essential for SSE endpoints like upload-progress)
- On UDS unreachable: returns `502 Bad Gateway` with a body explaining "is baluhost-backend-local.service running?"
- No header injection, no path rewriting — dumb forwarder

### Tauri config (`tauri.conf.json`)

```json
{
  "productName": "BaluHost Companion",
  "version": "0.1.0",
  "identifier": "com.baluhost.companion",
  "build": {
    "frontendDist": "../dist",
    "devUrl": "http://localhost:5173",
    "beforeDevCommand": "npm run dev -- --mode tauri",
    "beforeBuildCommand": "npm run build -- --mode tauri"
  },
  "app": {
    "windows": [{
      "title": "BaluHost Companion",
      "width": 1280,
      "height": 800,
      "minWidth": 1024,
      "minHeight": 600,
      "resizable": true
    }],
    "security": {
      "csp": "default-src 'self'; connect-src 'self' http://127.0.0.1:*; ..."
    }
  },
  "bundle": {
    "active": true,
    "targets": ["deb", "appimage"],
    "category": "Utility"
  }
}
```

### Webview → Proxy URL discovery

`client/src/lib/api.ts` is patched (small, additive):

```typescript
async function getApiBase(): Promise<string> {
  if (import.meta.env.VITE_TAURI === '1') {
    const { invoke } = await import('@tauri-apps/api/core');
    return await invoke<string>('get_api_base');
  }
  return import.meta.env.VITE_API_BASE || '/api';
}

export const api = axios.create({
  baseURL: await getApiBase(),
  // ... rest unchanged
});
```

In the Web build, `VITE_TAURI` is unset → the existing code path runs unchanged. No risk to the Web UI.

### Build/package

- GitHub Actions workflow `.github/workflows/tauri-build.yml` runs on `ubuntu-latest` (NOT self-hosted — Layer 2 of CI/CD security)
- Triggers: `push: main` (artifact only) + tag push (release-attached)
- Outputs: `.deb` + `.AppImage` as release assets
- Installation: standard `apt install ./baluhost-companion_*.deb` on the BaluNode. The .deb's postinst adds the interactive OS user to the `baluhost` group (so the user can read `/run/baluhost/local.sock`). User must log out/in once after install for group membership to take effect.

### No Tauri auto-updater in V1

User reinstalls the .deb when BaluHost gets an update. Simpler than maintaining a second signing chain. Promoted to a Non-Goal above.

## Frontend (Web UI + Tauri Webview share the same code)

### New: `client/src/api/system.ts` (or extends existing)

```typescript
export interface ChannelStatus {
  channel: 'local' | 'remote';
}

export async function getChannelStatus(): Promise<ChannelStatus> {
  const res = await api.get('/system/channel-status');
  return res.data;
}
```

### New hook: `client/src/hooks/useChannelStatus.ts`

```typescript
export function useChannelStatus() {
  const { data, isLoading } = useQuery({
    queryKey: ['channel-status'],
    queryFn: getChannelStatus,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  return {
    channel: data?.channel ?? 'remote',
    isLocal: data?.channel === 'local',
    isLoading,
  };
}
```

Default channel when unknown is `'remote'` — fail-safe (button stays disabled if backend hiccups).

Hook must NOT run before login — otherwise the channel-status query 401s into the cache. All Category-S buttons are inside admin-gated routes that already require auth, so this is a natural fit.

### New component: `client/src/components/LocalOnlyAction.tsx`

```tsx
interface Props {
  children: React.ReactElement<{ disabled?: boolean }>;
  hint?: string;
}

export function LocalOnlyAction({ children, hint }: Props) {
  const { isLocal, isLoading } = useChannelStatus();
  if (isLocal || isLoading) return children;

  return (
    <Tooltip content={hint ?? t('common.local_only_action_hint')}>
      <span className="inline-flex items-center gap-1">
        {React.cloneElement(children, { disabled: true })}
        <Lock className="w-3 h-3 text-muted-foreground" />
      </span>
    </Tooltip>
  );
}
```

### Pages touched

| File | Action |
|---|---|
| `client/src/pages/RaidManagement.tsx` | Wrap delete-array, create-array, format-disk buttons in `<LocalOnlyAction>` |
| Plugin admin page (locate during impl — likely `client/src/pages/PluginsPage.tsx`) | Wrap install / uninstall buttons |
| VPN admin (`client/src/pages/VPNAdminPage.tsx` or equivalent) | Wrap "Sync Server Keys" button |
| `client/src/pages/UsersPage.tsx` | Wrap bulk-delete button |
| Setup wizard pages | Show "Open BaluHost Companion app" banner when channel=remote and setup_required=true |

### i18n

Two new keys in `client/src/i18n/locales/{de,en}/common.json`:

```json
{
  "local_only_action_hint": "Nur über die BaluHost-Companion-App am Server selbst möglich.",
  "local_only_banner": "Diese Aktion erfordert physische Anwesenheit am BaluNode."
}
```

(English versions analogous.)

## Deployment / systemd

Three new files under `deploy/install/templates/`:

### `baluhost-backend-local.socket`

```ini
[Unit]
Description=BaluHost local-channel socket (Tauri Companion)

[Socket]
ListenStream=/run/baluhost/local.sock
SocketMode=0660
SocketUser=baluhost
SocketGroup=baluhost
RemoveOnStop=yes

[Install]
WantedBy=sockets.target
```

### `baluhost-backend-local.service`

```ini
[Unit]
Description=BaluHost backend (local channel, Unix socket)
Requires=baluhost-backend-local.socket
After=baluhost-backend-local.socket network.target postgresql.service

[Service]
Type=simple
User=baluhost
Group=baluhost
WorkingDirectory=/opt/baluhost/backend
EnvironmentFile=/etc/baluhost/.env.production
Environment="BALUHOST_CHANNEL=local"
ExecStart=/opt/baluhost/venv/bin/uvicorn app.main:app \
    --fd 3 \
    --workers 2 \
    --log-level info
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

### `/etc/tmpfiles.d/baluhost.conf`

```
d /run/baluhost 0755 baluhost baluhost - -
```

The existing `baluhost-backend.service` is unchanged. It runs without `BALUHOST_CHANNEL` set → defaults to `remote`.

## Migration plan

1. **Backend patch (channel marker + deps + endpoint `channel-status`), no endpoints gated yet.** Behavior 100% unchanged. Smoke-test: all admin endpoints work remote as before. One PR.
2. **Install `baluhost-backend-local.{service,socket}` + tmpfiles.d.** Verify with `sudo -u baluhost curl --unix-socket /run/baluhost/local.sock http://x/api/system/channel-status` → `{"channel":"local"}`. One PR (deploy/ changes only).
3. **Promote endpoints one at a time, lowest-blast-radius first:**
    1. Setup-wizard endpoints (affect only fresh installs)
    2. Plugin install/uninstall
    3. RAID delete-array / create-array / format-disk
    4. VPN sync-server-keys
    5. User bulk-delete
   After each PR, smoke-test Tauri (action goes through) + Web UI (button disabled with tooltip).
4. **Release Tauri .deb** as a GitHub Release asset; document install in `docs/`.

Rollback strategy: any endpoint promotion is a one-line revert in the route signature. UDS service can be `systemctl stop`ed; the TCP service keeps serving the Web UI unaffected.

## Testing

### Backend

**`tests/middleware/test_channel_marker.py`** (new):
- `test_channel_local_sets_request_state`
- `test_channel_remote_sets_request_state`
- `test_invalid_channel_raises_at_init`
- `test_loopback_fallback_marks_localhost_as_local_in_dev`
- `test_loopback_fallback_validator_blocks_prod`

**`tests/api/test_require_local_admin.py`** (new):
- `test_local_admin_passes`
- `test_remote_admin_blocked_with_audit_log`
- `test_unauth_returns_401`
- `test_non_admin_user_returns_403_admin_required`
- `test_audit_log_includes_username_path_and_role`

**Per-endpoint test** for each Category-S endpoint (extend existing `test_*_routes.py`):
- `test_<endpoint>_blocked_on_remote_channel` using a `remote_client` fixture
- Existing `test_*_requires_admin` keep working — see fixture change below

**`conftest.py` change:**
```python
@pytest.fixture
def client(monkeypatch):
    """Default test client runs with channel=local so existing 1465 admin tests
    keep passing without modification."""
    monkeypatch.setenv("BALUHOST_CHANNEL", "local")
    ...

@pytest.fixture
def remote_client(monkeypatch):
    monkeypatch.setenv("BALUHOST_CHANNEL", "remote")
    ...
```

Rationale: default test channel is `local` so 1465 existing tests need zero changes. New tests opt into `remote_client` when they specifically verify the local-channel gate.

### Frontend

**Vitest unit** for `useChannelStatus`:
- Returns `{isLocal: true}` when API says `channel: "local"`
- Returns `{isLocal: false}` when API says `channel: "remote"`
- Returns `{isLocal: false}` while loading (fail-safe)

**Vitest unit** for `<LocalOnlyAction>`:
- Renders child unchanged when `isLocal=true`
- Renders child with `disabled=true` + tooltip + Lock icon when `isLocal=false`
- Returns child unchanged while loading (no flicker)

**Playwright E2E** `client/tests/e2e/local-only.spec.ts`:
- Login as admin
- Mock `/api/system/channel-status` → `remote`: RAID delete button is `disabled`, has Lock icon
- Mock channel-status → `local` + invalidate react-query: button enabled
- Click on enabled button: no 403 modal

### Tauri (Rust)

**Unit tests in `src-tauri/src/proxy.rs`:**
- Forwards GET/POST/PUT/DELETE 1:1
- Headers preserved (Authorization, Content-Type, X-Device-ID)
- Streaming response not buffered
- UDS unreachable → 502 with explanatory body

**Manual integration test** (documented, not in CI):
1. Start `baluhost-backend-local.service` on BaluNode
2. `cargo tauri dev` opens the Companion app
3. Login → channel-status shows `"local"`
4. Delete-RAID button clickable; clicking actually deletes (in dev-storage sandbox)
5. In parallel, open `http://baluhost:8000` in browser, log in: same button disabled with tooltip

### CI

- Backend tests: continue on `ci-sandbox` (rootless Podman); default `BALUHOST_CHANNEL=local` in fixtures
- Frontend tests: `ubuntu-latest` (Vitest + Playwright)
- **New** `.github/workflows/tauri-build.yml` on `ubuntu-latest` (per CI/CD security Layer 2, not self-hosted). Trigger: `push: main` + tag. Output: `.deb` + `.AppImage`. Production deploys are unaffected.
- CODEOWNERS update: add `/client/src-tauri/` and `/.github/workflows/tauri-build.yml` to `@Xveyn`.

## Acceptance Criteria

A reviewer can verify the feature works by:

1. **Backend smoke**: `curl http://localhost:8000/api/system/channel-status` (admin token) → `{"channel":"remote"}`. `curl --unix-socket /run/baluhost/local.sock http://x/api/system/channel-status` (admin token) → `{"channel":"local"}`.
2. **Endpoint gate**: `curl -X POST http://localhost:8000/api/system/raid/delete-array …` (TCP, admin token) → 403 with `{"error": "local_channel_required", "message": "..."}`. Same call via `--unix-socket /run/baluhost/local.sock …` → 200 (or dev-mode mock response).
3. **Audit log**: after the failed call in (2), `audit_logs` has an entry `action=local_channel_required_denied` with `user=<admin-username>`, `details.path=/api/system/raid/delete-array`, `success=false`.
4. **Web UI**: logged in as admin → RAID Management → "Delete Array" button is disabled with Lock icon and tooltip in current locale.
5. **Tauri app**: `cargo tauri dev` opens, login, channel-status `"local"`, Delete button enabled, click goes through.
6. **Setup wizard**: fresh DB, `python start_dev.py --setup` → Tauri app shows wizard, admin creation succeeds. Web browser in parallel shows "Open BaluHost Companion app at the server."
7. **All backend tests green**: `python -m pytest backend` — new tests pass, existing 1465 unchanged.
8. **CI green**: `ci-check.yml` (backend-tests, frontend-build), `tauri-build.yml` produces .deb artifact.

## Risks / Known Trade-offs

1. **Doubled backend process** (~150 MB RAM). Accepted on a 16 GB box.
2. **`/run/baluhost/local.sock` group membership**: the interactive OS user on the BaluNode must be a member of the `baluhost` group, or the Tauri app can't connect. The .deb postinst adds the user; doc must call this out. Acceptable trust boundary — same as SSH access to the box.
3. **Setup-wizard `BALUHOST_SETUP_SECRET` bypass**: an Ansible operator with the env-var secret can provision remotely. Documented and intentional. Weakens the local-only promise by exactly the strength of that secret.
4. **Channel-status cache in React Query**: if someone restarts a backend with different channel at runtime (theoretical), frontend stays stale until reload. Practically irrelevant — channel is a process constant.
5. **Tauri Webview ↔ proxy isolation**: webview has unrestricted access to `127.0.0.1:<random-port>` (the proxy). If a malicious tool were listening on the same port, the webview would talk to it — but the kernel chooses a free port at boot, so race-binding requires winning a TOCTOU window inside the same OS user.
6. **Two Uvicorn processes share PostgreSQL state, not in-memory state**: e.g., the rate-limiter buckets diverge. Acceptable because the local-channel process only serves an already-authenticated admin — rate-limiting is not the primary defense there.
7. **CSP allowance for `127.0.0.1:*`**: Tauri webview needs `connect-src 'self' http://127.0.0.1:*` in its CSP. Web build keeps the tighter CSP without that allowance.

## Cross-reference with `.claude/rules/security-agent.md`

- **NEVER** list respected: no `shell=True`, no raw SQL, no secret logging, `_jail_path()` not bypassed, no default-secret use, no auth bypass.
- **ALWAYS** list satisfied: new endpoints have auth dependencies (`get_current_admin` chain), rate limits remain on each endpoint (existing `@user_limiter.limit(get_limit("admin_operations"))` is preserved), Pydantic schemas where applicable, audit logging via `get_audit_logger_db()`.
- New `require_local_admin` dependency is itself a composition of `get_current_admin` + a request-state check — no auth bypass anywhere.

## Files touched

### New

- `backend/app/middleware/channel_marker.py`
- `backend/tests/middleware/test_channel_marker.py`
- `backend/tests/api/test_require_local_admin.py`
- `client/src-tauri/Cargo.toml`
- `client/src-tauri/tauri.conf.json`
- `client/src-tauri/build.rs`
- `client/src-tauri/src/main.rs`
- `client/src-tauri/src/proxy.rs`
- `client/src-tauri/icons/` (placeholder set)
- `client/src/components/LocalOnlyAction.tsx`
- `client/src/hooks/useChannelStatus.ts`
- `client/tests/e2e/local-only.spec.ts`
- `client/src/components/__tests__/LocalOnlyAction.test.tsx`
- `client/src/hooks/__tests__/useChannelStatus.test.tsx`
- `deploy/install/templates/baluhost-backend-local.socket`
- `deploy/install/templates/baluhost-backend-local.service`
- `deploy/install/templates/tmpfiles-baluhost.conf`
- `.github/workflows/tauri-build.yml`

### Modified

- `backend/app/main.py` (add `ChannelMarkerMiddleware` registration)
- `backend/app/core/config.py` (add `channel`, `local_loopback_fallback` fields + validator)
- `backend/app/api/deps.py` (add `require_local_admin`, `require_local_or_setup_secret`)
- `backend/app/api/routes/system.py` (add `/channel-status` endpoint, response schema)
- `backend/app/schemas/system.py` (or wherever fits — add `ChannelStatusResponse`)
- `backend/app/api/routes/system_raid.py` (3 endpoints: delete-array, create-array, format-disk)
- `backend/app/api/routes/plugins.py` (uninstall_plugin)
- `backend/app/api/routes/plugins_marketplace.py` (install_plugin, uninstall_plugin)
- `backend/app/api/routes/vpn.py` (sync_server_keys)
- `backend/app/api/routes/users.py` (bulk_delete_users)
- `backend/app/api/routes/setup.py` (5 endpoints + remove inline `is_private_or_local_ip` block)
- `backend/tests/conftest.py` (default-channel fixture)
- `client/src/lib/api.ts` (`getApiBase()` with Tauri branch)
- `client/package.json` (`tauri:dev` / `tauri:build` scripts, `@tauri-apps/cli` devDep)
- `client/src/pages/RaidManagement.tsx` (wrap 3 buttons)
- Plugin admin page (locate during implementation)
- VPN admin page (locate during implementation)
- `client/src/pages/UsersPage.tsx` (wrap bulk-delete)
- Setup wizard pages (banner when channel=remote)
- `client/src/i18n/locales/de/common.json`, `client/src/i18n/locales/en/common.json`
- `.github/CODEOWNERS` (`/client/src-tauri/`, `/.github/workflows/tauri-build.yml`)
- `.claude/rules/ci-cd-security.md` (Layer 1 inventory list — add the two new paths)
- `start_dev.py` (set `BALUHOST_LOCAL_LOOPBACK_FALLBACK=true` for dev mode)
- `docs/` (install/usage of the Companion app)
