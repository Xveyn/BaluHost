# Dynamic Dev-Mode Login Credentials Hint

**Date:** 2026-04-12
**Status:** Approved

## Problem

The Login page currently shows a hardcoded `admin / changeme` hint when the backend reports dev mode (`client/src/pages/Login.tsx:322-326`). This is wrong in two ways:

1. The actual seeded admin password in dev is `DevMode2024` (from `settings.admin_password`, default in `backend/app/core/config.py`). The hint lies.
2. If a developer overrides `ADMIN_PASSWORD` via environment variable, the hint still shows the stale literal.

The hint must reflect the credentials that will actually work, and must never appear in production.

## Solution

Extend the existing public `GET /api/system/mode` endpoint to also return the admin username and password when `settings.is_dev_mode` is true. The Login page reads those fields and renders them in the hint block. In production the fields are absent and the hint block is not rendered.

Only the admin credentials are exposed. Demo users (`alex`, `maria`) are out of scope — a parallel impersonation feature covers non-admin testing.

## Requirements

- Login page in dev mode shows the real admin username and password from `settings`.
- Production responses from `GET /api/system/mode` never contain credentials, even if the endpoint is called directly.
- No plaintext password is written to disk, logs, or the database.
- No additional round trips on the login page beyond the existing `/api/system/mode` call.

## Design

### Backend

**File:** `backend/app/api/routes/system.py`

`get_system_mode` is extended:

```python
@router.get("/mode")
@limiter.limit(get_limit("system_monitor"))
async def get_system_mode(request: Request, response: Response) -> dict:
    """Get system mode (dev/prod). Public endpoint for login page."""
    from app.core.config import settings
    payload: dict = {"dev_mode": settings.is_dev_mode}
    if settings.is_dev_mode:
        payload["dev_credentials"] = {
            "username": settings.admin_username,
            "password": settings.admin_password,
        }
    return payload
```

The `if settings.is_dev_mode` branch is the single security gate. No logging of the password. Existing `@limiter.limit(get_limit("system_monitor"))` stays.

Response shape:

- **Dev:** `{"dev_mode": true, "dev_credentials": {"username": "admin", "password": "DevMode2024"}}`
- **Prod:** `{"dev_mode": false}` — `dev_credentials` key is absent, not null.

### Frontend

**File:** `client/src/pages/Login.tsx`

- Replace state `isDevMode: boolean` with `devCredentials: { username: string; password: string } | null`.
- The effect at lines 41–46 reads both fields from the response and sets `devCredentials` to the object in dev, `null` otherwise (or on fetch error).
- The hint block at lines 322–326 is rendered only when `devCredentials !== null`, and displays `devCredentials.username` and `devCredentials.password` instead of the literals `admin` / `changeme`.
- The `t('defaultCredentials')` label stays unchanged.

**File:** `client/src/api/system.ts`

`getSystemMode()` return type is widened:

```ts
export async function getSystemMode(): Promise<{
  dev_mode: boolean;
  dev_credentials?: { username: string; password: string };
}>
```

`Login.tsx` currently uses a raw `fetch` to `/api/system/mode`, not `getSystemMode()`, but the client type is kept consistent for future use.

### Tests

**File:** `backend/tests/test_dev_mode.py`

Add `test_system_mode_dev_returns_credentials`:

- Call `GET /api/system/mode` with the dev-mode test client.
- Assert `dev_mode is True`.
- Assert `dev_credentials["username"] == settings.admin_username`.
- Assert `dev_credentials["password"] == settings.admin_password`.

**File:** `backend/tests/test_dev_mode.py`

Add `test_system_mode_prod_omits_credentials`:

- Use `monkeypatch` to set `settings.is_dev_mode = False` for the duration of the test (following the pattern in `backend/tests/test_fritzbox_wol.py:51-56`).
- Call `GET /api/system/mode`.
- Assert `dev_mode is False` and `"dev_credentials" not in response.json()`.

## Files to Modify

| File | Change |
|------|--------|
| `backend/app/api/routes/system.py` | Extend `get_system_mode` to include `dev_credentials` in dev. |
| `client/src/pages/Login.tsx` | Replace `isDevMode` state with `devCredentials`, render dynamic values. |
| `client/src/api/system.ts` | Widen `getSystemMode()` return type. |
| `backend/tests/test_dev_mode.py` | Add tests for both dev (credentials present) and prod (credentials absent) responses. |

## Out of Scope

- Persisting plaintext passwords anywhere (file, DB, cache).
- Exposing demo users `alex` / `maria` — covered by the parallel impersonation feature.
- Autofill button, copy-to-clipboard button, or password masking on the hint.
- Touching the `defaultCredentials` i18n key or the hint layout.
- Production hardening beyond the existing `is_dev_mode` gate (no additional auth, no new rate limit).
