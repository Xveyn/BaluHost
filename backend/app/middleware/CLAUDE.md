# Middleware

Middleware applied to all requests. Most are Starlette `BaseHTTPMiddleware`;
`inflight.py` is deliberately pure ASGI. Registered in `main.py` — order matters. `add_middleware()` does `user_middleware.insert(0, ...)`, so **the last one registered is the outermost** and sees every request first (verified against starlette 0.41.3).

## Files

| File | Purpose | Runs on |
|---|---|---|
| `security_headers.py` | CSP, X-Frame-Options, HSTS, Referrer-Policy, Permissions-Policy. Dev mode allows `unsafe-inline`/`unsafe-eval` for Vite HMR; prod restricts `script-src` to `'self'`. HSTS only sent over HTTPS | All responses |
| `channel_marker.py` | Sets `request.state.channel` from `settings.channel` (provider-callable injection for test monkeypatch). The TCP-bound backend process gets `remote`; the UDS-bound process gets `local`. Used by `require_local_admin` (Task 5) to gate destructive admin endpoints behind physical presence. **The `request.state.channel` attribute is reserved for this purpose — other middleware/routes must not overwrite it.** | All requests |
| `error_counter.py` | Thread-safe counters for 4xx/5xx responses. Read via `ErrorCounterMiddleware.get_counts()` or `get_error_counts()`. Used by admin metrics dashboard | All responses |
| `device_tracking.py` | Updates `MobileDevice.last_seen` timestamp when `X-Device-ID` header is present. DB write runs in worker thread via `asyncio.to_thread()`, debounced to at most one write per device per `_WRITE_TTL_SECONDS` (60s) via a bounded LRU cache — the timestamps are coarse activity indicators, the dashboard's "recently active" threshold is 5 min (#322) | Requests with X-Device-ID |
| `local_only.py` | Blocks non-local-network requests to protected prefixes when `ENFORCE_LOCAL_ONLY=true`. Protected: `/api/server-profiles`, `/api/auth/login`, `/api/auth/register` | Configurable endpoints |
| `api_version.py` | Adds `X-API-Version` and `X-API-Min-Version` headers to all `/api/` responses | API responses |
| `plugin_gate.py` | Enforces plugin enabled-status and permissions at runtime. Reads the shared TTL cache in `services/plugin_enablement.py` (5s `CACHE_TTL_SECONDS`) rather than keeping a cache of its own. Management routes (toggle, config, UI assets) bypass the gate | `/api/plugins/{name}/...` |
| `sleep_auto_wake.py` | Counts HTTP requests for idle detection. Auto-wakes from soft sleep on non-whitelisted requests. Whitelisted: monitoring, health, docs, sleep status endpoints | All requests |
| `inflight.py` | Counts in-flight HTTP requests and their service time (clock stops at `http.response.start`, so SSE/streaming lifetime is excluded) for the concurrency probe (S1/#300). **Pure ASGI, not `BaseHTTPMiddleware`** — it exists to measure overhead, so it must not add any itself. Registered last in `main.py`, making it the outermost layer. Only registered when `CONCURRENCY_PROBE_ENABLED` is true — the off-switch has to reach the hot-path half too | All HTTP requests |

## Adding Middleware

1. Create file in `middleware/`
2. Pick a style:
   - **`BaseHTTPMiddleware`** (the default here, 8 of 9): extend it and implement
     `async dispatch(self, request, call_next)`. You get a `Request`/`Response`
     pair, so header rewriting, short-circuiting with a response, and
     `request.state` are straightforward.
   - **Pure ASGI** (`inflight.py`): implement
     `async __call__(self, scope, receive, send)` and call `self.app(...)`.
     Choose this when the per-request cost matters (BaseHTTPMiddleware wraps
     every request in an extra task group and Request/Response objects), when
     you must observe the raw ASGI messages (e.g. stop a timer at
     `http.response.start`), or when buffering a streaming response would be
     harmful. Cost: no `Request` convenience — you handle `scope` yourself and
     must pass non-`http` scopes (`lifespan`, `websocket`) straight through.
3. Register in `main.py` via `app.add_middleware(MyMiddleware)` or a `setup_*()` function
4. Keep middleware lightweight — it runs on every request
