# Password Recovery Codes — Self-Service Reset (LAN-only)

**Date:** 2026-06-29
**Status:** Approved (design)
**Branch:** `feat/password-recovery-codes`

## Problem

A user who forgets their password and is **not** an admin and has **no shell
access** to the box cannot recover on their own. Today the only ways to reset a
password are:

- `POST /api/auth/change-password` — requires being logged in **and** knowing
  the current password (`backend/app/api/routes/auth.py:588`).
- Admin reset via `PUT /api/users/{id}` with `{password}` — requires an admin.
- `backend/scripts/reset_password.py` — direct DB write, requires shell access
  to the server.

There is no self-service recovery path for a locked-out user. We want one that
adds **no new email infrastructure** (email was deliberately removed —
migration `042_remove_email_notifications.py`) and keeps the attack surface
minimal.

## Goals

- A locked-out user on the local network can reset their own password using a
  pre-provisioned, single-use **recovery code**.
- Security-first: minimal attack surface, no weakening of existing controls
  (2FA, rate limiting, audit logging, encryption-at-rest).
- Mirror the proven 2FA backup-code mechanism (`totp_service.py`) rather than
  invent a new primitive.

## Non-Goals

- **No email** reset links.
- **No remote (off-LAN) reset.** A user reachable only via VPN/WAN keeps the
  admin / `reset_password.py` fallback. (Explicitly accepted.)
- No change to the existing `change-password` or admin-reset paths.

## Key Decisions (from brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Channel | **LAN-only** | Smallest attack surface; mirrors Setup + PIN-login. A code leaked off-box is useless without local-network presence. |
| Effect of a valid code | **Reset password only — no session/token** | The recovery code replaces *only* the password. The user then logs in normally, so **2FA stays fully enforced**; the code can never become a 2FA bypass. |
| Provisioning | **On-demand in Security settings**, with a recommendation **banner** in user settings when not yet configured | Mirrors 2FA backup-code UX; opt-in but nudged. |
| Scope | **All roles (admin + user)** | Admin lockout is the most dangerous case (no super-admin above). Uniform UX. |
| Mechanism | **Dedicated recovery codes mirroring 2FA backup codes** | Clean boundary between two distinct secrets; single-column migration; reuses a tested pattern. |

### Approaches considered

1. **(Chosen) Dedicated recovery codes mirroring the 2FA backup-code pattern.**
   New encrypted column on `User`, dedicated service, dedicated endpoints.
2. **Reuse 2FA backup codes for both purposes.** Rejected — conflates two
   distinct secrets, a 2FA backup code would also reset the password, and codes
   would only exist when 2FA is enabled.
3. **Generic single-use token table for future reuse.** Rejected — YAGNI /
   over-engineering for a single use case.

## Security: Encryption-at-rest + RBAC (hard requirement)

Recovery codes are a **password-equivalent secret**. They are protected exactly
like 2FA backup codes, on two layers:

- **Hashed, then encrypted at rest.** Stored as a Fernet-encrypted JSON array of
  **SHA-256 hashes** of the codes — never plaintext, never a reversible form.
  Reuses the existing `MultiFernet` mechanism from `totp_service._get_totp_fernet()`
  (`TOTP_ENCRYPTION_KEY`, falling back to `VPN_ENCRYPTION_KEY`; dual-key decrypt).
  A DB dump alone yields neither the codes nor their bare hashes.
- **Plaintext shown exactly once.** Generation/regeneration returns the codes a
  single time in the HTTP response; they are never persisted in plaintext, never
  logged, and cannot be retrieved again.
- **RBAC-gated.** Code *management* (generate/regenerate/status) is bound to the
  **authenticated session** and operates **only on the caller's own account** —
  there is no cross-user code access and no admin endpoint that reveals another
  user's codes. The pre-auth *reset* endpoint is additionally **LAN-gated** and
  consumes a code without ever returning code material or a session.
- **Fail-closed.** If no encryption key is configured, code operations raise
  (same as TOTP/VPN) rather than degrade to plaintext.

Alignment note: the in-flight `2026-06-21-crypto-key-isolation.md` plan aims to
isolate per-domain crypto keys. This feature deliberately reuses the *current*
TOTP/VPN key mechanism (no weakening vs. today). If/when key isolation lands, a
dedicated `RECOVERY_CODES_ENCRYPTION_KEY` slots in via the same
`_get_*_fernet()` shape — called out as follow-up, out of scope here.

## Design

### 1. Data model

One new **nullable** column on `User` (mirrors `totp_backup_codes_encrypted`):

```python
# backend/app/models/user.py
password_recovery_codes_encrypted: Mapped[str | None] = mapped_column(
    Text, nullable=True, default=None
)
```

- `None` ⇒ recovery codes not configured (drives the banner + `configured=false`).
- Value ⇒ Fernet ciphertext of `json.dumps([sha256_hex, ...])`.
- One Alembic migration, chained onto the **real** `alembic heads` (per
  `project_alembic_migration_head_pitfall`). No new table.

### 2. Service — `backend/app/services/recovery_code_service.py`

Mirrors the TOTP backup-code functions; same hash+encrypt helpers (reuse
`totp_service._totp_encrypt`/`_totp_decrypt`, or a shared crypto util factored
out — implementation detail for the plan).

```python
RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_LENGTH = 8  # bytes of entropy per code (token_hex(LENGTH//2)... mirror TOTP format)

def generate_recovery_codes(db: Session, user_id: int) -> list[str]:
    """Generate N high-entropy codes, store hashed+encrypted, return plaintext ONCE.
    Regenerating overwrites the column → all previous codes are invalidated."""

def verify_and_consume_recovery_code(db: Session, user_id: int, code: str) -> bool:
    """Verify a code and consume it (single-use: remove its hash). Returns False on miss."""

def get_recovery_codes_remaining(db: Session, user_id: int) -> int: ...

def has_recovery_codes(db: Session, user_id: int) -> bool:
    """True iff the column is non-null and contains at least one unused code."""
```

Codes are generated with `secrets.token_hex(...)` (CSPRNG), uppercased, format
identical to 2FA backup codes for UI consistency.

### 3. Endpoints (`backend/app/api/routes/auth.py`)

**Authenticated management (RBAC: own account only)** — mirrors the 2FA backup
endpoints:

| Method/Path | Auth | Returns | Notes |
|---|---|---|---|
| `POST /api/auth/recovery-codes` | `get_current_user` | `{ recovery_codes: string[] }` (once) | Generate/regenerate. `@limiter.limit(...)`. Audit-logged. |
| `GET /api/auth/recovery-codes/status` | `get_current_user` | `{ configured: bool, remaining: int }` | Drives the banner. No code material. |

**Pre-auth reset (the "forgot password" flow)** — LAN-gated:

| Method/Path | Gate | Body | Returns |
|---|---|---|---|
| `POST /api/auth/recovery-reset` | **Local channel only** + hard rate limit | `RecoveryResetRequest{ username, recovery_code, new_password }` | `{ message }` — **no token** |

Reset handler order (so a weak password never burns a code):

1. **Pydantic validation** of `RecoveryResetRequest` — `new_password` runs the
   full strength validator (reuse the `RegisterRequest` password rules;
   deliberately **not** a raw `dict` like the `change-password` Known-Gap #8).
   Weak password ⇒ `422` **before** the handler body runs ⇒ code not consumed.
2. **LAN gate** — reuse the local-channel mechanism used by `login-pin`
   (`request.state.channel == "local"` / `is_private_or_local_ip`). Non-local ⇒
   `403`.
3. **Resolve user** by username; **verify + consume** the recovery code.
4. On success: `user_service.update_user_password(...)`; **Samba sync** if
   `user.smb_enabled` (mirror `change_password`'s `samba_service.sync_smb_password`).
5. Audit-log; return generic success. **No access token issued.**

**Anti-enumeration:** unknown username, wrong code, and "no codes configured"
all return the **same** generic failure (`"Invalid username or recovery code"`,
same status) with best-effort uniform timing. Hard rate limit
(`auth_recovery_reset`, on par with login) caps brute force; combined with
LAN-only + 10 single-use high-entropy codes, online guessing is impractical.

### 4. Frontend

- **`client/src/api/recovery-codes.ts`** — new API client mirroring
  `two-factor.ts` (`generateRecoveryCodes`, `getRecoveryCodesStatus`,
  `recoveryReset`).
- **Login page (`Login.tsx`)** — a **"Passwort vergessen?"** link opening a
  reset form (username, recovery code, new password + confirm). Uses the same
  pre-auth `fetch(buildApiUrl(...))` path as PIN-login. A `403` (non-local)
  shows a clear "only available on the local network" message.
- **Security settings** — a "Recovery-Codes" section analogous to the 2FA
  backup-codes UI: generate/regenerate, **show once**, copy/download, remaining
  count.
- **Banner** — in user settings, shown when `status.configured === false`, with
  an explicit recommendation to set up recovery codes.

### 5. Error handling & audit

- Audit via `get_audit_logger_db()`:
  - `recovery_codes_generated` (success)
  - `password_reset_via_recovery` (success)
  - `password_reset_via_recovery_failed` (bad code / unknown user / non-local)
- **Codes are never logged** at any level. Failures log username + reason only.
- Fail-closed on missing encryption key (raise, like TOTP/VPN).
- 2FA remains structurally intact: reset issues no session, so the subsequent
  normal login still enforces TOTP.

### 6. Testing (mirror `backend/tests/security/test_totp_2fa.py`)

**Service:**
- `generate_recovery_codes` returns `RECOVERY_CODE_COUNT` codes.
- A code verifies once, then is consumed (second use fails); remaining count
  decrements.
- Regenerate invalidates all previous codes.
- `has_recovery_codes` reflects configured/empty state.

**Endpoints:**
- Management requires auth; `POST` returns codes once; status endpoint shape.
- Reset (happy path): valid code + strong password ⇒ password changed, code
  consumed, **no token in response**, subsequent login with the new password
  succeeds.
- Reset rejects: wrong code, unknown user (generic identical response), **weak
  password ⇒ 422 and code NOT consumed**, reused code, **non-local channel ⇒ 403**.
- 2FA still required at login after a recovery reset (when enabled).
- Samba sync invoked when `smb_enabled`.

## Files to add / modify

**Backend**
- `backend/app/models/user.py` — new column.
- `backend/alembic/versions/<rev>_add_password_recovery_codes.py` — migration.
- `backend/app/services/recovery_code_service.py` — new service.
- `backend/app/schemas/auth.py` — `RecoveryResetRequest` (+ response schema).
- `backend/app/api/routes/auth.py` — 3 endpoints.
- `backend/app/core/rate_limiter.py` — `auth_recovery_reset` limit key.
- `backend/tests/security/test_recovery_codes.py` (+ endpoint tests).

**Frontend**
- `client/src/api/recovery-codes.ts` — new client.
- `client/src/pages/Login.tsx` — "Passwort vergessen?" link + reset form.
- Security settings component — recovery-codes section + banner.
- i18n strings.

**Docs**
- `backend/app/models/CLAUDE.md`, `backend/app/services/CLAUDE.md`,
  `backend/app/api/CLAUDE.md` — keep indexes in sync.

## Open follow-ups (out of scope)

- Dedicated `RECOVERY_CODES_ENCRYPTION_KEY` once key isolation
  (`2026-06-21-crypto-key-isolation.md`) lands.
- Optional: surface recovery-code management in the TUI users screen.
