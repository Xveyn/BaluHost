# Password Recovery Codes — Self-Service Reset (LAN-only)

**Date:** 2026-06-29
**Status:** Approved (design) — revised after critical review
**Branch:** `feat/password-recovery-codes`

> **Revision note (2026-06-29, post-review):** Three parallel review agents
> (security, correctness, design) found one critical design flaw and several
> hardening gaps. This spec is the corrected version. Key changes vs. the first
> draft: the LAN gate uses **`is_private_or_local_ip(request.client.host)`**
> (the Setup-wizard precedent) — **not** the `request.state.channel` mechanism,
> which is a same-host-UDS signal that is hardwired to `remote` in production and
> would 403 every web client. Generation now requires **step-up auth**, reset
> **revokes the user's sessions**, plus timing/field hardening. See "Review
> findings folded in" at the end.

## Problem

A user who forgets their password and is **not** an admin and has **no shell
access** cannot recover on their own. Today: `change-password` needs the old
password; admin reset needs an admin; `backend/scripts/reset_password.py` needs
shell access. There is no self-service path. We want one that adds **no email
infrastructure** (email was deliberately removed — migration
`042_remove_email_notifications.py`) and keeps the attack surface minimal.

## Goals / Non-Goals

**Goals:** a locked-out user on the local network resets their own password using
a pre-provisioned single-use recovery code; security-first; mirror the proven 2FA
backup-code mechanism.

**Non-Goals:** no email reset links; no off-LAN reset (a VPN/WAN-only user keeps
the admin / `reset_password.py` fallback); no change to `change-password` or
admin-reset.

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Channel/exposure | **LAN-only via `is_private_or_local_ip(request.client.host)`** | Realizes the user's "local network only" choice. Works in production because uvicorn runs `--proxy-headers --forwarded-allow-ips=127.0.0.1` (tested in `backend/tests/test_deploy_proxy_headers.py`), so `request.client.host` is the **real** client IP and X-Forwarded-For is only trusted from the local nginx (not spoofable). WireGuard-VPN clients fall in the private range and count as local — consistent with the system's trust model (VPN is the encrypted remote-access path). |
| Effect of a valid code | **Reset password only — no session/token** | The code replaces only the password. The user logs in normally afterward, so **2FA stays enforced**; the code can never become a 2FA bypass. |
| Session handling on reset | **Revoke all of the user's refresh tokens** | A recovery reset is an "I lost control" event. `TokenService.revoke_all_user_tokens` evicts an attacker holding a still-valid refresh token. |
| Code generation | **Requires step-up auth** | A recovery code is a password-equivalent, pre-auth-usable secret. Mirrors `set_pin` (fresh TOTP) so a hijacked session can't silently mint codes. Step-up = fresh TOTP/backup code when 2FA is enabled, else current-password re-entry. |
| Provisioning | **On-demand in Security settings** + a recommendation **banner** when not configured | Opt-in, nudged; mirrors 2FA backup-code UX. |
| Scope | **All roles (admin + user)** | Admin lockout is the worst case (no super-admin above). |
| Mechanism | **Dedicated recovery codes mirroring 2FA backup codes** | Clean boundary between two distinct secrets; single-column migration. |

### Approaches considered

1. **(Chosen)** Dedicated recovery codes mirroring the 2FA backup-code pattern.
2. Reuse 2FA backup codes for both purposes — rejected (conflates secrets; only
   exists when 2FA is enabled; a 2FA code would also reset the password).
3. Generic single-use token table — rejected (YAGNI).

## Security: Encryption-at-rest + RBAC (hard requirement)

Recovery codes are a **password-equivalent secret**, protected like 2FA backup
codes:

- **Hashed, then encrypted at rest.** A Fernet-encrypted JSON array of SHA-256
  hashes — never plaintext, never a bare hash on disk. Uses a shared public
  helper `app/core/crypto.py` (`encrypt_at_rest`/`decrypt_at_rest`, same
  `MultiFernet` key resolution as TOTP: `TOTP_ENCRYPTION_KEY` → `VPN_ENCRYPTION_KEY`).
  `totp_service._totp_encrypt/_totp_decrypt` are refactored to delegate to this
  helper (no behavior change, no private cross-module imports). A DB dump alone
  yields neither codes nor bare hashes.
- **Plaintext shown once.** Generation returns codes a single time; never
  persisted in plaintext, never logged, not retrievable again.
- **RBAC-gated + step-up.** Management (generate/status) is bound to the
  authenticated session and the caller's **own** account only — no cross-user
  access, no admin endpoint that reveals codes. Generation additionally requires
  step-up auth. The pre-auth reset is LAN-gated and returns no session.
- **Fail-closed.** No encryption key → operations raise (same as TOTP/VPN).

Alignment note: the in-flight `2026-06-21-crypto-key-isolation.md` plan can later
slot a dedicated `RECOVERY_CODES_ENCRYPTION_KEY` into `app/core/crypto.py` — this
spec creates that seam (the shared helper) without weakening today's posture.

## Design

### 1. Data model

One new **nullable** column on `User` (mirrors `totp_backup_codes_encrypted`):

```python
# backend/app/models/user.py
password_recovery_codes_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

`None` ⇒ not configured (drives the banner + `configured=false`); value ⇒ Fernet
ciphertext of `json.dumps([sha256_hex, ...])`. One Alembic migration chained onto
the **real** `alembic heads` (per `project_alembic_migration_head_pitfall`). No
new table.

### 2. Shared crypto helper — `backend/app/core/crypto.py`

Public API extracted so a second consumer doesn't import TOTP's underscore-private
functions:

```python
def get_at_rest_fernet() -> MultiFernet   # TOTP_ENCRYPTION_KEY then VPN_ENCRYPTION_KEY; raises if none
def encrypt_at_rest(plaintext: str) -> str
def decrypt_at_rest(ciphertext: str) -> str
```

`totp_service._totp_encrypt/_totp_decrypt` become thin delegates (names kept so
existing imports/tests are untouched).

### 3. Service — `backend/app/services/recovery_code_service.py`

```python
RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_HEX_BYTES = 5  # → 10 hex chars / 40 bits per code

def generate_recovery_codes(db, user_id) -> list[str]   # store hashed+encrypted, return plaintext once; regenerate overwrites
def verify_and_consume_recovery_code(db, user_id, code) -> bool   # single-use; never raises
def get_recovery_codes_remaining(db, user_id) -> int
def has_recovery_codes(db, user_id) -> bool
```

Codes: `secrets.token_hex(5).upper()` (CSPRNG, 40 bits). Verify uppercases input.

### 4. Endpoints (`backend/app/api/routes/auth.py`)

**Authenticated management (RBAC: own account; step-up on generate):**

| Method/Path | Auth | Body | Returns |
|---|---|---|---|
| `POST /api/auth/recovery-codes` | `get_current_user` **+ step-up** | `RecoveryCodesGenerateRequest{ code?, current_password? }` | `{ recovery_codes: string[] }` once |
| `GET /api/auth/recovery-codes/status` | `get_current_user` | — | `{ configured: bool, remaining: int }` |

Step-up rule (mirror `set_pin` + `change_password`): if `user.totp_enabled`,
require a fresh TOTP/backup code via `_verify_fresh_totp`; else require
`current_password` re-verified via `auth_service.authenticate_user`. On failure →
`401`.

**Pre-auth reset (LAN-only):**

| Method/Path | Gate | Body | Returns |
|---|---|---|---|
| `POST /api/auth/recovery-reset` | `is_private_or_local_ip(client.host)` + `auth_recovery_reset` limit | `RecoveryResetRequest{ username, recovery_code, new_password }` | `{ message }` — no token |

Reset handler order:

1. **Pydantic validation:** `new_password` runs `_validate_password_strength`
   (field_validator, not a raw `dict`); `username` ≤ 64 and `recovery_code` ≤ 32
   length bounds (the endpoint is pre-auth and writes `username` to the audit log
   — bound the attacker-controlled fields). A weak password ⇒ `422` before the
   handler ⇒ no code consumed.
2. **LAN gate:** `is_private_or_local_ip(request.client.host)` — else `403`
   `{"error": "local_network_required", "message": ...}` (audit-logged).
3. **Resolve + verify:** look up by username; treat `is_active=false` users as
   not-found. **Timing equalization:** on unknown/disabled user, run a dummy
   decrypt+hash so the response time matches the real path (no enumeration oracle).
   Verify + consume the code.
4. **On success:** `update_user_password`; **revoke all the user's refresh tokens**
   (`TokenService.revoke_all_user_tokens(db, user.id, reason="password_reset_via_recovery")`);
   **Samba sync in try/except** if `smb_enabled` (best-effort: log failure, still
   succeed); audit-log; return generic success. **No token issued.**

**Anti-enumeration:** unknown user, disabled user, and wrong code all return the
same `401 "Invalid username or recovery code"` with timing equalized.

### 5. Frontend

- **`client/src/api/recovery-codes.ts`** — typed client (generate w/ step-up,
  status, reset). Reset uses the raw-`fetch` pre-auth path (no bearer).
- **Login page (`Login.tsx`)** — a "Passwort vergessen?" link (placed inside the
  existing `pinMode` else-branch) opening `ForgotPasswordForm` (username, code,
  new password + confirm). A `403` shows "only available on the local network".
- **Security settings (`SettingsPage.tsx`)** — a `RecoveryCodesCard` next to
  `TwoFactorCard`: generate/regenerate (with the step-up prompt), **show once**,
  remaining count, and a **Download .txt** (Blob) plus copy. **Copy guards
  `navigator.clipboard?.writeText`** and toasts only on success (production is
  HTTP-over-LAN where `clipboard` is undefined) — the visible codes + download are
  the reliable path.
- **Banner** — shown when `status.configured === false`, recommending setup. A
  regenerate prompt warns it invalidates existing codes.
- **a11y:** real `<label>`/`aria-label` on every input (no placeholder-only labels).
- **i18n:** strings go into the existing `auth`/`settings` locale namespaces (the
  app is fully i18n'd; the entry point is a German string on the most-seen page).

### 6. Error handling & audit

- Audit via `get_audit_logger_db()`: `recovery_codes_generated`,
  `recovery_codes_generate_denied` (failed step-up), `password_reset_via_recovery`
  (success), `password_reset_via_recovery_failed` (bad code / unknown / disabled /
  non-local). **Codes never logged.**
- Fail-closed on missing encryption key.
- Reset issues no session → 2FA enforced at the next login.

### 7. Testing

**Service:** generate → 10 codes; single-use consume; regenerate invalidates old;
remaining count; `has_recovery_codes`.

**Crypto helper:** round-trips; `totp_service` delegates still decrypt
existing-format data (no 2FA regression).

**Endpoints:**
- generate requires auth **and** step-up (wrong/missing TOTP or password → 401;
  correct → codes).
- status shape.
- reset happy path: valid code + strong password ⇒ password changed, code
  consumed, **no token**, login with new password works, **pre-existing refresh
  token rejected** after reset.
- reset rejects: wrong code, unknown user (generic identical), **disabled user
  (generic)**, **weak password ⇒ 422 and code NOT consumed**, reused code,
  **non-local IP ⇒ 403**.
- **2FA still required at login after reset** (when enabled).
- **audit rows** asserted for success + non-local-denied.
- Samba sync invoked when `smb_enabled`; a sync failure still returns success.

Tests use a **dedicated throwaway user** (not the shared seeded fixture) and learn
its username from the fixture constant (no `/auth/me` round-trip). The non-local
case is simulated by overriding the client IP / `is_private_or_local_ip`.

## Files to add / modify

**Backend:** `models/user.py` (+column, +migration); `core/crypto.py` (new);
`services/totp_service.py` (delegate); `services/recovery_code_service.py` (new);
`schemas/auth.py` (`RecoveryCodesGenerateRequest`, `RecoveryResetRequest`,
`RecoveryCodesResponse`, `RecoveryCodesStatusResponse`); `core/rate_limiter.py`
(`auth_recovery_reset`); `api/routes/auth.py` (3 endpoints); tests under
`tests/services/`, `tests/core/`, `tests/api/`.

**Frontend:** `api/recovery-codes.ts` (+test under `src/__tests__/api/`);
`components/auth/ForgotPasswordForm.tsx`; `pages/Login.tsx`;
`components/settings/RecoveryCodesCard.tsx`; `pages/SettingsPage.tsx`; i18n locales.

**Docs:** `backend/app/services/CLAUDE.md`, `backend/app/api/CLAUDE.md`,
`backend/app/core/CLAUDE.md`.

## Review findings folded in

- **CRITICAL — wrong gate.** `request.state.channel == "local"` is a same-host-UDS
  signal (Tauri local-admin), hardwired to `remote` in the deployed backend (no
  UDS unit installed) → would 403 every LAN web client. **Fixed:** use
  `is_private_or_local_ip(request.client.host)`, valid because of the deployed
  `--proxy-headers --forwarded-allow-ips=127.0.0.1` anti-spoof pin. Removed the
  false "channel == local / is_private_or_local_ip" equivalence from the design.
- **HIGH — no session revocation.** Fixed: `revoke_all_user_tokens` on reset.
- **MUST — no step-up on generation.** Fixed: fresh TOTP (2FA) or current password.
- **MUST — clipboard silently fails on HTTP.** Fixed: guard + Download .txt fallback.
- **Hardening:** timing equalization on unknown/disabled user; length-bounded
  `username`/`recovery_code`; `is_active=false` treated as not-found; Samba sync
  best-effort; shared `core/crypto.py` instead of private `_totp` imports.
- **Test/infra fixes:** dedicated throwaway user; audit-row + 2FA-after-reset
  assertions; **vitest test under `src/__tests__/api/`** (the only path vitest
  collects); Login.tsx insertion inside the `pinMode` else-branch.
- **Accepted as-is:** JSON-blob column (mirrors 2FA, proportionate for a NAS);
  in-memory per-IP rate limiter resets on restart and is per-worker (existing
  Known Gap; brute-forcing one of 10×40-bit single-use codes is already
  negligible); no dedicated per-account lockout (LAN-gate + step-up + entropy make
  it unnecessary).

## Open follow-ups (out of scope)

- Dedicated `RECOVERY_CODES_ENCRYPTION_KEY` once key isolation lands (the
  `core/crypto.py` seam is ready).
- Same session-revocation hardening for `change_password` (separate issue per the
  repo's Nebenbefund rule).
- Optional `password_recovery_codes_generated_at` timestamp for a "generated on X"
  UI hint.
