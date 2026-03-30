# Middleware

Starlette `BaseHTTPMiddleware` classes applied to all requests. Registered in `main.py` — order matters (first added = outermost).

## Files

| File | Purpose | Runs on |
|---|---|---|
| `security_headers.py` | CSP, X-Frame-Options, HSTS, Referrer-Policy, Permissions-Policy. Dev mode allows `unsafe-inline`/`unsafe-eval` for Vite HMR; prod restricts `script-src` to `'self'`. HSTS only sent over HTTPS | All responses |
| `error_counter.py` | Thread-safe counters for 4xx/5xx responses. Read via `ErrorCounterMiddleware.get_counts()` or `get_error_counts()`. Used by admin metrics dashboard | All responses |
| `device_tracking.py` | Updates `MobileDevice.last_seen` timestamp when `X-Device-ID` header is present. DB write runs in worker thread via `asyncio.to_thread()` | Requests with X-Device-ID |
| `local_only.py` | Blocks non-local-network requests to protected prefixes when `ENFORCE_LOCAL_ONLY=true`. Protected: `/api/server-profiles`, `/api/auth/login`, `/api/auth/register` | Configurable endpoints |
| `api_version.py` | Adds `X-API-Version` and `X-API-Min-Version` headers to all `/api/` responses | API responses |
| `plugin_gate.py` | Enforces plugin enabled-status and permissions at runtime. Checks DB with 5s TTL cache. Management routes (toggle, config, UI assets) bypass the gate | `/api/plugins/{name}/...` |
| `sleep_auto_wake.py` | Counts HTTP requests for idle detection. Auto-wakes from soft sleep on non-whitelisted requests. Whitelisted: monitoring, health, docs, sleep status endpoints | All requests |

## Adding Middleware

1. Create file in `middleware/`
2. Extend `BaseHTTPMiddleware`, implement `async dispatch(self, request, call_next)`
3. Register in `main.py` via `app.add_middleware(MyMiddleware)` or a `setup_*()` function
4. Keep middleware lightweight — it runs on every request
