# Tauri PIN Login — Backend Implementation Plan (Plan 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend for signing into the Tauri Companion app with a numeric PIN in place of the password — local-channel only, 2FA-anchored, with an admin-global absolute grace window during which the PIN alone suffices.

**Architecture:** A new local-channel-only `POST /api/auth/login-pin` reuses the existing `2fa_pending`/`verify-2fa` flow and bcrypt (`pwd_context`). Within an admin-configured grace window (set on every successful TOTP) the PIN alone returns an access token; outside it, the PIN yields a `2fa_pending` token that the user completes with TOTP. PIN management is TOTP-gated; disabling 2FA destroys the PIN.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic, passlib bcrypt, Pytest.

Spec: `docs/superpowers/specs/2026-06-06-tauri-pin-login-design.md`. Frontend (Tauri login UI, PIN settings, admin policy UI, i18n) is **Plan 2**. Step-up 2FA is out of scope ([#169](https://github.com/Xveyn/BaluHost/issues/169)).

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `backend/app/models/user.py` | User ORM | +4 PIN columns |
| `backend/app/models/auth_policy.py` | `AuthPolicy` singleton (window + kill switch) | NEW |
| `backend/app/models/__init__.py` | model registry | register `AuthPolicy` |
| `backend/alembic/versions/<rev>_add_pin_and_auth_policy.py` | migration | NEW |
| `backend/app/services/auth_policy.py` | get-or-create singleton | NEW |
| `backend/app/services/pin_service.py` | PIN hash/verify, grace, lockout | NEW |
| `backend/app/schemas/auth.py` | PIN request/response + validator | +schemas |
| `backend/app/schemas/auth_policy.py` | policy schemas (cap-validated) | NEW |
| `backend/app/services/totp_service.py` | disable 2FA | clear PIN on disable |
| `backend/app/api/routes/auth.py` | auth routes | +`login-pin`, +`/pin` (GET/POST/DELETE), extend `verify_2fa` |
| `backend/app/api/routes/auth_policy.py` | admin policy endpoints | NEW |
| `backend/app/api/routes/__init__.py` | router registry | register `auth_policy` |
| `backend/app/core/rate_limiter.py` | limits | +`auth_pin_login` |
| `backend/tests/...` | tests | NEW per task |

---

## Task 1: User PIN columns + AuthPolicy model + migration

**Files:**
- Modify: `backend/app/models/user.py`
- Create: `backend/app/models/auth_policy.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<rev>_add_pin_and_auth_policy.py`
- Test: `backend/tests/models/test_pin_columns.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/models/test_pin_columns.py`:

```python
"""Schema presence tests for PIN columns and AuthPolicy."""
from app.models.user import User
from app.models.auth_policy import AuthPolicy


def test_user_has_pin_columns():
    cols = set(User.__table__.columns.keys())
    assert {"pin_hash", "pin_grace_until", "pin_failed_attempts", "pin_locked_until"} <= cols


def test_auth_policy_defaults(db_session):
    p = AuthPolicy(id=1)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    assert p.pin_login_enabled is True
    assert p.pin_grace_window_seconds == 86400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/models/test_pin_columns.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: app.models.auth_policy` / missing columns.

- [ ] **Step 3: Add the 4 PIN columns to `User`**

In `backend/app/models/user.py`, immediately after the TOTP block (after the line
`totp_enabled_at: Mapped[Optional[datetime]] = mapped_column(\n        DateTime(timezone=True), nullable=True\n    )`):

```python

    # PIN login (Tauri local channel) — anchored on 2FA
    pin_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    pin_grace_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pin_failed_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    pin_locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

- [ ] **Step 4: Create the `AuthPolicy` model**

Create `backend/app/models/auth_policy.py`:

```python
"""Singleton auth policy: PIN-login window + global kill switch."""
from __future__ import annotations

from sqlalchemy import Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuthPolicy(Base):
    """Single row (id=1) holding system-wide auth policy."""

    __tablename__ = "auth_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    pin_login_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    pin_grace_window_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=86400, server_default="86400"
    )
```

- [ ] **Step 5: Register `AuthPolicy` in the model registry**

In `backend/app/models/__init__.py`, add an import alongside the other model imports and add
`"AuthPolicy"` to `__all__` (mirror the existing entries):

```python
from app.models.auth_policy import AuthPolicy
```

- [ ] **Step 6: Run the schema test (passes without migration — in-memory `Base.metadata`)**

Run: `cd backend && python -m pytest tests/models/test_pin_columns.py -v --no-cov`
Expected: PASS (the `db_session` fixture builds tables from `Base.metadata`).

- [ ] **Step 7: Generate the Alembic migration**

Run: `cd backend && alembic heads`
Note the printed head revision (call it `<HEAD>`). Then:
Run: `cd backend && alembic revision --autogenerate -m "add pin columns and auth_policy"`

- [ ] **Step 8: Review & fix the migration**

Open the new file under `backend/alembic/versions/`. Confirm:
- `down_revision` equals `<HEAD>` from Step 7 (NOT a stale dev-DB head — if it differs, set it manually).
- `upgrade()` adds the 4 columns to `users` and creates `auth_policy`. If autogenerate missed anything, make `upgrade()` exactly:

```python
def upgrade():
    op.add_column("users", sa.Column("pin_hash", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("pin_grace_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("pin_failed_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("pin_locked_until", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "auth_policy",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pin_login_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("pin_grace_window_seconds", sa.Integer(), nullable=False, server_default="86400"),
    )


def downgrade():
    op.drop_table("auth_policy")
    op.drop_column("users", "pin_locked_until")
    op.drop_column("users", "pin_failed_attempts")
    op.drop_column("users", "pin_grace_until")
    op.drop_column("users", "pin_hash")
```

- [ ] **Step 9: Apply + verify the migration**

Run: `cd backend && alembic upgrade head && python -c "from app.core.database import engine; from sqlalchemy import inspect; i=inspect(engine); print('auth_policy' in i.get_table_names()); print('pin_hash' in [c['name'] for c in i.get_columns('users')])"`
Expected: `True` and `True`.

- [ ] **Step 10: Commit**

```bash
git add backend/app/models/user.py backend/app/models/auth_policy.py backend/app/models/__init__.py backend/alembic/versions/ backend/tests/models/test_pin_columns.py
git commit -m "feat(auth): pin columns on users + auth_policy singleton + migration"
```

---

## Task 2: PIN policy validator + PIN schemas

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Test: `backend/tests/schemas/test_pin_validator.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/schemas/test_pin_validator.py`:

```python
import pytest
from pydantic import ValidationError
from app.schemas.auth import PinSetRequest


@pytest.mark.parametrize("pin", ["4827", "13905", "90218746"])
def test_valid_pins(pin):
    req = PinSetRequest(pin=pin, code="123456")
    assert req.pin == pin


@pytest.mark.parametrize("pin", [
    "0000", "1111", "9999",     # all-same
    "1234", "2345", "5678",     # ascending
    "4321", "9876",             # descending
    "123",                       # too short
    "123456789",                 # too long
    "12a4", "ab12",              # non-digit
])
def test_invalid_pins(pin):
    with pytest.raises(ValidationError):
        PinSetRequest(pin=pin, code="123456")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/schemas/test_pin_validator.py -v --no-cov`
Expected: FAIL — `ImportError: cannot import name 'PinSetRequest'`.

- [ ] **Step 3: Add the validator + schemas**

In `backend/app/schemas/auth.py`, append at the end of the file (`re` and `field_validator` are already imported):

```python


# --- PIN login schemas ---

def _validate_pin(v: str) -> str:
    """PIN policy: 4–8 digits, no all-same, no strictly sequential pattern."""
    if not re.fullmatch(r"\d{4,8}", v):
        raise ValueError("PIN must be 4 to 8 digits")
    if len(set(v)) == 1:
        raise ValueError("PIN must not be all the same digit")
    digits = [int(c) for c in v]
    ascending = all(digits[i + 1] - digits[i] == 1 for i in range(len(digits) - 1))
    descending = all(digits[i] - digits[i + 1] == 1 for i in range(len(digits) - 1))
    if ascending or descending:
        raise ValueError("PIN must not be a sequential pattern")
    return v


class PinLoginRequest(BaseModel):
    username: str
    pin: str


class PinSetRequest(BaseModel):
    pin: str
    code: str  # fresh TOTP or backup code

    @field_validator("pin")
    @classmethod
    def _validate(cls, v: str) -> str:
        return _validate_pin(v)


class PinRemoveRequest(BaseModel):
    code: str  # fresh TOTP or backup code


class PinStatusResponse(BaseModel):
    pin_enabled: bool
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/schemas/test_pin_validator.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/auth.py backend/tests/schemas/test_pin_validator.py
git commit -m "feat(auth): PIN policy validator + PIN schemas"
```

---

## Task 3: PIN service + clear-PIN-on-2FA-disable

**Files:**
- Create: `backend/app/services/pin_service.py`
- Modify: `backend/app/services/totp_service.py`
- Test: `backend/tests/services/test_pin_service.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/services/test_pin_service.py`:

```python
from datetime import datetime, timezone, timedelta

from app.models.user import User
from app.services import pin_service, totp_service


def _user(db):
    u = User(username="pinuser", hashed_password="x", role="user", totp_enabled=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_hash_and_verify(db_session):
    u = _user(db_session)
    pin_service.set_pin(db_session, u, "4827")
    assert u.pin_hash and u.pin_hash != "4827"
    assert pin_service.verify_pin("4827", u.pin_hash) is True
    assert pin_service.verify_pin("4828", u.pin_hash) is False


def test_grace_window(db_session):
    u = _user(db_session)
    assert pin_service.in_grace_window(u) is False
    u.pin_grace_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    assert pin_service.in_grace_window(u) is True
    u.pin_grace_until = datetime.now(timezone.utc) - timedelta(minutes=5)
    assert pin_service.in_grace_window(u) is False


def test_lockout_after_5_failures(db_session):
    u = _user(db_session)
    for _ in range(5):
        pin_service.register_pin_failure(db_session, u)
    assert pin_service.is_pin_locked(u) is True
    assert u.pin_failed_attempts == 0  # reset when lock applied


def test_reset_failures(db_session):
    u = _user(db_session)
    pin_service.register_pin_failure(db_session, u)
    pin_service.reset_pin_failures(db_session, u)
    assert u.pin_failed_attempts == 0
    assert u.pin_locked_until is None


def test_disable_2fa_clears_pin(db_session):
    u = _user(db_session)
    pin_service.set_pin(db_session, u, "4827")
    u.pin_grace_until = datetime.now(timezone.utc) + timedelta(hours=1)
    db_session.commit()
    totp_service.disable(db_session, u.id)
    db_session.refresh(u)
    assert u.pin_hash is None
    assert u.pin_grace_until is None
    assert u.totp_enabled is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_pin_service.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: app.services.pin_service`.

- [ ] **Step 3: Create `pin_service.py`**

Create `backend/app/services/pin_service.py`:

```python
"""PIN credential service for the Tauri local-channel login.

PINs are hashed with the same bcrypt context as passwords. SQLite returns
naive datetimes, so timestamps are coerced to UTC before comparison.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.users import pwd_context

PIN_MAX_FAILED = 5
PIN_LOCK_MINUTES = 15


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def hash_pin(pin: str) -> str:
    return pwd_context.hash(pin)


def verify_pin(pin: str, pin_hash: str) -> bool:
    return pwd_context.verify(pin, pin_hash)


def in_grace_window(user: User, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    until = _as_utc(user.pin_grace_until)
    return until is not None and until > now


def is_pin_locked(user: User, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    until = _as_utc(user.pin_locked_until)
    return until is not None and until > now


def register_pin_failure(db: Session, user: User) -> None:
    user.pin_failed_attempts = (user.pin_failed_attempts or 0) + 1
    if user.pin_failed_attempts >= PIN_MAX_FAILED:
        user.pin_locked_until = datetime.now(timezone.utc) + timedelta(minutes=PIN_LOCK_MINUTES)
        user.pin_failed_attempts = 0
    db.commit()


def reset_pin_failures(db: Session, user: User) -> None:
    if user.pin_failed_attempts or user.pin_locked_until:
        user.pin_failed_attempts = 0
        user.pin_locked_until = None
        db.commit()


def set_pin(db: Session, user: User, pin: str) -> None:
    user.pin_hash = hash_pin(pin)
    user.pin_failed_attempts = 0
    user.pin_locked_until = None
    db.commit()


def clear_pin(db: Session, user: User) -> None:
    user.pin_hash = None
    user.pin_grace_until = None
    user.pin_failed_attempts = 0
    user.pin_locked_until = None
    db.commit()
```

- [ ] **Step 4: Clear the PIN when 2FA is disabled**

In `backend/app/services/totp_service.py`, in `disable(...)`, replace the body assignment block
(the four `user.totp_* = None/False` lines followed by `db.commit()`) with:

```python
    user.totp_secret_encrypted = None
    user.totp_enabled = False
    user.totp_backup_codes_encrypted = None
    user.totp_enabled_at = None
    # PIN login is anchored on 2FA — disabling 2FA must destroy the PIN.
    user.pin_hash = None
    user.pin_grace_until = None
    user.pin_failed_attempts = 0
    user.pin_locked_until = None
    db.commit()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/services/test_pin_service.py -v --no-cov`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/pin_service.py backend/app/services/totp_service.py backend/tests/services/test_pin_service.py
git commit -m "feat(auth): pin_service (hash/grace/lockout) + clear PIN on 2FA disable"
```

---

## Task 4: AuthPolicy service, schemas & admin endpoints

**Files:**
- Create: `backend/app/services/auth_policy.py`
- Create: `backend/app/schemas/auth_policy.py`
- Create: `backend/app/api/routes/auth_policy.py`
- Modify: `backend/app/api/routes/__init__.py`
- Test: `backend/tests/api/test_auth_policy.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/api/test_auth_policy.py`:

```python
from app.core.config import settings

URL = f"{settings.api_prefix}/admin/auth-policy"


def test_get_returns_defaults(client, admin_headers):
    r = client.get(URL, headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["pin_login_enabled"] is True
    assert body["pin_grace_window_seconds"] == 86400


def test_put_updates(client, admin_headers):
    r = client.put(URL, headers=admin_headers, json={"pin_grace_window_seconds": 3600, "pin_login_enabled": False})
    assert r.status_code == 200
    assert r.json()["pin_grace_window_seconds"] == 3600
    assert r.json()["pin_login_enabled"] is False


def test_put_rejects_over_cap(client, admin_headers):
    r = client.put(URL, headers=admin_headers, json={"pin_grace_window_seconds": 999999999})
    assert r.status_code == 422


def test_put_rejects_under_min(client, admin_headers):
    r = client.put(URL, headers=admin_headers, json={"pin_grace_window_seconds": 10})
    assert r.status_code == 422


def test_requires_admin(client, user_headers):
    assert client.get(URL, headers=user_headers).status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_auth_policy.py -v --no-cov`
Expected: FAIL — 404 (route not registered).

- [ ] **Step 3: Create the policy service**

Create `backend/app/services/auth_policy.py`:

```python
"""Read-or-create the singleton AuthPolicy row (id=1)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth_policy import AuthPolicy


def get_auth_policy(db: Session) -> AuthPolicy:
    policy = db.execute(select(AuthPolicy).where(AuthPolicy.id == 1)).scalar_one_or_none()
    if policy is None:
        policy = AuthPolicy(id=1)
        db.add(policy)
        db.commit()
        db.refresh(policy)
    return policy
```

- [ ] **Step 4: Create the policy schemas**

Create `backend/app/schemas/auth_policy.py`:

```python
from pydantic import BaseModel, Field

MIN_WINDOW_SECONDS = 60
MAX_WINDOW_SECONDS = 604800  # 7 days


class AuthPolicyResponse(BaseModel):
    pin_login_enabled: bool
    pin_grace_window_seconds: int


class AuthPolicyUpdate(BaseModel):
    pin_login_enabled: bool | None = None
    pin_grace_window_seconds: int | None = Field(
        default=None, ge=MIN_WINDOW_SECONDS, le=MAX_WINDOW_SECONDS
    )
```

- [ ] **Step 5: Create the admin policy router**

Create `backend/app/api/routes/auth_policy.py`:

```python
"""Admin endpoints for the system-wide auth policy."""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.auth_policy import AuthPolicyResponse, AuthPolicyUpdate
from app.services.auth_policy import get_auth_policy
from app.services.audit.logger_db import get_audit_logger_db

router = APIRouter()


def _to_response(p) -> AuthPolicyResponse:
    return AuthPolicyResponse(
        pin_login_enabled=p.pin_login_enabled,
        pin_grace_window_seconds=p.pin_grace_window_seconds,
    )


@router.get("", response_model=AuthPolicyResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def read_auth_policy(
    request: Request, response: Response,
    current_user=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> AuthPolicyResponse:
    return _to_response(get_auth_policy(db))


@router.put("", response_model=AuthPolicyResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_auth_policy(
    body: AuthPolicyUpdate,
    request: Request, response: Response,
    current_user=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> AuthPolicyResponse:
    policy = get_auth_policy(db)
    data = body.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None:
            setattr(policy, field, value)
    db.commit()
    db.refresh(policy)
    get_audit_logger_db().log_security_event(
        action="auth_policy_updated", user=current_user.username,
        details=data, success=True, db=db,
    )
    return _to_response(policy)
```

- [ ] **Step 6: Register the router**

In `backend/app/api/routes/__init__.py`:

1. Add `auth_policy` to the `from app.api.routes import (...)` import tuple (e.g. on the line with `setup,`/`games,` — just add `auth_policy,`).
2. Register it next to the other `/admin` router. After the existing line
   `api_router.include_router(rate_limit_config.router, prefix="/admin", tags=["admin"])` add:

```python
api_router.include_router(auth_policy.router, prefix="/admin/auth-policy", tags=["auth-policy"])
```

The aggregator is `api_router` (an `APIRouter()`), exactly like every other route module.

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/api/test_auth_policy.py -v --no-cov`
Expected: PASS (5 tests).

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/auth_policy.py backend/app/schemas/auth_policy.py backend/app/api/routes/auth_policy.py backend/app/api/routes/__init__.py backend/tests/api/test_auth_policy.py
git commit -m "feat(auth): admin auth-policy endpoints (pin window + kill switch)"
```

---

## Task 5: PIN management endpoints (GET/POST/DELETE /pin)

**Files:**
- Modify: `backend/app/api/routes/auth.py`
- Modify: `backend/app/core/rate_limiter.py`
- Test: `backend/tests/api/test_pin_management.py`

- [ ] **Step 1: Add the rate-limit key**

In `backend/app/core/rate_limiter.py`, in the `RATE_LIMITS` dict, immediately after the
`"auth_2fa_setup": "5/minute",` line:

```python
    "auth_pin_login": "5/minute",
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/api/test_pin_management.py`:

```python
import pyotp
from app.core.config import settings
from app.models.user import User
from app.services import totp_service

PIN_URL = f"{settings.api_prefix}/auth/pin"


def _enable_2fa(db_session, username) -> str:
    """Enable 2FA for a user, return the plain secret."""
    user = db_session.query(User).filter(User.username == username).first()
    setup = totp_service.generate_setup(user)
    secret = setup["secret"]
    totp_service.verify_and_enable(db_session, user.id, secret, pyotp.TOTP(secret).now())
    return secret


def test_status_false_then_true(client, admin_headers, db_session):
    secret = _enable_2fa(db_session, settings.admin_username)
    assert client.get(PIN_URL, headers=admin_headers).json()["pin_enabled"] is False
    r = client.post(PIN_URL, headers=admin_headers, json={"pin": "4827", "code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200
    assert client.get(PIN_URL, headers=admin_headers).json()["pin_enabled"] is True


def test_set_pin_requires_2fa_enabled(client, admin_headers):
    r = client.post(PIN_URL, headers=admin_headers, json={"pin": "4827", "code": "000000"})
    assert r.status_code == 400


def test_set_pin_rejects_bad_totp(client, admin_headers, db_session):
    _enable_2fa(db_session, settings.admin_username)
    r = client.post(PIN_URL, headers=admin_headers, json={"pin": "4827", "code": "000000"})
    assert r.status_code == 401


def test_remove_pin(client, admin_headers, db_session):
    secret = _enable_2fa(db_session, settings.admin_username)
    client.post(PIN_URL, headers=admin_headers, json={"pin": "4827", "code": pyotp.TOTP(secret).now()})
    r = client.request("DELETE", PIN_URL, headers=admin_headers, json={"code": pyotp.TOTP(secret).now()})
    assert r.status_code == 200
    assert client.get(PIN_URL, headers=admin_headers).json()["pin_enabled"] is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/api/test_pin_management.py -v --no-cov`
Expected: FAIL — 404/405 (routes missing).

- [ ] **Step 4: Add the PIN-schema imports to `auth.py`**

In `backend/app/api/routes/auth.py`, extend the `from app.schemas.auth import (...)` block to also import:

```python
    PinLoginRequest, PinSetRequest, PinRemoveRequest, PinStatusResponse,
```

- [ ] **Step 5: Add the three PIN-management endpoints**

In `backend/app/api/routes/auth.py`, immediately after the `get_2fa_status` endpoint (after its
`return TwoFactorStatusResponse(...)` block, before `regenerate_backup_codes`), add:

```python
@router.get("/pin", response_model=PinStatusResponse)
@user_limiter.limit(get_limit("user_operations"))
async def get_pin_status(
    request: Request, response: Response,
    current_user=Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> PinStatusResponse:
    """Whether the current user has a desktop-app PIN configured."""
    user_record = db.query(UserModel).filter(UserModel.id == current_user.id).first()
    return PinStatusResponse(pin_enabled=bool(user_record and user_record.pin_hash))


def _verify_fresh_totp(db: Session, user_id: int, code: str) -> bool:
    """Verify a fresh TOTP or backup code for a PIN-management action."""
    try:
        if totp_service.verify_code(db, user_id, code):
            return True
    except ValueError:
        pass
    try:
        return totp_service.verify_backup_code(db, user_id, code)
    except ValueError:
        return False


@router.post("/pin")
@limiter.limit(get_limit("auth_2fa_setup"))
async def set_pin(
    payload: PinSetRequest,
    request: Request, response: Response,
    current_user=Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    """Set/replace the desktop-app PIN. Requires 2FA enabled + a fresh TOTP code."""
    from app.services import pin_service
    audit_logger = get_audit_logger_db()
    user_record = db.query(UserModel).filter(UserModel.id == current_user.id).first()
    if not user_record or not user_record.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA must be enabled before setting a PIN")
    if not _verify_fresh_totp(db, current_user.id, payload.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid 2FA code")
    pin_service.set_pin(db, user_record, payload.pin)
    audit_logger.log_security_event(action="pin_set", user=current_user.username, success=True, db=db)
    return {"message": "PIN set"}


@router.delete("/pin")
@limiter.limit(get_limit("auth_2fa_setup"))
async def remove_pin(
    payload: PinRemoveRequest,
    request: Request, response: Response,
    current_user=Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    """Remove the desktop-app PIN. Requires a fresh TOTP code."""
    from app.services import pin_service
    audit_logger = get_audit_logger_db()
    user_record = db.query(UserModel).filter(UserModel.id == current_user.id).first()
    if not user_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not _verify_fresh_totp(db, current_user.id, payload.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid 2FA code")
    pin_service.clear_pin(db, user_record)
    audit_logger.log_security_event(action="pin_removed", user=current_user.username, success=True, db=db)
    return {"message": "PIN removed"}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_pin_management.py -v --no-cov`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/auth.py backend/app/core/rate_limiter.py backend/tests/api/test_pin_management.py
git commit -m "feat(auth): PIN management endpoints (status/set/remove, TOTP-gated)"
```

---

## Task 6: login-pin endpoint + verify-2fa grace window

**Files:**
- Modify: `backend/app/api/routes/auth.py`
- Test: `backend/tests/api/test_pin_login.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/api/test_pin_login.py`:

```python
from datetime import datetime, timezone, timedelta

import pyotp
from app.core.config import settings
from app.models.user import User
from app.services import totp_service, pin_service

LOGIN_PIN = f"{settings.api_prefix}/auth/login-pin"
VERIFY = f"{settings.api_prefix}/auth/verify-2fa"


def _user_with_pin(db_session, username=None):
    username = username or settings.admin_username
    user = db_session.query(User).filter(User.username == username).first()
    setup = totp_service.generate_setup(user)
    secret = setup["secret"]
    totp_service.verify_and_enable(db_session, user.id, secret, pyotp.TOTP(secret).now())
    pin_service.set_pin(db_session, user, "4827")
    return user, secret


def test_login_pin_within_window_returns_token(client, admin_user, db_session):
    user, _ = _user_with_pin(db_session)
    user.pin_grace_until = datetime.now(timezone.utc) + timedelta(hours=1)
    db_session.commit()
    r = client.post(LOGIN_PIN, json={"username": user.username, "pin": "4827"})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_pin_expired_window_requires_2fa(client, admin_user, db_session):
    user, secret = _user_with_pin(db_session)
    user.pin_grace_until = None
    db_session.commit()
    r = client.post(LOGIN_PIN, json={"username": user.username, "pin": "4827"})
    assert r.status_code == 200
    assert r.json().get("requires_2fa") is True
    pending = r.json()["pending_token"]
    # Completing TOTP returns a token AND opens the window
    v = client.post(VERIFY, json={"pending_token": pending, "code": pyotp.TOTP(secret).now()})
    assert v.status_code == 200 and "access_token" in v.json()
    db_session.refresh(user)
    assert pin_service.in_grace_window(user) is True


def test_login_pin_wrong_pin_401(client, admin_user, db_session):
    user, _ = _user_with_pin(db_session)
    r = client.post(LOGIN_PIN, json={"username": user.username, "pin": "9999"})
    assert r.status_code == 401


def test_login_pin_no_pin_set_401(client, admin_user, db_session):
    r = client.post(LOGIN_PIN, json={"username": settings.admin_username, "pin": "4827"})
    assert r.status_code == 401


def test_login_pin_lockout(client, admin_user, db_session):
    user, _ = _user_with_pin(db_session)
    user.pin_grace_until = datetime.now(timezone.utc) + timedelta(hours=1)
    db_session.commit()
    for _ in range(5):
        client.post(LOGIN_PIN, json={"username": user.username, "pin": "9999"})
    # Even the correct PIN is now refused (locked)
    r = client.post(LOGIN_PIN, json={"username": user.username, "pin": "4827"})
    assert r.status_code == 401


def test_login_pin_disabled_by_policy(client, admin_user, db_session):
    from app.services.auth_policy import get_auth_policy
    user, _ = _user_with_pin(db_session)
    user.pin_grace_until = datetime.now(timezone.utc) + timedelta(hours=1)
    get_auth_policy(db_session).pin_login_enabled = False
    db_session.commit()
    r = client.post(LOGIN_PIN, json={"username": user.username, "pin": "4827"})
    assert r.status_code == 401


def test_login_pin_remote_channel_forbidden(remote_client, admin_user, db_session):
    user, _ = _user_with_pin(db_session)
    user.pin_grace_until = datetime.now(timezone.utc) + timedelta(hours=1)
    db_session.commit()
    r = remote_client.post(LOGIN_PIN, json={"username": user.username, "pin": "4827"})
    assert r.status_code == 403
```

> Note: the default `client` fixture runs `channel=local` (PIN login allowed). `remote_client`
> monkeypatches `settings.channel="remote"`, which `ChannelMarkerMiddleware` reads **per-request**
> via its channel-provider callable — so it flips `request.state.channel` with no re-wiring needed.
> Working example to mirror: `backend/tests/api/test_power_authority_routes.py::test_put_authority_requires_local_channel`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/api/test_pin_login.py -v --no-cov`
Expected: FAIL — 404 (`/login-pin` missing) and the grace-window assertion in the verify test.

- [ ] **Step 3: Extend `verify_2fa` to open the grace window**

In `backend/app/api/routes/auth.py`, in `verify_2fa`, immediately **before** the
`token = auth_service.create_access_token(user_record)` line (the one inside `verify_2fa`, after the
successful-2FA audit logs), add:

```python
    # Open the PIN grace window from this successful TOTP (only when a PIN exists).
    if user_record.pin_hash:
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        from app.services.auth_policy import get_auth_policy
        window = get_auth_policy(db).pin_grace_window_seconds
        user_record.pin_grace_until = _dt.now(_tz.utc) + _td(seconds=window)
        db.commit()
```

- [ ] **Step 4: Add the `login-pin` endpoint**

In `backend/app/api/routes/auth.py`, immediately after the `verify_2fa` endpoint (before
`setup_2fa`), add:

```python
@router.post("/login-pin")
@limiter.limit(get_limit("auth_pin_login"))
async def login_pin(payload: PinLoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """PIN login — LOCAL CHANNEL ONLY.

    Returns an access token when within the grace window, otherwise a
    TwoFactorRequiredResponse (the client completes it via /verify-2fa).
    """
    from app.services import pin_service
    from app.services.auth_policy import get_auth_policy
    audit_logger = get_audit_logger_db()
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    # Hard invariant: PIN login is only valid over the local channel.
    if getattr(request.state, "channel", "remote") != "local":
        audit_logger.log_security_event(
            action="pin_login_remote_denied", user=payload.username,
            details={"ip_address": ip_address}, success=False, db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "local_channel_required",
                "message": "PIN login is only available from the BaluHost Companion app on the server.",
            },
        )

    if not get_auth_policy(db).pin_login_enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="PIN login is disabled")

    user_record = user_service.get_user_by_username(payload.username, db=db)
    # Generic failure — never reveal which precondition failed (no enumeration).
    if not user_record or not user_record.pin_hash or not user_record.totp_enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if pin_service.is_pin_locked(user_record):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="PIN locked — use your password")

    if not pin_service.verify_pin(payload.pin, user_record.pin_hash):
        pin_service.register_pin_failure(db, user_record)
        audit_logger.log_security_event(
            action="pin_login_failed", user=user_record.username,
            details={"ip_address": ip_address}, success=False, db=db,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    pin_service.reset_pin_failures(db, user_record)

    # Within the grace window → PIN alone suffices.
    if pin_service.in_grace_window(user_record):
        audit_logger.log_authentication_attempt(
            username=user_record.username, success=True,
            ip_address=ip_address, user_agent=user_agent, db=db,
        )
        audit_logger.log_security_event(
            action="pin_login_grace", user=user_record.username,
            details={"ip_address": ip_address}, success=True, db=db,
        )
        token = auth_service.create_access_token(user_record)
        return TokenResponse(access_token=token, user=user_service.serialize_user(user_record))

    # Window expired → require TOTP via the existing pending flow.
    pending_token = security.create_2fa_pending_token(user_record.id)
    audit_logger.log_security_event(
        action="pin_login_2fa_required", user=user_record.username,
        details={"ip_address": ip_address}, success=True, db=db,
    )
    return TwoFactorRequiredResponse(pending_token=pending_token)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_pin_login.py -v --no-cov`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/auth.py backend/tests/api/test_pin_login.py
git commit -m "feat(auth): local-channel login-pin + grace window on verify-2fa"
```

---

## Task 7: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Run all new PIN/auth tests**

Run: `cd backend && python -m pytest tests/models/test_pin_columns.py tests/schemas/test_pin_validator.py tests/services/test_pin_service.py tests/api/test_auth_policy.py tests/api/test_pin_management.py tests/api/test_pin_login.py -v --no-cov`
Expected: PASS (all).

- [ ] **Step 2: Run the existing auth/2FA suites (no regression)**

Run: `cd backend && python -m pytest tests/api/test_2fa_endpoints.py tests/security/test_totp_2fa.py tests/auth -q --no-cov`
Expected: PASS (all previously-passing tests still pass — especially that disabling 2FA still works).

- [ ] **Step 3: No commit** (verification only).

---

## Notes for the implementer

- **Channel in tests:** the default `client` fixture is `channel=local`, so `login-pin` is allowed; `remote_client` is the canonical remote simulation (see Task 6 note + `test_require_local_admin.py`).
- **SQLite naive datetimes:** `pin_service._as_utc()` coerces stored timestamps before comparison — do not drop it; without it the grace/lock comparisons raise on SQLite.
- **Migration head:** set `down_revision` to the real `alembic heads` output (not a stale dev-DB head) — this repo has hit multi-head prod failures before.
- **Frontend is Plan 2:** Tauri login option (username + PIN, then TOTP if challenged), `DesktopPinSettings` (set/remove with TOTP, only when 2FA on), `AuthPolicySettings` (admin), and i18n consume these endpoints.
```
