# BaluHost Security Audit Report

**Date**: March 16, 2026 | **Branch**: `development` | **Production**: Debian 13, PostgreSQL 17.7

Reviewed: 44 route modules, all services, frontend, dependencies, middleware, config.
Methodology: Parallel code review agents + manual analysis + OWASP Top 10:2025 mapping.

---

## CRITICAL (Immediate Action Required)

### C1. Token Revocation System Is Completely Inoperative

**Files**: `backend/app/services/auth.py:63`, `backend/app/schemas/auth.py:91`, `backend/app/core/security.py`

Three interrelated bugs render the entire JTI-based revocation system (Security Fix #6) ineffective:

1. **`auth_service.decode_token()` hardcodes `token_type="access"`** — The refresh endpoint accepts access tokens as refresh tokens (token type confusion). Actual refresh tokens (`type="refresh"`) are **rejected**.
2. **JTI is never mapped in `TokenPayload`** — `jti` always remains `None`, so `token_service.is_token_revoked()` is never called.
3. **Mobile "Refresh Token" is an Access Token** (`mobile.py:268`) — Uses `create_access_token()` with 30-day TTL instead of `create_refresh_token()`. No JTI, no revocation possible.

**Impact**: No token can be revoked server-side. Stolen tokens remain valid until expiration.

**Fix**:
- Extend `auth_service.decode_token()` with a `token_type` parameter; the refresh endpoint must pass `token_type="refresh"`
- Map JTI from decoded payload into `TokenPayload`: `jti=decoded.get("jti")`
- Mobile: use `create_refresh_token()` instead of `create_access_token()`, store JTI in `RefreshToken`

### C2. Logout Does Not Invalidate Tokens Server-Side

**File**: `backend/app/api/routes/auth.py:484-487`

The `/logout` endpoint returns `{"message": "Logged out"}` without revoking refresh tokens. The `RefreshToken.revoke()` method exists but is never called. Tests explicitly confirm: "refresh token revocation not yet implemented."

**Impact**: Combined with C1 — stolen tokens cannot be invalidated.

**Fix**: Call `token_service.revoke_all_user_tokens(db, current_user.id, reason="logout")` in the logout handler.

### C3. Access Tokens Live 12 Hours Instead of 15 Minutes

**Files**: `backend/app/core/config.py:37`, `backend/app/services/auth.py:49`

`auth_service.create_access_token()` uses `settings.token_expire_minutes` (720 min = 12h) instead of `settings.ACCESS_TOKEN_EXPIRE_MINUTES` (15 min). The short-TTL design is completely undermined.

**Impact**: C1 + C2 + C3 combined = a stolen token is usable for **12 hours** and **cannot be revoked**.

**Fix**: Use `settings.ACCESS_TOKEN_EXPIRE_MINUTES` instead of `settings.token_expire_minutes`. Remove the legacy field or add a deprecation warning.

### C4. Prometheus Metrics Without Authentication

**File**: `backend/app/api/routes/metrics.py:483-509`

`GET /api/metrics` uses `get_current_user_optional` — returns full system metrics (CPU, RAM, disk, RAID status, SMART, user count, version) to **any unauthenticated requester**.

**Impact**: Complete system fingerprinting for attackers on the network.

**Fix**: Use `get_current_admin` as dependency. For Prometheus scraping: validate a dedicated scrape secret via query parameter.

---

## HIGH (Fix Promptly)

### H1. `get_current_user` Does Not Check `is_active`

**File**: `backend/app/api/deps.py:89-105`

A deactivated user with a valid JWT can continue making API requests. The API key path checks `is_active`, but the JWT path does not.

**Fix**: After `user = user_service.get_user(payload.sub, db=db)`, check: `if not user.is_active: raise HTTP 401`.

### H2. IDOR in Mobile Camera/Sync Endpoints

**File**: `backend/app/api/routes/mobile.py:363-454`

`GET/PUT /mobile/camera/settings/{device_id}`, `GET/POST /mobile/sync/folders/{device_id}`, `DELETE /mobile/sync/folders/{folder_id}` — no ownership check. Any authenticated user can read/write settings of other users' devices.

**Fix**: In each affected handler, first call `MobileService.get_device(db, device_id, user_id=current_user.id)` and return 404 if not found.

### H3. Brute-Force Counter Resets After Alert

**File**: `backend/app/api/routes/auth.py:72`

After 5 failed attempts, `_failed_login_attempts[ip] = []` — counter reset to zero. Attacker gets unlimited new 5-attempt windows. No blocking, no cooldown.

**Fix**: Do not reset the counter. Let TTL-based expiry run its course naturally. Optionally: temporary IP blocking after repeated alerts.

### H4. 2FA Verification Only Rate-Limited by IP

**File**: `backend/app/api/routes/auth.py:114`

5/min per IP, but not per user. TOTP = 6 digits = 1M possibilities. An attacker with multiple IPs or a multi-worker setup can brute-force TOTP codes.

**Fix**: Key the rate limit by `user_id` from the pending token's `sub` claim, not just by IP.

### H5. TOTP Key Falls Back to VPN Encryption Key

**File**: `backend/app/services/totp_service.py:33-34`

```python
key = settings.totp_encryption_key or settings.vpn_encryption_key
```

Without `TOTP_ENCRYPTION_KEY`, TOTP secrets are encrypted with the VPN key. Compromise of one key compromises both systems.

**Fix**: Require `TOTP_ENCRYPTION_KEY` as a separate key, validate at startup, do not allow fallback.

### H6. Open Registration Enabled by Default in Production

**File**: `backend/app/core/config.py:43`

`registration_enabled` defaults to `True`, no production validator. Anyone on the network can create accounts.

**Fix**: Add a production validator analogous to `SECRET_KEY` that rejects or warns when `registration_enabled=True` in production. Default to `False` in production.

### H7. `passlib` Is Unmaintained (No Release Since 2022)

**File**: `backend/pyproject.toml:17`

Also blocks `bcrypt` updates (pinned to `<4.1.0`). No security patches.

**Fix**: Migrate to direct `bcrypt` usage or `argon2-cffi`. Existing hashes are compatible.

### H8. VPN Keys Stored in Plaintext When `VPN_ENCRYPTION_KEY` Is Missing

**File**: `backend/app/services/vpn/service.py:43-49`

Documentation states "fails loudly if missing" — in reality, only `logger.warning` is emitted and the key is written to the database unencrypted.

**Fix**: Raise `ValueError` instead of silent fallback, or write an audit log entry.

### H9. SMART Self-Test: Unvalidated `device` Parameter

**File**: `backend/app/services/hardware/smart/scheduler.py:76`

```python
result = subprocess.run(["sudo", "-n", smartctl, "-t", test_type, device], ...)
```

`device` is passed directly to `smartctl` without allowlist validation (no `shell=True`, but missing input validation).

**Fix**: Regex validation: `re.fullmatch(r"/dev/(sd[a-z][0-9]?|nvme[0-9]+n[0-9]+|hd[a-z])", device)`, analogous to `_normalize_device()` in the RAID backend.

### H10. WebSocket Fallback Passes Full Access Token in URL

**File**: `client/src/hooks/useNotificationSocket.ts:82-86`

If the WS token endpoint fails, the full access token is passed as a query parameter — appears in Nginx logs, browser history, referrer headers.

**Fix**: Remove the fallback. On WS token failure: connection error instead of token leak. Fail closed.

---

## MEDIUM (Should Be Fixed)

| # | Finding | File | Fix |
|---|---------|------|-----|
| M1 | Password change does not revoke active refresh tokens | `routes/auth.py:438` | Call `token_service.revoke_all_user_tokens()` |
| M2 | Audit logs accessible to all users, not admin-only | `routes/logging.py:291` | Use `get_current_admin` or restrict non-admin visibility |
| M3 | CSP `connect-src https:` allows exfiltration to any HTTPS host | `security_headers.py:43` | Restrict to `'self'` |
| M4 | VPN server config uses manual role check instead of `get_current_admin` | `routes/vpn.py:527` | Use standard dependency |
| M5 | Chunked upload: no upper limit for `total_size`, no check `> 0` | `routes/chunked_upload.py:128` | `Field(..., gt=0, le=MAX_UPLOAD)` |
| M6 | Chunked upload: race condition on `next_chunk_index` | `files/chunked_upload.py:165` | Hold session lock during chunk write |
| M7 | Frontend password minimum (6 characters) weaker than backend (8) | `SettingsPage.tsx:90` | Adjust frontend to 8 characters + strength feedback |
| M8 | Ownership check in FileManager uses string comparison instead of number | `FileManager.tsx:59` | `Number(ownerId) === Number(user.id)` |
| M9 | Server profiles SSH hosts visible without auth when flag is active | `routes/server_profiles.py:32` | Include in `LocalOnlyMiddleware` prefixes |
| M10 | `psycopg2-binary` instead of `psycopg2` in production | `pyproject.toml:16` | Migrate to `psycopg2` (compiled) or `psycopg[binary]` |
| M11 | Samba config: username directly interpolated in INI | `samba_service.py:179` | Local re-validation: `re.fullmatch(r"^[a-zA-Z0-9_-]+$", username)` |
| M12 | `Pillow` without upper version bound (frequent CVEs) | `pyproject.toml:38` | Add upper bound |
| M13 | Mobile token + VPN config stored in localStorage | `MobileDevicesPage.tsx:90` | Use in-memory React state instead of localStorage |
| M14 | `debug=True` has no production validator | `config.py:206` | Validate analogously to `SECRET_KEY` |
| M15 | Rate limiter `_is_test_mode` name collision (bool vs function) | `rate_limiter.py:31/161` | Rename, eliminate shadowing |

---

## LOW (Nice to Have)

| # | Finding |
|---|---------|
| N1 | JWT in localStorage (documented trade-off, Known Gap #7) |
| N2 | Brute-force tracker ephemeral across workers/restarts |
| N3 | In-memory rate limiter resets on restart (Known Gap #3) |
| N4 | `package-lock.json` version out of sync with `package.json` |
| N5 | Avatars served without auth (UUIDs, not guessable) |
| N6 | `firebase-admin` always installed (large attack surface) |
| N7 | Health/ping endpoints leak version string |
| N8 | `console.error` logs raw error objects in frontend (`FileViewer.tsx:83`) |
| N9 | `GET /api/updates/version` and `/release-notes` without auth (version fingerprinting) |
| N10 | `GET /api/system/info/local` IP check bypassed by Nginx proxy |
| N11 | Desktop pairing device code flow unauthenticated (rate-limit only) |

---

## OWASP Top 10:2025 Mapping

| OWASP Category | BaluHost Status | Most Critical Findings |
|---|---|---|
| **A01 Broken Access Control** | Vulnerabilities present | C4 (Metrics unauth), H2 (IDOR Mobile), H1 (is_active) |
| **A02 Security Misconfiguration** | Partial | H6 (Open registration), C3 (12h token TTL), M14 (debug) |
| **A03 Supply Chain** | At risk | H7 (passlib unmaintained), M10 (psycopg2-binary) |
| **A04 Cryptographic Failures** | At risk | H5 (TOTP/VPN key sharing), H8 (Plaintext VPN keys) |
| **A05 Injection** | Well protected | H9 (SMART device unvalidated, but no shell=True) |
| **A06 Insecure Design** | Structural issues | C1-C3 (Token lifecycle completely broken) |
| **A07 Authentication Failures** | Vulnerabilities | H3 (Brute-force reset), H4 (2FA bypass), C2 (Logout) |
| **A08 Integrity Failures** | OK | No insecure deserialization found |
| **A09 Logging Failures** | Good | Audit logging present, but M2 (access rights) |
| **A10 Exception Handling** | OK | No insecure error handling found |

---

## Positive Findings (Well Implemented)

- **Subprocess security**: All `subprocess.run()` calls use list args, no `shell=True` in app code
- **Path traversal protection**: `_jail_path()` prevents traversal correctly, `..` is rejected
- **Admin DB**: Table whitelist + REDACT_PATTERN — no raw SQL with user input
- **Rclone**: `asyncio.create_subprocess_exec` (no shell)
- **Production validators**: SECRET_KEY and token_secret are validated in production
- **CORS**: Origins explicitly listed (no wildcard `*`)
- **Security headers**: CSP, X-Frame-Options, HSTS, Referrer-Policy, Permissions-Policy present
- **Frontend**: No `dangerouslySetInnerHTML`, `eval`, `exec`, `pickle.load` found
- **Encryption at rest**: Fernet encryption for VPN/SSH keys
- **2FA**: TOTP with backup codes fully implemented
- **Tests**: 1,465 tests in 82 test files
- **Timing-safe auth**: Dummy hash prevents username enumeration
- **Pydantic**: Request validation on all critical endpoints
- **Audit logging**: Security events are logged (login, password change, admin ops)

---

## Recommended Prioritization

### Immediate (This Week)
1. **Fix token lifecycle**: Address C1 + C2 + C3 together (decode_token type, JTI mapping, TTL, logout)
2. **Put `/api/metrics` behind auth** (C4)
3. **Add `is_active` check to `get_current_user`** (H1)
4. **Fix IDOR in Mobile Camera/Sync** (H2)

### Short-Term (2 Weeks)
5. Set `registration_enabled` default to `False` + production validator (H6)
6. Do not reset brute-force counter (H3)
7. 2FA rate limit per user ID (H4)
8. Abort VPN key encryption when key is missing instead of plaintext fallback (H8)
9. SMART device allowlist (H9)
10. Remove WebSocket token fallback (H10)

### Medium-Term (1 Month)
11. Replace `passlib` with direct `bcrypt` usage (H7)
12. Restrict CSP `connect-src` to `'self'` (M3)
13. Separate TOTP encryption key from VPN key (H5)
14. Address remaining MEDIUM findings

---

## Known Gaps Update

The following documented Known Gaps (from `security-agent.md`) have changed:

| # | Documented | Current Status |
|---|---|---|
| 8 | `change-password` uses raw `dict` | **Fixed** — now uses `ChangePasswordRequest` Pydantic model |
| 9 | VPN encryption key "fails loudly if missing" | **Inaccurate** — actually silent fallback to plaintext (H8) |

---

## Sources

- [OWASP Top 10:2025](https://owasp.org/Top10/2025/)
- [OWASP Top 10 2025 Changes - GitLab](https://about.gitlab.com/blog/2025-owasp-top-10-whats-changed-and-why-it-matters/)
- [JWT Vulnerabilities 2026 - Red Sentry](https://redsentry.com/resources/blog/jwt-vulnerabilities-list-2026-security-risks-mitigation-guide)
- [FastAPI Security Best Practices 2025](https://toxigon.com/python-fastapi-security-best-practices-2025)
- [FastAPI CVE Database - Snyk](https://security.snyk.io/package/pip/fastapi)
- [Self-hosted Hardening 2026](https://readthemanual.co.uk/secure-your-homelab-2025/)
