# Wake-on-LAN Feature Completion — Design Spec

**Date**: 2026-03-22
**Status**: Draft
**Scope**: Three-phase incremental completion of WoL in BaluHost

---

## Context

BaluHost has a working local WoL implementation (magic packet via raw UDP socket, MAC stored in `sleep_config`, frontend controls in SleepModePanel/SleepConfigPanel). The primary gap is remote WoL — waking the NAS from outside the LAN, e.g. from the BaluApp over the internet.

**Hardware**: Fritz!Box 7682 (supports TR-064 SOAP API), NAS on Debian 13.
**Network**: BaluApp connects via Fritz!Box WireGuard VPN (not NAS-hosted WG).
**Primary use-case**: Wake the NAS from BaluApp when it's in True Suspend.

---

## Phase 1 — Harden Local WoL

Small, low-risk improvements to the existing implementation.

### 1.1 MAC Address Validation

**Files**: `backend/app/schemas/sleep.py`

Add a Pydantic `field_validator` to `WolRequest.mac_address` and `SleepConfigUpdate.wol_mac_address`:

- Accept `AA:BB:CC:DD:EE:FF` and `AA-BB-CC-DD-EE-FF` (case-insensitive)
- Normalize to uppercase with colons (`AA:BB:CC:DD:EE:FF`)
- Reject invalid formats with a clear error message
- `None` passes through unchanged (means "don't update this field")
- Empty string `""` is normalized to `None` (means "clear this field")

Extract the validator as a reusable `validate_mac_address()` function in a shared location (e.g. `backend/app/schemas/validators.py`) since Phase 2 and Phase 3 reuse the same logic.

### 1.2 Auto-Detect Own MAC

**Files**: `backend/app/services/power/sleep.py` (SleepBackend ABC), `sleep_backend_linux.py`, `sleep_backend_dev.py`, `backend/app/schemas/sleep.py`

New abstract method `get_own_mac() -> Optional[str]` on `SleepBackend`:

- **LinuxSleepBackend**: Determine the default-route interface by reading `/proc/net/route` (find the line where `Destination` is `00000000`; column 0 is the iface name). Then read `/sys/class/net/<iface>/address`. No subprocess needed — pure file reads.
- **DevSleepBackend**: Return `"DE:AD:BE:EF:00:01"` (fake).

Extend `SleepCapabilities` schema with `own_mac_address: Optional[str]`. The `get_capabilities()` method in `SleepManager` calls `get_own_mac()`.

**Frontend** (`client/src/components/power/SleepConfigPanel.tsx`): Show detected MAC as a clickable suggestion next to the MAC input field: "Erkannt: `AA:BB:CC:DD:EE:FF` — Übernehmen?". Only shown when `capabilities.own_mac_address` is set and the MAC input is empty or different.

### 1.3 Post-WoL Health-Check

**Decision: Not implemented in Phase 1.**

Rationale: Local WoL from the NAS to itself is a no-op (backend must be running to send the request). The real health-check need is in the BaluApp after sending WoL remotely — that's BaluApp-side logic. The existing `SleepModePanel` already polls `/api/system/sleep/status` every 5s, which covers the web-UI case.

---

## Phase 2 — Fritz!Box TR-064 WoL

Core feature: send WoL via Fritz!Box router, enabling remote wake when the NAS backend is unreachable.

### 2.1 Fritz!Box Config Model

**New file**: `backend/app/models/fritzbox.py`

Singleton DB model `FritzBoxConfig` (id=1, like `SleepConfig`). Uses SQLAlchemy 2.0 `Mapped[T] = mapped_column()` style (the project standard for new/migrated models — see `SleepConfig`, `mobile.py`, `rate_limit_config.py`):

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `id` | Integer PK | 1 | Singleton |
| `host` | String(255) | `"192.168.178.1"` | Fritz!Box address |
| `port` | Integer | `49000` | TR-064 port (49000=HTTP, 49443=HTTPS) |
| `username` | String(255) | `""` | TR-064 user (often empty on Fritz!Box) |
| `password_encrypted` | Text | `""` | Fernet-encrypted (same as VPN keys) |
| `nas_mac_address` | String(17) | `None` | MAC of NAS for WoL (validated) |
| `enabled` | Boolean | `False` | Integration active |
| `updated_at` | DateTime | `now()` | Last config change |

Alembic migration to create the table.

### 2.2 FritzBoxWoLService

**New file**: `backend/app/services/power/fritzbox_wol.py`

Placed under `services/power/` (next to the sleep/WoL code it integrates with), not under a new `services/fritzbox/` directory. This avoids confusion with the existing `services/vpn/fritzbox.py`.

```python
class FritzBoxWoLService:
    """Singleton service — instantiated once, loads config from DB per call."""

    async def send_wol(self, mac: Optional[str] = None) -> bool
    async def test_connection(self) -> tuple[bool, str]
    def _load_config(self) -> Optional[FritzBoxConfig]
```

**Lifecycle**: Module-level singleton (same pattern as `SleepManagerService`):
```python
_fritzbox_wol: Optional[FritzBoxWoLService] = None

def get_fritzbox_wol_service() -> FritzBoxWoLService:
    global _fritzbox_wol
    if _fritzbox_wol is None:
        _fritzbox_wol = FritzBoxWoLService()
    return _fritzbox_wol
```

**DB access**: Uses `SessionLocal()` context manager per call (same pattern as `SleepManagerService._load_config()`). No DB session parameter needed in public methods.

**TR-064 Implementation**:
- SOAP call to `urn:dslforum-org:service:Hosts:1` action `X_AVM-DE_WakeOnLANByMACAddress`
- URL: `http://<host>:<port>/upnp/control/hosts`
- Auth: HTTP Digest Authentication via `httpx.DigestAuth(username, password)` — empty username is valid (common Fritz!Box setup)
- HTTP client: `httpx.AsyncClient` (already a project dependency)
- Timeout: 10 seconds
- SOAP response parsing: Use `xml.etree.ElementTree` (safe against XXE by default in Python). Do NOT use `lxml` without `defusedxml`.
- Returns `True` on HTTP 200 with successful SOAP response

**Dev backend**: In dev mode (`settings.is_dev_mode`), `send_wol()` and `test_connection()` simulate success and log the call. No separate dev backend file needed — a simple `if settings.is_dev_mode` guard at the top of each method (the service is small enough).

**Error handling**:
- Connection refused → `(False, "Fritz!Box not reachable at <host>:<port>")`
- Auth failure (401) → `(False, "Authentication failed — check username/password")`
- SOAP fault → `(False, "<fault message>")`
- Timeout → `(False, "Connection timed out")`

### 2.3 Schemas

**New file**: `backend/app/schemas/fritzbox.py`

```python
class FritzBoxConfigResponse(BaseModel):
    host: str
    port: int
    username: str
    nas_mac_address: Optional[str]
    enabled: bool
    has_password: bool  # True if password is set, never expose actual password

class FritzBoxConfigUpdate(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = Field(None, ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None  # Plain text in, encrypted at storage
    nas_mac_address: Optional[str] = None  # Validated with shared MAC validator
    enabled: Optional[bool] = None

class FritzBoxTestResponse(BaseModel):
    success: bool
    message: str

class FritzBoxWolResponse(BaseModel):
    success: bool
    message: str
```

### 2.4 API Routes

**New file**: `backend/app/api/routes/fritzbox.py`

Router registered in `main.py` with `app.include_router(fritzbox_router, prefix="/api/fritzbox", tags=["fritzbox"])`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/fritzbox/config` | Admin | Get Fritz!Box config |
| `PUT` | `/api/fritzbox/config` | Admin | Update Fritz!Box config |
| `POST` | `/api/fritzbox/test` | Admin | Test Fritz!Box connection |
| `POST` | `/api/fritzbox/wol` | Admin | Send WoL via Fritz!Box |

All routes: rate-limited (`admin_operations`), Pydantic schemas for request/response, `Depends(get_current_admin)`.

**Audit logging**: `PUT /api/fritzbox/config` and `POST /api/fritzbox/wol` log via `get_audit_logger_db()` (security-relevant: credential change and power action).

The `/api/fritzbox/wol` route is the **primary** entry point for Fritz!Box WoL. It works independently of the sleep system — it's "wake my NAS" not "exit sleep mode".

**Error responses**:
- `400` — Fritz!Box integration not enabled, or no MAC configured
- `503` — Fritz!Box not reachable or auth failed (detail contains reason)

### 2.5 Extend Existing WoL Route (secondary entry point)

`POST /api/system/sleep/wol` — `WolRequest` gets optional field:

```python
method: Literal["local", "fritzbox"] = "local"
```

When `method="fritzbox"`, the sleep manager delegates to `FritzBoxWoLService` instead of `SleepBackend.send_wol_packet()`. This is a convenience integration — the primary Fritz!Box WoL path is `/api/fritzbox/wol`.

This is a backward-compatible schema change (new optional field with default).

### 2.6 Frontend

**`client/src/api/fritzbox.ts`** — New API client with typed functions for all four endpoints.

**`client/src/components/power/SleepConfigPanel.tsx`** — New "Fritz!Box Integration" section:
- Host, Port, Username, Password fields
- NAS MAC field (pre-filled from sleep config if set)
- "Test Connection" button (calls `POST /api/fritzbox/test`)
- Enable/disable toggle

**`client/src/components/power/SleepModePanel.tsx`** — WoL button behavior:
- If Fritz!Box is enabled: sends `method: "fritzbox"` by default
- Tooltip shows which method is active

### 2.7 BaluApp Protocol Documentation

**New file**: `docs/network/FRITZBOX_WOL_PROTOCOL.md`

Documents the TR-064 WoL protocol so the BaluApp can implement the same call directly (for when the NAS backend is unreachable):

- TR-064 SOAP endpoint and envelope format
- HTTP Digest Authentication flow
- Fritz!Box empty-username handling
- Example request (cURL)
- Example Kotlin implementation (BaluApp is native Kotlin)
- Fritz!Box credentials: the app should store them locally (encrypted) after user configures them once

---

## Phase 3 — Remote Server WoL (Future)

Extends the Remote Servers feature to support WoL as a fallback when SSH is unreachable.

### 3.1 ServerProfile Extension

**File**: `backend/app/models/server_profile.py`

Add `wol_mac_address` column. `ServerProfile` currently uses the legacy `Column()` style (no `Mapped` type hints). Two options:
- **Minimal**: Add the new column in the same legacy style for file consistency: `wol_mac_address = Column(String(17), nullable=True)`
- **Preferred**: Migrate the entire model to `Mapped[T] = mapped_column()` style (matching `SleepConfig`, `mobile.py`) in the same commit

Decision deferred to implementation time. Alembic migration either way.

Update `ServerProfileCreate` / `ServerProfileResponse` schemas accordingly. MAC validated with the shared validator from Phase 1.

### 3.2 Start Endpoint Fallback

**File**: `backend/app/api/routes/server_profiles.py`

`POST /api/server-profiles/{id}/start` logic change:
1. Try SSH `power_on_command` (existing behavior)
2. If SSH connection fails AND `wol_mac_address` is set → attempt WoL (local broadcast or Fritz!Box depending on config)
3. Response includes `method: "ssh" | "wol"` to indicate what happened

**Limitation**: WoL for remote servers only works if the target is on the same LAN as the NAS (local broadcast) or on the Fritz!Box's LAN (Fritz!Box WoL). Cross-network WoL is not supported.

### 3.3 Frontend

**File**: `client/src/pages/RemoteServersPage.tsx`

- Server profile form: optional MAC address field
- "Start Server" button: after failed SSH, show "Server nicht erreichbar. Per WoL aufwecken?" (only if MAC configured)

---

## Security Considerations

- Fritz!Box password stored Fernet-encrypted (same pattern as VPN keys, `REDACT_PATTERN` already covers `password`)
- Fritz!Box config routes are admin-only with rate limiting
- TR-064 credentials never exposed in API responses (`has_password: bool` instead)
- No `shell=True` in any new code (TR-064 is pure HTTP)
- MAC validation prevents injection into SOAP envelope (regex-enforced format)
- SOAP XML parsing uses `xml.etree.ElementTree` (safe against XXE by default)
- **Audit logging** for Fritz!Box config changes (`PUT /api/fritzbox/config`) and WoL sends (`POST /api/fritzbox/wol`) via `get_audit_logger_db()`
- **Accepted risk**: TR-064 uses plain HTTP (`http://<host>:49000`). Fritz!Box password travels unencrypted between NAS and router on the local LAN. This is the Fritz!Box TR-064 standard and is on a trusted LAN segment. Optionally configurable to port 49443 (HTTPS) if supported by the Fritz!Box firmware.

## Testing Strategy

### Phase 1
- Unit tests for MAC validator (valid formats, invalid formats, normalization, None passthrough, empty-string-to-None)
- Unit test for `DevSleepBackend.get_own_mac()`
- Unit test for `LinuxSleepBackend.get_own_mac()` with mocked `/proc/net/route` and `/sys/class/net/`
- Existing WoL tests remain green

### Phase 2
- Unit tests for `FritzBoxWoLService` with mocked httpx responses (success, auth failure, timeout, SOAP fault)
- Integration tests for all four Fritz!Box routes (auth guards, validation, error responses)
- Dev mode simulation test
- Manual test: actual Fritz!Box WoL (production)

### Phase 3
- Unit test for SSH-fail → WoL-fallback logic
- Integration test for start endpoint with mock SSH + mock WoL

## Migration Path

Each phase is an independent Alembic migration and can be deployed separately. No breaking changes to existing API contracts — all new fields are optional, all new routes are additive.

- Phase 1: No migration (schema-only changes)
- Phase 2: `alembic revision --autogenerate -m "Add fritzbox_config table"`
- Phase 3: `alembic revision --autogenerate -m "Add wol_mac_address to server_profiles"`
