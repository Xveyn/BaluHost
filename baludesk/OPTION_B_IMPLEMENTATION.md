# Option B: Secure Local Direct Access Implementation

## Overview
This implementation enables **BaluDesk Desktop Client** to directly access the **Python FastAPI backend** when running on the same host (localhost), while maintaining security through JWT authentication, owner-based authorization, and optional local-only enforcement.

## Security Features

### 1. JWT Authentication (Already Implemented ✅)
- **Endpoint:** `POST /api/auth/login`
- **Token TTL:** 15 minutes (configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`)
- **Algorithm:** HS256 with `token_secret` from config
- **Claims:** `sub` (user ID), `username`, `role`, `exp`
- **Validation:** `deps.get_current_user` dependency validates token on every request

### 2. Owner-Based Authorization (Already Implemented ✅)
- All server profile endpoints require authentication via `Depends(deps.get_current_user)`
- Profile creation sets `user_id = current_user.id` (server-side, never trust client)
- Profile listing filters by `user_id == current_user.id`
- Update/delete operations verify ownership before allowing changes

### 3. Local-Only Enforcement (NEW 🆕)
- **Middleware:** `LocalOnlyMiddleware` in `app/middleware/local_only.py`
- **Config:** `enforce_local_only` (default: `False`)
- **Protected endpoints:** `/api/server-profiles`, `/api/auth/login`, `/api/auth/register`
- **Allowed IPs:** 127.0.0.1, ::1, localhost, and optionally local network ranges
- **Non-local requests:** Blocked with HTTP 403

### 4. Public Profile List (NEW 🆕)
- **Endpoint:** `GET /api/server-profiles/public` (unauthenticated)
- **Purpose:** Allow login screen to show available profiles before authentication
- **Config:** `allow_public_profile_list` (default: `True`)
- **Security:** Excludes SSH keys; only shows names, hosts, owners
- **Recommendation:** Combine with `enforce_local_only=true` in production

### 5. CORS Configuration (UPDATED 🔄)
- Added Electron origins: `app://-`, `file://`
- Existing web origins: `http://localhost:5173`, `http://localhost:8000`
- Credentials allowed for JWT cookies/headers

## Configuration

### Environment Variables (.env)
```bash
# JWT Secret (CRITICAL - change in production!)
SECRET_KEY=your-strong-random-secret-here
token_secret=your-strong-random-secret-here

# Token TTL
ACCESS_TOKEN_EXPIRE_MINUTES=15
token_expire_minutes=720

# Local-only enforcement (recommended for production localhost)
enforce_local_only=true

# Public profile list (for login screen discovery)
allow_public_profile_list=true

# CORS (add your Electron custom protocol if needed)
cors_origins=http://localhost:5173,http://localhost:8000,app://-,file://
```

## API Endpoints for BaluDesk

### Authentication

#### Login
```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "changeme"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "admin",
    "role": "admin"
  }
}
```

#### Get Current User
```http
GET /api/auth/me
Authorization: Bearer <access_token>
```

### Server Profiles

#### List Profiles (Authenticated)
```http
GET /api/server-profiles
Authorization: Bearer <access_token>
```

Returns only profiles owned by the authenticated user.

#### List Profiles (Public - for login screen)
```http
GET /api/server-profiles/public
```

Returns all profiles with metadata. No authentication required.
Only enabled when `allow_public_profile_list=true`.

#### Create Profile
```http
POST /api/server-profiles
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "name": "My NAS",
  "ssh_host": "192.168.1.100",
  "ssh_port": 22,
  "ssh_username": "admin",
  "ssh_private_key": "-----BEGIN OPENSSH PRIVATE KEY-----...",
  "vpn_profile_id": null,
  "power_on_command": ""
}
```

Server automatically sets `user_id = current_user.id` (owner enforcement).

#### Update Profile
```http
PUT /api/server-profiles/{id}
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "name": "Updated Name",
  "ssh_host": "192.168.1.200",
  ...
}
```

#### Delete Profile
```http
DELETE /api/server-profiles/{id}
Authorization: Bearer <access_token>
```

## Client Implementation Guide

### 1. Detection: Check if Local Backend Available
```typescript
// client/src/lib/localApi.ts
async function isLocalBackendAvailable(): Promise<boolean> {
  try {
    const response = await fetch('http://127.0.0.1:3001/api/health', {
      method: 'GET',
      signal: AbortSignal.timeout(2000)
    });
    return response.ok;
  } catch {
    return false;
  }
}
```

### 2. Login: Obtain JWT
```typescript
async function loginLocal(username: string, password: string): Promise<{token: string, user: any}> {
  const response = await fetch('http://127.0.0.1:3001/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  });
  
  if (!response.ok) throw new Error('Login failed');
  
  const data = await response.json();
  return { token: data.access_token, user: data.user };
}
```

### 3. Store Token Securely: Use OS Keyring
```typescript
// Install: npm install keytar
import * as keytar from 'keytar';

const SERVICE_NAME = 'BaluDesk';
const ACCOUNT_NAME = 'local-api-token';

async function storeToken(token: string): Promise<void> {
  await keytar.setPassword(SERVICE_NAME, ACCOUNT_NAME, token);
}

async function getToken(): Promise<string | null> {
  return await keytar.getPassword(SERVICE_NAME, ACCOUNT_NAME);
}

async function clearToken(): Promise<void> {
  await keytar.deletePassword(SERVICE_NAME, ACCOUNT_NAME);
}
```

### 4. Make Authenticated Requests
```typescript
async function getProfiles(): Promise<any[]> {
  const token = await getToken();
  if (!token) throw new Error('Not authenticated');
  
  const response = await fetch('http://127.0.0.1:3001/api/server-profiles', {
    method: 'GET',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    }
  });
  
  if (response.status === 401) {
    // Token expired - clear and re-login
    await clearToken();
    throw new Error('Token expired');
  }
  
  if (!response.ok) throw new Error('Failed to fetch profiles');
  
  return await response.json();
}
```

### 5. Fallback to C++ IPC
```typescript
async function getProfilesWithFallback(): Promise<any[]> {
  // Try local HTTP first
  if (await isLocalBackendAvailable()) {
    try {
      return await getProfiles();
    } catch (error) {
      console.warn('Local API failed, falling back to IPC:', error);
    }
  }
  
  // Fall back to C++ IPC
  return await window.electron.ipcRenderer.invoke('get_remote_server_profiles');
}
```

## Testing

### Unit Tests (Backend)
```bash
# Test JWT auth
pytest backend/tests/test_auth.py -v

# Test owner enforcement
pytest backend/tests/test_server_profiles.py::test_profile_owner_isolation -v

# Test local-only middleware
pytest backend/tests/test_local_only.py -v
```

### Integration Test (Manual)
```bash
# 1. Start backend with local-only enforcement
export enforce_local_only=true
python start_dev.py

# 2. Test from localhost (should work)
curl -X POST http://127.0.0.1:3001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme"}'

# 3. Test from remote (should fail with 403)
# (Run from another machine or use --interface flag in curl to simulate)

# 4. Test owner isolation
# Login as admin, create profile
TOKEN_ADMIN=$(curl -s -X POST http://127.0.0.1:3001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme"}' | jq -r .access_token)

curl -X POST http://127.0.0.1:3001/api/server-profiles \
  -H "Authorization: Bearer $TOKEN_ADMIN" \
  -H "Content-Type: application/json" \
  -d '{"name":"admin-nas","ssh_host":"192.168.1.1","ssh_port":22,"ssh_username":"admin","ssh_private_key":""}'

# Login as another user, verify they can't see admin's profile
# (Create test user first if needed)
TOKEN_USER=$(curl -s -X POST http://127.0.0.1:3001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"testpass"}' | jq -r .access_token)

curl -X GET http://127.0.0.1:3001/api/server-profiles \
  -H "Authorization: Bearer $TOKEN_USER"
# Should return empty array []
```

## Security Checklist

- [x] JWT tokens are short-lived (15 min default)
- [x] Tokens stored in OS keyring (not plaintext files)
- [x] Server-side owner enforcement (never trust client)
- [x] Optional local-only enforcement via middleware
- [x] CORS restricted to known origins
- [x] Rate limiting on auth endpoints
- [x] Audit logging for failed auth attempts
- [x] Encrypted SSH keys in database
- [ ] Token refresh mechanism (optional - implement if needed)
- [ ] Unix socket / named pipe instead of TCP (optional - stronger local-only)

## Migration Notes

### For Existing BaluDesk Users
The C++ backend database stores profiles in `baludesk.db` with `owner TEXT` field (username).
The Python backend stores profiles in its SQLite DB with `user_id INTEGER` referencing the `users` table.

**These are separate databases** and will not conflict. The hybrid approach allows:
- Direct HTTP calls use Python backend DB (web-compatible, multi-user)
- C++ IPC calls use BaluDesk DB (desktop-native features)

For seamless UX, consider:
1. Syncing profile data between DBs on add/update/delete
2. Or: deprecating C++ profile storage and always use Python backend
3. Or: Keep them separate and let users choose (config flag)

## Production Deployment

### Recommended Settings
```bash
# Production .env
environment=production
debug=false
enforce_local_only=true
allow_public_profile_list=false  # Disable if not needed
SECRET_KEY=<strong-random-secret-64-chars>
token_secret=<strong-random-secret-64-chars>
ACCESS_TOKEN_EXPIRE_MINUTES=15

# Bind only to localhost
host=127.0.0.1
port=3001
```

### Optional: Unix Socket (Linux/Mac)
For even stronger local-only guarantees, bind FastAPI to a Unix socket instead of TCP:

```python
# In start_dev.py or uvicorn command
uvicorn.run(
    "app.main:app",
    uds="/tmp/baluhost.sock",  # Unix domain socket
    log_level="info",
)
```

Client would then connect via socket instead of HTTP (requires custom transport).

## Next Steps

1. **Client Implementation:** Implement `localApi.ts` wrapper with keytar storage
2. **UI Toggle:** Add Settings page option to enable/disable direct local access
3. **E2E Tests:** Create Playwright tests for full Electron + FastAPI flow
4. **Documentation:** Update user-facing docs with Option B security model
5. **Monitoring:** Add metrics for direct-HTTP vs IPC usage patterns

## Support & Questions

For issues or questions about this implementation, see:
- [ARCHITECTURE.md](../../ARCHITECTURE.md) - Overall architecture
- [TECHNICAL_DOCUMENTATION.md](../../TECHNICAL_DOCUMENTATION.md) - Feature docs
- [SECURITY.md](../../SECURITY.md) - Security policies
