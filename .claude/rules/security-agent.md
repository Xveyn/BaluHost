# Security Enforcement Agent

Active security enforcement rule for BaluHost. Applies to all changes in `backend/app/`, `client/src/`, authentication, file operations, and system commands. Claude MUST verify compliance with these invariants before generating or reviewing code.

---

## Security Invariants

### NEVER

- Use `shell=True` in `subprocess.run()` or `subprocess.Popen()` — all 15+ service files use list-args exclusively; the only `shell=True` is in `scripts/setup/setup_postgresql.py` (one-time admin script, not app code)
- Execute raw SQL with user-controlled input — ORM-only; sole exception: static query strings in `services/audit/admin_db.py`
- Log secrets, tokens, passwords, or API keys — not even at DEBUG level
- Return password hashes, internal stack traces, or server internals in API responses
- Disable or bypass the token-type check in `core/security.py:163` (`payload.get("type") != token_type`)
- Bypass `_jail_path()` for user-facing file operations (`api/routes/files.py:38`)
- Use default secrets (`"change-me-in-prod"`) in production — `config.py:206-242` validates this
- Commit `.env` or `.env.production` files
- Expose VPN private keys, SSH keys, or Fernet encryption keys in responses or logs
- Add new endpoints without authentication dependencies (unless explicitly public)

### ALWAYS

- Use `Depends(deps.get_current_user)` or `Depends(deps.get_current_admin)` on protected endpoints
- Use `ensure_owner_or_privileged()` from `services/permissions.py` for ownership checks
- Apply rate-limiting via `@limiter.limit(get_limit("..."))` on new endpoints (`core/rate_limiter.py:148`)
- Use Pydantic schemas for request body validation — never accept raw `dict` payloads
- Reject `..` in all user-supplied file paths
- Log security-relevant actions via `get_audit_logger_db()` (login, password change, admin ops, failed auth)
- Use `subprocess.run()` with explicit argument lists (never string commands)
- Ensure new sensitive database columns match `REDACT_PATTERN` in `services/audit/admin_db.py:13`

---

## Auth & Authorization Reference

### Token Types
| Type | TTL | Claim `type` | Features |
|------|-----|---------------|----------|
| Access | 15 min (`ACCESS_TOKEN_EXPIRE_MINUTES`) | `"access"` | Contains `sub`, `username`, `role` |
| Refresh | 7 days (`REFRESH_TOKEN_EXPIRE_DAYS`) | `"refresh"` | Contains `jti` for revocation |
| SSE | 60 sec | `"sse"` | Scoped to single `upload_id`, safe for query params |

### Dependency Chain
```
get_current_user          — JWT validation, returns UserPublic
  get_current_admin       — Depends on above, checks role == "admin"
get_current_user_optional — Returns None if no token (for optional auth)
verify_mobile_device_token — Validates JWT + X-Device-ID header + device expiry
```

### Role Model
- Roles: `admin`, `user`
- `is_privileged(user)` checks against `settings.privileged_roles` (configurable)
- Admin-only endpoints use `Depends(deps.get_current_admin)`

### Password Policy (`schemas/auth.py:20-59`)
- Length: 8-128 characters
- Required: uppercase + lowercase + digit
- Blacklist: 11 common passwords (case-insensitive comparison)
- Enforced via Pydantic `field_validator` on `RegisterRequest`

### Key Files
- `core/security.py` — Token creation/verification (HS256)
- `api/deps.py` — FastAPI dependency injection for auth
- `schemas/auth.py` — Login/Register schemas, password validation
- `services/permissions.py` — `is_privileged()`, `ensure_owner_or_privileged()`

---

## Input Validation & Path Safety

### `_jail_path()` (`api/routes/files.py:38-80`)
- **Admin**: path returned unchanged (via `is_privileged()`)
- **User**: restricted to own home dir, `Shared/`, `Shared with me`, or FileShare-validated paths
- **Always**: rejects `..` components, normalizes path via `PurePosixPath`
- Used in: `files.py` (8 call sites), `chunked_upload.py` (1 call site)

### System Directories
- `.system` — internal metadata, avatars, thumbnails
- `lost+found` — filesystem recovery, hidden from users
- `.Trash-*` — trash directories, hidden from users

### Subprocess Safety
- 15+ service files use `subprocess.run()` — all with list arguments
- Zero `shell=True` usage in application code
- User input must never be interpolated into command strings

### Frontend
- React JSX auto-escapes output — do not use React's raw-HTML escape hatch
- No dynamic code evaluation in source
- API responses rendered through typed React components

---

## Data Protection

### Secrets Validation
- `SECRET_KEY`: production validator requires 32+ chars, rejects default (`config.py:206-223`)
- `token_secret`: same validation (`config.py:225-242`)
- Both use `field_validator` — app refuses to start with weak secrets in prod

### Encryption at Rest
- VPN/SSH keys: Fernet (AES-128-CBC) via `services/vpn/encryption.py`
- `VPNEncryption.encrypt_key()` / `decrypt_key()` — requires `VPN_ENCRYPTION_KEY` env var
- Key validated at use-time (raises `ValueError` if missing)

### Admin Database Inspection
- `REDACT_PATTERN = password|secret|token|private_key|api_key` (`services/audit/admin_db.py:13`)
- Applied to all column values before returning in admin-db API responses

### Token Storage (Frontend)
- JWT stored in `localStorage` — accepted trade-off (see Known Gaps)
- Mitigated by CSP headers restricting script sources

---

## OWASP Threat Categories for NAS

### 1. Broken Authentication
- **Mitigations**: Rate-limiting on login/register/password-change, JWT type claims prevent token confusion, short access TTL (15min), JTI on refresh tokens
- **Watch for**: New auth endpoints without rate limits, token handling that skips type verification

### 2. Broken Access Control
- **Mitigations**: `_jail_path()` enforces per-user file isolation, `ensure_owner_or_privileged()` for resource ownership, admin-only routes via `get_current_admin`
- **Watch for**: New file operations bypassing `_jail_path()`, endpoints missing auth dependencies, ownership checks using string comparison instead of int

### 3. Injection
- **Mitigations**: SQLAlchemy ORM-only (no raw SQL with user input), subprocess with list-args, path normalization via `PurePosixPath`
- **Watch for**: String interpolation in subprocess commands, raw SQL queries, `os.path.join` with unsanitized user paths

### 4. Security Misconfiguration
- **Mitigations**: Production secret validators refuse weak defaults, security headers middleware (CSP, X-Frame-Options, HSTS, X-Content-Type-Options), structured JSON error responses hide internals
- **Watch for**: Debug/verbose error messages leaking to API responses, new config values without prod validation

### 5. Sensitive Data Exposure
- **Mitigations**: Fernet encryption for VPN/SSH keys, `REDACT_PATTERN` in admin-db, audit log filtering
- **Watch for**: New API responses exposing hashed passwords, private keys, or internal tokens; logging sensitive data

### 6. SSRF
- **Attack surfaces**: Cloud import (rclone with user-specified remotes), remote server SSH connections, Tapo smart plug communication
- **Watch for**: User-controlled URLs passed to server-side HTTP clients without validation, new external service integrations

---

## Security Review Checklist

### New API Endpoints
- [ ] Auth dependency present? (`get_current_user` / `get_current_admin`)
- [ ] Rate-limiting configured? (`@limiter.limit(get_limit("..."))`)
- [ ] Pydantic schema for request body? (not raw `dict`)
- [ ] Audit logging for security-relevant events?
- [ ] Response contains only data the requester is authorized to see?
- [ ] Added to `@requires_power()` if applicable?

### File Operations
- [ ] Path validated through `_jail_path()`?
- [ ] Ownership checked via `ensure_owner_or_privileged()`?
- [ ] System directories (`.system`, `lost+found`, `.Trash-*`) protected?

### Subprocess / System Commands
- [ ] `subprocess.run()` with list arguments? (no string commands)
- [ ] No `shell=True`?
- [ ] User input sanitized before inclusion in command args?
- [ ] Timeout set to prevent hangs?

### Database
- [ ] ORM-only queries? (no raw SQL with user input)
- [ ] New sensitive columns match `REDACT_PATTERN`?
- [ ] No sensitive data in query logs?

### Frontend
- [ ] No raw-HTML rendering bypass? (use React JSX auto-escaping)
- [ ] User input sanitized before display?
- [ ] API error messages don't leak server internals?

### Config & Secrets
- [ ] New secrets have production validation? (32+ chars, no defaults)
- [ ] `.env` variables documented in `.env.example`, not committed?
- [ ] No hardcoded secrets in source code?

---

## Known Gaps & Accepted Risks

Do NOT attempt to fix these without explicit discussion — they are documented trade-offs:

1. **CSP `unsafe-inline` / `unsafe-eval`** — Required by Vite dev server; production build could tighten this but currently uses same policy (`middleware/security_headers.py:29-30`)
2. **CORS `allow_methods=["*"]` / `allow_headers=["*"]`** — Scoped to configured `cors_origins` list (`main.py:558-564`), not a wildcard origin
3. **In-memory rate limiter** — Resets on service restart; acceptable for single-instance deployment
4. **JTI without universal revocation check** — Refresh tokens have JTI but no server-side revocation store; rotation is the primary defense
5. **No CSRF protection** — Mitigated by JWT Bearer auth (not cookie-based); no state-changing cookie auth exists
6. **HTTPS not enforced** — External access via WireGuard VPN (encrypted tunnel); HTTP acceptable on trusted LAN
7. **Token in localStorage** — XSS risk mitigated by CSP headers; HttpOnly cookies would require significant auth refactor
8. **`change-password` uses raw `dict`** — `api/routes/auth.py:121` accepts `payload: dict` instead of Pydantic model, meaning new passwords bypass the `RegisterRequest` password strength validator
9. **VPN encryption key empty default** — Validated at use-time in `VPNEncryption` methods, not at startup; fails loudly if missing
10. **SECURITY.md outdated** — Documents limitations that have since been fixed; needs full rewrite
