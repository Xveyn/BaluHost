# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.23.x  | :white_check_mark: |
| < 1.23  | :x:                |

## Reporting a Vulnerability

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to: **security@baluhost.example**

### What to Include

Please include the following information:
- Type of vulnerability
- Full paths of source file(s) related to the vulnerability
- Location of the affected source code (tag/branch/commit or direct URL)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if available)
- Impact of the issue, including how an attacker might exploit it

### What to Expect

- You'll receive a confirmation within 48 hours
- We'll investigate and provide an estimated timeline
- We'll notify you when the issue is fixed
- We'll credit you in the release notes (if you wish)

## Implemented Security Features

### Authentication & Authorization
- [x] JWT authentication with HS256 signing (access + refresh tokens)
- [x] Access tokens: 15 min TTL, Refresh tokens: 7 days with JTI for revocation
- [x] Two-Factor Authentication (TOTP) with authenticator apps
- [x] Password policy: 8-128 chars, uppercase + lowercase + digit, blacklist
- [x] Role-based access control (admin/user) with `is_privileged()` checks
- [x] Rate limiting on all endpoints via slowapi (per-endpoint limits)
- [x] Mobile device authentication with device-specific JWT + X-Device-ID

### Input Validation & Path Safety
- [x] Pydantic schemas for all request validation
- [x] Path jailing via `_jail_path()` — users restricted to own home, Shared/, or validated share paths
- [x] Path traversal prevention (`..` rejection, PurePosixPath normalization)
- [x] SQLAlchemy ORM-only queries (no raw SQL with user input)
- [x] `subprocess.run()` with list arguments only (no `shell=True` in app code)

### Network & Headers
- [x] Security headers middleware (CSP, X-Frame-Options, HSTS, X-Content-Type-Options)
- [x] CORS scoped to configured origins list
- [x] Rate limiting via Nginx reverse proxy (100 req/s API, 10 req/s auth)
- [x] WireGuard VPN for encrypted remote access

### Data Protection
- [x] Encrypted VPN/SSH keys at rest (Fernet AES-128-CBC)
- [x] Production secret validation (32+ chars, rejects defaults)
- [x] Sensitive column redaction in admin-db API (`REDACT_PATTERN`)
- [x] Audit logging for all security-relevant actions (login, password change, admin ops)
- [x] Structured JSON logging (no secrets logged)

## Security Best Practices

### For Developers

**Authentication:**
- Never commit tokens, passwords, or secrets to Git
- Use environment variables for sensitive configuration
- All new endpoints must use `Depends(get_current_user)` or `Depends(get_current_admin)`
- Apply rate limiting via `@limiter.limit(get_limit("..."))` on new endpoints

**Authorization:**
- Use `ensure_owner_or_privileged()` for ownership checks
- Validate file paths through `_jail_path()`
- Never trust client-side checks alone

**Input Validation:**
- Use Pydantic schemas for all request bodies (never raw `dict`)
- Reject `..` in all user-supplied file paths
- Use `subprocess.run()` with explicit argument lists (never string commands)

**File Operations:**
- All file operations go through `_jail_path()` sandbox
- Check quota before uploads
- Ownership tracked via database

### For Users

**Passwords:**
- Use strong, unique passwords (min 8 chars, uppercase + lowercase + digit)
- Change default passwords immediately after setup
- Enable 2FA in Settings for additional security
- Never share passwords

**Access Control:**
- Review user permissions regularly
- Remove unused accounts
- Use least privilege principle
- Monitor audit logs (Logging page)

**Network Security:**
- Use WireGuard VPN for remote access
- Don't expose directly to internet without VPN or reverse proxy
- Keep firewall configured properly

## Known Limitations & Accepted Trade-offs

These are documented trade-offs — do not attempt to fix without discussion:

1. **Tokens in localStorage** — XSS risk mitigated by CSP headers; HttpOnly cookies would require significant auth refactor
2. **CSP `unsafe-inline`/`unsafe-eval`** — Required by Vite dev server; production could tighten
3. **CORS `allow_methods=["*"]`/`allow_headers=["*"]`** — Scoped to configured `cors_origins` list
4. **In-memory rate limiter** — Resets on restart; acceptable for single-instance deployment
5. **No CSRF protection** — Mitigated by JWT Bearer auth (not cookie-based)
6. **HTTPS not enforced** — External access via WireGuard VPN (encrypted tunnel); HTTP on trusted LAN
7. **JTI without server-side revocation store** — Token rotation is the primary defense

## Security Checklist for Production

Before deploying to production:

- [x] Change all default passwords
- [x] Set strong `SECRET_KEY` (min 32 characters, validated at startup)
- [x] Set strong `TOKEN_SECRET` (min 32 characters, validated at startup)
- [x] Configure firewall rules
- [x] Disable debug mode
- [x] Review CORS settings (restrict to known origins)
- [x] Enable audit logging
- [x] Set up backups (pg_dump)
- [x] Configure structured JSON logging
- [x] Review user permissions
- [ ] Use HTTPS with valid SSL certificate (optional, VPN provides encryption)
- [ ] Set up log rotation
- [ ] Run security audit tools

## Dependency Security

We use automated tools to check for vulnerabilities:

**Python (Backend):**
```bash
pip install safety
safety check
```

**Node.js (Frontend):**
```bash
npm audit
npm audit fix
```

## Security Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)

## Disclosure Policy

- We follow responsible disclosure practices
- We'll acknowledge security researchers in release notes
- We aim to fix critical issues within 7 days
- We'll notify affected users if needed

## Contact

For security-related questions or concerns:
- **Email:** security@baluhost.example

---

**Last Updated:** April 2026
**Version:** 1.23.0
