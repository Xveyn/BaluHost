# Password Recovery Codes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a LAN-only, self-service "forgot password" flow using single-use recovery codes, mirroring the existing 2FA backup-code mechanism.

**Architecture:** A new encrypted column on `User` stores Fernet-encrypted SHA-256 hashes of recovery codes (identical at-rest protection to 2FA backup codes). A dedicated `recovery_code_service` generates/verifies/consumes codes. Three new `auth` endpoints: two session-gated (generate, status) bound to the caller's own account, and one **pre-auth, local-channel-only** reset that sets a new password and issues **no token** (so 2FA stays enforced at the subsequent login). Frontend adds a "Passwort vergessen?" form on the login page and a recovery-codes management card (with a setup-nudge banner) in security settings.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, slowapi, `cryptography` Fernet (via `totp_service`), pytest; React 18 + TypeScript, axios (`apiClient`), Vitest.

## Global Constraints

- **Reset is LOCAL CHANNEL ONLY.** Gate with `getattr(request.state, "channel", "remote") != "local"` → `403 {"error": "local_channel_required", ...}`. Mirror `login_pin` (`backend/app/api/routes/auth.py`).
- **Reset issues NO session/token.** It only sets a new password. 2FA is preserved because the user logs in normally afterward.
- **Codes are hashed THEN encrypted at rest.** SHA-256 hex of each code, JSON array, Fernet-encrypted via `totp_service._totp_encrypt` / `_totp_decrypt` (`TOTP_ENCRYPTION_KEY` → `VPN_ENCRYPTION_KEY` fallback). Never store or log plaintext codes.
- **RBAC:** management endpoints use `Depends(deps.get_current_user)` and operate only on `current_user.id` — never another user's codes. No admin endpoint reveals codes.
- **Password strength:** `new_password` validated by `_validate_password_strength` (`backend/app/schemas/auth.py`) — via a Pydantic `field_validator`, NOT a raw `dict`, so a weak password is `422` **before** the handler runs (no code consumed).
- **Anti-enumeration:** unknown user, wrong code, no-codes-configured all return the **same** `401 "Invalid username or recovery code"`.
- **Scope:** all roles (admin + user).
- **Codes:** `RECOVERY_CODE_COUNT = 10`, format = uppercased `secrets.token_hex(4)` (8 hex chars), identical to 2FA backup codes.
- **Alembic head pitfall:** set the migration `down_revision` to the real `alembic heads` output, NOT a stale dev-DB head.
- **Windows CRLF repo:** repo uses `core.autocrlf=true`; the `LF will be replaced by CRLF` warning on commit is expected.
- **Spec:** `docs/superpowers/specs/2026-06-29-password-recovery-codes-design.md`.

---

## File Structure

**Backend**
- `backend/app/models/user.py` — new `password_recovery_codes_encrypted` column.
- `backend/alembic/versions/<rev>_add_password_recovery_codes.py` — migration.
- `backend/app/services/recovery_code_service.py` — new service (generate/verify/consume/status).
- `backend/app/schemas/auth.py` — `RecoveryResetRequest`, `RecoveryCodesResponse`, `RecoveryCodesStatusResponse`.
- `backend/app/core/rate_limiter.py` — `auth_recovery_reset` limit key.
- `backend/app/api/routes/auth.py` — 3 endpoints.
- `backend/tests/services/test_recovery_code_service.py`, `backend/tests/api/test_recovery_codes.py`.

**Frontend**
- `client/src/api/recovery-codes.ts` — typed client (management + reset).
- `client/src/api/__tests__/recovery-codes.test.ts` — vitest.
- `client/src/components/auth/ForgotPasswordForm.tsx` — self-contained reset form.
- `client/src/pages/Login.tsx` — render the form behind a "Passwort vergessen?" link.
- `client/src/components/settings/RecoveryCodesCard.tsx` — management card + nudge banner.
- Settings security section — render `<RecoveryCodesCard />` next to `<TwoFactorCard />`.

**Docs**
- `backend/app/services/CLAUDE.md`, `backend/app/api/CLAUDE.md`, `backend/app/models/CLAUDE.md`.

---

### Task 1: User model column + migration

**Files:**
- Modify: `backend/app/models/user.py:49` (after `totp_backup_codes_encrypted`)
- Create: `backend/alembic/versions/<rev>_add_password_recovery_codes.py`
- Test: `backend/tests/services/test_recovery_code_service.py`

**Interfaces:**
- Produces: `User.password_recovery_codes_encrypted: Mapped[str | None]` (Text, nullable, default `None`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/services/test_recovery_code_service.py`:

```python
"""Tests for password recovery codes (column + service)."""
from app.models.user import User


def test_user_has_recovery_codes_column():
    # Column exists and defaults to None on a fresh instance.
    u = User(username="x", hashed_password="h", role="user")
    assert hasattr(u, "password_recovery_codes_encrypted")
    assert u.password_recovery_codes_encrypted is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_recovery_code_service.py::test_user_has_recovery_codes_column -v --no-cov`
Expected: FAIL — `AttributeError: ... has no attribute 'password_recovery_codes_encrypted'`.

- [ ] **Step 3: Add the column**

In `backend/app/models/user.py`, immediately after line 52 (the `totp_enabled_at` column, end of the "TOTP 2FA fields" block) add:

```python

    # Password recovery codes (self-service forgot-password, LAN-only reset).
    # Fernet-encrypted JSON array of SHA-256 hashes; None = not configured.
    password_recovery_codes_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

(`Text` and `Optional` are already imported in this file.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/services/test_recovery_code_service.py::test_user_has_recovery_codes_column -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Generate the migration against the REAL head**

Run: `cd backend && alembic heads`
Note the revision id printed (call it `<HEAD>`).

Run: `cd backend && alembic revision -m "add password_recovery_codes_encrypted to users"`

Open the new file in `backend/alembic/versions/`. Set `down_revision = "<HEAD>"` (the value from `alembic heads`) and make the body exactly:

```python
def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_recovery_codes_encrypted", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "password_recovery_codes_encrypted")
```

- [ ] **Step 6: Verify the migration is reversible**

Run: `cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
Expected: upgrade adds the column, downgrade drops it, re-upgrade re-adds — no errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/user.py backend/alembic/versions/ backend/tests/services/test_recovery_code_service.py
git commit -m "feat(auth): add password_recovery_codes_encrypted column + migration"
```

---

### Task 2: `recovery_code_service`

**Files:**
- Create: `backend/app/services/recovery_code_service.py`
- Test: `backend/tests/services/test_recovery_code_service.py` (append)

**Interfaces:**
- Consumes: `User.password_recovery_codes_encrypted`; `totp_service._totp_encrypt/_totp_decrypt`.
- Produces:
  - `generate_recovery_codes(db: Session, user_id: int) -> list[str]`
  - `verify_and_consume_recovery_code(db: Session, user_id: int, code: str) -> bool`
  - `get_recovery_codes_remaining(db: Session, user_id: int) -> int`
  - `has_recovery_codes(db: Session, user_id: int) -> bool`
  - `RECOVERY_CODE_COUNT = 10`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/services/test_recovery_code_service.py`:

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
    assert all(isinstance(c, str) and c for c in codes)
    assert rcs.has_recovery_codes(db_session, a_user.id) is True
    assert rcs.get_recovery_codes_remaining(db_session, a_user.id) == 10


def test_code_is_single_use(db_session, a_user):
    codes = rcs.generate_recovery_codes(db_session, a_user.id)
    assert rcs.verify_and_consume_recovery_code(db_session, a_user.id, codes[0]) is True
    # second use of the same code fails
    assert rcs.verify_and_consume_recovery_code(db_session, a_user.id, codes[0]) is False
    assert rcs.get_recovery_codes_remaining(db_session, a_user.id) == 9


def test_regenerate_invalidates_old_codes(db_session, a_user):
    old = rcs.generate_recovery_codes(db_session, a_user.id)
    new = rcs.generate_recovery_codes(db_session, a_user.id)
    assert rcs.verify_and_consume_recovery_code(db_session, a_user.id, old[0]) is False
    assert rcs.verify_and_consume_recovery_code(db_session, a_user.id, new[0]) is True


def test_wrong_code_and_unconfigured(db_session, a_user):
    assert rcs.has_recovery_codes(db_session, a_user.id) is False
    assert rcs.verify_and_consume_recovery_code(db_session, a_user.id, "DEADBEEF") is False
    rcs.generate_recovery_codes(db_session, a_user.id)
    assert rcs.verify_and_consume_recovery_code(db_session, a_user.id, "NOTACODE") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_recovery_code_service.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: app.services.recovery_code_service`.

- [ ] **Step 3: Implement the service**

Create `backend/app/services/recovery_code_service.py`:

```python
"""Password recovery codes.

Single-use codes that let a user reset their own password without an admin or
shell access. Stored exactly like 2FA backup codes: a Fernet-encrypted JSON
array of SHA-256 hashes (hash + encrypt; never plaintext at rest). LAN-only
reset is enforced at the route layer, not here.
"""
import hashlib
import json
import logging
import secrets

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.totp_service import _totp_encrypt, _totp_decrypt

logger = logging.getLogger(__name__)

RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_HEX_BYTES = 4  # → 8 hex chars per code (matches 2FA backup codes)


def _generate_codes() -> list[str]:
    return [secrets.token_hex(RECOVERY_CODE_HEX_BYTES).upper() for _ in range(RECOVERY_CODE_COUNT)]


def _store_codes(user: User, plain_codes: list[str]) -> None:
    hashed = [hashlib.sha256(c.encode()).hexdigest() for c in plain_codes]
    user.password_recovery_codes_encrypted = _totp_encrypt(json.dumps(hashed))


def _load_hashes(user: User) -> list[str]:
    if not user.password_recovery_codes_encrypted:
        return []
    try:
        return json.loads(_totp_decrypt(user.password_recovery_codes_encrypted))
    except Exception:
        return []


def generate_recovery_codes(db: Session, user_id: int) -> list[str]:
    """Generate fresh codes, store hashed+encrypted, return plaintext ONCE.
    Regenerating overwrites the column → all previous codes are invalidated."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")
    codes = _generate_codes()
    _store_codes(user, codes)
    db.commit()
    return codes


def verify_and_consume_recovery_code(db: Session, user_id: int, code: str) -> bool:
    """Verify a code and consume it (single-use). False on any miss; never raises."""
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
    user.password_recovery_codes_encrypted = _totp_encrypt(json.dumps(hashes))
    db.commit()
    logger.info("Recovery code consumed for user %d, %d remaining", user_id, len(hashes))
    return True


def get_recovery_codes_remaining(db: Session, user_id: int) -> int:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return 0
    return len(_load_hashes(user))


def has_recovery_codes(db: Session, user_id: int) -> bool:
    return get_recovery_codes_remaining(db, user_id) > 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_recovery_code_service.py -v --no-cov`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/recovery_code_service.py backend/tests/services/test_recovery_code_service.py
git commit -m "feat(auth): recovery_code_service (generate/verify/consume, hash+encrypt at rest)"
```

---

### Task 3: Schemas, rate-limit key, management endpoints

**Files:**
- Modify: `backend/app/schemas/auth.py` (after `ChangePasswordRequest`)
- Modify: `backend/app/core/rate_limiter.py:151` (inside `RATE_LIMITS`)
- Modify: `backend/app/api/routes/auth.py` (after the `2fa/backup-codes` endpoint)
- Test: `backend/tests/api/test_recovery_codes.py`

**Interfaces:**
- Consumes: `recovery_code_service`, `deps.get_current_user`, `get_limit`, `get_audit_logger_db`.
- Produces (schemas):
  - `RecoveryCodesResponse{ recovery_codes: list[str] }`
  - `RecoveryCodesStatusResponse{ configured: bool, remaining: int }`
  - `RecoveryResetRequest{ username: str, recovery_code: str, new_password: str }` (strength-validated)
- Produces (routes): `POST /api/auth/recovery-codes`, `GET /api/auth/recovery-codes/status`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/api/test_recovery_codes.py`:

```python
"""Recovery-code management endpoints + LAN-only reset."""
from app.core.config import settings

PREFIX = settings.api_prefix


class TestRecoveryCodeManagement:
    def test_status_unconfigured_then_generate(self, client, user_headers):
        s = client.get(f"{PREFIX}/auth/recovery-codes/status", headers=user_headers)
        assert s.status_code == 200
        assert s.json() == {"configured": False, "remaining": 0}

        g = client.post(f"{PREFIX}/auth/recovery-codes", headers=user_headers)
        assert g.status_code == 200
        codes = g.json()["recovery_codes"]
        assert len(codes) == 10

        s2 = client.get(f"{PREFIX}/auth/recovery-codes/status", headers=user_headers)
        assert s2.json() == {"configured": True, "remaining": 10}

    def test_generate_requires_auth(self, client):
        r = client.post(f"{PREFIX}/auth/recovery-codes")
        assert r.status_code == 401
```

> Fixtures `client`, `user_headers` come from `backend/tests/conftest.py` (same ones the 2FA endpoint tests use). The default `client` runs `channel=local`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/api/test_recovery_codes.py -v --no-cov`
Expected: FAIL — 404 (routes not defined).

- [ ] **Step 3: Add the schemas**

In `backend/app/schemas/auth.py`, immediately after `ChangePasswordRequest` (line 96) add:

```python
class RecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


class RecoveryCodesStatusResponse(BaseModel):
    configured: bool
    remaining: int


class RecoveryResetRequest(BaseModel):
    username: str
    recovery_code: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, v: str) -> str:
        """Enforce password policy; a weak password fails BEFORE the handler runs."""
        return _validate_password_strength(v)
```

- [ ] **Step 4: Add the rate-limit key**

In `backend/app/core/rate_limiter.py`, inside the `RATE_LIMITS` dict, after the `"auth_pin_login": "5/minute",` line (line 121) add:

```python
    "auth_recovery_reset": "5/minute",
```

- [ ] **Step 5: Add the management endpoints**

In `backend/app/api/routes/auth.py`, find the `regenerate_backup_codes` endpoint (the `@router.post("/2fa/backup-codes" ...)` block) and add immediately after it. First ensure the new schemas are imported — locate the existing `from app.schemas.auth import (...)` block and add `RecoveryCodesResponse`, `RecoveryCodesStatusResponse`, `RecoveryResetRequest` to it.

```python
@router.post("/recovery-codes", response_model=RecoveryCodesResponse)
@limiter.limit(get_limit("auth_2fa_setup"))
async def generate_recovery_codes_endpoint(
    request: Request,
    response: Response,
    current_user=Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    """Generate/regenerate the caller's own password-recovery codes (shown once)."""
    from app.services import recovery_code_service
    audit_logger = get_audit_logger_db()
    ip_address = request.client.host if request.client else None

    codes = recovery_code_service.generate_recovery_codes(db, current_user.id)
    audit_logger.log_security_event(
        action="recovery_codes_generated",
        user=current_user.username,
        details={"ip_address": ip_address},
        success=True,
        db=db,
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

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_recovery_codes.py -v --no-cov`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/auth.py backend/app/core/rate_limiter.py backend/app/api/routes/auth.py backend/tests/api/test_recovery_codes.py
git commit -m "feat(auth): recovery-code management endpoints (generate + status)"
```

---

### Task 4: LAN-only `recovery-reset` endpoint

**Files:**
- Modify: `backend/app/api/routes/auth.py` (after `recovery_codes_status`)
- Test: `backend/tests/api/test_recovery_codes.py` (append)

**Interfaces:**
- Consumes: `RecoveryResetRequest`, `recovery_code_service`, `user_service.get_user_by_username/update_user_password`, `samba_service.sync_smb_password`, channel gate.
- Produces: `POST /api/auth/recovery-reset` → `{ "message": str }`, no token.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/api/test_recovery_codes.py`:

```python
class TestRecoveryReset:
    def test_reset_happy_path_no_token(self, client, user_headers, db_session):
        # Arrange: the seeded test user generates codes via the API.
        g = client.post(f"{PREFIX}/auth/recovery-codes", headers=user_headers)
        code = g.json()["recovery_codes"][0]
        # Resolve the username behind user_headers.
        me = client.get(f"{PREFIX}/auth/me", headers=user_headers).json()
        username = me["username"]

        # Act: reset (default client = local channel).
        r = client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": username, "recovery_code": code, "new_password": "BrandNew9xPass",
        })
        assert r.status_code == 200, r.text
        assert "access_token" not in r.json()

        # New password works at the normal login.
        login = client.post(f"{PREFIX}/auth/login", json={
            "username": username, "password": "BrandNew9xPass",
        })
        assert login.status_code == 200

    def test_reset_rejects_wrong_code_generic(self, client, user_headers):
        client.post(f"{PREFIX}/auth/recovery-codes", headers=user_headers)
        me = client.get(f"{PREFIX}/auth/me", headers=user_headers).json()
        r = client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": me["username"], "recovery_code": "WRONGCOD", "new_password": "BrandNew9xPass",
        })
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid username or recovery code"

    def test_reset_unknown_user_same_generic(self, client):
        r = client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": "ghost", "recovery_code": "ABCD1234", "new_password": "BrandNew9xPass",
        })
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid username or recovery code"

    def test_reset_weak_password_422_does_not_consume(self, client, user_headers, db_session):
        g = client.post(f"{PREFIX}/auth/recovery-codes", headers=user_headers)
        code = g.json()["recovery_codes"][0]
        me = client.get(f"{PREFIX}/auth/me", headers=user_headers).json()
        # weak password → 422 before handler; code must remain usable.
        bad = client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": me["username"], "recovery_code": code, "new_password": "weak",
        })
        assert bad.status_code == 422
        good = client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": me["username"], "recovery_code": code, "new_password": "BrandNew9xPass",
        })
        assert good.status_code == 200

    def test_reset_remote_channel_forbidden(self, remote_client, user_headers):
        # Generate codes over the local client first.
        from app.core.config import settings as _s
        gen = remote_client.post(f"{PREFIX}/auth/recovery-codes", headers=user_headers)
        # management endpoints are not channel-gated, so this still works (200);
        code = gen.json()["recovery_codes"][0]
        me = remote_client.get(f"{PREFIX}/auth/me", headers=user_headers).json()
        r = remote_client.post(f"{PREFIX}/auth/recovery-reset", json={
            "username": me["username"], "recovery_code": code, "new_password": "BrandNew9xPass",
        })
        assert r.status_code == 403
        assert r.json()["detail"]["error"] == "local_channel_required"
```

> Notes: `remote_client` monkeypatches `settings.channel="remote"` (canonical example: `backend/tests/api/test_power_authority_routes.py::test_put_authority_requires_local_channel`). Remove the stray `user_service_module` placeholder import — it was only to flag that you resolve usernames via `users.get_user_by_username`; the actual tests use `/auth/me`. If `/auth/me` is not the correct path in this repo, resolve the username via the `user_headers` fixture's known username instead.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/api/test_recovery_codes.py::TestRecoveryReset -v --no-cov`
Expected: FAIL — 404 (route not defined). Fix the `_seed_codes` helper / `/auth/me` path per the note before continuing if a test errors for an unrelated reason.

- [ ] **Step 3: Add the reset endpoint**

In `backend/app/api/routes/auth.py`, immediately after `recovery_codes_status`, add:

```python
@router.post("/recovery-reset")
@limiter.limit(get_limit("auth_recovery_reset"))
async def recovery_reset(
    payload: RecoveryResetRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Reset a password via a single-use recovery code — LOCAL CHANNEL ONLY.

    Issues NO session: the user logs in normally afterward, so 2FA stays
    enforced. Returns a generic failure to avoid username enumeration.
    """
    from app.services import recovery_code_service
    audit_logger = get_audit_logger_db()
    ip_address = request.client.host if request.client else None

    # Hard invariant: recovery reset is only valid over the local channel.
    if getattr(request.state, "channel", "remote") != "local":
        audit_logger.log_security_event(
            action="password_reset_via_recovery_failed",
            user=payload.username,
            details={"ip_address": ip_address, "reason": "remote_channel"},
            success=False,
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "local_channel_required",
                "message": "Password recovery is only available from the local network.",
            },
        )

    user_record = user_service.get_user_by_username(payload.username, db=db)
    code_ok = False
    if user_record:
        code_ok = recovery_code_service.verify_and_consume_recovery_code(
            db, user_record.id, payload.recovery_code
        )
    if not user_record or not code_ok:
        audit_logger.log_security_event(
            action="password_reset_via_recovery_failed",
            user=payload.username,
            details={"ip_address": ip_address},
            success=False,
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or recovery code",
        )

    user_service.update_user_password(user_record.id, payload.new_password, db=db)

    # Keep the Samba password in sync when SMB is enabled (mirror change_password).
    user_record = db.query(UserModel).filter(UserModel.id == user_record.id).first()
    if user_record and user_record.smb_enabled:
        from app.services import samba_service
        await samba_service.sync_smb_password(user_record.username, payload.new_password)

    audit_logger.log_security_event(
        action="password_reset_via_recovery",
        user=user_record.username,
        details={"ip_address": ip_address},
        success=True,
        db=db,
    )
    return {"message": "Password reset successfully"}
```

> `UserModel`, `user_service`, `status`, `HTTPException`, `Request`, `Response`, `get_db`, `get_audit_logger_db` are all already imported in this file (used by `change_password`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_recovery_codes.py -v --no-cov`
Expected: PASS (all).

- [ ] **Step 5: Run the auth/2FA suites for regressions**

Run: `cd backend && python -m pytest tests/api/test_2fa_endpoints.py tests/security/test_change_password_validation.py tests/api/test_pin_login.py -q --no-cov`
Expected: PASS (no regressions).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/auth.py backend/tests/api/test_recovery_codes.py
git commit -m "feat(auth): LAN-only recovery-reset endpoint (no session, anti-enumeration)"
```

---

### Task 5: Frontend API client

**Files:**
- Create: `client/src/api/recovery-codes.ts`
- Test: `client/src/api/__tests__/recovery-codes.test.ts`

**Interfaces:**
- Produces: `generateRecoveryCodes()`, `getRecoveryCodesStatus()`, `recoveryReset(username, recoveryCode, newPassword)` and types `RecoveryCodes`, `RecoveryCodesStatus`.

- [ ] **Step 1: Write the failing test**

Create `client/src/api/__tests__/recovery-codes.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { generateRecoveryCodes, getRecoveryCodesStatus } from '../recovery-codes';
import { apiClient } from '../../lib/api';

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>();
  return {
    ...actual,
    apiClient: { get: vi.fn(), post: vi.fn() },
    buildApiUrl: (p: string) => p,
  };
});

describe('recovery-codes api', () => {
  beforeEach(() => vi.clearAllMocks());

  it('generateRecoveryCodes posts and unwraps data', async () => {
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: { recovery_codes: ['A', 'B'] } });
    const res = await generateRecoveryCodes();
    expect(apiClient.post).toHaveBeenCalledWith('/api/auth/recovery-codes');
    expect(res.recovery_codes).toEqual(['A', 'B']);
  });

  it('getRecoveryCodesStatus gets and unwraps data', async () => {
    (apiClient.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: { configured: true, remaining: 9 } });
    const res = await getRecoveryCodesStatus();
    expect(apiClient.get).toHaveBeenCalledWith('/api/auth/recovery-codes/status');
    expect(res).toEqual({ configured: true, remaining: 9 });
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd client && npx vitest run src/api/__tests__/recovery-codes.test.ts`
Expected: FAIL — cannot resolve `../recovery-codes`.

- [ ] **Step 3: Implement the client**

Create `client/src/api/recovery-codes.ts`:

```typescript
/** Password recovery codes: self-service management + LAN-only reset. */
import { apiClient, buildApiUrl } from '../lib/api';

export interface RecoveryCodes {
  recovery_codes: string[];
}

export interface RecoveryCodesStatus {
  configured: boolean;
  remaining: number;
}

export async function generateRecoveryCodes(): Promise<RecoveryCodes> {
  const res = await apiClient.post<RecoveryCodes>('/api/auth/recovery-codes');
  return res.data;
}

export async function getRecoveryCodesStatus(): Promise<RecoveryCodesStatus> {
  const res = await apiClient.get<RecoveryCodesStatus>('/api/auth/recovery-codes/status');
  return res.data;
}

/**
 * Pre-auth, local-channel-only reset. Mirrors Login.tsx's raw-fetch path
 * (no bearer token). Throws with the server's message on failure.
 */
export async function recoveryReset(
  username: string,
  recoveryCode: string,
  newPassword: string,
): Promise<{ message: string }> {
  const res = await fetch(buildApiUrl('/api/auth/recovery-reset'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, recovery_code: recoveryCode, new_password: newPassword }),
  });
  const data = (await res.json().catch(() => ({}))) as { message?: string; detail?: unknown };
  if (!res.ok) {
    const d = data.detail;
    const msg =
      typeof d === 'string'
        ? d
        : d && typeof d === 'object' && 'message' in d
          ? String((d as { message: unknown }).message)
          : `Reset failed (${res.status})`;
    throw new Error(msg);
  }
  return { message: String(data.message ?? 'Password reset successfully') };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd client && npx vitest run src/api/__tests__/recovery-codes.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add client/src/api/recovery-codes.ts client/src/api/__tests__/recovery-codes.test.ts
git commit -m "feat(client): recovery-codes API client (management + LAN-only reset)"
```

---

### Task 6: "Passwort vergessen?" form on the login page

**Files:**
- Create: `client/src/components/auth/ForgotPasswordForm.tsx`
- Modify: `client/src/pages/Login.tsx`

**Interfaces:**
- Consumes: `recoveryReset` from `../api/recovery-codes`.
- Produces: `<ForgotPasswordForm onDone={() => void} />` (self-contained).

- [ ] **Step 1: Create the self-contained form**

Create `client/src/components/auth/ForgotPasswordForm.tsx`:

```tsx
import React, { FormEvent, useState } from 'react';
import toast from 'react-hot-toast';
import { recoveryReset } from '../../api/recovery-codes';

interface Props {
  /** Called after a successful reset (e.g. to return to the login form). */
  onDone: () => void;
}

export const ForgotPasswordForm: React.FC<Props> = ({ onDone }) => {
  const [username, setUsername] = useState('');
  const [code, setCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (newPassword !== confirm) {
      setError('Passwords do not match');
      return;
    }
    setLoading(true);
    try {
      await recoveryReset(username.trim(), code.trim(), newPassword);
      toast.success('Password reset. Please sign in with your new password.');
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <p className="text-xs text-slate-100-tertiary">
        Reset your password with a recovery code. Only available on the local network.
      </p>
      {error && <div className="rounded-lg bg-red-950/40 px-3 py-2 text-xs text-red-300">{error}</div>}
      <input
        className="w-full rounded-lg border border-slate-800 bg-slate-950-secondary px-3 py-2 text-sm"
        placeholder="Username" autoComplete="username" value={username}
        onChange={(e) => setUsername(e.target.value)} required
      />
      <input
        className="w-full rounded-lg border border-slate-800 bg-slate-950-secondary px-3 py-2 text-sm"
        placeholder="Recovery code" value={code}
        onChange={(e) => setCode(e.target.value)} required
      />
      <input
        type="password"
        className="w-full rounded-lg border border-slate-800 bg-slate-950-secondary px-3 py-2 text-sm"
        placeholder="New password" autoComplete="new-password" value={newPassword}
        onChange={(e) => setNewPassword(e.target.value)} required
      />
      <input
        type="password"
        className="w-full rounded-lg border border-slate-800 bg-slate-950-secondary px-3 py-2 text-sm"
        placeholder="Confirm new password" autoComplete="new-password" value={confirm}
        onChange={(e) => setConfirm(e.target.value)} required
      />
      <div className="flex gap-2">
        <button
          type="submit" disabled={loading}
          className="flex-1 rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {loading ? 'Resetting…' : 'Reset password'}
        </button>
        <button
          type="button" onClick={onDone}
          className="rounded-lg border border-slate-800 px-3 py-2 text-sm text-slate-100-secondary"
        >
          Back
        </button>
      </div>
    </form>
  );
};
```

> Tailwind tokens (`slate-950-secondary`, `slate-100-tertiary`) are taken from `Login.tsx`'s existing classes — if a class name differs in this repo, copy the equivalent token actually used in `Login.tsx`.

- [ ] **Step 2: Wire it into `Login.tsx`**

In `client/src/pages/Login.tsx`:
- Add the import near the other imports: `import { ForgotPasswordForm } from '../components/auth/ForgotPasswordForm';`
- Add state next to the other `useState` hooks (e.g. after `const [showPassword, setShowPassword] = useState(false);`): `const [forgotMode, setForgotMode] = useState(false);`
- In the JSX, wrap the existing login `<form>` so that when `forgotMode` is true the form is replaced by `<ForgotPasswordForm onDone={() => setForgotMode(false)} />`. Concretely, find the element that renders the main login form (the `<form onSubmit={handleSubmit}>`) and render conditionally:

```tsx
{forgotMode ? (
  <ForgotPasswordForm onDone={() => setForgotMode(false)} />
) : (
  /* existing login form JSX (the <form onSubmit={handleSubmit}> … </form>) */
)}
```

- Add the link that enters forgot mode. Below the login form's submit button (inside the `else` branch, near the existing dev-credentials hint block), add:

```tsx
{!twoFactorRequired && (
  <button
    type="button"
    onClick={() => setForgotMode(true)}
    className="mt-4 w-full text-center text-xs text-sky-400 hover:text-sky-300"
  >
    Passwort vergessen?
  </button>
)}
```

- [ ] **Step 3: Typecheck / build**

Run: `cd client && npx eslint src/components/auth/ForgotPasswordForm.tsx src/pages/Login.tsx && npm run build`
Expected: PASS (0 eslint errors, build succeeds).

- [ ] **Step 4: Manual smoke test**

Run (repo root): `python start_dev.py`. Open `http://localhost:5173/login`:
- Click "Passwort vergessen?" → the reset form appears.
- With a seeded user, generate codes in settings first (Task 7), then reset here; confirm login with the new password works.
- "Back" returns to the login form.

- [ ] **Step 5: Commit**

```bash
git add client/src/components/auth/ForgotPasswordForm.tsx client/src/pages/Login.tsx
git commit -m "feat(client): forgot-password form on the login page (LAN-only reset)"
```

---

### Task 7: Recovery-codes management card + nudge banner

**Files:**
- Create: `client/src/components/settings/RecoveryCodesCard.tsx`
- Modify: the settings security section that renders `<TwoFactorCard />`

**Interfaces:**
- Consumes: `generateRecoveryCodes`, `getRecoveryCodesStatus` from `../../api/recovery-codes`.
- Produces: `<RecoveryCodesCard />` (self-contained, fetches its own status).

- [ ] **Step 1: Create the card**

Create `client/src/components/settings/RecoveryCodesCard.tsx`:

```tsx
import React, { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { generateRecoveryCodes, getRecoveryCodesStatus, RecoveryCodesStatus } from '../../api/recovery-codes';

export const RecoveryCodesCard: React.FC = () => {
  const [status, setStatus] = useState<RecoveryCodesStatus | null>(null);
  const [codes, setCodes] = useState<string[] | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    try {
      setStatus(await getRecoveryCodesStatus());
    } catch {
      /* status is best-effort; leave null */
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const res = await generateRecoveryCodes();
      setCodes(res.recovery_codes);
      await refresh();
      toast.success('Recovery codes generated. Store them somewhere safe.');
    } catch {
      toast.error('Could not generate recovery codes');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (codes) void navigator.clipboard.writeText(codes.join('\n'));
    toast.success('Copied');
  };

  const notConfigured = status !== null && !status.configured;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-950-secondary p-4">
      <h3 className="text-sm font-semibold text-slate-100">Recovery codes</h3>
      <p className="mt-1 text-xs text-slate-100-tertiary">
        Single-use codes to reset your password if you forget it. The reset works only on the local network.
      </p>

      {notConfigured && (
        <div className="mt-3 rounded-lg border border-amber-700/50 bg-amber-950/30 px-3 py-2 text-xs text-amber-300">
          You have no recovery codes yet. We strongly recommend generating a set and storing them safely.
        </div>
      )}

      {status?.configured && !codes && (
        <p className="mt-3 text-xs text-slate-100-secondary">{status.remaining} unused codes remaining.</p>
      )}

      {codes && (
        <div className="mt-3">
          <div className="grid grid-cols-2 gap-2 rounded-lg bg-slate-950 p-3 font-mono text-xs text-slate-100">
            {codes.map((c) => (
              <span key={c}>{c}</span>
            ))}
          </div>
          <button onClick={handleCopy} className="mt-2 text-xs text-sky-400 hover:text-sky-300">
            Copy all
          </button>
          <p className="mt-1 text-xs text-amber-300">Shown once — save them now.</p>
        </div>
      )}

      <button
        onClick={handleGenerate}
        disabled={loading}
        className="mt-4 rounded-lg bg-sky-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {loading ? 'Generating…' : status?.configured ? 'Regenerate codes' : 'Generate codes'}
      </button>
    </div>
  );
};
```

- [ ] **Step 2: Render it next to the 2FA card**

Find where `TwoFactorCard` is rendered in the settings security section (search the codebase for `<TwoFactorCard`). In that file:
- Add the import: `import { RecoveryCodesCard } from '<correct relative path>/RecoveryCodesCard';`
- Render `<RecoveryCodesCard />` immediately after `<TwoFactorCard ... />`.

- [ ] **Step 3: Typecheck / build**

Run: `cd client && npx eslint src/components/settings/RecoveryCodesCard.tsx && npm run build`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add client/src/components/settings/RecoveryCodesCard.tsx client/src/<settings file edited>
git commit -m "feat(client): recovery-codes settings card + setup-nudge banner"
```

---

### Task 8: Docs sync + final verification

**Files:**
- Modify: `backend/app/services/CLAUDE.md`, `backend/app/api/CLAUDE.md`, `backend/app/models/CLAUDE.md`

- [ ] **Step 1: Update the backend CLAUDE.md indexes**

- In `backend/app/services/CLAUDE.md`, add to the top-level services table:
  `| recovery_code_service.py | Password recovery codes — generate/verify/consume single-use codes (hash+encrypt at rest), LAN-only reset |`
- In `backend/app/api/CLAUDE.md`, note the three new `auth` routes (`/recovery-codes`, `/recovery-codes/status`, `/recovery-reset` — LAN-only, no session).
- In `backend/app/models/CLAUDE.md` (or wherever the `User` columns are summarized), note the `password_recovery_codes_encrypted` column under Auth & Users if columns are listed there.

- [ ] **Step 2: Run the full new test set + targeted regressions**

Run: `cd backend && python -m pytest tests/services/test_recovery_code_service.py tests/api/test_recovery_codes.py tests/api/test_2fa_endpoints.py tests/security/test_change_password_validation.py -q --no-cov`
Expected: PASS (all). The full backend suite on Windows may be run in CI (per repo convention) — the relevant subset above is the local gate.

Run: `cd client && npx vitest run src/api/__tests__/recovery-codes.test.ts && npx eslint . && npm run build`
Expected: PASS (vitest, 0 eslint errors, build succeeds).

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/CLAUDE.md backend/app/api/CLAUDE.md backend/app/models/CLAUDE.md
git commit -m "docs(claude): index recovery-code service + auth routes"
```

---

## Self-Review notes for the implementer

- **Username resolution in tests:** the reset tests resolve the test user's username via `GET /api/auth/me`. If that route differs in this repo, use the username the `user_headers` fixture logs in as (check `backend/tests/conftest.py`).
- **`remote_client` fixture:** confirm it exists in `conftest.py` (it backs the PIN-login remote test). If named differently, mirror that fixture's `settings.channel="remote"` monkeypatch.
- **Encryption helpers:** importing `_totp_encrypt`/`_totp_decrypt` from `totp_service` is deliberate — identical key + at-rest posture as 2FA backup codes (per spec). Do not duplicate key logic.
- **No token from reset:** the happy-path test asserts `"access_token" not in r.json()` — keep it.
- **Frontend i18n:** strings are inline English/German for self-containment. If the security settings + login page are fully i18n'd in this repo, lift these strings into the existing `settings`/`auth` locale namespaces as a follow-up (out of scope for the core feature).
