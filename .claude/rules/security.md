# Security & Constraints

## DO NOT Modify
- `.metadata.json` files (managed by file service)
- `dev-storage/` contents (recreated on startup in dev mode)

## Security Patterns
- All file operations check ownership or admin role
- Path traversal prevention via `is_within_sandbox()`
- JWT access tokens expire after 15 minutes, refresh tokens after 7 days (`ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` in `core/config.py`). Short-lived special-purpose tokens (`sse`, `ws`, `2fa_pending`, `setup`) are listed in `.claude/rules/security-agent.md` and `backend/app/core/CLAUDE.md` — keep those two in sync rather than restating TTLs here
- Audit logging for sensitive operations
- Rate limiting implemented via slowapi

## Middleware
- `error_counter.py` - Tracks 4xx/5xx errors for admin metrics
- `security_headers.py` - CSP, X-Frame-Options, HSTS
- `device_tracking.py` - Mobile device last_seen tracking
- `local_only.py` - Enforces local-network-only access for sensitive endpoints

## Windows Compatibility
- All features work on Windows via dev-mode simulation
- Disk I/O monitor detects Windows drives (`PhysicalDrive0`, `PhysicalDrive1`)
- No Linux-specific commands required in dev mode
