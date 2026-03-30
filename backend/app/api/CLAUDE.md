# API Layer

REST API endpoints for BaluHost. All routes are registered in `routes/__init__.py` and mounted under `/api` prefix in `main.py`.

## Structure

- `deps.py` — FastAPI dependency injection for auth (`get_current_user`, `get_current_admin`, `get_current_user_optional`, `verify_mobile_device_token`)
- `docs.py` — Custom Swagger UI + ReDoc with BaluHost dark theme styling
- `routes/` — One file per feature domain (~55 route modules)
- `versioned/` — API versioning support (reserved)

## Auth Dependencies (deps.py)

| Dependency | Returns | Use case |
|---|---|---|
| `get_current_user` | `UserPublic` | Any authenticated endpoint |
| `get_current_admin` | `UserPublic` | Admin-only endpoints |
| `get_current_user_optional` | `UserPublic \| None` | Optional auth (public shares) |
| `verify_mobile_device_token` | `UserPublic` | Mobile endpoints (validates X-Device-ID header + device expiry) |

Supports both JWT (`Bearer <token>`) and API key (`balu_...` prefix) authentication paths.

## Adding a New Route

1. Create `routes/my_feature.py` with a `router = APIRouter()`
2. Add auth dependency: `Depends(deps.get_current_user)` or `get_current_admin`
3. Add rate limiting: `@limiter.limit(get_limit("my_feature"))`
4. Use Pydantic schemas for request/response bodies
5. Register in `routes/__init__.py`: `api_router.include_router(my_feature.router, prefix="/my-feature", tags=["my-feature"])`

## Conventions

- Route files define a `router = APIRouter()` — no prefix in the file, prefix set in `__init__.py`
- Business logic lives in `services/`, routes only handle HTTP concerns
- File operations must go through `_jail_path()` for path sandboxing
- Rate limits configured in `core/rate_limiter.py` via `get_limit()` lookup
- Power-intensive endpoints use `@requires_power(ServicePowerProperty.SURGE)` decorator
- Audit logging for security-relevant actions via `get_audit_logger_db()`
