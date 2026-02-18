# API Rate Limiting - Quick Start Guide

## 🚀 What's Implemented

API rate limiting is now active to protect against:
- ✅ Brute force login attacks (5 attempts/minute)
- ✅ Spam registrations (3/minute)
- ✅ Upload flooding (20/minute)
- ✅ Share link abuse (10/minute)
- ✅ General API abuse (custom limits per endpoint type)

## 📋 Rate Limits Summary

### Critical Security Endpoints
- **Login**: 5 requests/minute
- **Register**: 3 requests/minute
- **Mobile Registration**: 3 requests/minute

### File Operations
- **Upload**: 20 requests/minute
- **Download**: 100 requests/minute
- **List Files**: 60 requests/minute
- **Delete**: 30 requests/minute

### Sharing
- **Create Share**: 10 requests/minute
- **List Shares**: 60 requests/minute
- **Public Access**: 100 requests/minute

## 🔧 How It Works

1. **IP-based tracking** for unauthenticated requests
2. **User-based tracking** for authenticated requests (via JWT)
3. **Automatic 429 responses** when limits are exceeded
4. **X-RateLimit-* headers** inform clients about usage

## 📖 For Frontend Developers

When you hit a rate limit, you'll receive:

```json
HTTP/1.1 429 Too Many Requests
Retry-After: 60

{
  "error": "Too Many Requests",
  "detail": "Rate limit exceeded. Please try again later.",
  "retry_after": 60
}
```

**Recommended client behavior:**
1. Check for `429` status code
2. Read `Retry-After` header or `retry_after` from response
3. Display user-friendly message: "Too many requests. Please wait {retry_after} seconds."
4. Optionally implement automatic retry with exponential backoff

## 🧪 Testing

```bash
# Run all rate limiting tests
cd backend
python -m pytest tests/test_rate_limiting.py -v

# Test configuration only
pytest tests/test_rate_limiting.py::TestRateLimitConfiguration -v
```

## 🛠️ Configuration

All rate limits are defined in `backend/app/core/rate_limiter.py`:

```python
RATE_LIMITS = {
    "auth_login": "5/minute",
    "file_upload": "20/minute",
    # ... etc
}
```

## 📊 Monitoring

- Check logs for rate limit warnings
- Audit logs track authentication failures
- 429 responses are logged with IP/user info

## 🔒 Security Benefits

1. **Brute Force Protection**: Login rate limits prevent password guessing
2. **DoS Prevention**: Request limits prevent resource exhaustion
3. **Fair Usage**: Ensures all users get equal access
4. **Spam Prevention**: Limits prevent automated abuse

## 🚀 Future Enhancements

- [ ] Redis backend for multi-instance deployments
- [ ] Per-user daily/monthly quotas
- [ ] Admin dashboard for rate limit monitoring
- [ ] Configurable limits via environment variables
- [ ] Role-based rate limit tiers (premium users get higher limits)

## 📚 Full Documentation

See `docs/API_RATE_LIMITING.md` for complete implementation details.
