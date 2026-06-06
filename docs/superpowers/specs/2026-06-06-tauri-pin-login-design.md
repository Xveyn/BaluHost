# Tauri PIN Login — Design Spec

**Date:** 2026-06-06
**Status:** Approved
**Author:** Sven (Xveyn) + Claude (via brainstorming session)
**Branch:** `feat/tauri-pin-login`

## Problem

Logging into the BaluHost Companion (Tauri) app — which runs **on the server** and talks to the
backend over the local Unix socket (`channel=local`) — currently requires the full username +
password (+ TOTP, if 2FA is enabled), every time. For a desktop app you open repeatedly on a
trusted machine, typing a long password each time is friction.

We want to let users sign in with a short **PIN instead of their password** in the Tauri app —
but only as a hardened convenience, never a weakening.

## Goals

- A user may sign in to the **Tauri app** with a numeric **PIN in place of their password**.
- Only available when the user has **2FA (TOTP) enabled** — 2FA is the security anchor.
- A short **admin-configured grace window** during which the PIN **alone** suffices; outside it,
  the login is genuine **PIN + TOTP**.
- Reuse the existing auth building blocks (`2fa_pending`/`verify-2fa`, `pwd_context`/bcrypt, the
  channel mechanism, audit logger) — minimal new surface.
- Password login stays unchanged and remains available everywhere (incl. the Tauri app) as fallback.

## Non-Goals

- PIN login over the **remote/TCP** channel — hard invariant: PIN login is **local-channel only**.
  A 4-digit PIN over the internet would be trivially brute-forced.
- Replacing 2FA. The grace window is opened **only** by a successful TOTP verification.
- Step-up 2FA for sensitive in-session actions — tracked separately as a future idea
  ([#169](https://github.com/Xveyn/BaluHost/issues/169)).
- Per-device PIN binding / multiple PINs per user — one PIN per user (v1).
- Client-side token vault (PIN unlocking a stored refresh token) — rejected; keeps security on the
  server auth layer rather than local storage.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Factor model | PIN replaces the **password**; TOTP still required, but a grace window allows PIN-only within it |
| Grace window length | **Admin-global policy** (one system-wide setting), default 24h, hard cap 7 days |
| Grace reset | **Absolute** — window runs from the last successful TOTP; PIN-only logins do **not** extend it |
| PIN policy | Numeric, 4–8 digits; reject all-same (`0000`) and ascending/descending sequences (`1234`/`9876`) |
| Scope | Any user with 2FA enabled may set up a PIN (not admin-only) |
| PIN management | Set/change/remove from anywhere when authenticated **+ fresh TOTP code**; only PIN *login* is local-only |
| Policy change | Admin (`get_current_admin`) |
| Brute-force | 5 failed PIN attempts → 15-min lockout; reset on success; rate-limited + audited |

## Architecture

```
Tauri-App (channel=local)
  │
  ▼
POST /api/auth/login-pin   { username, pin }     ← local channel ONLY (else 403)
  │
  ├─ global policy pin_login_enabled?   (else refuse → use password)
  ├─ user found, totp_enabled, not pin-locked?
  ├─ verify pin against pin_hash (bcrypt, constant-time)
  │
  ├─ now < pin_grace_until ?
  │     YES → return access token directly            (PIN-only, within window)
  │     NO  → return 2fa_pending token (existing)      (window expired)
  │             │
  │             ▼
  │        POST /api/auth/verify-2fa { pending_token, code }   ← existing, minimally extended
  │             ├─ verify TOTP or backup code (unchanged)
  │             ├─ if user has pin_hash: pin_grace_until = now + policy.window   (absolute)
  │             └─ return access token
  └─ ...
```

**Core idea:** one new local login path; everything else is existing machinery.
`create_2fa_pending_token` / `verify-2fa` / `pwd_context` / audit logger / `request.state.channel`
already exist. New: `login-pin`, PIN management endpoints, an admin policy singleton, and four
user columns.

## Components

### Data model — 4 new columns on `users` (one additive migration)

| Column | Type | Purpose |
|---|---|---|
| `pin_hash` | `String(255)`, nullable | bcrypt hash of the PIN (same `pwd_context` as the password) |
| `pin_grace_until` | `DateTime(timezone=True)`, nullable | absolute grace-window expiry; set on `verify-2fa` success when a PIN is configured |
| `pin_failed_attempts` | `Integer`, default 0, server_default "0" | brute-force counter |
| `pin_locked_until` | `DateTime(timezone=True)`, nullable | PIN lockout expiry |

### Admin policy — new singleton model `AuthPolicy` (id=1, mirrors `monitoring_config`)

| Field | Default | Constraint |
|---|---|---|
| `pin_login_enabled` | `true` | global kill switch |
| `pin_grace_window_seconds` | `86400` (24h) | 60 ≤ x ≤ `604800` (7 days), enforced in the Pydantic schema |

New file: `backend/app/models/auth_policy.py`, migration, schema `backend/app/schemas/auth_policy.py`,
service helper to read-or-create the singleton.

### Endpoints

| Endpoint | Auth / Gate | Behavior |
|---|---|---|
| `POST /api/auth/login-pin` | **pre-auth, local-only** (inline `request.state.channel == "local"`, else 403 `local_channel_required`); rate-limited | `{username, pin}` → access token (within window) **or** `TwoFactorRequiredResponse` (window expired). Refuses if policy disabled, no PIN, no 2FA, or pin-locked. |
| `POST /api/auth/verify-2fa` | existing | **extended:** on success, if user has `pin_hash`, set `pin_grace_until = now + policy.window` |
| `GET /api/auth/pin` | `get_current_user` | `{ pin_enabled: bool }` for the UI |
| `POST /api/auth/pin` | `get_current_user` + valid **TOTP code** + `totp_enabled` | set/replace PIN (PIN-policy validated); audit `pin_set` |
| `DELETE /api/auth/pin` | `get_current_user` + valid **TOTP code** | remove PIN (clears `pin_hash`, grace, lock); audit `pin_removed` |
| `GET /api/admin/auth-policy` | `get_current_admin` | read policy |
| `PUT /api/admin/auth-policy` | `get_current_admin` | update policy (cap enforced); audit |

### PIN policy validator

Shared helper (in `backend/app/schemas/auth.py`, used by the `POST /api/auth/pin` body):

```
- must match ^\d{4,8}$
- reject if all digits identical (0000, 1111, …)
- reject if strictly ascending consecutive (1234, 2345, …, 5678)
- reject if strictly descending consecutive (4321, 9876, …)
```

Clear `400` error messages per rule.

## Data Flow / Login sequence (Tauri)

```
1. App detects local channel (existing isTauri / channel-status).
2. User picks "Sign in with PIN" → enters username + PIN.
3. POST /api/auth/login-pin:
     a. channel != local  → 403  (never reachable from the Tauri UDS path)
     b. policy.pin_login_enabled == false → 401 "PIN login disabled"
     c. user missing / no pin_hash / not totp_enabled → 401 generic "Invalid credentials"
        (do not reveal which)
     d. pin_locked_until in the future → 423/401 "locked, use password"
     e. bcrypt verify pin → wrong: failed_attempts++, maybe lock, audit pin_login_failed, 401
     f. correct:
          - reset failed_attempts
          - now < pin_grace_until → access token, audit pin_login_grace
          - else → 2fa_pending token, audit pin_login_2fa_required
4. If 2fa_pending: user enters TOTP → POST /api/auth/verify-2fa (existing path)
     → sets pin_grace_until = now + policy.window; returns access token.
```

## Edge Cases

| Case | Handling |
|---|---|
| **User disables 2FA** | Clear `pin_hash`, `pin_grace_until`, `pin_locked_until`, `pin_failed_attempts` in the disable-2FA path — a PIN must never outlive its 2FA anchor |
| Remote call to `login-pin` | 403 `local_channel_required` (audit `pin_login_remote_denied`); the Tauri UDS path is the only way in |
| Policy `pin_login_enabled = false` | `login-pin` refuses; password login unaffected |
| No PIN set / wrong username | Generic 401 (no user enumeration) |
| PIN locked | Refuse PIN login until `pin_locked_until`; password+TOTP still works and is the recovery path |
| Window expired | `2fa_pending` path; only a successful TOTP reopens the window |
| Backup code at the TOTP step | Works unchanged (reuses `verify-2fa`) |
| Setting PIN without 2FA | Rejected (`totp_enabled` required) |
| Multiple Uvicorn workers / local + remote process | `pin_grace_until` is a DB column → consistent across processes; only the local process serves `login-pin` |

## Security Invariants

- **PIN login is local-channel only** — enforced in the endpoint, audited on violation.
- PIN is **never logged**; stored only as a bcrypt hash; verified in constant time via `pwd_context`.
- The grace window is **server-authoritative and absolute**, set **only** by a successful TOTP.
- 2FA remains mandatory: no PIN exists without `totp_enabled`, and disabling 2FA destroys the PIN.
- PIN management requires a **fresh TOTP code**, so a hijacked session cannot silently plant a PIN.
- Rate-limiting + lockout bound the 4-digit brute-force surface; local channel bounds exposure to
  physical presence.

Cross-checked against `.claude/rules/security-agent.md`: auth dependencies present, Pydantic schemas
(no raw dicts), audit logging for all PIN/policy events, no `shell=True`, no raw SQL, no secret
logging, secrets validation untouched.

## Components / Files

### New

- `backend/app/models/auth_policy.py` — `AuthPolicy` singleton model
- `backend/alembic/versions/<rev>_add_pin_columns_and_auth_policy.py` — migration (4 user columns + `auth_policy` table)
- `backend/app/schemas/auth_policy.py` — `AuthPolicyResponse`, `AuthPolicyUpdate` (cap-validated)
- `backend/app/services/auth_policy.py` — read-or-create singleton, get window seconds
- `backend/tests/api/test_pin_login.py`, `backend/tests/api/test_pin_management.py`, `backend/tests/api/test_auth_policy.py`
- `client/src/api/pin.ts` — PIN status/set/remove + login-pin client
- `client/src/components/settings/DesktopPinSettings.tsx` — set/change/remove PIN (TOTP-gated)
- `client/src/components/admin/AuthPolicySettings.tsx` — admin window + kill switch
- Vitest specs for the above

### Modified

- `backend/app/models/user.py` — 4 columns
- `backend/app/api/routes/auth.py` — `login-pin`, `GET/POST/DELETE /pin`, extend `verify-2fa` to set the window
- `backend/app/schemas/auth.py` — `PinLoginRequest`, `PinSetRequest` (+ PIN validator), `PinStatusResponse`
- `backend/app/api/routes/` (admin router) — `GET/PUT /admin/auth-policy`
- `backend/app/services/totp_service.py` (or the disable-2FA route) — clear PIN fields when 2FA is disabled
- `backend/app/core/rate_limiter.py` — `auth_pin_login` limit key
- `client/src/pages/Login.tsx` — PIN login option in the Tauri/local context (+ TOTP step reuse)
- `client/src/i18n/locales/{de,en}/*.json` — PIN + policy strings

## Build Order

1. Migration + `User` columns + `AuthPolicy` model + policy service (DB foundation)
2. PIN policy validator + `PinSetRequest`/`PinLoginRequest` schemas (TDD)
3. PIN management endpoints (`GET/POST/DELETE /pin`) + clear-on-2FA-disable
4. `login-pin` endpoint (local-only, lockout, window vs 2fa_pending) + `verify-2fa` window-set
5. Admin auth-policy endpoints
6. Frontend: PIN settings, admin policy, Tauri login option, i18n
7. Tests green (backend + frontend), manual smoke

## Tests

**Backend:**
- PIN validator: accepts `4827`; rejects `0000`, `1111`, `1234`, `9876`, `123` (too short), `abc1`.
- `login-pin`: remote → 403; within window → access token; expired → `2fa_pending`; policy-disabled → refuse; no PIN → 401; locked → refuse.
- `verify-2fa`: sets `pin_grace_until = now + window` when PIN present; unchanged when no PIN.
- Lockout: 5 wrong PINs → locked; correct PIN resets counter.
- **Disable 2FA clears PIN** fields.
- Auth-policy: GET/PUT, cap (`> 604800` rejected, `< 60` rejected), admin-only.
- PIN management requires valid TOTP; `totp_enabled` required.

**Frontend:** Vitest for the PIN login flow (token vs TOTP-challenge branches), PIN settings (set/remove with TOTP), admin policy form; smoke that the PIN option only shows in the local/Tauri context and only when 2FA is enabled.

## Manual Smoke (dev)

1. Enable 2FA for a user; set a PIN in Security settings (enter TOTP).
2. In the Tauri/local app: sign in with username + PIN + TOTP → window opens.
3. Sign out, sign in again within the window with PIN only → straight in.
4. Advance past the admin window (or shorten it) → PIN now prompts for TOTP again.
5. Wrong PIN ×5 → locked; password+TOTP still works.
6. Disable 2FA → PIN is gone; `login-pin` refuses.
7. `curl` `login-pin` over TCP → 403 `local_channel_required`.

## Risks / Trade-offs

1. **PIN-only within the window is a single secret (+ local channel).** Bounded by: local-channel
   (physical presence), admin-tunable window, absolute (non-sliding) expiry forcing periodic TOTP,
   and lockout. The admin window length is the security/convenience dial.
2. **Admin-global window** (not per-user) — simpler; one knob. Per-user could come later if needed.
3. **bcrypt on a 4-digit PIN** is cheap to brute-force offline if the hash leaks — but the hash lives
   in the same DB as password hashes; a DB compromise is already game-over. Lockout + local-only
   bound the online attack.
