# Audit Remediation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all confirmed critical and high findings from the March 2026 code audit.

**Architecture:** Targeted fixes across backend security, performance, and CI/CD. No architectural refactors — each task is a focused fix with tests. Security fixes first, then performance, then CI.

**Tech Stack:** Python FastAPI, Pydantic, SQLAlchemy, pytest, GitHub Actions, TypeScript/Vitest

---

## Phase 1: Security Critical (Priority 1)

### Task 1: Add Pydantic models for change-password and refresh-token endpoints

**Context:** The `/auth/change-password` endpoint (auth.py:430) accepts `payload: dict`, bypassing password strength validation. A user can set password to "a". The `/auth/refresh` endpoint (auth.py:487) also uses raw dict. This is Known Gap #8 in security-agent.md.

**Files:**
- Modify: `backend/app/schemas/auth.py` — add `ChangePasswordRequest` and `RefreshTokenRequest` models
- Modify: `backend/app/api/routes/auth.py:427-460` — use new Pydantic models
- Modify: `backend/app/api/routes/auth.py:485-520` — use new Pydantic model
- Test: `backend/tests/security/test_password_validation.py` (new or extend existing)

**Step 1: Write failing tests**

```python
# backend/tests/security/test_change_password_validation.py

import pytest
from fastapi.testclient import TestClient


def test_change_password_rejects_weak_password(client: TestClient, auth_headers: dict):
    """New password must meet strength requirements (8+ chars, upper, lower, digit)."""
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "DevMode2024", "new_password": "a"},
        headers=auth_headers,
    )
    assert response.status_code == 422  # Pydantic validation error


def test_change_password_rejects_common_password(client: TestClient, auth_headers: dict):
    """New password must not be in common password blacklist."""
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "DevMode2024", "new_password": "Password123"},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_change_password_accepts_strong_password(client: TestClient, auth_headers: dict):
    """Strong passwords should be accepted."""
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": "DevMode2024", "new_password": "NewStr0ngPass!"},
        headers=auth_headers,
    )
    assert response.status_code in (200, 400)  # 200 success or 400 wrong current pw


def test_refresh_token_requires_token_field(client: TestClient):
    """Refresh endpoint must require refresh_token field."""
    response = client.post("/api/auth/refresh", json={})
    assert response.status_code == 422
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/security/test_change_password_validation.py -v`
Expected: FAIL — currently accepts weak passwords (returns 200 instead of 422)

**Step 3: Add Pydantic models to schemas/auth.py**

Add after the existing `RegisterRequest` class:

```python
class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        # Reuse the same validation logic as RegisterRequest
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        common_passwords = [
            "password", "12345678", "qwerty123", "admin123",
            "letmein1", "welcome1", "monkey123", "dragon12",
            "master12", "abc12345", "password123",
        ]
        if v.lower() in common_passwords:
            raise ValueError("This password is too common")
        return v


class RefreshTokenRequest(BaseModel):
    refresh_token: str
```

Note: Check the existing `RegisterRequest.validate_password_strength` validator in `schemas/auth.py` and reuse or call the same logic to stay DRY. If the validation logic is identical, extract a shared helper function `_validate_password_strength(v: str) -> str` and call it from both validators.

**Step 4: Update change-password endpoint in auth.py**

Change the function signature from:
```python
async def change_password(
    payload: dict,
```
to:
```python
async def change_password(
    payload: ChangePasswordRequest,
```

Update field access from `payload.get("current_password")` / `payload.get("new_password")` to `payload.current_password` / `payload.new_password`. Remove the manual presence checks (lines ~443-444) since Pydantic handles that now.

**Step 5: Update refresh-token endpoint in auth.py**

Change from `payload: dict` to `payload: RefreshTokenRequest`. Update field access from `payload.get("refresh_token")` to `payload.refresh_token`.

**Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/security/test_change_password_validation.py -v`
Expected: ALL PASS

**Step 7: Run full auth test suite for regressions**

Run: `cd backend && python -m pytest tests/ -k auth -v`
Expected: ALL PASS

**Step 8: Commit**

```bash
git add backend/app/schemas/auth.py backend/app/api/routes/auth.py backend/tests/security/test_change_password_validation.py
git commit -m "fix(security): add Pydantic validation to change-password and refresh-token endpoints"
```

---

### Task 2: Restrict user registration to admin-authorized paths

**Context:** `/auth/register` (auth.py:369) is publicly accessible. Anyone who can reach the API can create accounts. For a NAS on a local network this is medium risk, but should be restricted.

**Files:**
- Modify: `backend/app/core/config.py` — add `registration_enabled: bool` setting
- Modify: `backend/app/api/routes/auth.py:369-405` — check setting before allowing registration
- Test: `backend/tests/auth/test_registration_restriction.py` (new)

**Step 1: Write failing tests**

```python
# backend/tests/auth/test_registration_restriction.py

import pytest
from unittest.mock import patch


def test_register_rejected_when_disabled(client):
    """Registration should fail when registration_enabled=False."""
    with patch("app.api.routes.auth.settings") as mock_settings:
        mock_settings.registration_enabled = False
        # Copy other needed attributes from real settings
        response = client.post(
            "/api/auth/register",
            json={"username": "newuser", "password": "Str0ngPass1"},
        )
    assert response.status_code == 403
    assert "registration" in response.json()["detail"].lower()


def test_register_allowed_when_enabled(client):
    """Registration should work when registration_enabled=True (default)."""
    response = client.post(
        "/api/auth/register",
        json={"username": "newuser2", "password": "Str0ngPass1"},
    )
    assert response.status_code in (201, 409)  # 201 created or 409 already exists
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/auth/test_registration_restriction.py -v`

**Step 3: Add config setting**

In `backend/app/core/config.py`, add to the Settings class:
```python
registration_enabled: bool = True  # Set to False in production to require admin-created accounts
```

**Step 4: Add guard to register endpoint**

At the top of the `register()` function in `auth.py`, add:
```python
if not settings.registration_enabled:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Public registration is disabled. Contact an administrator.",
    )
```

**Step 5: Run tests**

Run: `cd backend && python -m pytest tests/auth/test_registration_restriction.py -v`
Expected: ALL PASS

**Step 6: Run full auth test suite**

Run: `cd backend && python -m pytest tests/ -k auth -v`

**Step 7: Commit**

```bash
git add backend/app/core/config.py backend/app/api/routes/auth.py backend/tests/auth/test_registration_restriction.py
git commit -m "feat(security): add registration_enabled config to restrict public registration"
```

---

### Task 3: Add production validator for default admin password

**Context:** `admin_password` defaults to "DevMode2024" (config.py:47). Unlike `SECRET_KEY`, there is no validator rejecting this default in production mode. The admin account is silently created with this known password.

**Files:**
- Modify: `backend/app/core/config.py` — add production validator for admin_password
- Test: `backend/tests/test_config_validation.py` (extend existing or new)

**Step 1: Write failing test**

```python
# In backend/tests/test_config_validation.py or new file

import pytest
from unittest.mock import patch
import os


def test_production_rejects_default_admin_password():
    """Production mode must reject the default admin password."""
    env = {
        "NAS_MODE": "prod",
        "SECRET_KEY": "a" * 64,
        "TOKEN_SECRET": "b" * 64,
        "ADMIN_PASSWORD": "DevMode2024",  # the default
        "DATABASE_URL": "postgresql://user:pass@localhost/db",
    }
    with patch.dict(os.environ, env, clear=False):
        from app.core.config import Settings
        with pytest.raises(ValueError, match="admin.password|ADMIN_PASSWORD"):
            Settings()


def test_production_accepts_strong_admin_password():
    """Production mode should accept a strong admin password."""
    env = {
        "NAS_MODE": "prod",
        "SECRET_KEY": "a" * 64,
        "TOKEN_SECRET": "b" * 64,
        "ADMIN_PASSWORD": "MyStr0ngAdm1nPass!",
        "DATABASE_URL": "postgresql://user:pass@localhost/db",
    }
    with patch.dict(os.environ, env, clear=False):
        from app.core.config import Settings
        settings = Settings()
        assert settings.admin_password == "MyStr0ngAdm1nPass!"
```

Note: Adapt imports and fixture setup to match the existing config test patterns in the codebase.

**Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_config_validation.py -v -k admin_password`

**Step 3: Add validator to config.py**

Add a `@field_validator("admin_password")` similar to the existing `validate_secret_key` and `validate_token_secret` validators. Place it after those validators:

```python
@field_validator("admin_password")
@classmethod
def validate_admin_password(cls, v: str, info) -> str:
    """Reject default admin password in production mode."""
    values = info.data
    if values.get("nas_mode") == "prod" or values.get("environment") == "production":
        if v == "DevMode2024":
            raise ValueError(
                "ADMIN_PASSWORD must be changed from default for production. "
                "Set ADMIN_PASSWORD environment variable."
            )
        if len(v) < 12:
            raise ValueError(
                "ADMIN_PASSWORD must be at least 12 characters in production."
            )
    return v
```

Note: Check the exact field names and validator order in config.py. Pydantic v2 validators run in field-definition order, and `nas_mode` must be defined before `admin_password` for `info.data` to contain it.

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_config_validation.py -v -k admin_password`

**Step 5: Run full config tests**

Run: `cd backend && python -m pytest tests/ -k config -v`

**Step 6: Commit**

```bash
git add backend/app/core/config.py backend/tests/test_config_validation.py
git commit -m "fix(security): reject default admin password in production mode"
```

---

### Task 4: Encrypt VPN server private key and preshared keys at rest

**Context:** `VPNConfig.server_private_key` and `VPNClient.preshared_key` are stored as plaintext in the database. The `VPNEncryption` class and Fritz!Box config path already use Fernet encryption — the standard VPN path just doesn't use it.

**Files:**
- Modify: `backend/app/services/vpn/service.py:164-205` — encrypt keys before DB storage, decrypt on read
- Modify: `backend/app/models/vpn.py` — rename columns to `*_encrypted` for clarity (optional, may need migration)
- Create: `backend/alembic/versions/039_encrypt_vpn_keys.py` — data migration to encrypt existing plaintext keys
- Test: `backend/tests/test_vpn_encryption.py` (extend or new)

**Step 1: Write failing test**

```python
def test_vpn_server_private_key_stored_encrypted(db_session):
    """Server private key must be encrypted at rest in the database."""
    # After creating a VPN config, the raw DB column should not contain
    # the plaintext private key
    from app.services.vpn.encryption import VPNEncryption

    # Create a VPN config through the service
    # ... (adapt to existing test fixtures)

    # Query the raw column value
    raw = db_session.execute(
        text("SELECT server_private_key FROM vpn_config WHERE id = :id"),
        {"id": config_id}
    ).scalar()

    # Should be Fernet-encrypted (starts with 'gAAAAA' base64)
    assert raw != plaintext_key
    assert raw.startswith("gAAAAA")
```

**Step 2: Implement encryption in service.py**

In `create_client_config()` and wherever `server_private_key` / `preshared_key` are stored:
- Wrap with `VPNEncryption.encrypt_key(key)` before storing
- Wrap with `VPNEncryption.decrypt_key(encrypted)` when reading for config generation

**Step 3: Create Alembic migration for existing data**

Create a data migration that:
1. Reads all existing plaintext keys
2. Encrypts them with `VPNEncryption.encrypt_key()`
3. Updates the rows

Important: This migration requires `VPN_ENCRYPTION_KEY` to be set. Add a check at the top.

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/ -k vpn -v`

**Step 5: Commit**

```bash
git add backend/app/services/vpn/service.py backend/alembic/versions/039_encrypt_vpn_keys.py backend/tests/test_vpn_encryption.py
git commit -m "fix(security): encrypt VPN server and preshared keys at rest"
```

---

### Task 5: Use scoped short-lived token for WebSocket authentication

**Context:** The notification WebSocket endpoint (`notifications.py:319`) accepts the full JWT access token as a query parameter. Query params are logged in server access logs, proxy logs, and browser history. The SSE token pattern already exists as a template.

**Files:**
- Modify: `backend/app/api/routes/notifications.py:319-323` — accept WS-scoped token
- Modify: `backend/app/core/security.py` — add `create_ws_token()` (similar to existing `create_sse_token()`)
- Add endpoint: `backend/app/api/routes/notifications.py` — `POST /notifications/ws-token` to issue scoped token
- Test: `backend/tests/test_websocket_auth.py` (new)

**Step 1: Write failing test**

```python
def test_websocket_rejects_full_access_token(client, auth_headers):
    """WebSocket should reject full access tokens passed as query param."""
    token = auth_headers["Authorization"].replace("Bearer ", "")
    with client.websocket_connect(f"/api/notifications/ws?token={token}") as ws:
        # Should be rejected — full access tokens not accepted
        pass
    # Expect connection close or 403


def test_websocket_accepts_scoped_ws_token(client, auth_headers):
    """WebSocket should accept short-lived WS-scoped tokens."""
    # Get a WS token
    response = client.post("/api/notifications/ws-token", headers=auth_headers)
    assert response.status_code == 200
    ws_token = response.json()["token"]

    # Connect with scoped token
    with client.websocket_connect(f"/api/notifications/ws?token={ws_token}") as ws:
        pass  # Connection should succeed
```

**Step 2: Add `create_ws_token()` to security.py**

Follow the existing `create_sse_token()` pattern:
```python
def create_ws_token(user_id: int, username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(seconds=60)
    payload = {
        "sub": str(user_id),
        "username": username,
        "type": "ws",
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
```

**Step 3: Add token-issuing endpoint**

```python
@router.post("/ws-token")
async def get_ws_token(current_user = Depends(deps.get_current_user)):
    token = create_ws_token(current_user.id, current_user.username)
    return {"token": token}
```

**Step 4: Update WebSocket handler to validate token type**

In the WebSocket handler, after decoding the token, check `payload.get("type") == "ws"`.

**Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_websocket_auth.py -v`

**Step 6: Update frontend WebSocket connection code**

In the frontend, update the WebSocket connection to first fetch a WS token via `POST /api/notifications/ws-token`, then use that token in the query parameter.

**Step 7: Commit**

```bash
git add backend/app/core/security.py backend/app/api/routes/notifications.py backend/tests/test_websocket_auth.py client/src/
git commit -m "fix(security): use scoped short-lived token for WebSocket auth"
```

---

### Task 6: Add TTL + max-size bound to brute-force tracking dict

**Context:** `_failed_login_attempts` dict in auth.py:28 grows without bound. An attacker flooding with unique IPs could consume memory.

**Files:**
- Modify: `backend/app/api/routes/auth.py:28` — replace dict with `cachetools.TTLCache`
- Test: `backend/tests/auth/test_brute_force_limits.py` (new or extend)

**Step 1: Write test**

```python
def test_brute_force_tracker_has_max_size():
    """Brute-force tracker should not grow unbounded."""
    from app.api.routes.auth import _failed_login_attempts
    from cachetools import TTLCache
    assert isinstance(_failed_login_attempts, TTLCache)
    assert _failed_login_attempts.maxsize <= 10000
```

**Step 2: Replace dict with TTLCache**

```python
from cachetools import TTLCache

# Max 10,000 tracked IPs, entries expire after 30 minutes
_failed_login_attempts: TTLCache = TTLCache(maxsize=10000, ttl=1800)
```

Verify `cachetools` is already in dependencies (check `pyproject.toml`). If not, add it.

**Step 3: Run tests**

Run: `cd backend && python -m pytest tests/ -k "auth or brute" -v`

**Step 4: Commit**

```bash
git add backend/app/api/routes/auth.py backend/tests/auth/test_brute_force_limits.py
git commit -m "fix(security): bound brute-force tracking dict with TTLCache"
```

---

### Task 7: Default debug to False

**Context:** `config.py:8` defaults `debug=True`. Anyone deploying without explicitly setting `DEBUG=false` gets debug mode with potential stack trace exposure.

**Files:**
- Modify: `backend/app/core/config.py` — change `debug: bool = True` to `debug: bool = False`
- Modify: `backend/app/core/config.py` — in `_apply_dev_defaults`, set `debug=True` for dev mode

**Step 1: Change default**

In `config.py`, change:
```python
debug: bool = True
```
to:
```python
debug: bool = False
```

**Step 2: Ensure dev mode still enables debug**

In the `_apply_dev_defaults` model validator, add:
```python
if values.get("nas_mode") == "dev":
    values.setdefault("debug", True)
```

Check: `start_dev.py` may already set `NAS_MODE=dev` which triggers the validator.

**Step 3: Run tests**

Run: `cd backend && python -m pytest tests/ -v --timeout=60`

**Step 4: Commit**

```bash
git add backend/app/core/config.py
git commit -m "fix(security): default debug=False, only enable in dev mode"
```

---

## Phase 2: Performance Critical (Priority 2)

### Task 8: Fix N+1 query pattern in directory listing

**Context:** `list_directory()` in `operations.py:118` issues 3-4 DB queries per filesystem entry. A directory with 100 files = 300-400 queries. This is the most impactful performance issue.

**Files:**
- Modify: `backend/app/services/files/operations.py:118-187` — batch-fetch metadata
- Modify: `backend/app/services/files/metadata_db.py` — add bulk query methods
- Test: `backend/tests/files/test_directory_listing_perf.py` (new)

**Step 1: Write test asserting query count**

```python
def test_list_directory_uses_bounded_queries(db_session, tmp_path):
    """Directory listing should use O(1) queries, not O(n) per entry."""
    # Create 50 test files in directory
    for i in range(50):
        (tmp_path / f"file_{i}.txt").write_text(f"content {i}")

    # Count DB queries during list_directory
    query_count = 0
    original_execute = db_session.execute

    def counting_execute(*args, **kwargs):
        nonlocal query_count
        query_count += 1
        return original_execute(*args, **kwargs)

    db_session.execute = counting_execute

    result = list_directory(str(tmp_path), user=mock_user, db=db_session)

    # Should be O(1) queries (batch), not O(n)
    # Allow up to 10 queries total (not 150-200)
    assert query_count < 15, f"Expected <15 queries, got {query_count}"
```

**Step 2: Add bulk query methods to metadata_db.py**

```python
def get_owners_bulk(paths: list[str], db: Session) -> dict[str, int | None]:
    """Fetch owners for multiple paths in a single query."""
    results = db.query(FileMetadata.path, FileMetadata.owner_id).filter(
        FileMetadata.path.in_(paths)
    ).all()
    return {r.path: r.owner_id for r in results}


def get_metadata_bulk(paths: list[str], db: Session) -> dict[str, FileMetadata]:
    """Fetch metadata for multiple paths in a single query."""
    results = db.query(FileMetadata).filter(
        FileMetadata.path.in_(paths)
    ).all()
    return {r.path: r for r in results}


def get_share_permissions_bulk(db: Session, paths: list[str], user_id: int) -> dict[str, str]:
    """Fetch share permissions for multiple paths in a single query."""
    results = db.query(FileShare.path, FileShare.permission).filter(
        FileShare.path.in_(paths),
        FileShare.shared_with_id == user_id,
    ).all()
    return {r.path: r.permission for r in results}
```

**Step 3: Refactor list_directory() to use bulk queries**

1. First, collect all entry paths
2. Batch-fetch all metadata, owners, and shares in 3 queries
3. Build lookup dicts
4. Iterate entries and populate from dicts

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/files/ -v`

**Step 5: Commit**

```bash
git add backend/app/services/files/operations.py backend/app/services/files/metadata_db.py backend/tests/files/test_directory_listing_perf.py
git commit -m "perf: fix N+1 query pattern in directory listing with bulk fetches"
```

---

### Task 9: Fix synchronous file listing blocking event loop

**Context:** `list_files` route is `async def` but calls synchronous `list_directory()` with filesystem I/O and DB queries. This blocks the event loop. Two options: (a) change route to `def` (FastAPI auto-threadpools sync routes), or (b) wrap in `asyncio.to_thread()`.

**Files:**
- Modify: `backend/app/api/routes/files.py:485` — change `async def list_files` to `def list_files`

**Step 1: Change the route handler**

Change:
```python
async def list_files(
```
to:
```python
def list_files(
```

FastAPI will automatically run sync route handlers in a thread pool, preventing event loop blocking. This is the simplest fix.

Note: Check that the function body doesn't use `await` anywhere. If it does, use `asyncio.to_thread()` instead.

**Step 2: Run tests**

Run: `cd backend && python -m pytest tests/files/ -v`

**Step 3: Commit**

```bash
git add backend/app/api/routes/files.py
git commit -m "perf: convert list_files to sync def to prevent event loop blocking"
```

---

### Task 10: Fix notification count — use COUNT(*) instead of fetching 10k rows

**Context:** `notifications.py:67` fetches up to 10,000 notification objects to count total for pagination. Should use SQL COUNT.

**Files:**
- Modify: `backend/app/api/routes/notifications.py:67-84` — use count query
- Modify: `backend/app/services/notification_service.py` — add `count_user_notifications()` method

**Step 1: Add count method to service**

```python
def count_user_notifications(self, db: Session, user_id: int, ...) -> int:
    """Return count of notifications matching filters."""
    query = db.query(func.count(Notification.id)).filter(
        Notification.user_id == user_id
    )
    # Apply same filters as get_user_notifications
    return query.scalar()
```

**Step 2: Update route handler**

Replace:
```python
total_notifications = service.get_user_notifications(db=db, user_id=..., limit=10000, offset=0)
total = len(total_notifications)
```
with:
```python
total = service.count_user_notifications(db=db, user_id=current_user.id, ...)
```

**Step 3: Run tests**

Run: `cd backend && python -m pytest tests/ -k notification -v`

**Step 4: Commit**

```bash
git add backend/app/services/notification_service.py backend/app/api/routes/notifications.py
git commit -m "perf: use COUNT(*) query for notification pagination total"
```

---

### Task 11: Fix notification unread count — single GROUP BY instead of 9 queries

**Context:** `notifications.py:105` runs 9 separate queries (1 per category + 1 total) for unread count.

**Files:**
- Modify: `backend/app/services/notification_service.py` — add `get_unread_counts()` method
- Modify: `backend/app/api/routes/notifications.py:105` — use new method

**Step 1: Add grouped count method**

```python
def get_unread_counts(self, db: Session, user_id: int) -> dict[str, int]:
    """Get unread counts per category in a single query."""
    results = db.query(
        Notification.category,
        func.count(Notification.id)
    ).filter(
        Notification.user_id == user_id,
        Notification.is_read == False,
    ).group_by(Notification.category).all()

    counts = {cat: count for cat, count in results}
    counts["total"] = sum(counts.values())
    return counts
```

**Step 2: Update route handler**

Replace 9 individual service calls with one `get_unread_counts()` call.

**Step 3: Run tests**

Run: `cd backend && python -m pytest tests/ -k notification -v`

**Step 4: Commit**

```bash
git add backend/app/services/notification_service.py backend/app/api/routes/notifications.py
git commit -m "perf: single GROUP BY query for notification unread counts"
```

---

### Task 12: Replace list.pop(0) with deque in monitoring buffer

**Context:** `monitoring/base.py:128` uses `list.pop(0)` which is O(n). Called every 5 seconds for 4 collectors.

**Files:**
- Modify: `backend/app/services/monitoring/base.py:128` — replace list with `collections.deque`

**Step 1: Replace buffer implementation**

```python
from collections import deque

# In __init__:
self._buffer: deque = deque(maxlen=buffer_size)

# Remove the manual pop(0) and len check — deque(maxlen=...) handles eviction automatically
# Replace:
#   if len(self._buffer) >= self._buffer_size:
#       self._buffer.pop(0)
#   self._buffer.append(sample)
# With:
#   self._buffer.append(sample)
```

**Step 2: Run tests**

Run: `cd backend && python -m pytest tests/ -k monitoring -v`

**Step 3: Commit**

```bash
git add backend/app/services/monitoring/base.py
git commit -m "perf: replace list.pop(0) with deque(maxlen) in monitoring buffer"
```

---

## Phase 3: CI/CD (Priority 3)

### Task 13: Add GitHub Actions workflow for full pytest suite

**Context:** Only RAID-specific tests run in CI. The full 1121-test suite is never validated on push/PR.

**Files:**
- Create: `.github/workflows/backend-tests.yml`

**Step 1: Create workflow**

```yaml
name: Backend Tests

on:
  push:
    branches: [main, development]
    paths:
      - 'backend/**'
  pull_request:
    branches: [main, development]
    paths:
      - 'backend/**'

jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Run tests
        run: python -m pytest -q --timeout=120
        env:
          NAS_MODE: dev
```

**Step 2: Commit**

```bash
git add .github/workflows/backend-tests.yml
git commit -m "ci: add GitHub Actions workflow for full backend pytest suite"
```

---

### Task 14: Add Vitest step to frontend CI workflow

**Context:** `build-client.yml` only runs `npm run build`, not tests.

**Files:**
- Modify: `.github/workflows/build-client.yml` — add test step

**Step 1: Add test step**

After the `npm run build` step, add:
```yaml
      - name: Run unit tests
        run: npx vitest run
```

**Step 2: Commit**

```bash
git add .github/workflows/build-client.yml
git commit -m "ci: add Vitest run to frontend build workflow"
```

---

## Phase 4: Quick Wins (Priority 4)

### Task 15: Remove committed data artifacts from git

**Context:** `backend/baluhost.db.backup-*`, benchmark results, and dev-backup archives are tracked in git.

**Files:**
- Modify: `.gitignore` — add patterns
- Run: `git rm --cached` for tracked artifacts

**Step 1: Update .gitignore**

Add:
```
backend/baluhost.db.backup-*
backend/benchmark_results/
backend/dev-backups/
```

**Step 2: Remove from tracking**

```bash
git rm --cached backend/baluhost.db.backup-20251209-215648
git rm --cached -r backend/benchmark_results/ 2>/dev/null || true
git rm --cached -r backend/dev-backups/ 2>/dev/null || true
```

**Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: remove data artifacts from git tracking"
```

---

### Task 16: Fix version number drift

**Context:** `__init__.py` says 1.8.2, `pyproject.toml` says 1.12.0. The FastAPI app reports wrong version in Swagger.

**Files:**
- Modify: `backend/app/__init__.py:3` — update `__version__` to match pyproject.toml

**Step 1: Fix version**

```python
__version__ = "1.12.0"
```

**Step 2: Commit**

```bash
git add backend/app/__init__.py
git commit -m "fix: sync __version__ with pyproject.toml (1.12.0)"
```

---

### Task 17: Make CSP conditional on environment

**Context:** `security_headers.py:29` applies `unsafe-inline` and `unsafe-eval` in all environments including production. This is Known Gap #1 but can be improved.

**Files:**
- Modify: `backend/app/middleware/security_headers.py` — conditional CSP

**Step 1: Make CSP environment-aware**

```python
from app.core.config import settings

if settings.is_dev_mode:
    script_src = "'self' 'unsafe-inline' 'unsafe-eval'"
else:
    script_src = "'self'"

csp = f"default-src 'self'; script-src {script_src}; ..."
```

Note: Test the production frontend build to ensure it works without unsafe-inline. If it breaks (e.g., inline event handlers), add nonce-based CSP instead.

**Step 2: Run tests**

Run: `cd backend && python -m pytest tests/ -k security -v`

**Step 3: Commit**

```bash
git add backend/app/middleware/security_headers.py
git commit -m "fix(security): tighten CSP in production, allow unsafe-inline only in dev"
```

---

### Task 18: Separate encryption keys for TOTP and SSH

**Context:** `VPN_ENCRYPTION_KEY` is reused for VPN keys, TOTP secrets, and SSH keys. Single key compromise exposes all.

**Files:**
- Modify: `backend/app/core/config.py` — add `TOTP_ENCRYPTION_KEY` setting (falls back to `VPN_ENCRYPTION_KEY` for migration)
- Modify: `backend/app/services/totp_service.py:89` — use dedicated key
- Test: Verify TOTP encryption/decryption still works

**Step 1: Add config**

```python
totp_encryption_key: str = ""  # Falls back to VPN_ENCRYPTION_KEY if not set
```

**Step 2: Add key resolution in totp_service.py**

```python
def _get_totp_key() -> str:
    key = settings.totp_encryption_key or settings.VPN_ENCRYPTION_KEY
    if not key:
        raise ValueError("No encryption key configured for TOTP")
    return key
```

**Step 3: Run tests**

Run: `cd backend && python -m pytest tests/ -k totp -v`

**Step 4: Commit**

```bash
git add backend/app/core/config.py backend/app/services/totp_service.py
git commit -m "fix(security): add dedicated TOTP_ENCRYPTION_KEY (falls back to VPN key)"
```

---

### Task 19: Restrict CORS methods and headers

**Context:** `main.py:939-945` uses `allow_methods=["*"]` and `allow_headers=["*"]`. Origins are restricted but methods/headers are not.

**Files:**
- Modify: `backend/app/main.py:943-944`

**Step 1: Restrict methods and headers**

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin) for origin in settings.cors_origins],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Device-ID", "X-Requested-With"],
)
```

Note: Check if any frontend requests use headers beyond these. Search the frontend code for custom headers.

**Step 2: Test frontend still works**

Start dev environment and verify login, file upload, and WebSocket connections work.

**Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "fix(security): restrict CORS methods and headers to required set"
```

---

### Task 20: Add timing-safe user enumeration prevention

**Context:** `auth.py:23` returns early when user not found (skipping bcrypt), creating a timing difference for username enumeration. Low severity but easy fix.

**Files:**
- Modify: `backend/app/services/auth.py:23`

**Step 1: Add dummy hash comparison**

```python
from passlib.context import CryptContext

# Precomputed bcrypt hash of a random string for timing normalization
_DUMMY_HASH = "$2b$12$LJ3m4ys3QS0pB/XfManNqeJShDW5F1.2JEOVBc6IeDPSq2G7z/5Oq"

def authenticate_user(username: str, password: str, db: Session):
    user = get_user_by_username(db, username)
    if not user:
        # Perform dummy hash comparison to normalize timing
        pwd_context.verify(password, _DUMMY_HASH)
        return None
    if not pwd_context.verify(password, user.hashed_password):
        return None
    return user
```

**Step 2: Run tests**

Run: `cd backend && python -m pytest tests/ -k auth -v`

**Step 3: Commit**

```bash
git add backend/app/services/auth.py
git commit -m "fix(security): add timing-safe dummy hash on failed user lookup"
```

---

## Summary

| Phase | Tasks | Impact |
|-------|-------|--------|
| 1: Security | Tasks 1-7 | Fixes all confirmed critical + high security vulnerabilities |
| 2: Performance | Tasks 8-12 | Fixes N+1 queries, event loop blocking, inefficient counts |
| 3: CI/CD | Tasks 13-14 | Enables 1100+ backend tests and frontend tests in CI |
| 4: Quick Wins | Tasks 15-20 | Version sync, CSP, CORS, git cleanup, timing attack |

**Estimated total: 20 tasks, each 2-15 minutes implementation time.**

**Not addressed (accepted trade-offs from Known Gaps #1-#10):**
- JWT in localStorage (would require full auth refactor)
- In-memory rate limiter (acceptable for single-instance)
- WebSocket horizontal scaling (by design for NAS)
- CSRF (not applicable with Bearer auth)
- Samba command injection (false positive — already safe)
- 532 bare except (false positive — actually 8, all in TUI/scripts)
