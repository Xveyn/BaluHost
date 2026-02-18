# API Rate Limiting - Implementation Documentation

## Overview

API rate limiting has been successfully implemented using `slowapi` to protect the BaluHost NAS API from abuse and ensure fair resource allocation.

## Implementation Details

### Technology Stack

- **Library**: [slowapi](https://github.com/laurentS/slowapi) v0.1.9+
- **Storage Backend**: In-memory storage (`memory://`)
- **Identification Methods**: 
  - IP-based for unauthenticated endpoints
  - User-based (JWT) for authenticated endpoints

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     FastAPI App                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Rate Limit Middleware (slowapi)                  │  │
│  │  - Tracks requests per IP/User                    │  │
│  │  - Returns 429 when limit exceeded                │  │
│  │  - Adds X-RateLimit-* headers                     │  │
│  └───────────────────────────────────────────────────┘  │
│                          ↓                              │
│  ┌───────────────────────────────────────────────────┐  │
│  │  API Routes (with @limiter.limit decorators)      │  │
│  │  - /api/auth/login (5/minute)                     │  │
│  │  - /api/auth/register (3/minute)                  │  │
│  │  - /api/files/upload (20/minute)                  │  │
│  │  - /api/files/download (100/minute)               │  │
│  │  - /api/shares/links (10/minute)                  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Rate Limit Configuration

### Authentication Endpoints (Strict Limits)

| Endpoint | Limit | Reason |
|----------|-------|--------|
| `POST /api/auth/login` | 5/minute | Prevent brute force attacks |
| `POST /api/auth/register` | 3/minute | Prevent spam registrations |
| `POST /api/mobile/register` | 3/minute | Prevent device registration spam |

### File Operations (Moderate Limits)

| Endpoint | Limit | Reason |
|----------|-------|--------|
| `POST /api/files/upload` | 20/minute | Balance upload capacity |
| `GET /api/files/download/*` | 100/minute | Allow reasonable file access |
| `GET /api/files/list` | 60/minute | Moderate directory listing |
| `DELETE /api/files/*` | 30/minute | Control file deletion rate |

### Share Operations (Moderate Limits)

| Endpoint | Limit | Reason |
|----------|-------|--------|
| `POST /api/shares/links` | 10/minute | Control share creation |
| `GET /api/shares/links` | 60/minute | Allow listing shares |
| `POST /api/shares/public/{token}/access` | 100/minute | Public share access |

### System Operations (Generous Limits)

| Endpoint | Limit | Reason |
|----------|-------|--------|
| System monitor endpoints | 120/minute | Allow frequent monitoring |
| User operations | 30/minute | Standard CRUD operations |
| Admin operations | 30/minute | Administrative tasks |

## Files Changed

### New Files

1. **`backend/app/core/rate_limiter.py`**
   - Limiter initialization with memory backend
   - Rate limit configurations (RATE_LIMITS dict)
   - Custom exception handler for 429 responses
   - User-based identifier function for JWT users

### Modified Files

1. **`backend/pyproject.toml`**
   - Added `slowapi>=0.1.9,<0.2.0` dependency

2. **`backend/app/main.py`**
   - Import slowapi components
   - Register limiter with app state
   - Add exception handler for RateLimitExceeded

3. **`backend/app/api/routes/auth.py`**
   - Added `@limiter.limit()` to login endpoint
   - Added `@limiter.limit()` to register endpoint
   - Added `Request` parameter to function signatures

4. **`backend/app/api/routes/files.py`**
   - Added rate limiting to all critical file endpoints
   - Used `user_limiter` for authenticated endpoints
   - Added `Request` parameter to function signatures

5. **`backend/app/api/routes/shares.py`**
   - Added rate limiting to share creation and listing
   - Added rate limiting to public share access
   - Added `Request` parameter to function signatures

### Test Files

1. **`backend/tests/test_rate_limiting.py`**
   - Tests for rate limit enforcement
   - Tests for rate limit configuration
   - Tests for response format and headers

## Usage

### For Developers

Apply rate limiting to a new endpoint:

```python
from app.core.rate_limiter import limiter, user_limiter, get_limit
from fastapi import Request

# For unauthenticated endpoints (IP-based)
@router.post("/public-endpoint")
@limiter.limit(get_limit("public_share"))
async def public_endpoint(request: Request, ...):
    pass

# For authenticated endpoints (User-based)
@router.get("/protected-endpoint")
@user_limiter.limit(get_limit("file_list"))
async def protected_endpoint(
    request: Request,
    user: UserPublic = Depends(get_current_user),
    ...
):
    pass
```

### Adding New Rate Limits

Edit `backend/app/core/rate_limiter.py`:

```python
RATE_LIMITS = {
    # ... existing limits ...
    "new_endpoint_type": "50/minute",  # 50 requests per minute
}
```

## Response Format

### Successful Request (Within Limit)

```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1704283200
```

### Rate Limit Exceeded

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
X-RateLimit-Limit: 100
X-RateLimit-Reset: 1704283200
Content-Type: application/json

{
  "error": "Too Many Requests",
  "detail": "Rate limit exceeded. Please try again later.",
  "retry_after": 60
}
```

## Testing

Run rate limiting tests:

```bash
cd backend
python -m pytest tests/test_rate_limiting.py -v
```

Test specific scenarios:

```bash
# Configuration tests
pytest tests/test_rate_limiting.py::TestRateLimitConfiguration -v

# Rate limit enforcement tests
pytest tests/test_rate_limiting.py::TestRateLimiting -v
```

## Configuration Options

### Memory Backend (Current)

- **Pros**: No external dependencies, simple setup
- **Cons**: Resets on server restart, not suitable for multi-instance deployments

### Redis Backend (Future Enhancement)

For production with multiple instances, consider switching to Redis:

```python
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute", "1000/hour"],
    headers_enabled=True,
    storage_uri="redis://localhost:6379"
)
```

## Security Considerations

1. **Bypass Prevention**: Rate limits are enforced at the FastAPI level before reaching business logic
2. **Header Information**: X-RateLimit-* headers inform clients about their usage
3. **Graceful Degradation**: 429 responses include retry-after information
4. **User-based Tracking**: Authenticated users are tracked independently of IP

## Monitoring

Monitor rate limit hits through:

1. **Application Logs**: Check for rate limit warnings
2. **Audit Logs**: Failed authentication attempts are logged
3. **Metrics** (Future): Export rate limit metrics to monitoring systems

## Future Enhancements

- [ ] Add Redis backend for distributed rate limiting
- [ ] Implement per-user quotas (daily/monthly limits)
- [ ] Add admin API to view/modify rate limits dynamically
- [ ] Export rate limit metrics to Prometheus
- [ ] Implement tiered rate limits based on user roles
- [ ] Add configurable rate limits via environment variables

## References

- [slowapi Documentation](https://github.com/laurentS/slowapi)
- [Flask-Limiter](https://flask-limiter.readthedocs.io/) (slowapi is based on this)
- [IETF Draft: RateLimit Header Fields](https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-ratelimit-headers)

---

**Implementation Date**: January 2, 2026  
**Status**: ✅ Complete and Tested
