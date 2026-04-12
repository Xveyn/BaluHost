# Dev-Mode Admin → User Impersonation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an admin logged in via `start_dev.py` switch into any user's session from the topbar, with an unmissable banner and one-click return — zero footprint in production.

**Architecture:** New dev-only backend endpoint `POST /api/auth/dev/impersonate/{user_id}` issues a full JWT for the target user with an `impersonated_by` claim and 30-minute TTL. Frontend stashes the admin token in `sessionStorage`, swaps `localStorage.token`, clears the React Query cache, and renders a banner. "Back to admin" restores the original token.

**Tech Stack:** FastAPI, SQLAlchemy, pyjwt, pytest (backend); React 18, TypeScript, Tailwind, react-i18next, Vitest, Playwright (frontend).

**Spec:** `docs/superpowers/specs/2026-04-12-dev-impersonation-design.md`

---

## File Structure

**Backend — create:**
- `backend/app/api/routes/auth_dev.py` — new dev-only impersonation route (~60 lines)
- `backend/tests/auth/test_dev_impersonation.py` — endpoint tests

**Backend — modify:**
- `backend/app/core/security.py` — add optional `impersonated_by` kwarg to `create_access_token`
- `backend/app/api/routes/__init__.py` — conditionally register the dev router
- `backend/app/main.py` — startup warning when dev impersonation is enabled

**Frontend — create:**
- `client/src/api/authDev.ts` — API wrapper for the impersonation endpoint
- `client/src/hooks/useSystemMode.ts` — cached `/api/system/mode` hook
- `client/src/components/UserMenu.tsx` — new dropdown wrapping the topbar username display, with the "Switch to user →" submenu
- `client/src/components/ImpersonationBanner.tsx` — banner rendered above the header
- `client/src/__tests__/contexts/AuthContext.impersonation.test.tsx` — unit test for the new context methods
- `client/tests/e2e/dev-impersonation.spec.ts` — Playwright happy-path

**Frontend — modify:**
- `client/src/contexts/AuthContext.tsx` — add `isImpersonating`, `impersonationOrigin`, `impersonate()`, `endImpersonation()`, origin-aware bootstrap, origin-aware `auth:expired` handler, logout cleanup
- `client/src/components/Layout.tsx` — wrap the username display in `<UserMenu />`, render `<ImpersonationBanner />` above the header
- `client/src/i18n/locales/de/common.json` — new strings
- `client/src/i18n/locales/en/common.json` — new strings

---

## Task 1: Backend — extend `create_access_token` with `impersonated_by` kwarg

**Files:**
- Modify: `backend/app/core/security.py:20-61`
- Test: `backend/tests/auth/test_dev_impersonation.py` (new file, this task adds only the first test)

**Why:** `create_access_token` currently builds a fixed payload from user data. We need to tack on an optional `impersonated_by` claim without disturbing existing callers.

- [ ] **Step 1: Create the test directory if missing and write the first failing test**

File: `backend/tests/auth/test_dev_impersonation.py`

```python
"""Tests for dev-only admin → user impersonation endpoint."""
from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import User


def test_create_access_token_includes_impersonated_by_when_set():
    """`impersonated_by` claim is included when the kwarg is passed."""
    fake_user = {"id": 42, "username": "alice", "role": "user"}
    token = create_access_token(fake_user, impersonated_by=7)
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])

    assert payload["sub"] == "42"
    assert payload["username"] == "alice"
    assert payload["role"] == "user"
    assert payload["type"] == "access"
    assert payload["impersonated_by"] == 7


def test_create_access_token_omits_impersonated_by_by_default():
    """Existing callers get the same payload they had before."""
    fake_user = {"id": 1, "username": "admin", "role": "admin"}
    token = create_access_token(fake_user)
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])

    assert "impersonated_by" not in payload
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/auth/test_dev_impersonation.py -v`
Expected: FAIL — `create_access_token() got an unexpected keyword argument 'impersonated_by'`

- [ ] **Step 3: Extend `create_access_token` with the optional kwarg**

Replace the function body in `backend/app/core/security.py` (lines 20–61) with:

```python
def create_access_token(
    user: User | dict,
    expires_delta: timedelta | None = None,
    impersonated_by: int | None = None,
) -> str:
    """
    Create a JWT access token with short TTL (15 minutes default).

    Args:
        user: User object or dict with user data (must have 'id' field)
        expires_delta: Optional custom expiration time
        impersonated_by: Optional admin user id (dev-only impersonation audit marker)

    Returns:
        Encoded JWT token string
    """
    if isinstance(user, dict):
        user_id = user.get("id") or user.get("sub")
        username = user.get("username")
        role = user.get("role")
    else:
        user_id = user.id
        username = user.username
        role = user.role

    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "type": "access",
        "exp": expire,
        "iat": now,
    }
    if impersonated_by is not None:
        payload["impersonated_by"] = impersonated_by

    encoded_jwt = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm="HS256"
    )

    return encoded_jwt
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest backend/tests/auth/test_dev_impersonation.py -v`
Expected: PASS — both tests green.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/security.py backend/tests/auth/test_dev_impersonation.py
git commit -m "feat(auth): add optional impersonated_by claim to access tokens"
```

---

## Task 2: Backend — write failing tests for the `auth_dev` endpoint

**Files:**
- Test: `backend/tests/auth/test_dev_impersonation.py` (extend)

**Why:** Define the endpoint contract through tests before writing the route. TDD.

- [ ] **Step 1: Append endpoint tests to the existing test file**

Append to `backend/tests/auth/test_dev_impersonation.py`:

```python
# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

from app.services import users as user_service
from app.schemas.user import UserCreate

IMPERSONATE_URL = "/api/auth/dev/impersonate"


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        f"{settings.api_prefix}/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
def admin_token(client: TestClient) -> str:
    # Seeded admin in dev-mode test fixtures
    return _login(client, "admin", "DevMode2024")


@pytest.fixture
def regular_user(db_session: Session) -> User:
    payload = UserCreate(username="alice_imp", password="Passw0rd!", role="user")
    return user_service.create_user(payload, db=db_session)


@pytest.fixture
def regular_token(client: TestClient, regular_user: User) -> str:
    return _login(client, regular_user.username, "Passw0rd!")


def test_impersonate_as_admin_in_dev_mode_returns_token(
    client: TestClient, admin_token: str, regular_user: User
):
    response = client.post(
        f"{IMPERSONATE_URL}/{regular_user.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == regular_user.username

    payload = jwt.decode(body["access_token"], settings.SECRET_KEY, algorithms=["HS256"])
    assert payload["sub"] == str(regular_user.id)
    assert payload["username"] == regular_user.username
    assert payload["role"] == "user"
    assert "impersonated_by" in payload


def test_impersonate_as_regular_user_returns_403(
    client: TestClient, regular_token: str, regular_user: User
):
    response = client.post(
        f"{IMPERSONATE_URL}/{regular_user.id}",
        headers={"Authorization": f"Bearer {regular_token}"},
    )
    assert response.status_code == 403


def test_impersonate_without_auth_returns_401(client: TestClient, regular_user: User):
    response = client.post(f"{IMPERSONATE_URL}/{regular_user.id}")
    assert response.status_code == 401


def test_impersonate_nonexistent_user_returns_404(client: TestClient, admin_token: str):
    response = client.post(
        f"{IMPERSONATE_URL}/999999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


def test_impersonate_inactive_user_returns_404(
    client: TestClient, admin_token: str, db_session: Session, regular_user: User
):
    regular_user.is_active = False
    db_session.commit()
    response = client.post(
        f"{IMPERSONATE_URL}/{regular_user.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 404


def test_impersonate_self_returns_400(
    client: TestClient, admin_token: str, db_session: Session
):
    admin = user_service.get_user_by_username("admin", db=db_session)
    response = client.post(
        f"{IMPERSONATE_URL}/{admin.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 400


def test_impersonation_token_works_for_user_endpoints(
    client: TestClient, admin_token: str, regular_user: User
):
    imp_response = client.post(
        f"{IMPERSONATE_URL}/{regular_user.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    imp_token = imp_response.json()["access_token"]

    me = client.get(
        f"{settings.api_prefix}/auth/me",
        headers={"Authorization": f"Bearer {imp_token}"},
    )
    assert me.status_code == 200
    assert me.json()["user"]["username"] == regular_user.username


def test_impersonate_writes_audit_log(
    client: TestClient, admin_token: str, regular_user: User, db_session: Session
):
    from app.models.audit_log import AuditLog

    client.post(
        f"{IMPERSONATE_URL}/{regular_user.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "dev_impersonation_started")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert entry is not None
    assert entry.user == "admin"
    assert str(regular_user.id) in (entry.details or "")
```

- [ ] **Step 2: Run the new tests — expect failures**

Run: `python -m pytest backend/tests/auth/test_dev_impersonation.py -v`
Expected: First two tests still PASS. New tests FAIL with 404 (route does not exist).

- [ ] **Step 3: Commit (red state)**

```bash
git add backend/tests/auth/test_dev_impersonation.py
git commit -m "test(auth): add failing tests for dev impersonation endpoint"
```

**Note on fixtures:** `client`, `db_session`, and `admin`/`admin_token` conventions vary. If `db_session` is not a fixture name in this repo, inspect `backend/tests/conftest.py` and replace with the local equivalent (commonly `db` or `db_session`). The seeded admin password `DevMode2024` comes from `.claude/rules/development.md`. If the test harness uses a different seed, update `_login(...)` and `test_impersonate_self_returns_400`.

---

## Task 3: Backend — implement the `auth_dev` route

**Files:**
- Create: `backend/app/api/routes/auth_dev.py`

- [ ] **Step 1: Create the route file**

File: `backend/app/api/routes/auth_dev.py`

```python
"""Dev-only impersonation endpoint.

Allows an admin to obtain a full JWT for any user without re-authenticating.
Only registered when `settings.is_dev_mode` is True (see routes/__init__.py).
Belt-and-suspenders: the route itself also rejects non-dev mode at runtime.
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api import deps
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limiter import limiter, get_limit
from app.core.security import create_access_token
from app.schemas.user import UserPublic
from app.services import users as user_service
from app.services.audit.logger_db import get_audit_logger_db

router = APIRouter()


@router.post("/impersonate/{user_id}")
@limiter.limit(get_limit("auth_login"))
async def impersonate_user(
    user_id: int,
    request: Request,
    admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Issue an access token for the target user. Admin + dev-mode only."""
    # Runtime gate (in addition to the registration gate in routes/__init__.py).
    if not settings.is_dev_mode:
        raise HTTPException(status_code=404)

    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot impersonate yourself")

    target = user_service.get_user(user_id, db=db)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="User not found")

    token = create_access_token(
        target,
        expires_delta=timedelta(minutes=30),
        impersonated_by=admin.id,
    )

    audit_logger = get_audit_logger_db()
    audit_logger.log_security_event(
        action="dev_impersonation_started",
        user=admin.username,
        resource=f"user:{target.id}",
        details={
            "admin_id": admin.id,
            "target_user_id": target.id,
            "target_username": target.username,
        },
        success=True,
        db=db,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": UserPublic.model_validate(target, from_attributes=True),
    }
```

- [ ] **Step 2: Run tests — still red, because the router is not registered yet**

Run: `python -m pytest backend/tests/auth/test_dev_impersonation.py -v`
Expected: endpoint tests still FAIL with 404 — file exists but is not mounted yet. (This is fine; Task 4 mounts it.)

---

## Task 4: Backend — conditionally register the dev router + startup warning

**Files:**
- Modify: `backend/app/api/routes/__init__.py` (add conditional include at end)
- Modify: `backend/app/main.py` (startup warning)

- [ ] **Step 1: Register the router conditionally in routes/__init__.py**

Append **before** `__all__ = ["api_router"]` at the bottom of `backend/app/api/routes/__init__.py`:

```python
# Dev-only: admin → user impersonation.
# Registered only when NAS_MODE=dev. Runtime check in the route is redundant-by-design.
from app.core.config import settings as _settings
if _settings.is_dev_mode:
    from app.api.routes import auth_dev
    api_router.include_router(
        auth_dev.router, prefix="/auth/dev", tags=["auth-dev"]
    )
```

- [ ] **Step 2: Add startup warning in main.py**

Open `backend/app/main.py`, find the startup block where the logger is initialised (search for `logger = logging.getLogger` or `app = FastAPI`). Immediately after logger setup (or inside the lifespan startup section if that's the convention), add:

```python
# Dev-only impersonation warning
from app.core.config import settings as _bh_settings
if _bh_settings.is_dev_mode:
    logger.warning(
        "DEV IMPERSONATION ENDPOINT ENABLED at "
        "%s/auth/dev/impersonate/{user_id} — do not run this in production",
        _bh_settings.api_prefix,
    )
```

If `main.py` already uses the settings singleton under a different alias, reuse it instead of re-importing.

- [ ] **Step 3: Run the full impersonation test file — expect GREEN**

Run: `python -m pytest backend/tests/auth/test_dev_impersonation.py -v`
Expected: ALL tests PASS (including self, inactive, 401, 403, 404, audit).

- [ ] **Step 4: Run the broader auth test suite for regression**

Run: `python -m pytest backend/tests/auth -v`
Expected: No new failures compared to baseline.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/auth_dev.py backend/app/api/routes/__init__.py backend/app/main.py
git commit -m "feat(auth): dev-only impersonation endpoint with registration gate"
```

---

## Task 5: Frontend — `useSystemMode` hook

**Files:**
- Create: `client/src/hooks/useSystemMode.ts`

**Why:** The topbar submenu and banner need to know if we're in dev mode. `/api/system/mode` is public. We cache it for the session.

- [ ] **Step 1: Create the hook**

File: `client/src/hooks/useSystemMode.ts`

```typescript
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../lib/api';

export interface SystemMode {
  dev_mode: boolean;
}

export function useSystemMode() {
  return useQuery<SystemMode>({
    queryKey: ['system-mode'],
    queryFn: async () => {
      const { data } = await apiClient.get<SystemMode>('/api/system/mode');
      return data;
    },
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
  });
}
```

**Note:** This project already uses `@tanstack/react-query` — verify by checking `client/package.json`. If React Query is not installed, fall back to a plain `useEffect`-backed hook storing the result in a module-level variable.

- [ ] **Step 2: Commit**

```bash
git add client/src/hooks/useSystemMode.ts
git commit -m "feat(frontend): add useSystemMode hook"
```

---

## Task 6: Frontend — `authDev` API client

**Files:**
- Create: `client/src/api/authDev.ts`

- [ ] **Step 1: Write the API wrapper**

File: `client/src/api/authDev.ts`

```typescript
import { apiClient } from '../lib/api';
import type { User } from '../types/auth';

export interface ImpersonationResponse {
  access_token: string;
  token_type: 'bearer';
  user: User;
}

export async function impersonateUser(userId: number): Promise<ImpersonationResponse> {
  const { data } = await apiClient.post<ImpersonationResponse>(
    `/api/auth/dev/impersonate/${userId}`,
  );
  return data;
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/api/authDev.ts
git commit -m "feat(frontend): add authDev API wrapper"
```

---

## Task 7: Frontend — extend `AuthContext` (failing tests first)

**Files:**
- Create: `client/src/__tests__/contexts/AuthContext.impersonation.test.tsx`
- Modify: `client/src/contexts/AuthContext.tsx`

**Why:** TDD the context changes. Keep mutations isolated so future readers can trace the flow.

- [ ] **Step 1: Write failing unit tests**

File: `client/src/__tests__/contexts/AuthContext.impersonation.test.tsx`

```tsx
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, waitFor, act } from '@testing-library/react';
import { AuthProvider, useAuth } from '../../contexts/AuthContext';

// Mock the dev API
vi.mock('../../api/authDev', () => ({
  impersonateUser: vi.fn(),
}));

// Mock buildApiUrl used by auth/me fetch
vi.mock('../../lib/api', async (orig) => ({
  ...(await orig<typeof import('../../lib/api')>()),
  buildApiUrl: (p: string) => p,
}));

import { impersonateUser } from '../../api/authDev';

const adminUser = { id: 1, username: 'admin', role: 'admin' as const };
const targetUser = { id: 2, username: 'alice', role: 'user' as const };

function TestConsumer({ captureRef }: { captureRef: (ctx: ReturnType<typeof useAuth>) => void }) {
  const ctx = useAuth();
  captureRef(ctx);
  return null;
}

describe('AuthContext impersonation', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.clearAllMocks();
    // Seed admin session
    localStorage.setItem('token', 'admin-token');
    global.fetch = vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ user: adminUser }), { status: 200 }),
      ),
    ) as any;
  });

  it('stores origin token and swaps to impersonation token', async () => {
    (impersonateUser as any).mockResolvedValue({
      access_token: 'imp-token',
      token_type: 'bearer',
      user: targetUser,
    });

    let ctx!: ReturnType<typeof useAuth>;
    render(
      <AuthProvider>
        <TestConsumer captureRef={(c) => (ctx = c)} />
      </AuthProvider>,
    );
    await waitFor(() => expect(ctx.user?.username).toBe('admin'));

    await act(async () => {
      await ctx.impersonate(targetUser.id);
    });

    expect(sessionStorage.getItem('impersonation_origin_token')).toBe('admin-token');
    expect(sessionStorage.getItem('impersonation_origin_username')).toBe('admin');
    expect(localStorage.getItem('token')).toBe('imp-token');
    expect(ctx.isImpersonating).toBe(true);
    expect(ctx.impersonationOrigin).toBe('admin');
    expect(ctx.user?.username).toBe('alice');
  });

  it('endImpersonation restores the admin token', async () => {
    (impersonateUser as any).mockResolvedValue({
      access_token: 'imp-token',
      token_type: 'bearer',
      user: targetUser,
    });

    let ctx!: ReturnType<typeof useAuth>;
    render(
      <AuthProvider>
        <TestConsumer captureRef={(c) => (ctx = c)} />
      </AuthProvider>,
    );
    await waitFor(() => expect(ctx.user?.username).toBe('admin'));

    await act(async () => {
      await ctx.impersonate(targetUser.id);
    });
    expect(ctx.isImpersonating).toBe(true);

    // /api/auth/me will be re-fetched with the admin token
    (global.fetch as any).mockImplementationOnce(() =>
      Promise.resolve(new Response(JSON.stringify({ user: adminUser }), { status: 200 })),
    );

    await act(async () => {
      ctx.endImpersonation();
    });

    await waitFor(() => expect(ctx.isImpersonating).toBe(false));
    expect(localStorage.getItem('token')).toBe('admin-token');
    expect(sessionStorage.getItem('impersonation_origin_token')).toBeNull();
    expect(ctx.user?.username).toBe('admin');
  });
});
```

- [ ] **Step 2: Run tests — expect failure**

Run: `cd client && npx vitest run src/__tests__/contexts/AuthContext.impersonation.test.tsx`
Expected: FAIL — `ctx.impersonate is not a function`.

- [ ] **Step 3: Update `AuthContext.tsx` with the new API**

Replace the contents of `client/src/contexts/AuthContext.tsx` with:

```tsx
import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { buildApiUrl } from '../lib/api';
import type { User } from '../types/auth';
import { impersonateUser as apiImpersonateUser } from '../api/authDev';

interface AuthContextValue {
  user: User | null;
  token: string | null;
  login: (user: User, token: string) => void;
  logout: () => void;
  isAdmin: boolean;
  loading: boolean;
  isImpersonating: boolean;
  impersonationOrigin: string | null;
  impersonate: (userId: number) => Promise<void>;
  endImpersonation: () => void;
}

const ORIGIN_TOKEN_KEY = 'impersonation_origin_token';
const ORIGIN_USERNAME_KEY = 'impersonation_origin_username';

const AuthContext = createContext<AuthContextValue | null>(null);

async function fetchMe(token: string): Promise<User | null> {
  try {
    const res = await fetch(buildApiUrl('/api/auth/me'), {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data.user || data;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [impersonationOrigin, setImpersonationOrigin] = useState<string | null>(
    sessionStorage.getItem(ORIGIN_USERNAME_KEY),
  );

  const isImpersonating = impersonationOrigin !== null;

  useEffect(() => {
    const storedToken = localStorage.getItem('token');
    if (!storedToken) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    setToken(storedToken);
    fetchMe(storedToken).then((userData) => {
      if (cancelled) return;
      if (userData?.username) {
        setUser(userData);
      } else {
        localStorage.removeItem('token');
        sessionStorage.removeItem(ORIGIN_TOKEN_KEY);
        sessionStorage.removeItem(ORIGIN_USERNAME_KEY);
        setToken(null);
        setUser(null);
        setImpersonationOrigin(null);
      }
      setLoading(false);
    });

    return () => { cancelled = true; };
  }, []);

  const login = (userData: User, newToken: string) => {
    localStorage.setItem('token', newToken);
    setToken(newToken);
    setUser(userData);
  };

  const logout = useCallback(() => {
    localStorage.removeItem('token');
    sessionStorage.removeItem(ORIGIN_TOKEN_KEY);
    sessionStorage.removeItem(ORIGIN_USERNAME_KEY);
    setToken(null);
    setUser(null);
    setImpersonationOrigin(null);
  }, []);

  const impersonate = useCallback(async (userId: number) => {
    const currentToken = localStorage.getItem('token');
    const currentUsername = user?.username;
    if (!currentToken || !currentUsername) {
      throw new Error('No active session to impersonate from');
    }
    const resp = await apiImpersonateUser(userId);
    sessionStorage.setItem(ORIGIN_TOKEN_KEY, currentToken);
    sessionStorage.setItem(ORIGIN_USERNAME_KEY, currentUsername);
    localStorage.setItem('token', resp.access_token);
    setToken(resp.access_token);
    setUser(resp.user);
    setImpersonationOrigin(currentUsername);
  }, [user?.username]);

  const endImpersonation = useCallback(() => {
    const originToken = sessionStorage.getItem(ORIGIN_TOKEN_KEY);
    if (!originToken) {
      logout();
      return;
    }
    localStorage.setItem('token', originToken);
    sessionStorage.removeItem(ORIGIN_TOKEN_KEY);
    sessionStorage.removeItem(ORIGIN_USERNAME_KEY);
    setToken(originToken);
    setImpersonationOrigin(null);
    fetchMe(originToken).then((adminUser) => {
      if (adminUser?.username) {
        setUser(adminUser);
      } else {
        logout();
      }
    });
  }, [logout]);

  // Listen for global auth:expired events.
  // If we are impersonating, try to recover by restoring the admin token
  // before falling back to a full logout.
  useEffect(() => {
    const handler = () => {
      const originToken = sessionStorage.getItem(ORIGIN_TOKEN_KEY);
      if (originToken) {
        localStorage.setItem('token', originToken);
        sessionStorage.removeItem(ORIGIN_TOKEN_KEY);
        sessionStorage.removeItem(ORIGIN_USERNAME_KEY);
        setToken(originToken);
        setImpersonationOrigin(null);
        fetchMe(originToken).then((adminUser) => {
          if (adminUser?.username) {
            setUser(adminUser);
          } else {
            logout();
          }
        });
        return;
      }
      setToken(null);
      setUser(null);
    };
    window.addEventListener('auth:expired', handler);
    return () => window.removeEventListener('auth:expired', handler);
  }, [logout]);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        login,
        logout,
        isAdmin: user?.role === 'admin',
        loading,
        isImpersonating,
        impersonationOrigin,
        impersonate,
        endImpersonation,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
```

- [ ] **Step 4: Run unit tests — expect PASS**

Run: `cd client && npx vitest run src/__tests__/contexts/AuthContext.impersonation.test.tsx`
Expected: both tests PASS.

- [ ] **Step 5: Run the existing AuthContext test suite to catch regressions**

Run: `cd client && npx vitest run src/__tests__/contexts/AuthContext.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add client/src/contexts/AuthContext.tsx client/src/__tests__/contexts/AuthContext.impersonation.test.tsx
git commit -m "feat(auth): add impersonate/endImpersonation to AuthContext"
```

---

## Task 8: Frontend — i18n strings

**Files:**
- Modify: `client/src/i18n/locales/de/common.json`
- Modify: `client/src/i18n/locales/en/common.json`

- [ ] **Step 1: Inspect the existing common.json shape**

Open both files and find the top-level keys so the new strings merge into a sensible section. Add a new top-level `impersonation` section.

- [ ] **Step 2: Add German strings**

Add to `client/src/i18n/locales/de/common.json`:

```json
"impersonation": {
  "switchToUser": "Als Benutzer anzeigen",
  "banner": {
    "viewingAs": "Angemeldet als {{username}} ({{role}})",
    "backToAdmin": "Zurück zu {{admin}}"
  },
  "role": {
    "admin": "Admin",
    "user": "Benutzer"
  },
  "loading": "Benutzer laden…",
  "empty": "Keine weiteren Benutzer"
}
```

- [ ] **Step 3: Add English strings**

Add to `client/src/i18n/locales/en/common.json`:

```json
"impersonation": {
  "switchToUser": "Switch to user",
  "banner": {
    "viewingAs": "Viewing as {{username}} ({{role}})",
    "backToAdmin": "Back to {{admin}}"
  },
  "role": {
    "admin": "admin",
    "user": "user"
  },
  "loading": "Loading users…",
  "empty": "No other users"
}
```

**Important:** Merge these into the existing JSON object. Don't overwrite the files.

- [ ] **Step 4: Commit**

```bash
git add client/src/i18n/locales/de/common.json client/src/i18n/locales/en/common.json
git commit -m "i18n(common): add impersonation strings"
```

---

## Task 9: Frontend — `ImpersonationBanner` component

**Files:**
- Create: `client/src/components/ImpersonationBanner.tsx`

- [ ] **Step 1: Write the component**

File: `client/src/components/ImpersonationBanner.tsx`

```tsx
import { useTranslation } from 'react-i18next';
import { AlertTriangle } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

export default function ImpersonationBanner() {
  const { t } = useTranslation('common');
  const { isImpersonating, impersonationOrigin, user, endImpersonation } = useAuth();

  if (!isImpersonating || !user || !impersonationOrigin) return null;

  const roleLabel = user.role === 'admin' ? t('impersonation.role.admin') : t('impersonation.role.user');

  return (
    <div
      role="alert"
      className="fixed top-0 right-0 left-0 lg:left-72 z-40 flex items-center justify-between gap-3 bg-amber-500 px-4 py-2 text-sm font-medium text-amber-950 shadow-md"
    >
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4" />
        <span>
          {t('impersonation.banner.viewingAs', { username: user.username, role: roleLabel })}
        </span>
      </div>
      <button
        type="button"
        onClick={endImpersonation}
        className="rounded-md border border-amber-900/40 bg-amber-100/60 px-3 py-1 text-xs font-semibold text-amber-950 transition hover:bg-amber-100"
      >
        {t('impersonation.banner.backToAdmin', { admin: impersonationOrigin })}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/components/ImpersonationBanner.tsx
git commit -m "feat(frontend): add ImpersonationBanner component"
```

---

## Task 10: Frontend — `UserMenu` dropdown with "Switch to user →" submenu

**Files:**
- Create: `client/src/components/UserMenu.tsx`

**Why:** The existing Layout shows the username as a static pill (lines 519–524 in `Layout.tsx`). We replace that pill with a clickable dropdown and hang the impersonation submenu off it. This isolates the change from the rest of Layout.

- [ ] **Step 1: Write the component**

File: `client/src/components/UserMenu.tsx`

```tsx
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { UserPlus, ChevronRight, Shield, User as UserIcon } from 'lucide-react';
import toast from 'react-hot-toast';
import { useAuth } from '../contexts/AuthContext';
import { useSystemMode } from '../hooks/useSystemMode';
import { apiClient } from '../lib/api';
import type { User } from '../types/auth';

interface UserListResponse {
  users?: User[];
}

export default function UserMenu() {
  const { t } = useTranslation('common');
  const { user, isAdmin, isImpersonating, impersonate } = useAuth();
  const { data: systemMode } = useSystemMode();
  const [open, setOpen] = useState(false);
  const [submenuOpen, setSubmenuOpen] = useState(false);
  const [users, setUsers] = useState<User[] | null>(null);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const canSwitchUser = systemMode?.dev_mode === true && isAdmin && !isImpersonating;

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
        setSubmenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const loadUsers = async () => {
    if (users !== null || loadingUsers) return;
    setLoadingUsers(true);
    try {
      const { data } = await apiClient.get<UserListResponse | User[]>('/api/users');
      const list: User[] = Array.isArray(data) ? data : data.users ?? [];
      setUsers(list);
    } catch {
      toast.error('Failed to load users');
      setUsers([]);
    } finally {
      setLoadingUsers(false);
    }
  };

  const onSwitchToUser = async (targetId: number) => {
    try {
      await impersonate(targetId);
      setOpen(false);
      setSubmenuOpen(false);
    } catch (e: any) {
      toast.error(e?.message ?? 'Impersonation failed');
    }
  };

  if (!user) return null;

  return (
    <div ref={rootRef} className="relative hidden md:block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/40 px-3 py-1.5 transition hover:border-sky-500/50 hover:shadow-[0_0_12px_rgba(56,189,248,0.15)]"
      >
        <div className="flex flex-col text-left">
          <span className="text-sm font-medium text-slate-100">{user.username}</span>
          <span className="text-[11px] text-slate-100-tertiary">{isAdmin ? 'Admin' : 'User'}</span>
        </div>
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-64 rounded-xl border border-slate-800 bg-slate-900/95 p-2 shadow-2xl backdrop-blur-xl">
          {canSwitchUser && (
            <div
              className="relative"
              onMouseEnter={() => {
                setSubmenuOpen(true);
                loadUsers();
              }}
              onMouseLeave={() => setSubmenuOpen(false)}
            >
              <button
                type="button"
                className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm text-slate-200 transition hover:bg-slate-800/70"
              >
                <span className="flex items-center gap-2">
                  <UserPlus className="h-4 w-4" />
                  {t('impersonation.switchToUser')}
                </span>
                <ChevronRight className="h-4 w-4 text-slate-400" />
              </button>

              {submenuOpen && (
                <div className="absolute right-full top-0 mr-1 w-64 max-h-80 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900/95 p-2 shadow-2xl backdrop-blur-xl">
                  {loadingUsers && (
                    <div className="px-3 py-2 text-sm text-slate-400">
                      {t('impersonation.loading')}
                    </div>
                  )}
                  {!loadingUsers && users && users.length === 0 && (
                    <div className="px-3 py-2 text-sm text-slate-400">
                      {t('impersonation.empty')}
                    </div>
                  )}
                  {!loadingUsers &&
                    users &&
                    users
                      .filter((u) => u.id !== user.id)
                      .map((u) => (
                        <button
                          key={u.id}
                          type="button"
                          onClick={() => onSwitchToUser(u.id)}
                          className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-sm text-slate-200 transition hover:bg-slate-800/70"
                        >
                          <span className="flex items-center gap-2">
                            {u.role === 'admin' ? (
                              <Shield className="h-4 w-4 text-amber-400" />
                            ) : (
                              <UserIcon className="h-4 w-4 text-slate-400" />
                            )}
                            {u.username}
                          </span>
                          <span
                            className={
                              u.role === 'admin'
                                ? 'rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-300'
                                : 'rounded-full bg-slate-700/50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-slate-300'
                            }
                          >
                            {u.role}
                          </span>
                        </button>
                      ))}
                </div>
              )}
            </div>
          )}
          {!canSwitchUser && (
            <div className="px-3 py-2 text-xs text-slate-500">{user.username}</div>
          )}
        </div>
      )}
    </div>
  );
}
```

**Note:** If `GET /api/users` returns a shape other than `User[]` or `{users: User[]}` (check `client/src/api/users.ts`), adjust `loadUsers` accordingly. The target user of `GET /api/users` in BaluHost is admin-only — that is fine, this submenu is gated on `isAdmin`.

- [ ] **Step 2: Commit**

```bash
git add client/src/components/UserMenu.tsx
git commit -m "feat(frontend): add UserMenu with dev-only switch-to-user submenu"
```

---

## Task 11: Frontend — wire `UserMenu` and `ImpersonationBanner` into `Layout`

**Files:**
- Modify: `client/src/components/Layout.tsx`

- [ ] **Step 1: Add the imports at the top of Layout.tsx**

After the existing imports (around line 17), add:

```tsx
import UserMenu from './UserMenu';
import ImpersonationBanner from './ImpersonationBanner';
```

- [ ] **Step 2: Replace the static username pill with `<UserMenu />`**

In `Layout.tsx`, replace lines 519–524 (the `<div className="hidden md:flex items-center gap-3 ...">` block containing `{user?.username}` and `{isAdmin ? 'Admin' : 'User'}`) with a single line:

```tsx
<UserMenu />
```

Before:

```tsx
<div className="hidden md:flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/40 px-3 py-1.5 transition hover:border-sky-500/50 hover:shadow-[0_0_12px_rgba(56,189,248,0.15)]">
  <div className="flex flex-col">
    <span className="text-sm font-medium text-slate-100">{user?.username}</span>
    <span className="text-[11px] text-slate-100-tertiary">{isAdmin ? 'Admin' : 'User'}</span>
  </div>
</div>
```

After:

```tsx
<UserMenu />
```

- [ ] **Step 3: Render the banner above the header**

Find the `<header className="fixed top-0 right-0 ...">` element (around line 489). Immediately **before** it, add:

```tsx
<ImpersonationBanner />
```

The banner uses the same `fixed top-0 ... z-40` positioning so it sits above the header without reserving layout space when hidden.

- [ ] **Step 4: Run the dev server manually and smoke-test**

```bash
python start_dev.py
```

Verify:
- Login as `admin / DevMode2024`.
- Click the username pill in the topbar → dropdown opens.
- Hover "Switch to user →" → submenu lists users with role badges.
- Click `user` → banner appears, URL resets to `/`, file manager shows user's own files only.
- Click "Back to admin" → banner disappears, full admin view is back.
- F5 while impersonating → banner persists.
- Open a fresh tab at `http://localhost:5173` → clean admin view (sessionStorage not shared).

- [ ] **Step 5: Commit**

```bash
git add client/src/components/Layout.tsx
git commit -m "feat(layout): wire UserMenu and ImpersonationBanner into topbar"
```

---

## Task 12: Frontend — Playwright E2E happy path

**Files:**
- Create: `client/tests/e2e/dev-impersonation.spec.ts`

- [ ] **Step 1: Write the test**

File: `client/tests/e2e/dev-impersonation.spec.ts`

```typescript
import { test, expect } from '@playwright/test';

const adminUser = { id: 1, username: 'admin', role: 'admin', email: 'admin@local' };
const aliceUser = { id: 2, username: 'alice', role: 'user', email: 'alice@local' };

const json = (body: any) => ({
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify(body),
});

test('admin can impersonate a user and return', async ({ browser }) => {
  const context = await browser.newContext({ ignoreHTTPSErrors: true });

  await context.route('**/api/health', (r) => r.fulfill(json({ status: 'ok' })));
  await context.route('**/api/system/mode', (r) => r.fulfill(json({ dev_mode: true })));
  await context.route('**/api/updates/version', (r) => r.fulfill(json({ version: '0.0.0' })));
  await context.route('**/api/plugins', (r) => r.fulfill(json([])));
  await context.route('**/api/plugins/ui/manifest', (r) => r.fulfill(json({})));
  await context.route('**/api/auth/login', (r) =>
    r.fulfill(json({ access_token: 'admin-token', token_type: 'bearer', user: adminUser })),
  );

  let currentUser = adminUser;
  await context.route('**/api/auth/me', (r) => r.fulfill(json({ user: currentUser })));
  await context.route('**/api/users', (r) => r.fulfill(json([adminUser, aliceUser])));
  await context.route('**/api/auth/dev/impersonate/2', (r) => {
    currentUser = aliceUser;
    return r.fulfill(
      json({ access_token: 'imp-token', token_type: 'bearer', user: aliceUser }),
    );
  });

  const page = await context.newPage();
  await page.goto('/login');
  await page.fill('#username', 'admin');
  await page.fill('#password', 'DevMode2024');
  await page.click('button[type="submit"]');

  // Wait for the topbar username pill
  await expect(page.getByText('admin', { exact: true }).first()).toBeVisible({ timeout: 5000 });

  // Open the user menu
  await page.getByText('admin', { exact: true }).first().click();

  // Hover "Switch to user" to open submenu
  await page.getByText('Switch to user').hover();

  // Click alice
  await page.getByRole('button', { name: /alice/i }).click();

  // Banner appears
  await expect(page.getByRole('alert')).toContainText(/alice/i);

  // Click "Back to admin" button
  currentUser = adminUser;
  await page.getByRole('button', { name: /back to admin/i }).click();

  // Banner gone
  await expect(page.getByRole('alert')).toHaveCount(0);

  await context.close();
});
```

- [ ] **Step 2: Run the e2e test**

Run: `cd client && npx playwright test tests/e2e/dev-impersonation.spec.ts`
Expected: PASS.

If the existing Playwright setup already requires a specific mock helper or base URL, mirror the convention from `client/tests/e2e/login.spec.ts` instead of the inline routes above.

- [ ] **Step 3: Commit**

```bash
git add client/tests/e2e/dev-impersonation.spec.ts
git commit -m "test(e2e): add dev impersonation happy path"
```

---

## Task 13: Final verification & PR

- [ ] **Step 1: Run the full backend test suite**

Run: `python -m pytest backend -q`
Expected: PASS (no regressions).

Per project convention (`feedback_run_tests_before_pr.md`), this is mandatory before opening a PR.

- [ ] **Step 2: Run frontend unit tests**

Run: `cd client && npx vitest run`
Expected: PASS.

- [ ] **Step 3: Type-check frontend**

Run: `cd client && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Verify production mode blocks the endpoint**

```bash
NAS_MODE=prod python -m pytest backend/tests/auth/test_dev_impersonation.py::test_impersonate_as_admin_in_dev_mode_returns_token -v
```

Expected: FAIL with 404 (because the router is not registered in prod). This is the desired behavior — if it PASSES, the registration gate is broken.

After confirming, revert to dev mode.

- [ ] **Step 5: Manual smoke test**

Run `python start_dev.py`, then walk through the manual test plan from the design doc (`docs/superpowers/specs/2026-04-12-dev-impersonation-design.md`, "Manual test plan" section). All eleven steps must pass.

- [ ] **Step 6: Open PR to `development`**

```bash
git push -u origin <branch>
gh pr create --base development --title "feat(auth): dev-mode admin→user impersonation" --body "$(cat <<'EOF'
## Summary
- Dev-only `POST /api/auth/dev/impersonate/{user_id}` endpoint (registration + runtime gated)
- `AuthContext` impersonation flow with sessionStorage-backed origin token
- `UserMenu` topbar dropdown with "Switch to user →" submenu
- `ImpersonationBanner` with one-click return
- 30-minute impersonation token TTL, audit-logged, rate-limited

## Test plan
- [x] `python -m pytest backend -q`
- [x] `cd client && npx vitest run`
- [x] `cd client && npx playwright test tests/e2e/dev-impersonation.spec.ts`
- [x] Manual: login as admin, switch to user, verify file jail, notifications, return
- [x] Manual: `NAS_MODE=prod` → endpoint 404, submenu hidden

Spec: `docs/superpowers/specs/2026-04-12-dev-impersonation-design.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Rollback plan

If the feature needs to be ripped out:

1. Delete `backend/app/api/routes/auth_dev.py`.
2. Remove the conditional include block from `backend/app/api/routes/__init__.py`.
3. Remove the startup warning from `backend/app/main.py`.
4. Revert the `impersonated_by` kwarg on `create_access_token` (or leave it — it is a no-op when unused).
5. Delete `client/src/components/UserMenu.tsx`, `ImpersonationBanner.tsx`, `client/src/api/authDev.ts`, `client/src/hooks/useSystemMode.ts`, `client/src/__tests__/contexts/AuthContext.impersonation.test.tsx`, `client/tests/e2e/dev-impersonation.spec.ts`.
6. Revert `AuthContext.tsx` and `Layout.tsx` to pre-feature state.
7. Remove the `impersonation` section from `common.json` (de + en).
