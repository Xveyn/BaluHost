# Password Recovery Codes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A LAN-only, self-service "forgot password" flow using single-use recovery codes, mirroring the 2FA backup-code mechanism, hardened per a three-agent critical review.

**Architecture:** A new encrypted column on `User` stores Fernet-encrypted SHA-256 hashes of recovery codes. A shared `app/core/crypto.py` provides public at-rest encrypt/decrypt (TOTP delegates to it). A `recovery_code_service` generates/verifies/consumes codes with timing equalization. Three new `auth` endpoints: generate (session + **step-up auth**) and status (session), both bound to the caller's own account; and a **pre-auth, LAN-gated** reset (`is_private_or_local_ip`) that sets a new password, **revokes the user's refresh tokens**, and issues **no token**. Frontend adds a "Passwort vergessen?" form and a recovery-codes settings card.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, slowapi, `cryptography` Fernet, pytest; React 18 + TypeScript, axios, Vitest, react-hot-toast, i18next.

## Global Constraints

- **Reset LAN gate:** `is_private_or_local_ip(request.client.host)` from `app.core.network_utils` (NOT `request.state.channel` — that's a same-host-UDS signal, hardwired `remote` in prod). Valid because uvicorn runs `--proxy-headers --forwarded-allow-ips=127.0.0.1` (`backend/tests/test_deploy_proxy_headers.py`), so `request.client.host` is the real, unspoofable client IP. Failure → `403 {"error":"local_network_required","message":...}`, audit-logged.
- **Reset issues NO token.** It only resets the password (2FA preserved at next login) and revokes the user's refresh tokens (`TokenService.revoke_all_user_tokens`).
- **Generation requires step-up:** if `user.totp_enabled` → fresh TOTP/backup code via `_verify_fresh_totp(db, user_id, code)`; else → `current_password` re-verified via `auth_service.authenticate_user(username, password, db=db)`. Failure → 401.
- **Codes hashed THEN encrypted at rest** via `app/core/crypto.encrypt_at_rest`/`decrypt_at_rest`. Never store/log plaintext. `RECOVERY_CODE_COUNT=10`, `secrets.token_hex(5).upper()` (40 bits).
- **RBAC:** management endpoints use `Depends(deps.get_current_user)`, act only on `current_user.id`.
- **Password strength:** `new_password` via `_validate_password_strength` field_validator (422 before handler → no code consumed). Bound attacker fields: `username` ≤ 64, `recovery_code` ≤ 32.
- **Anti-enumeration + timing:** unknown user, `is_active=false` user, and wrong code all return identical `401 "Invalid username or recovery code"`; unknown/disabled paths run a dummy decrypt+hash to equalize timing.
- **Alembic head pitfall:** `down_revision` = real `alembic heads` output.
- **Windows CRLF repo:** the `LF will be replaced by CRLF` commit warning is expected.
- **Vitest collects only `client/src/__tests__/**`** (`vite.config.ts` include glob).
- **Spec:** `docs/superpowers/specs/2026-06-29-password-recovery-codes-design.md`.

## Verified anchors (from review)

- `users.get_user_by_username(username, db=)`:164, `update_user_password(user_id, new_password, db=)`:265, `create_user(UserCreate(...), db=)`:170. `UserCreate(username, email, password, role)`.
- `auth_service.authenticate_user(username, password, db=)` (used by `change_password`).
- `auth.py` already imports: `Depends, HTTPException, Request, Response, status, get_db, limiter, get_limit, auth_service, user_service, UserModel, get_audit_logger_db, deps, totp_service`. `_verify_fresh_totp(db, user_id, code)` defined at `auth.py:441`. `from app.schemas.auth import (...)` block at `auth.py:8-16`.
- `TokenService.revoke_all_user_tokens(db, user_id, reason=)`:132 (`from app.services.token_service import token_service`).
- `samba_service.sync_smb_password(username, plaintext_password)` async:99.
- `network_utils.is_private_or_local_ip(ip)`:6.
- conftest: `client` (channel=local), `user_headers` → `testuser`/`Testpass123!`, `admin_headers`, `db_session`. `_validate_password_strength` in `schemas/auth.py:15`.
- Frontend: `apiClient`/`buildApiUrl` in `lib/api.ts`; `<TwoFactorCard>` rendered in `client/src/pages/SettingsPage.tsx`; `Login.tsx` form nests `twoFactorRequired ? … : (pinMode ? … : <form onSubmit={handleSubmit}>)`; `toast` from `react-hot-toast`.

---

### Task 1: User model column + migration

**Files:** Modify `backend/app/models/user.py` (after line 52); Create `backend/alembic/versions/<rev>_add_password_recovery_codes.py`; Test `backend/tests/services/test_recovery_code_service.py`.

**Produces:** `User.password_recovery_codes_encrypted: Mapped[Optional[str]]` (Text, nullable).

- [ ] **Step 1: Failing test** — create `backend/tests/services/test_recovery_code_service.py`:

```python
"""Tests for password recovery codes (column + service)."""
from app.models.user import User


def test_user_has_recovery_codes_column():
    u = User(username="x", hashed_password="h", role="user")
    assert hasattr(u, "password_recovery_codes_encrypted")
    assert u.password_recovery_codes_encrypted is None
```

- [ ] **Step 2: Run → fail.** `cd backend && python -m pytest tests/services/test_recovery_code_service.py::test_user_has_recovery_codes_column -v --no-cov` → `AttributeError`.

- [ ] **Step 3: Add the column.** In `backend/app/models/user.py`, after the `totp_enabled_at` column (line 52):

```python

    # Password recovery codes (self-service forgot-password, LAN-only reset).
    # Fernet-encrypted JSON array of SHA-256 hashes; None = not configured.
    password_recovery_codes_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

(`Text` and `Optional` are already imported.)

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Migration.** `cd backend && alembic heads` (note `<HEAD>`). `cd backend && alembic revision -m "add password_recovery_codes_encrypted to users"`. Edit the new file: `down_revision = "<HEAD>"`, body:

```python
def upgrade() -> None:
    op.add_column("users", sa.Column("password_recovery_codes_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_recovery_codes_encrypted")
```

- [ ] **Step 6: Reversible.** `cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head` → no errors.

- [ ] **Step 7: Commit.** `git add backend/app/models/user.py backend/alembic/versions/ backend/tests/services/test_recovery_code_service.py && git commit -m "feat(auth): add password_recovery_codes_encrypted column + migration"`

---

### Task 2: Shared at-rest crypto helper

**Files:** Create `backend/app/core/crypto.py`; Modify `backend/app/services/totp_service.py:29-54`; Test `backend/tests/core/test_crypto_at_rest.py`.

**Interfaces — Produces:** `get_at_rest_fernet() -> MultiFernet`, `encrypt_at_rest(str) -> str`, `decrypt_at_rest(str) -> str`.

- [ ] **Step 1: Failing test** — create `backend/tests/core/test_crypto_at_rest.py`:

```python
from app.core import crypto


def test_round_trip():
    ct = crypto.encrypt_at_rest("hello")
    assert ct != "hello"
    assert crypto.decrypt_at_rest(ct) == "hello"


def test_totp_helpers_delegate_and_interop():
    # Data written via totp helpers must decrypt via the shared helper and vice versa.
    from app.services import totp_service
    ct = totp_service._totp_encrypt("x")
    assert crypto.decrypt_at_rest(ct) == "x"
    ct2 = crypto.encrypt_at_rest("y")
    assert totp_service._totp_decrypt(ct2) == "y"
```

- [ ] **Step 2: Run → fail.** `cd backend && python -m pytest tests/core/test_crypto_at_rest.py -v --no-cov` → `ModuleNotFoundError: app.core.crypto`.

- [ ] **Step 3: Create `backend/app/core/crypto.py`** (logic lifted verbatim from `totp_service._get_totp_fernet`):

```python
"""Shared at-rest encryption (Fernet/MultiFernet).

Single seam for encrypting secrets at rest. Encrypts with TOTP_ENCRYPTION_KEY
when set (else VPN_ENCRYPTION_KEY); decrypts by trying the dedicated key first,
then the VPN key (dual-key fallback). A future RECOVERY_CODES_ENCRYPTION_KEY can
be added here without touching consumers.
"""
from cryptography.fernet import Fernet, MultiFernet


def get_at_rest_fernet() -> MultiFernet:
    from app.core.config import settings
    keys: list[Fernet] = []
    if settings.totp_encryption_key:
        keys.append(Fernet(settings.totp_encryption_key.encode()))
    if settings.vpn_encryption_key:
        keys.append(Fernet(settings.vpn_encryption_key.encode()))
    if not keys:
        raise ValueError("No encryption key configured (set TOTP_ENCRYPTION_KEY or VPN_ENCRYPTION_KEY)")
    return MultiFernet(keys)


def encrypt_at_rest(plaintext: str) -> str:
    return get_at_rest_fernet().encrypt(plaintext.encode()).decode()


def decrypt_at_rest(ciphertext: str) -> str:
    return get_at_rest_fernet().decrypt(ciphertext.encode()).decode()
```

- [ ] **Step 4: Delegate the TOTP helpers.** In `backend/app/services/totp_service.py`, replace the bodies of `_get_totp_fernet`/`_totp_encrypt`/`_totp_decrypt` (lines 29-54) with delegations (keep the names — existing imports/tests unchanged):

```python
def _get_totp_fernet():
    from app.core.crypto import get_at_rest_fernet
    return get_at_rest_fernet()


def _totp_encrypt(plaintext: str) -> str:
    from app.core.crypto import encrypt_at_rest
    return encrypt_at_rest(plaintext)


def _totp_decrypt(ciphertext: str) -> str:
    from app.core.crypto import decrypt_at_rest
    return decrypt_at_rest(ciphertext)
```

- [ ] **Step 5: Run → pass + no 2FA regression.** `cd backend && python -m pytest tests/core/test_crypto_at_rest.py tests/security/test_totp_2fa.py -q --no-cov` → PASS (all).

- [ ] **Step 6: Commit.** `git add backend/app/core/crypto.py backend/app/services/totp_service.py backend/tests/core/test_crypto_at_rest.py && git commit -m "refactor(core): shared at-rest crypto helper; totp delegates to it"`

---

### Task 3: `recovery_code_service`

**Files:** Create `backend/app/services/recovery_code_service.py`; Test append to `backend/tests/services/test_recovery_code_service.py`.

**Interfaces — Consumes:** `User.password_recovery_codes_encrypted`, `core.crypto`, `users.get_user_by_username`. **Produces:** `RECOVERY_CODE_COUNT=10`, `generate_recovery_codes(db,user_id)->list[str]`, `verify_and_consume_recovery_code(db,user_id,code)->bool`, `verify_and_consume_for_username(db,username,code)->User|None`, `get_recovery_codes_remaining(db,user_id)->int`, `has_recovery_codes(db,user_id)->bool`.

- [ ] **Step 1: Failing tests** — append:

```python
import pytest
from app.services import recovery_code_service as rcs


@pytest.fixture
def a_user(db_session):
    from app.services import users as user_service
    from app.schemas.user import UserCreate
    return user_service.create_user(
        UserCreate(username="recov", email="r@example.com", password="StrongPass9x", role="user"),
        db=db_session,
    )


def test_generate_returns_ten_codes(db_session, a_user):
    codes = rcs.generate_recovery_codes(db_session, a_user.id)
    assert len(codes) == rcs.RECOVERY_CODE_COUNT
    assert rcs.has_recovery_codes(db_session, a_user.id) is True
    assert rcs.get_recovery_codes_remaining(db_session, a_user.id) == 10


def test_code_is_single_use(db_session, a_user):
    codes = rcs.generate_recovery_codes(db_session, a_user.id)
    assert rcs.verify_and_consume_recovery_code(db_session, a_user.id, codes[0]) is True
    assert rcs.verify_and_consume_recovery_code(db_session, a_user.id, codes[0]) is False
    assert rcs.get_recovery_codes_remaining(db_session, a_user.id) == 9


def test_regenerate_invalidates_old(db_session, a_user):
    old = rcs.generate_recovery_codes(db_session, a_user.id)
    new = rcs.generate_recovery_codes(db_session, a_user.id)
    assert rcs.verify_and_consume_recovery_code(db_session, a_user.id, old[0]) is False
    assert rcs.verify_and_consume_recovery_code(db_session, a_user.id, new[0]) is True


def test_verify_for_username_success_and_misses(db_session, a_user):
    codes = rcs.generate_recovery_codes(db_session, a_user.id)
    assert rcs.verify_and_consume_for_username(db_session, "recov", codes[0]) is not None
    # consumed
    assert rcs.verify_and_consume_for_username(db_session, "recov", codes[0]) is None
    # unknown user → None (no raise)
    assert rcs.verify_and_consume_for_username(db_session, "ghost", "AAAA111122") is None


def test_verify_for_username_disabled_user(db_session, a_user):
    rcs.generate_recovery_codes(db_session, a_user.id)
    a_user.is_active = False
    db_session.commit()
    codes = rcs.generate_recovery_codes(db_session, a_user.id)  # still generatable directly
    assert rcs.verify_and_consume_for_username(db_session, "recov", codes[0]) is None
```

- [ ] **Step 2: Run → fail.** `ModuleNotFoundError`.

- [ ] **Step 3: Implement** `backend/app/services/recovery_code_service.py`:

```python
"""Password recovery codes.

Single-use codes that let a user reset their own password without an admin or
shell access. Stored like 2FA backup codes: a Fernet-encrypted JSON array of
SHA-256 hashes (hash + encrypt; never plaintext). LAN-only reset is enforced at
the route layer.
"""
import hashlib
import json
import logging
import secrets
from typing import Optional

from sqlalchemy.orm import Session

from app.core.crypto import encrypt_at_rest, decrypt_at_rest
from app.models.user import User

logger = logging.getLogger(__name__)

RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_HEX_BYTES = 5  # → 10 hex chars / 40 bits per code

_DUMMY_BLOB: Optional[str] = None


def _generate_codes() -> list[str]:
    return [secrets.token_hex(RECOVERY_CODE_HEX_BYTES).upper() for _ in range(RECOVERY_CODE_COUNT)]


def _store_codes(user: User, plain_codes: list[str]) -> None:
    hashed = [hashlib.sha256(c.encode()).hexdigest() for c in plain_codes]
    user.password_recovery_codes_encrypted = encrypt_at_rest(json.dumps(hashed))


def _load_hashes(user: User) -> list[str]:
    if not user.password_recovery_codes_encrypted:
        return []
    try:
        return json.loads(decrypt_at_rest(user.password_recovery_codes_encrypted))
    except Exception:
        return []


def _equalize_timing(code: str) -> None:
    """Run an equivalent decrypt+hash for unknown/disabled users (anti-enumeration)."""
    global _DUMMY_BLOB
    try:
        if _DUMMY_BLOB is None:
            _DUMMY_BLOB = encrypt_at_rest(json.dumps([hashlib.sha256(b"dummy").hexdigest()]))
        hashes = json.loads(decrypt_at_rest(_DUMMY_BLOB))
    except Exception:
        hashes = []
    _ = hashlib.sha256(code.strip().upper().encode()).hexdigest() in hashes


def generate_recovery_codes(db: Session, user_id: int) -> list[str]:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")
    codes = _generate_codes()
    _store_codes(user, codes)
    db.commit()
    return codes


def verify_and_consume_recovery_code(db: Session, user_id: int, code: str) -> bool:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    hashes = _load_hashes(user)
    if not hashes:
        return False
    code_hash = hashlib.sha256(code.strip().upper().encode()).hexdigest()
    if code_hash not in hashes:
        return False
    hashes.remove(code_hash)
    user.password_recovery_codes_encrypted = encrypt_at_rest(json.dumps(hashes))
    db.commit()
    logger.info("Recovery code consumed for user %d, %d remaining", user_id, len(hashes))
    return True


def verify_and_consume_for_username(db: Session, username: str, code: str) -> Optional[User]:
    """Resolve username, verify+consume a code. Returns the User on success, else None.
    Unknown or disabled users run a dummy verify to equalize timing (anti-enumeration)."""
    from app.services import users as user_service
    user = user_service.get_user_by_username(username, db=db)
    if not user or not user.is_active:
        _equalize_timing(code)
        return None
    if verify_and_consume_recovery_code(db, user.id, code):
        return user
    return None


def get_recovery_codes_remaining(db: Session, user_id: int) -> int:
    user = db.query(User).filter(User.id == user_id).first()
    return len(_load_hashes(user)) if user else 0


def has_recovery_codes(db: Session, user_id: int) -> bool:
    return get_recovery_codes_remaining(db, user_id) > 0
```

- [ ] **Step 4: Run → pass.** `cd backend && python -m pytest tests/services/test_recovery_code_service.py -v --no-cov`.

- [ ] **Step 5: Commit.** `git add backend/app/services/recovery_code_service.py backend/tests/services/test_recovery_code_service.py && git commit -m "feat(auth): recovery_code_service with timing-equalized username verify"`

---

### Task 4: Schemas, rate-limit key, management endpoints (generate + step-up, status)

**Files:** Modify `backend/app/schemas/auth.py` (after `ChangePasswordRequest`:96); `backend/app/core/rate_limiter.py:121`; `backend/app/api/routes/auth.py` (after `2fa/backup-codes`); Test `backend/tests/api/test_recovery_codes.py`.

**Produces:** `RecoveryCodesGenerateRequest{ code?, current_password? }`, `RecoveryCodesResponse{ recovery_codes }`, `RecoveryCodesStatusResponse{ configured, remaining }`; routes `POST /api/auth/recovery-codes`, `GET /api/auth/recovery-codes/status`.

- [ ] **Step 1: Failing tests** — create `backend/tests/api/test_recovery_codes.py`:

```python
"""Recovery-code management endpoints (generate with step-up, status)."""
from app.core.config import settings

PREFIX = settings.api_prefix
# user_headers logs in as testuser / Testpass123! (conftest)
USER_PW = "Testpass123!"


class TestRecoveryCodeManagement:
    def test_status_unconfigured_then_generate_with_password_stepup(self, client, user_headers):
        s = client.get(f"{PREFIX}/auth/recovery-codes/status", headers=user_headers)
        assert s.status_code == 200
        assert s.json() == {"configured": False, "remaining": 0}

        # testuser has no 2FA → step-up is current_password
        g = client.post(f"{PREFIX}/auth/recovery-codes",
                        json={"current_password": USER_PW}, headers=user_headers)
        assert g.status_code == 200
        assert len(g.json()["recovery_codes"]) == 10

        s2 = client.get(f"{PREFIX}/auth/recovery-codes/status", headers=user_headers)
        assert s2.json() == {"configured": True, "remaining": 10}

    def test_generate_wrong_password_denied(self, client, user_headers):
        g = client.post(f"{PREFIX}/auth/recovery-codes",
                        json={"current_password": "WrongPass9x"}, headers=user_headers)
        assert g.status_code == 401

    def test_generate_requires_auth(self, client):
        assert client.post(f"{PREFIX}/auth/recovery-codes", json={}).status_code == 401
```

- [ ] **Step 2: Run → fail** (404).

- [ ] **Step 3: Schemas.** In `backend/app/schemas/auth.py`, after `ChangePasswordRequest` (line 96):

```python
class RecoveryCodesGenerateRequest(BaseModel):
    code: str | None = None              # fresh TOTP/backup code (when 2FA enabled)
    current_password: str | None = None  # password re-entry (when 2FA disabled)


class RecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


class RecoveryCodesStatusResponse(BaseModel):
    configured: bool
    remaining: int


class RecoveryResetRequest(BaseModel):
    username: str = Field(max_length=64)
    recovery_code: str = Field(max_length=32)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)
```

Add `Field` to the pydantic import at the top of the file: `from pydantic import BaseModel, EmailStr, Field, field_validator`.

- [ ] **Step 4: Rate-limit key.** In `backend/app/core/rate_limiter.py`, after `"auth_pin_login": "5/minute",` (line 121): `    "auth_recovery_reset": "5/minute",`

- [ ] **Step 5: Endpoints.** In `backend/app/api/routes/auth.py`, add `RecoveryCodesGenerateRequest, RecoveryCodesResponse, RecoveryCodesStatusResponse, RecoveryResetRequest` to the `from app.schemas.auth import (...)` block, then add after the `regenerate_backup_codes` endpoint:

```python
@router.post("/recovery-codes", response_model=RecoveryCodesResponse)
@limiter.limit(get_limit("auth_2fa_setup"))
async def generate_recovery_codes_endpoint(
    payload: RecoveryCodesGenerateRequest,
    request: Request,
    response: Response,
    current_user=Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    """Generate/regenerate the caller's own recovery codes (shown once). Step-up required."""
    from app.services import recovery_code_service
    audit_logger = get_audit_logger_db()
    ip_address = request.client.host if request.client else None
    user_record = db.query(UserModel).filter(UserModel.id == current_user.id).first()
    if not user_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Step-up: fresh TOTP when 2FA is on, else current-password re-entry.
    ok = False
    if user_record.totp_enabled:
        ok = bool(payload.code) and _verify_fresh_totp(db, current_user.id, payload.code)
    else:
        ok = bool(payload.current_password) and bool(
            auth_service.authenticate_user(current_user.username, payload.current_password, db=db)
        )
    if not ok:
        audit_logger.log_security_event(
            action="recovery_codes_generate_denied", user=current_user.username,
            details={"ip_address": ip_address}, success=False, db=db,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Step-up authentication failed")

    codes = recovery_code_service.generate_recovery_codes(db, current_user.id)
    audit_logger.log_security_event(
        action="recovery_codes_generated", user=current_user.username,
        details={"ip_address": ip_address}, success=True, db=db,
    )
    return RecoveryCodesResponse(recovery_codes=codes)


@router.get("/recovery-codes/status", response_model=RecoveryCodesStatusResponse)
@limiter.limit(get_limit("auth_2fa_setup"))
async def recovery_codes_status(
    request: Request,
    response: Response,
    current_user=Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    """Whether the caller has recovery codes configured (drives the setup banner)."""
    from app.services import recovery_code_service
    remaining = recovery_code_service.get_recovery_codes_remaining(db, current_user.id)
    return RecoveryCodesStatusResponse(configured=remaining > 0, remaining=remaining)
```

- [ ] **Step 6: Run → pass.** `cd backend && python -m pytest tests/api/test_recovery_codes.py -v --no-cov`.

- [ ] **Step 7: Commit.** `git add backend/app/schemas/auth.py backend/app/core/rate_limiter.py backend/app/api/routes/auth.py backend/tests/api/test_recovery_codes.py && git commit -m "feat(auth): recovery-code management endpoints (generate w/ step-up, status)"`

---

### Task 5: LAN-only `recovery-reset` endpoint

**Files:** Modify `backend/app/api/routes/auth.py` (after `recovery_codes_status`); Test append `backend/tests/api/test_recovery_codes.py`.

**Produces:** `POST /api/auth/recovery-reset` → `{ "message": str }`, no token.

- [ ] **Step 1: Failing tests** — append. A dedicated throwaway user avoids polluting the shared fixture; the non-local case overrides `is_private_or_local_ip`.

```python
import pytest


@pytest.fixture
def reset_user(db_session):
    from app.services import users as user_service
    from app.schemas.user import UserCreate
    from app.services import recovery_code_service
    u = user_service.create_user(
        UserCreate(username="resetme", email="reset@example.com", password="OldPass123x", role="user"),
        db=db_session,
    )
    codes = recovery_code_service.generate_recovery_codes(db_session, u.id)
    return u, codes


class TestRecoveryReset:
    def test_happy_path_no_token_and_login_works(self, client, reset_user, db_session):
        u, codes = reset_user
        r = client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": "resetme", "recovery_code": codes[0], "new_password": "BrandNew9xPass",
        })
        assert r.status_code == 200, r.text
        assert "access_token" not in r.json()
        login = client.post(f"{PREFIX}/auth/login", json={"username": "resetme", "password": "BrandNew9xPass"})
        assert login.status_code == 200

    def test_revokes_existing_refresh_tokens(self, client, reset_user, db_session):
        u, codes = reset_user
        from app.services.token_service import token_service
        # seed an active refresh token
        from datetime import datetime, timezone, timedelta
        token_service.store_refresh_token(
            db_session, jti="jti-test", user_id=u.id, token="rawtok",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": "resetme", "recovery_code": codes[0], "new_password": "BrandNew9xPass",
        })
        assert token_service.is_token_revoked(db_session, "jti-test") is True

    def test_wrong_code_generic(self, client, reset_user):
        r = client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": "resetme", "recovery_code": "WRONGCODE0", "new_password": "BrandNew9xPass",
        })
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid username or recovery code"

    def test_unknown_user_same_generic(self, client):
        r = client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": "ghost", "recovery_code": "ABCD123456", "new_password": "BrandNew9xPass",
        })
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid username or recovery code"

    def test_weak_password_422_does_not_consume(self, client, reset_user):
        u, codes = reset_user
        bad = client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": "resetme", "recovery_code": codes[0], "new_password": "weak",
        })
        assert bad.status_code == 422
        good = client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": "resetme", "recovery_code": codes[0], "new_password": "BrandNew9xPass",
        })
        assert good.status_code == 200

    def test_non_local_forbidden(self, client, reset_user, monkeypatch):
        u, codes = reset_user
        import app.api.routes.auth as auth_routes
        monkeypatch.setattr(auth_routes, "is_private_or_local_ip", lambda ip: False)
        r = client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": "resetme", "recovery_code": codes[0], "new_password": "BrandNew9xPass",
        })
        assert r.status_code == 403
        assert r.json()["detail"]["error"] == "local_network_required"

    def test_audit_rows_written(self, client, reset_user, db_session):
        u, codes = reset_user
        client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": "resetme", "recovery_code": codes[0], "new_password": "BrandNew9xPass",
        })
        from app.models import AuditLog
        row = db_session.query(AuditLog).filter(AuditLog.action == "password_reset_via_recovery").first()
        assert row is not None
```

> The non-local test monkeypatches the name `is_private_or_local_ip` **as imported into the auth module** (`import app.api.routes.auth as auth_routes`), so import it by name in the endpoint (Step 3) rather than calling it through the package.

- [ ] **Step 2: Run → fail** (404 / NameError until Step 3).

- [ ] **Step 3: Add the endpoint.** In `backend/app/api/routes/auth.py`, add the import near the top: `from app.core.network_utils import is_private_or_local_ip`. Then after `recovery_codes_status`:

```python
@router.post("/recovery-reset")
@limiter.limit(get_limit("auth_recovery_reset"))
async def recovery_reset(
    payload: RecoveryResetRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Reset a password via a single-use recovery code — LAN-only. Issues NO session.

    The user logs in normally afterward (2FA stays enforced). On success the user's
    refresh tokens are revoked. Generic failures avoid username enumeration.
    """
    from app.services import recovery_code_service
    from app.services.token_service import token_service
    audit_logger = get_audit_logger_db()
    ip_address = request.client.host if request.client else None

    # LAN gate (real client IP via --proxy-headers --forwarded-allow-ips=127.0.0.1).
    if not is_private_or_local_ip(ip_address):
        audit_logger.log_security_event(
            action="password_reset_via_recovery_failed", user=payload.username,
            details={"ip_address": ip_address, "reason": "non_local"}, success=False, db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "local_network_required",
                    "message": "Password recovery is only available from the local network."},
        )

    user_record = recovery_code_service.verify_and_consume_for_username(
        db, payload.username, payload.recovery_code
    )
    if not user_record:
        audit_logger.log_security_event(
            action="password_reset_via_recovery_failed", user=payload.username,
            details={"ip_address": ip_address}, success=False, db=db,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid username or recovery code")

    user_service.update_user_password(user_record.id, payload.new_password, db=db)
    token_service.revoke_all_user_tokens(db, user_record.id, reason="password_reset_via_recovery")

    # Best-effort Samba sync — never fail the reset on an SMB hiccup.
    if user_record.smb_enabled:
        try:
            from app.services import samba_service
            await samba_service.sync_smb_password(user_record.username, payload.new_password)
        except Exception:
            logger.warning("Samba password sync failed after recovery reset for %s", user_record.username)

    audit_logger.log_security_event(
        action="password_reset_via_recovery", user=user_record.username,
        details={"ip_address": ip_address}, success=True, db=db,
    )
    return {"message": "Password reset successfully"}
```

> `logger` is already module-level in `auth.py`. If not, add `import logging; logger = logging.getLogger(__name__)`.

- [ ] **Step 4: Run → pass.** `cd backend && python -m pytest tests/api/test_recovery_codes.py -v --no-cov`.

- [ ] **Step 5: Regression.** `cd backend && python -m pytest tests/api/test_2fa_endpoints.py tests/security/test_change_password_validation.py tests/api/test_pin_login.py tests/security/test_totp_2fa.py -q --no-cov` → PASS.

- [ ] **Step 6: Commit.** `git add backend/app/api/routes/auth.py backend/tests/api/test_recovery_codes.py && git commit -m "feat(auth): LAN-only recovery-reset (no session, revoke tokens, anti-enumeration)"`

---

### Task 6: Frontend API client

**Files:** Create `client/src/api/recovery-codes.ts`; Test `client/src/__tests__/api/recovery-codes.test.ts` (note: `src/__tests__/api/`, the only dir vitest collects).

**Produces:** `generateRecoveryCodes(body)`, `getRecoveryCodesStatus()`, `recoveryReset(username, code, newPassword)`; types `RecoveryCodes`, `RecoveryCodesStatus`.

- [ ] **Step 1: Failing test** — create `client/src/__tests__/api/recovery-codes.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { generateRecoveryCodes, getRecoveryCodesStatus } from '../../api/recovery-codes';
import { apiClient } from '../../lib/api';

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return { ...actual, apiClient: { get: vi.fn(), post: vi.fn() }, buildApiUrl: (p: string) => p };
});

describe('recovery-codes api', () => {
  beforeEach(() => vi.clearAllMocks());

  it('generateRecoveryCodes posts step-up body and unwraps data', async () => {
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: { recovery_codes: ['A', 'B'] } });
    const res = await generateRecoveryCodes({ current_password: 'pw' });
    expect(apiClient.post).toHaveBeenCalledWith('/api/auth/recovery-codes', { current_password: 'pw' });
    expect(res.recovery_codes).toEqual(['A', 'B']);
  });

  it('getRecoveryCodesStatus unwraps data', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: { configured: true, remaining: 9 } });
    expect(await getRecoveryCodesStatus()).toEqual({ configured: true, remaining: 9 });
  });
});
```

- [ ] **Step 2: Run → fail.** `cd client && npx vitest run src/__tests__/api/recovery-codes.test.ts` → cannot resolve.

- [ ] **Step 3: Implement** `client/src/api/recovery-codes.ts`:

```typescript
/** Password recovery codes: self-service management + LAN-only reset. */
import { apiClient, buildApiUrl } from '../lib/api';

export interface RecoveryCodes { recovery_codes: string[]; }
export interface RecoveryCodesStatus { configured: boolean; remaining: number; }
export interface RecoveryCodesStepUp { code?: string; current_password?: string; }

export async function generateRecoveryCodes(stepUp: RecoveryCodesStepUp): Promise<RecoveryCodes> {
  const res = await apiClient.post<RecoveryCodes>('/api/auth/recovery-codes', stepUp);
  return res.data;
}

export async function getRecoveryCodesStatus(): Promise<RecoveryCodesStatus> {
  const res = await apiClient.get<RecoveryCodesStatus>('/api/auth/recovery-codes/status');
  return res.data;
}

/** Pre-auth, LAN-only. Raw fetch (no bearer). Throws with the server's message. */
export async function recoveryReset(username: string, recoveryCode: string, newPassword: string): Promise<{ message: string }> {
  const res = await fetch(buildApiUrl('/api/auth/recovery-reset'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, recovery_code: recoveryCode, new_password: newPassword }),
  });
  const data = (await res.json().catch(() => ({}))) as { message?: string; detail?: unknown };
  if (!res.ok) {
    const d = data.detail;
    const msg = typeof d === 'string' ? d
      : d && typeof d === 'object' && 'message' in d ? String((d as { message: unknown }).message)
      : `Reset failed (${res.status})`;
    throw new Error(msg);
  }
  return { message: String(data.message ?? 'Password reset successfully') };
}
```

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Commit.** `git add client/src/api/recovery-codes.ts client/src/__tests__/api/recovery-codes.test.ts && git commit -m "feat(client): recovery-codes API client (step-up + LAN-only reset)"`

---

### Task 7: "Passwort vergessen?" form on the login page

**Files:** Create `client/src/components/auth/ForgotPasswordForm.tsx`; Modify `client/src/pages/Login.tsx`; i18n: add keys to the `auth` namespace locales.

- [ ] **Step 1: Create the form** (labels for a11y; i18n via `useTranslation('auth')`). Create `client/src/components/auth/ForgotPasswordForm.tsx`:

```tsx
import React, { FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { recoveryReset } from '../../api/recovery-codes';

interface Props { onDone: () => void; }

export const ForgotPasswordForm: React.FC<Props> = ({ onDone }) => {
  const { t } = useTranslation('auth');
  const [username, setUsername] = useState('');
  const [code, setCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (newPassword !== confirm) { setError(t('forgot.mismatch')); return; }
    setLoading(true);
    try {
      await recoveryReset(username.trim(), code.trim(), newPassword);
      toast.success(t('forgot.success'));
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('forgot.failed'));
    } finally { setLoading(false); }
  };

  const field = 'w-full rounded-lg border border-slate-800 bg-slate-950-secondary px-3 py-2 text-sm';
  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <p className="text-xs text-slate-100-tertiary">{t('forgot.hint')}</p>
      {error && <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">{error}</div>}
      <label className="block space-y-1">
        <span className="text-xs text-slate-100-secondary">{t('forgot.username')}</span>
        <input className={field} autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
      </label>
      <label className="block space-y-1">
        <span className="text-xs text-slate-100-secondary">{t('forgot.code')}</span>
        <input className={field} value={code} onChange={(e) => setCode(e.target.value)} required />
      </label>
      <label className="block space-y-1">
        <span className="text-xs text-slate-100-secondary">{t('forgot.newPassword')}</span>
        <input type="password" className={field} autoComplete="new-password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required />
      </label>
      <label className="block space-y-1">
        <span className="text-xs text-slate-100-secondary">{t('forgot.confirm')}</span>
        <input type="password" className={field} autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
      </label>
      <div className="flex gap-2">
        <button type="submit" disabled={loading} className="flex-1 rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">
          {loading ? t('forgot.resetting') : t('forgot.reset')}
        </button>
        <button type="button" onClick={onDone} className="rounded-lg border border-slate-800 px-3 py-2 text-sm text-slate-100-secondary">
          {t('forgot.back')}
        </button>
      </div>
    </form>
  );
};
```

- [ ] **Step 2: i18n keys.** Add a `forgot` block to the `auth` namespace files (`client/src/i18n/locales/{en,de}/auth.json` — match the repo's locale layout): `hint`, `username`, `code`, `newPassword`, `confirm`, `reset`, `resetting`, `back`, `mismatch`, `success`, `failed`, and a `forgotLink` ("Passwort vergessen?" / "Forgot password?"). If the `auth` namespace file name differs, use the existing one that holds Login strings.

- [ ] **Step 3: Wire into `Login.tsx`.** Add `import { ForgotPasswordForm } from '../components/auth/ForgotPasswordForm';` and `const [forgotMode, setForgotMode] = useState(false);`. **Inside the existing `pinMode` else-branch** (around `Login.tsx:346`, where `<form onSubmit={handleSubmit}>` lives), render conditionally:

```tsx
{forgotMode ? (
  <ForgotPasswordForm onDone={() => setForgotMode(false)} />
) : (
  /* existing <form onSubmit={handleSubmit}> … </form> */
)}
```

And add the trigger link in the `else` (non-forgot) branch, near the dev-credentials hint (`:415`):

```tsx
{!twoFactorRequired && (
  <button type="button" onClick={() => setForgotMode(true)}
    className="mt-4 w-full text-center text-xs text-sky-400 hover:text-sky-300">
    {t('forgot.forgotLink')}
  </button>
)}
```

(Use whatever `t`/`useTranslation` hook `Login.tsx` already has; if it uses a different namespace, key it accordingly.)

- [ ] **Step 4: Lint + build.** `cd client && npx eslint src/components/auth/ForgotPasswordForm.tsx src/pages/Login.tsx && npm run build` → PASS.

- [ ] **Step 5: Commit.** `git add client/src/components/auth/ForgotPasswordForm.tsx client/src/pages/Login.tsx client/src/i18n/locales && git commit -m "feat(client): forgot-password form on login (a11y + i18n)"`

---

### Task 8: Recovery-codes settings card + step-up prompt + banner

**Files:** Create `client/src/components/settings/RecoveryCodesCard.tsx`; Modify `client/src/pages/SettingsPage.tsx`; i18n: `settings` namespace.

- [ ] **Step 1: Create the card.** Production is HTTP-over-LAN, so `navigator.clipboard` may be undefined — guard it and provide a Download .txt fallback. The card needs a step-up input (password, or a code if 2FA). It reads 2FA status via the existing `get2FAStatus` client. Create `client/src/components/settings/RecoveryCodesCard.tsx`:

```tsx
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import toast from 'react-hot-toast';
import { generateRecoveryCodes, getRecoveryCodesStatus, RecoveryCodesStatus } from '../../api/recovery-codes';
import { get2FAStatus } from '../../api/two-factor';

export const RecoveryCodesCard: React.FC = () => {
  const { t } = useTranslation('settings');
  const [status, setStatus] = useState<RecoveryCodesStatus | null>(null);
  const [twoFA, setTwoFA] = useState(false);
  const [stepUp, setStepUp] = useState('');
  const [codes, setCodes] = useState<string[] | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    try { setStatus(await getRecoveryCodesStatus()); } catch { /* best-effort */ }
    try { setTwoFA((await get2FAStatus()).enabled); } catch { /* best-effort */ }
  };
  useEffect(() => { void refresh(); }, []);

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const body = twoFA ? { code: stepUp } : { current_password: stepUp };
      const res = await generateRecoveryCodes(body);
      setCodes(res.recovery_codes);
      setStepUp('');
      await refresh();
      toast.success(t('recovery.generated'));
    } catch {
      toast.error(t('recovery.generateFailed'));
    } finally { setLoading(false); }
  };

  const handleCopy = async () => {
    if (!codes) return;
    try {
      if (!navigator.clipboard?.writeText) throw new Error('no clipboard');
      await navigator.clipboard.writeText(codes.join('\n'));
      toast.success(t('recovery.copied'));
    } catch {
      toast.error(t('recovery.copyUnavailable'));
    }
  };

  const handleDownload = () => {
    if (!codes) return;
    const blob = new Blob([codes.join('\n') + '\n'], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'baluhost-recovery-codes.txt';
    a.click(); URL.revokeObjectURL(url);
  };

  const notConfigured = status !== null && !status.configured;
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950-secondary p-4">
      <h3 className="text-sm font-semibold text-slate-100">{t('recovery.title')}</h3>
      <p className="mt-1 text-xs text-slate-100-tertiary">{t('recovery.desc')}</p>

      {notConfigured && (
        <div className="mt-3 rounded-lg border border-amber-700/50 bg-amber-950/30 px-3 py-2 text-xs text-amber-300">
          {t('recovery.banner')}
        </div>
      )}
      {status?.configured && !codes && (
        <p className="mt-3 text-xs text-slate-100-secondary">{t('recovery.remaining', { count: status.remaining })}</p>
      )}

      {codes && (
        <div className="mt-3">
          <div className="grid grid-cols-2 gap-2 rounded-lg bg-slate-950 p-3 font-mono text-xs text-slate-100">
            {codes.map((c) => (<span key={c}>{c}</span>))}
          </div>
          <div className="mt-2 flex gap-3">
            <button onClick={handleCopy} className="text-xs text-sky-400 hover:text-sky-300">{t('recovery.copy')}</button>
            <button onClick={handleDownload} className="text-xs text-sky-400 hover:text-sky-300">{t('recovery.download')}</button>
          </div>
          <p className="mt-1 text-xs text-amber-300">{t('recovery.shownOnce')}</p>
        </div>
      )}

      <label className="mt-4 block space-y-1">
        <span className="text-xs text-slate-100-secondary">{twoFA ? t('recovery.stepUpCode') : t('recovery.stepUpPassword')}</span>
        <input
          type={twoFA ? 'text' : 'password'}
          autoComplete={twoFA ? 'one-time-code' : 'current-password'}
          value={stepUp} onChange={(e) => setStepUp(e.target.value)}
          className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm"
        />
      </label>
      <button onClick={handleGenerate} disabled={loading || !stepUp}
        className="mt-3 rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">
        {loading ? t('recovery.generating') : status?.configured ? t('recovery.regenerate') : t('recovery.generate')}
      </button>
      {status?.configured && <p className="mt-1 text-xs text-slate-100-tertiary">{t('recovery.regenWarning')}</p>}
    </div>
  );
};
```

- [ ] **Step 2: i18n keys.** Add a `recovery` block to the `settings` namespace (`title`, `desc`, `banner`, `remaining` (with `{{count}}`), `copy`, `download`, `shownOnce`, `copied`, `copyUnavailable`, `generated`, `generateFailed`, `stepUpCode`, `stepUpPassword`, `generate`, `regenerate`, `generating`, `regenWarning`) in `client/src/i18n/locales/{en,de}/settings.json`.

- [ ] **Step 3: Render in `SettingsPage.tsx`.** Add `import { RecoveryCodesCard } from '../components/settings/RecoveryCodesCard';` and render `<RecoveryCodesCard />` immediately after `<TwoFactorCard ... />` in the security section.

- [ ] **Step 4: Lint + build.** `cd client && npx eslint src/components/settings/RecoveryCodesCard.tsx src/pages/SettingsPage.tsx && npm run build` → PASS.

- [ ] **Step 5: Commit.** `git add client/src/components/settings/RecoveryCodesCard.tsx client/src/pages/SettingsPage.tsx client/src/i18n/locales && git commit -m "feat(client): recovery-codes settings card (step-up, clipboard guard, download, banner)"`

---

### Task 9: Docs sync + final verification

**Files:** Modify `backend/app/services/CLAUDE.md`, `backend/app/api/CLAUDE.md`, `backend/app/core/CLAUDE.md`.

- [ ] **Step 1: CLAUDE.md indexes.**
  - `services/CLAUDE.md` top-level table: `| recovery_code_service.py | Password recovery codes — generate/verify/consume single-use codes (hash+encrypt at rest), timing-equalized username verify |`.
  - `core/CLAUDE.md` files table: `| crypto.py | Shared at-rest encryption (MultiFernet, TOTP→VPN key); totp_service delegates here |`.
  - `api/CLAUDE.md`: note the three new `auth` routes (`/recovery-codes` [step-up], `/recovery-codes/status`, `/recovery-reset` [LAN-only, no session]).

- [ ] **Step 2: Backend verification.** `cd backend && python -m pytest tests/core/test_crypto_at_rest.py tests/services/test_recovery_code_service.py tests/api/test_recovery_codes.py tests/security/test_totp_2fa.py tests/api/test_2fa_endpoints.py tests/security/test_change_password_validation.py -q --no-cov` → PASS. (Full Windows suite may go to CI.)

- [ ] **Step 3: Frontend verification.** `cd client && npx vitest run src/__tests__/api/recovery-codes.test.ts && npx eslint . && npm run build` → PASS (vitest, 0 eslint errors, build OK).

- [ ] **Step 4: Commit.** `git add backend/app/services/CLAUDE.md backend/app/api/CLAUDE.md backend/app/core/CLAUDE.md && git commit -m "docs(claude): index recovery-code service, core/crypto, auth routes"`

---

## Notes for the implementer

- **Step-up in tests:** `testuser` has no 2FA, so generate uses `current_password: "Testpass123!"`. For a 2FA path test, enable 2FA first (see `test_2fa_endpoints.py` setup) and pass a fresh TOTP as `code`.
- **Non-local simulation:** monkeypatch `is_private_or_local_ip` *as bound in the auth module* (import it by name in the endpoint, Step 3 of Task 5). The default test `client` would otherwise present a loopback IP that passes the gate.
- **No `/api/auth/me` round-trip** — tests use the known fixture usernames and a dedicated `resetme`/`resetuser` throwaway user.
- **Crypto helper** is the single seam; do not re-introduce `_totp_encrypt` imports into `recovery_code_service`.
- **Frontend i18n namespaces** — match the repo's existing `auth`/`settings` namespace files; if Login.tsx uses a different namespace for its strings, key `forgotLink` there.
