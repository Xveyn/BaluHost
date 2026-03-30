# Core

Application foundation: configuration, database, security, and cross-cutting infrastructure.

## Files

| File | Purpose |
|---|---|
| `config.py` | `Settings` (pydantic-settings) — all config via env vars. Access via `settings` singleton or `get_settings()`. Production validators reject weak secrets |
| `database.py` | SQLAlchemy engine + `SessionLocal` factory. SQLite (dev, WAL mode) or PostgreSQL (prod, QueuePool). `get_db()` is the FastAPI dependency. `init_db()` creates tables (SQLite only; Postgres uses Alembic) |
| `security.py` | JWT token creation/verification (HS256). Token types: `access` (15min), `refresh` (7d, has JTI), `sse` (60s), `ws` (60s), `2fa_pending` (5min). Always validates `type` claim |
| `rate_limiter.py` | slowapi-based rate limiting. `limiter` instance + `get_limit(endpoint_type)` lookup. DB-backed config with in-memory cache. Dev/test mode relaxes non-auth limits. `user_limiter` for per-user limits |
| `lifespan.py` | FastAPI lifespan: startup/shutdown orchestration. Primary-worker election via file lock. Starts hardware services, plugins, mDNS, heartbeat writer. `IS_PRIMARY_WORKER` flag controls which process runs hardware tasks |
| `service_registry.py` | Registers all background services with the admin status dashboard. Provides DB-based status readers for secondary workers. Defines `PRIMARY_ONLY_SERVICES` and `MONITORING_WORKER_SERVICES` |
| `logging_config.py` | Structured logging setup. JSON format for production (pythonjsonlogger), text for dev. In-memory ring buffer for SSE log streaming |
| `network_utils.py` | IP address classification: `is_private_or_local_ip()`, `is_localhost()`. Handles IPv4, IPv6, IPv6-mapped-IPv4 |
| `power_rating.py` | `@requires_power(ServicePowerProperty)` decorator and `PowerPropertyContext` async context manager. Registers/unregisters power demands with PowerManager for CPU frequency scaling |

## Key Patterns

- **Config**: All settings have env var equivalents (uppercase). `NAS_MODE=dev` enables dev mode with mock backends
- **Multi-worker**: Production runs 4 Uvicorn workers. Only one becomes primary (file lock in `/tmp/baluhost-primary.lock`). Hardware services (fans, power, mDNS, monitoring) only run on primary
- **DB sessions**: Always use `get_db()` dependency in routes or `SessionLocal()` context manager in services. Never hold sessions across async boundaries
- **Token types**: `decode_token(token, token_type="access")` enforces type claim — prevents using refresh tokens as access tokens
