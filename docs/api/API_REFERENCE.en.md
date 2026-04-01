# BaluHost API Reference

BaluHost provides a REST API for all features. The complete, interactive documentation is available as Swagger UI.

## Swagger UI (Interactive)

The recommended way to explore the API:

```
http://baluhost.local/docs
```

There you'll find all endpoints with parameters, schemas, and can test requests directly.

## Base URL

```
http://baluhost.local/api
```

All API endpoints use the `/api` prefix.

## Authentication

Most endpoints require JWT authentication. Include the token in the `Authorization` header:

```http
Authorization: Bearer <access_token>
```

### Token Types

| Type | Validity | Usage |
|------|----------|-------|
| **Access Token** | 15 minutes | API requests |
| **Refresh Token** | 7 days | Renew access token |
| **SSE Token** | 60 seconds | Server-Sent Events (upload progress) |

### Login

```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "string",
  "password": "string"
}
```

Response:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "role": "admin"
  }
}
```

### Refresh Token

```http
POST /api/auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJ..."
}
```

## API Areas

| Path | Area | Auth |
|------|------|------|
| `/api/auth/*` | Authentication (Login, Register, Refresh, 2FA) | Partial |
| `/api/files/*` | File management (Upload, Download, Folders, Search) | Yes |
| `/api/users/*` | User management | Admin |
| `/api/shares/*` | File sharing | Yes |
| `/api/system/*` | System info, RAID, SMART, Telemetry | Yes |
| `/api/monitoring/*` | Real-time metrics (CPU, RAM, Network, Disk I/O) | Yes |
| `/api/power/*` | CPU profiles, power management | Admin |
| `/api/fans/*` | Fan control, temperature curves | Admin |
| `/api/vpn/*` | VPN configuration | Admin |
| `/api/backup/*` | Backup/Restore | Admin |
| `/api/sync/*` | Desktop synchronization | Yes |
| `/api/mobile/*` | Mobile device management | Admin |
| `/api/logging/*` | Audit logs | Yes (restricted) |
| `/api/schedulers/*` | Scheduler management | Admin |
| `/api/notifications/*` | Push notifications | Yes |
| `/api/plugins/*` | Plugin system | Admin |
| `/api/pihole/*` | Pi-hole DNS | Admin |
| `/api/cloud/*` | Cloud import (rclone) | Yes |
| `/api/updates/*` | Update mechanism | Admin |
| `/api/sleep/*` | Sleep mode | Admin |
| `/api/webdav/*` | WebDAV server | Admin |
| `/api/samba/*` | Samba/SMB shares | Admin |
| `/api/benchmark/*` | System benchmark | Admin |
| `/api/api-keys/*` | API key management | Yes |
| `/api/admin/*` | Admin dashboard | Admin |
| `/api/admin-db/*` | Database inspection | Admin |
| `/api/energy/*` | Energy consumption | Admin |
| `/api/tapo/*` | Smart plug control (TP-Link Tapo) | Admin |
| `/api/setup/*` | Setup wizard | Setup token |

## Rate Limiting

API requests are protected by rate limiting:

| Endpoint type | Limit |
|--------------|-------|
| General API | 100 requests/second |
| Auth endpoints (Login, Register) | 10 requests/second |
| Password change | 5 requests/minute |

When exceeded: HTTP 429 (Too Many Requests).

## API Keys

As an alternative to JWT authentication, API keys can be used for integrations:

1. Settings → API Keys → "Create new key"
2. Include key in header: `X-API-Key: <key>`

## Error Format

All errors follow a consistent format:

```json
{
  "detail": "Error description"
}
```

Common HTTP status codes:
- `401` — Not authenticated
- `403` — No permission
- `404` — Resource not found
- `422` — Validation error
- `429` — Rate limit exceeded

---

**Version:** 1.23.0  
**Last updated:** April 2026
