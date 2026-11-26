# API Layer

REST API endpoints for BaluHost. All routes are registered in `routes/__init__.py` and mounted under `/api` prefix in `main.py`.

## Structure

- `deps.py` — FastAPI dependency injection for auth (`get_current_user`, `get_current_admin`, `get_current_user_optional`, `verify_mobile_device_token`)
- `docs.py` — Custom Swagger UI + ReDoc with BaluHost dark theme styling
- `routes/` — One file per feature domain (~65 route modules)
  - `auth.py` — Auth endpoints. Recovery-code routes: `POST /recovery-codes` (step-up: TOTP if 2FA on, else current-password), `GET /recovery-codes/status`, `POST /recovery-reset` (LAN-only, no session issued; consumes a single-use code to reset password). Session handoff (#847): `POST /handoff` (LAN-only, proof is a device-pairing refresh token in the body, counts as its use; account PIN mandatory if set; deliberately no password/2FA) issues a 30 s one-time code; `POST /handoff/redeem` (public, no LAN gate) exchanges it for a normal session via `_issue_session_token()`.
  - `devices.py` — Device management (mobile + desktop). `DELETE /desktop/{device_id}` (owner or admin) revokes a desktop pairing: refresh tokens (`device_removed`), `SyncState` row, audit `desktop_device_removed` (#847).
  - `setup.py` — Setup wizard endpoints (status, admin creation, user creation, file access, completion)
  - `chunked_upload.py` — Chunked upload routes (`/files/upload/chunked/...`). **Must be registered before `files.router`** in `routes/__init__.py`: `files.py` ends in `DELETE /{resource_path:path}`, which matches every path under `/files` — registered after it, the abort route `DELETE /upload/chunked/{upload_id}` was never reached. Any worker serves any step (sessions are on disk); `complete` re-validates target and file name against the authenticated user, because the session file is not trusted.
  - `plugins_marketplace.py` — Marketplace listing + install routes. **Must be registered before `plugins.router`** in `routes/__init__.py`; otherwise `GET /plugins/marketplace` is swallowed as a plugin-name lookup.
- `versioned/` — API versioning support (reserved)

## Auth Dependencies (deps.py)

| Dependency | Returns | Use case |
|---|---|---|
| `get_current_user` | `UserPublic` | Any authenticated endpoint |
| `get_current_admin` | `UserPublic` | Admin-only endpoints |
| `get_current_user_optional` | `UserPublic \| None` | Optional auth (public shares) |
| `verify_mobile_device_token` | `UserPublic` | Mobile endpoints (validates X-Device-ID header + device expiry) |
| `require_power_<action>` | `UserPublic` | Delegated power actions (admin or the matching `can_<action>` permission, e.g. `require_power_launch_games` for the steam_gaming launch routes) |

Supports both JWT (`Bearer <token>`) and API key (`balu_...` prefix) authentication paths.

## Adding a New Route

1. Create `routes/my_feature.py` with a `router = APIRouter()`
2. Add auth dependency: `Depends(deps.get_current_user)` or `get_current_admin`
3. Add rate limiting: `@limiter.limit(get_limit("my_feature"))`
4. Use Pydantic schemas for request/response bodies
5. Register in `routes/__init__.py`: `api_router.include_router(my_feature.router, prefix="/my-feature", tags=["my-feature"])`
6. A handler that takes `Depends(get_db)` and awaits nothing is `def`, not `async def` — FastAPI runs it in the threadpool. `tests/test_route_async_convention.py` fails for a new `async def` of that shape.

## Conventions

- Route files define a `router = APIRouter()` — no prefix in the file, prefix set in `__init__.py`
- Business logic lives in `services/`, routes only handle HTTP concerns
- File operations must go through `_jail_path()` for path sandboxing
- Rate limits configured in `core/rate_limiter.py` via `get_limit()` lookup
- Power-intensive endpoints use `@requires_power(ServicePowerProperty.SURGE)` decorator
- Audit logging for security-relevant actions via `get_audit_logger_db()`
