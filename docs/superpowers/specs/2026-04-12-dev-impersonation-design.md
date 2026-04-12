# Dev-Mode Admin → User Impersonation

**Status:** Spec
**Date:** 2026-04-12
**Scope:** Dev-only feature — allow an admin who logged in via `start_dev.py` to switch into any user's session without re-entering credentials, and switch back.

## Problem

While developing and testing BaluHost features, an admin often needs to verify "what does user X actually see?" — file jail behavior, notifications routed to them, quotas, share visibility, etc. Today this requires logging out and logging back in with another account, losing React Query cache, open tabs, and scroll state. It also discourages testing from a user's perspective at all.

## Goals

- In dev mode only, let an admin switch into any user's view with one click from the topbar dropdown.
- The switched session must be an *actual* session for that user — backend permissions, `_jail_path`, quotas, shares, notifications all resolve as if the user had logged in directly.
- Provide an unmissable visual indicator and a one-click way back to the admin session.
- Leave zero footprint in production: the backend endpoint must not be registered, the UI entry point must not be visible.
- Every impersonation must be traceable in the audit log.

## Non-Goals

- Impersonation in production. Never.
- A "read-only" impersonation mode (would defeat the point — we want to test real user flows).
- Per-mutation audit entries tagging the originating admin. v1 logs only the start event; richer tracing can be added later if needed.
- Mobile/BaluApp impersonation. Web UI only.
- A deep-link URL like `/impersonate/42` — unnecessary complexity, the topbar dropdown is the entry point.

## Architecture

```
┌────────────────────────────────┐        ┌─────────────────────────────┐
│ Browser (admin logged in)      │        │ Backend (NAS_MODE=dev)      │
│                                │        │                             │
│ Topbar → "Switch to user →"    │        │ main.py:                    │
│   submenu (admin + dev only)   │        │  if settings.is_dev_mode:   │
│       │                        │        │    include auth_dev router  │
│       │ click user row         │        │                             │
│       ▼                        │        │ POST /api/auth/dev/         │
│ AuthContext.impersonate(id) ───┼────────┤      impersonate/{user_id}  │
│       │                        │        │  • get_current_admin        │
│       │ response               │        │  • settings.is_dev_mode     │
│       ▼                        │        │  • target exists + active   │
│ sessionStorage.origin_token ←──┼────────┤  • target.id != admin.id    │
│ localStorage.token = new       │        │  • create_access_token(     │
│ queryClient.clear()            │        │      impersonated_by=admin) │
│ navigate('/')                  │        │  • audit_log("dev_imp...")  │
│       │                        │        │                             │
│       ▼                        │        └─────────────────────────────┘
│ ImpersonationBanner visible    │
│   "Viewing as alice (user)     │
│    [Back to admin]"            │
└────────────────────────────────┘
```

The impersonation token is a fully valid JWT for the target user. The backend does not read or act on the `impersonated_by` claim — it exists solely so the audit log (and future tooling) can reconstruct who was behind a given session. Backend behavior is indistinguishable from a real login for the target user.

## Backend

### New route: `POST /api/auth/dev/impersonate/{user_id}`

New file: `backend/app/api/routes/auth_dev.py`.

```python
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api import deps
from app.core.config import settings
from app.core.rate_limiter import limiter, get_limit
from app.core.security import create_access_token
from app.schemas.auth import UserPublic
from app.services import user_service
from app.services.audit import get_audit_logger_db

router = APIRouter()

@router.post("/impersonate/{user_id}")
@limiter.limit(get_limit("auth_login"))
async def impersonate_user(
    user_id: int,
    request: Request,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(deps.get_db),
):
    if not settings.is_dev_mode:
        raise HTTPException(status_code=404)

    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot impersonate yourself")

    target = user_service.get_user_by_id(user_id, db=db)
    if not target or not target.is_active:
        raise HTTPException(status_code=404, detail="User not found")

    token = create_access_token(
        data={
            "sub": str(target.id),
            "username": target.username,
            "role": target.role,
            "impersonated_by": admin.id,
        },
        expires_delta=timedelta(minutes=30),
    )

    get_audit_logger_db(db).log(
        event_type="dev_impersonation_started",
        user_id=admin.id,
        details={"target_user_id": target.id, "target_username": target.username},
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": UserPublic.model_validate(target),
    }
```

### Registration gate (main.py)

```python
if settings.is_dev_mode:
    from app.api.routes import auth_dev
    app.include_router(
        auth_dev.router,
        prefix=f"{settings.api_prefix}/auth/dev",
        tags=["dev"],
    )
    logger.warning("DEV IMPERSONATION ENDPOINT ENABLED — do not run in production")
```

Both the registration gate and the runtime `if not settings.is_dev_mode` check in the route are deliberate belt-and-suspenders redundancy. If either gate is accidentally removed, the other still protects production.

### No changes required in

- `core/security.py` — `create_access_token` already forwards arbitrary claim data.
- `api/deps.py` — `get_current_user` ignores the `impersonated_by` claim, which is the intended behavior.
- `services/auth.py` — unchanged.

### Audit log

One event type: `dev_impersonation_started`. Payload:

```json
{
  "event_type": "dev_impersonation_started",
  "user_id": <admin_id>,
  "details": {
    "target_user_id": <user_id>,
    "target_username": "<name>"
  }
}
```

v1 does not log per-mutation impersonation context. The start event plus existing per-user audit entries are sufficient to reconstruct timelines manually. Richer tracing is explicitly out of scope.

### Rate limit

Reuse `get_limit("auth_login")` (the strictest existing category). Impersonation should never be called in volume; a strict limit prevents accidental token flooding loops from dev code.

## Frontend

### Dev-mode detection

`GET /api/system/mode` already exists and returns `{dev_mode: boolean}`. Wrap it in a React Query hook (`useSystemMode`) with `staleTime: Infinity`. Load it once after login. No new endpoint.

### AuthContext extension

File: `client/src/contexts/AuthContext.tsx` (or wherever `useAuth` is defined).

New fields on the context value:

```typescript
interface AuthContextValue {
  // existing fields: user, isAdmin, loading, login, logout, ...
  isImpersonating: boolean;
  impersonationOrigin: string | null;  // original admin username for banner
  impersonate: (userId: number) => Promise<void>;
  endImpersonation: () => void;
}
```

#### `impersonate(userId)`

1. `POST /api/auth/dev/impersonate/{userId}` with current (admin) token.
2. On success, response contains `{access_token, user}`.
3. `sessionStorage.setItem('impersonation_origin_token', currentToken)`
4. `sessionStorage.setItem('impersonation_origin_username', currentUser.username)`
5. `localStorage.setItem('token', response.access_token)` — uses the same key the existing API client reads.
6. `setUser(response.user)`, `setIsImpersonating(true)`, `setImpersonationOrigin(previousUsername)`.
7. `queryClient.clear()` — purge React Query cache so admin-scoped data does not leak into the user view.
8. `navigate('/')` — start from a neutral route.

#### `endImpersonation()`

1. Read `sessionStorage.getItem('impersonation_origin_token')`.
2. `localStorage.setItem('token', originToken)`.
3. `sessionStorage.removeItem('impersonation_origin_token')` + `impersonation_origin_username`.
4. Re-fetch `GET /api/auth/me` and `setUser(adminUser)`.
5. `setIsImpersonating(false)`, `setImpersonationOrigin(null)`.
6. `queryClient.clear()`, `navigate('/')`.

#### Bootstrap / reload handling

During initial `AuthContext` hydration: if `sessionStorage.impersonation_origin_token` exists AND the current `localStorage.token` is still a valid JWT (i.e., `/api/auth/me` succeeds), restore `isImpersonating=true` and `impersonationOrigin` from sessionStorage. This lets F5 keep the impersonation session alive.

#### Logout cleanup

Extend the existing `logout()` to unconditionally `sessionStorage.removeItem('impersonation_origin_token')` + `impersonation_origin_username`. Prevents stale sessionStorage from confusing the next login.

#### 401 during impersonation

The existing API client error handler is extended: if a 401 arrives while `isImpersonating === true`, call `endImpersonation()` first (which restores the admin token) before the generic 401 → login-screen flow runs. If the admin token is also expired, the normal logout path takes over. This handles the case where the 30-minute impersonation TTL expires mid-session gracefully.

### Topbar dropdown

The existing user dropdown (triggered by clicking the username in the topbar) gets a new submenu item **"Switch to user →"**, rendered **only when**:

- `systemMode?.dev_mode === true` AND
- `isAdmin === true` AND
- `!isImpersonating`

Submenu content: fetches `GET /api/users` via React Query on hover/open. Displays a scrollable list:

```
┌─────────────────────┐
│ admin2    [admin]   │
│ alice     [user]    │
│ bob       [user]    │
└─────────────────────┘
```

Clicking a row calls `impersonate(user.id)` and closes the dropdown.

### ImpersonationBanner

New component: `client/src/components/ImpersonationBanner.tsx`.

- Rendered in `Layout.tsx` above the topbar, only when `isImpersonating === true`.
- Full-width strip with amber background (`bg-amber-500 text-amber-950`).
- Content: `⚠ Viewing as {username} ({role}) — [Back to {adminUsername}]`
- The "Back to admin" button calls `endImpersonation()`.

### Files to create / modify

**Create:**
- `client/src/components/ImpersonationBanner.tsx`
- `client/src/api/authDev.ts` — wraps `POST /api/auth/dev/impersonate/{id}`
- `client/src/hooks/useSystemMode.ts` — React Query hook around existing `/api/system/mode`

**Modify:**
- `client/src/contexts/AuthContext.tsx` — new methods, state, bootstrap, logout cleanup
- `client/src/components/Layout.tsx` (or the topbar component) — add submenu + banner
- `client/src/lib/api.ts` — 401 handler: if impersonating, call `endImpersonation()` first
- `client/src/i18n/locales/de/common.json`
- `client/src/i18n/locales/en/common.json`

**i18n keys added:**
- `topbar.switchToUser`
- `impersonation.banner.viewingAs`
- `impersonation.banner.backToAdmin`
- `impersonation.role.admin`
- `impersonation.role.user`

## Security

| Risk | Mitigation |
|---|---|
| Endpoint leaks into production | Registration gate in `main.py` + runtime `is_dev_mode` check in route (redundant by design) |
| Brute force on impersonation | `@limiter.limit(get_limit("auth_login"))` — strictest existing limit |
| Audit gap | `dev_impersonation_started` event logged with admin_id + target details |
| Non-admin calls endpoint | `Depends(deps.get_current_admin)` |
| Token without expiry | 30-minute TTL hardcoded on issuance |
| Admin impersonates self | Explicit 400 |
| Inactive target user | 404 |
| Target user does not exist | 404 |
| `impersonated_by` claim misused backend-side | Backend explicitly does not read this claim; it exists only for audit reconstruction |
| Production build ships impersonation UI code | Intentionally kept. Gated at runtime by `systemMode.dev_mode`. Tree-shaking not required — code size is negligible and the API endpoint returning `dev_mode: false` makes the UI inert |
| sessionStorage wiped mid-session | Admin must re-login. Acceptable in dev |
| Token stacking (nested impersonation) | Submenu hidden when `isImpersonating` — must end one session before starting another |
| Logout during impersonation | Logout clears both `localStorage.token` and `sessionStorage.impersonation_origin_*` |

### Cross-reference with `.claude/rules/security-agent.md`

- **NEVER** list items respected: no `shell=True`, no raw SQL, no secret logging, token-type check untouched (this endpoint issues a normal access token), `_jail_path` not bypassed.
- **ALWAYS** list items satisfied: `get_current_admin` dependency ✓, Pydantic response (`UserPublic`), rate limiting applied, audit logging via `get_audit_logger_db()`, Pydantic schemas for responses.
- The endpoint is a new admin-only security-relevant action — matches all patterns in the "New API Endpoints" section of the security checklist.

## Tests

### Backend: `backend/tests/auth/test_dev_impersonation.py` (new)

1. `test_impersonate_as_admin_in_dev_mode_returns_token` — happy path, decode token, assert `sub`, `username`, `role`, `impersonated_by` claims.
2. `test_impersonate_as_regular_user_returns_403` — non-admin blocked by `get_current_admin`.
3. `test_impersonate_without_auth_returns_401`.
4. `test_impersonate_nonexistent_user_returns_404`.
5. `test_impersonate_inactive_user_returns_404`.
6. `test_impersonate_self_returns_400`.
7. `test_impersonate_in_prod_mode_router_not_registered` — build app with `is_dev_mode=False`, POST returns 404 because the router was never included.
8. `test_impersonate_writes_audit_log` — after success, one `dev_impersonation_started` entry exists with correct admin_id and target_user_id.
9. `test_impersonation_token_is_valid_for_user_endpoints` — use the returned token to call `/api/auth/me` and `/api/files`, assert it behaves as the target user.
10. `test_impersonation_endpoint_is_rate_limited` — verify strict limit is applied.

### Frontend

**Playwright E2E**: `client/tests/e2e/dev-impersonation.spec.ts` (new)

Happy path with mocked routes (pattern existing in `login.spec.ts`):
- Mock `/api/system/mode` → `{dev_mode: true}`
- Mock `/api/auth/login` → admin login
- Mock `/api/users` → two users
- Mock `/api/auth/dev/impersonate/2` → user token
- Flow: login → open dropdown → hover "Switch to user →" → click user → banner appears → click "Back to admin" → banner gone.

**Vitest unit test** for `AuthContext.impersonate()`:
- Mock the API call
- Assert sessionStorage state before/after
- Assert `queryClient.clear()` is called
- Assert `navigate('/')` is called

### Manual test plan

Documented in this spec, not automated (UI-level verification):

1. `python start_dev.py`
2. Login as `admin / DevMode2024`
3. Click topbar username → dropdown → "Switch to user →" → click `user`
4. Banner appears; URL is `/`
5. Open File Manager — user's own files only (not admin's multi-mountpoint view)
6. Open notifications — user-scoped list
7. Attempt to open an admin-only route (e.g., `/admin/database`) — expect 403 or redirect
8. Click "Back to admin" — instant return to full admin view
9. Press F5 while impersonating — banner persists
10. Open a fresh tab on `localhost:5173` — clean admin view (sessionStorage not shared)
11. Restart with `NAS_MODE=prod` — submenu item not visible, POST to the endpoint returns 404

### Pre-PR

Per project convention (`feedback_run_tests_before_pr.md`), run `python -m pytest backend` locally before opening the PR.

## Out of Scope

- Production impersonation
- Per-mutation impersonation audit entries
- Mobile app / BaluDesk impersonation
- Read-only impersonation mode
- Deep-link impersonation URLs
- Impersonation history / timeline UI in the admin dashboard
