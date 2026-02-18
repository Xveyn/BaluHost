# BaluHost API Reference

Complete API documentation for BaluHost NAS Management Platform.

## 🌐 Base URL

**Development:**
```
http://localhost:3001/api
```

**Production:**
```
https://your-domain.com/api
```

## 🔐 Authentication

Most endpoints require JWT authentication. Include the token in the `Authorization` header:

```http
Authorization: Bearer <your_jwt_token>
```

### Obtaining a Token

**Endpoint:** `POST /auth/login`

**Request:**
```json
{
  "username": "admin",
  "password": "changeme"
}
```

**Response:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "role": "admin",
    "created_at": "2025-01-01T00:00:00Z"
  }
}
```

## 📋 API Endpoints

### Authentication

#### Login
```http
POST /auth/login
```

**Request Body:**
```json
{
  "username": "string",
  "password": "string"
}
```

**Response:** `200 OK`
```json
{
  "token": "string",
  "user": {
    "id": 1,
    "username": "string",
    "email": "string",
    "role": "admin|user",
    "created_at": "2025-01-01T00:00:00Z"
  }
}
```

**Errors:**
- `401 Unauthorized` - Invalid credentials

#### Logout
```http
POST /auth/logout
```

**Headers:** Requires authentication

**Response:** `200 OK`
```json
{
  "message": "Logged out successfully"
}
```

#### Get Current User
```http
GET /auth/me
```

**Headers:** Requires authentication

**Response:** `200 OK`
```json
{
  "id": 1,
  "username": "string",
  "email": "string",
  "role": "admin|user",
  "created_at": "2025-01-01T00:00:00Z"
}
```

---

### File Management

#### List Files
```http
GET /files/list
```

**Query Parameters:**
- `path` (optional): Directory path (default: "/")

**Headers:** Requires authentication

**Response:** `200 OK`
```json
{
  "files": [
    {
      "name": "document.pdf",
      "path": "/documents/document.pdf",
      "is_directory": false,
      "size": 1048576,
      "modified": "2025-01-01T12:00:00Z",
      "owner_id": 1
    },
    {
      "name": "photos",
      "path": "/photos",
      "is_directory": true,
      "size": 0,
      "modified": "2025-01-01T10:00:00Z",
      "owner_id": 1
    }
  ],
  "current_path": "/"
}
```

**Errors:**
- `404 Not Found` - Path doesn't exist
- `403 Forbidden` - No access to path

#### Upload File
```http
POST /files/upload
```

**Headers:** 
- Requires authentication
- `Content-Type: multipart/form-data`

**Request Body (FormData):**
- `file`: File to upload
- `path` (optional): Target directory (default: "/")

**Response:** `200 OK`
```json
{
  "message": "File uploaded successfully",
  "file": {
    "name": "document.pdf",
    "path": "/documents/document.pdf",
    "size": 1048576,
    "owner_id": 1
  }
}
```

**Errors:**
- `413 Payload Too Large` - File exceeds quota
- `403 Forbidden` - No write access
- `400 Bad Request` - Invalid file

#### Download File
```http
GET /files/download
```

**Query Parameters:**
- `path` (required): File path

**Headers:** Requires authentication

**Response:** `200 OK`
- Returns file content with appropriate `Content-Type` header

**Errors:**
- `404 Not Found` - File doesn't exist
- `403 Forbidden` - No read access

#### Create Folder
```http
POST /files/create-folder
```

**Headers:** Requires authentication

**Request Body:**
```json
{
  "path": "/new-folder",
  "name": "My Folder"
}
```

**Response:** `200 OK`
```json
{
  "message": "Folder created successfully",
  "folder": {
    "name": "My Folder",
    "path": "/new-folder/My Folder",
    "is_directory": true,
    "owner_id": 1
  }
}
```

**Errors:**
- `409 Conflict` - Folder already exists
- `403 Forbidden` - No write access

#### Rename File/Folder
```http
POST /files/rename
```

**Headers:** Requires authentication

**Request Body:**
```json
{
  "path": "/old-name.txt",
  "new_name": "new-name.txt"
}
```

**Response:** `200 OK`
```json
{
  "message": "Renamed successfully",
  "file": {
    "name": "new-name.txt",
    "path": "/new-name.txt"
  }
}
```

**Errors:**
- `404 Not Found` - Source doesn't exist
- `409 Conflict` - Target already exists
- `403 Forbidden` - Not owner or admin

#### Move File/Folder
```http
POST /files/move
```

**Headers:** Requires authentication

**Request Body:**
```json
{
  "source": "/folder1/file.txt",
  "destination": "/folder2/"
}
```

**Response:** `200 OK`
```json
{
  "message": "Moved successfully"
}
```

**Errors:**
- `404 Not Found` - Source doesn't exist
- `403 Forbidden` - Not owner or admin

#### Delete File/Folder
```http
DELETE /files/delete
```

**Headers:** Requires authentication

**Query Parameters:**
- `path` (required): Path to delete

**Response:** `200 OK`
```json
{
  "message": "Deleted successfully"
}
```

**Errors:**
- `404 Not Found` - Path doesn't exist
- `403 Forbidden` - Not owner or admin

---

### User Management (Admin Only)

#### List Users
```http
GET /users
```

**Headers:** Requires admin authentication

**Response:** `200 OK`
```json
{
  "users": [
    {
      "id": 1,
      "username": "admin",
      "email": "admin@example.com",
      "role": "admin",
      "created_at": "2025-01-01T00:00:00Z"
    }
  ]
}
```

#### Create User
```http
POST /users
```

**Headers:** Requires admin authentication

**Request Body:**
```json
{
  "username": "newuser",
  "email": "user@example.com",
  "password": "securepassword",
  "role": "user"
}
```

**Response:** `201 Created`
```json
{
  "id": 2,
  "username": "newuser",
  "email": "user@example.com",
  "role": "user",
  "created_at": "2025-01-01T12:00:00Z"
}
```

**Errors:**
- `409 Conflict` - Username already exists
- `403 Forbidden` - Not admin

#### Update User
```http
PUT /users/{user_id}
```

**Headers:** Requires admin authentication

**Request Body:**
```json
{
  "email": "newemail@example.com",
  "role": "admin"
}
```

**Response:** `200 OK`
```json
{
  "id": 2,
  "username": "newuser",
  "email": "newemail@example.com",
  "role": "admin",
  "created_at": "2025-01-01T12:00:00Z"
}
```

#### Delete User
```http
DELETE /users/{user_id}
```

**Headers:** Requires admin authentication

**Response:** `200 OK`
```json
{
  "message": "User deleted successfully"
}
```

**Errors:**
- `404 Not Found` - User doesn't exist
- `403 Forbidden` - Cannot delete yourself

---

### System Information

#### System Info
```http
GET /system/info
```

**Headers:** Requires authentication

**Response:** `200 OK`
```json
{
  "hostname": "baluhost-server",
  "platform": "Linux",
  "architecture": "x86_64",
  "cpu_count": 8,
  "total_memory_gb": 16.0,
  "uptime_seconds": 86400
}
```

#### Storage Info
```http
GET /system/storage
```

**Headers:** Requires authentication

**Response:** `200 OK`
```json
{
  "total": 5368709120,
  "used": 1073741824,
  "available": 4294967296,
  "percent": 20.0,
  "quota": 5368709120
}
```

#### Storage Quota
```http
GET /system/quota
```

**Headers:** Requires authentication

**Response:** `200 OK`
```json
{
  "quota_bytes": 5368709120,
  "quota_gb": 5.0
}
```

#### Process List
```http
GET /system/processes
```

**Query Parameters:**
- `limit` (optional): Number of processes (default: 10)

**Headers:** Requires authentication

**Response:** `200 OK`
```json
{
  "processes": [
    {
      "pid": 1234,
      "name": "python",
      "cpu_percent": 5.2,
      "memory_mb": 512.0
    }
  ]
}
```

#### Telemetry History
```http
GET /system/telemetry/history
```

**Headers:** Requires authentication

**Response:** `200 OK`
```json
{
  "history": [
    {
      "timestamp": "2025-01-01T12:00:00Z",
      "cpu_percent": 45.2,
      "memory_percent": 62.5,
      "disk_read_mbps": 12.5,
      "disk_write_mbps": 8.3,
      "network_down_mbps": 5.2,
      "network_up_mbps": 2.1
    }
  ]
}
```

---

### RAID Management (Admin Only)

#### RAID Status
```http
GET /system/raid/status
```

**Headers:** Requires admin authentication

**Response:** `200 OK`
```json
{
  "arrays": [
    {
      "name": "md0",
      "level": "raid1",
      "state": "healthy",
      "size_gb": 5,
      "devices": [
        {
          "name": "sda1",
          "state": "active"
        },
        {
          "name": "sdb1",
          "state": "active"
        }
      ],
      "sync_progress": null
    }
  ],
  "available_disks": [
    {
      "name": "sdc",
      "size_gb": 10,
      "model": "Virtual Disk",
      "in_raid": false
    }
  ]
}
```

#### Degrade Array (Dev Mode)
```http
POST /system/raid/degrade
```

**Headers:** Requires admin authentication

**Request Body:**
```json
{
  "array": "md0",
  "device": "sda1"
}
```

**Response:** `200 OK`
```json
{
  "message": "[DEV MODE] Array md0 degraded - device sda1 marked as failed"
}
```

#### Rebuild Array (Dev Mode)
```http
POST /system/raid/rebuild
```

**Headers:** Requires admin authentication

**Request Body:**
```json
{
  "array": "md0",
  "device": "sda1"
}
```

**Response:** `200 OK`
```json
{
  "message": "[DEV MODE] Rebuild started for md0"
}
```

#### Finalize Rebuild (Dev Mode)
```http
POST /system/raid/finalize
```

**Headers:** Requires admin authentication

**Request Body:**
```json
{
  "array": "md0"
}
```

**Response:** `200 OK`
```json
{
  "message": "Array md0 restored to optimal state"
}
```

#### Set RAID Options
```http
POST /system/raid/options
```

**Headers:** Requires admin authentication

**Request Body:**
```json
{
  "array": "md0",
  "bitmap": "internal",
  "sync_min": 10000,
  "sync_max": 200000
}
```

**Response:** `200 OK`
```json
{
  "message": "RAID options updated"
}
```

---

### SMART Disk Health

#### SMART Status
```http
GET /system/smart/status
```

**Headers:** Requires authentication

**Response:** `200 OK`
```json
{
  "disks": [
    {
      "name": "/dev/sda",
      "model": "Samsung SSD 860",
      "serial": "S3Z9NB0K123456",
      "capacity_gb": 500,
      "status": "PASSED",
      "temperature_c": 32,
      "power_on_hours": 12345,
      "power_cycle_count": 456,
      "reallocated_sectors": 0
    }
  ]
}
```

---

### Audit Logging

#### Get Audit Logs
```http
GET /logging/audit
```

**Query Parameters:**
- `days` (optional): Number of days (default: 1)
- `limit` (optional): Max number of logs (default: 100)
- `action` (optional): Filter by action type
- `user` (optional): Filter by username

**Headers:** Requires authentication

**Response:** `200 OK`
```json
{
  "logs": [
    {
      "timestamp": "2025-01-01T12:00:00Z",
      "user": "admin",
      "action": "upload",
      "resource": "/documents/report.pdf",
      "status": "success",
      "details": "File uploaded successfully",
      "ip_address": "127.0.0.1"
    }
  ],
  "total": 1
}
```

---

### Scheduler Management

#### List All Schedulers
```http
GET /schedulers
```

**Headers:** Requires authentication

**Response:** `200 OK`
```json
{
  "schedulers": [
    {
      "name": "raid_scrub",
      "display_name": "RAID Scrub",
      "description": "Performs RAID array scrub to check data integrity",
      "is_running": false,
      "is_enabled": true,
      "interval_seconds": 604800,
      "interval_display": "Every 7 days",
      "last_run": "2026-01-28T03:00:00Z",
      "last_status": "completed",
      "next_run": "2026-02-04T03:00:00Z",
      "execution_count": 5,
      "error_count": 0
    }
  ],
  "total_running": 0,
  "total_enabled": 6
}
```

#### Get Scheduler Details
```http
GET /schedulers/{name}
```

**Path Parameters:**
- `name` (required): Scheduler name (raid_scrub, smart_scan, backup, sync_check, notification_check, upload_cleanup)

**Headers:** Requires authentication

**Response:** `200 OK`
```json
{
  "name": "raid_scrub",
  "display_name": "RAID Scrub",
  "description": "Performs RAID array scrub to check data integrity and repair errors",
  "is_running": false,
  "is_enabled": true,
  "interval_seconds": 604800,
  "interval_display": "Every 7 days",
  "last_run": "2026-01-28T03:00:00Z",
  "last_status": "completed",
  "next_run": "2026-02-04T03:00:00Z",
  "execution_count": 5,
  "error_count": 0
}
```

**Errors:**
- `404 Not Found` - Scheduler doesn't exist

#### Run Scheduler Now
```http
POST /schedulers/{name}/run-now
```

**Path Parameters:**
- `name` (required): Scheduler name

**Headers:** Requires admin authentication

**Response:** `200 OK`
```json
{
  "message": "Scheduler raid_scrub started",
  "execution_id": 123,
  "started_at": "2026-01-29T12:00:00Z"
}
```

**Errors:**
- `404 Not Found` - Scheduler doesn't exist
- `409 Conflict` - Scheduler is already running
- `403 Forbidden` - Not admin

#### Get Scheduler History
```http
GET /schedulers/{name}/history
```

**Path Parameters:**
- `name` (required): Scheduler name

**Query Parameters:**
- `limit` (optional): Number of entries (default: 50)
- `offset` (optional): Pagination offset (default: 0)

**Headers:** Requires authentication

**Response:** `200 OK`
```json
{
  "scheduler_name": "raid_scrub",
  "executions": [
    {
      "id": 123,
      "started_at": "2026-01-28T03:00:00Z",
      "ended_at": "2026-01-28T03:45:00Z",
      "status": "completed",
      "trigger_type": "scheduled",
      "duration_seconds": 2700,
      "error_message": null
    }
  ],
  "total": 5
}
```

#### Get All Scheduler History (Timeline)
```http
GET /schedulers/history/all
```

**Query Parameters:**
- `limit` (optional): Number of entries (default: 100)
- `hours` (optional): Hours of history to fetch (default: 24)

**Headers:** Requires authentication

**Response:** `200 OK`
```json
{
  "executions": [
    {
      "id": 123,
      "scheduler_name": "raid_scrub",
      "display_name": "RAID Scrub",
      "started_at": "2026-01-28T03:00:00Z",
      "ended_at": "2026-01-28T03:45:00Z",
      "status": "completed",
      "trigger_type": "scheduled",
      "duration_seconds": 2700
    },
    {
      "id": 124,
      "scheduler_name": "smart_scan",
      "display_name": "SMART Scan",
      "started_at": "2026-01-28T04:00:00Z",
      "ended_at": "2026-01-28T04:02:00Z",
      "status": "completed",
      "trigger_type": "scheduled",
      "duration_seconds": 120
    }
  ],
  "total": 2
}
```

#### Toggle Scheduler
```http
POST /schedulers/{name}/toggle
```

**Path Parameters:**
- `name` (required): Scheduler name

**Headers:** Requires admin authentication

**Request Body:**
```json
{
  "enabled": false
}
```

**Response:** `200 OK`
```json
{
  "message": "Scheduler raid_scrub disabled",
  "scheduler_name": "raid_scrub",
  "is_enabled": false
}
```

**Errors:**
- `404 Not Found` - Scheduler doesn't exist
- `403 Forbidden` - Not admin

---

## 🔄 Response Format

### Success Response
```json
{
  "message": "Operation successful",
  "data": { /* response data */ }
}
```

### Error Response
```json
{
  "detail": "Error message",
  "error": "Detailed error description"
}
```

### Common HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | OK - Request successful |
| 201 | Created - Resource created |
| 204 | No Content - Success with no response body |
| 400 | Bad Request - Invalid input |
| 401 | Unauthorized - Authentication required |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found - Resource doesn't exist |
| 409 | Conflict - Resource already exists |
| 413 | Payload Too Large - File/quota limit exceeded |
| 500 | Internal Server Error - Server error |

---

## 🧪 Interactive API Documentation

FastAPI provides auto-generated interactive documentation:

**Swagger UI:**
```
http://localhost:3001/docs
```

**ReDoc:**
```
http://localhost:3001/redoc
```

These interfaces allow you to:
- View all endpoints
- See request/response schemas
- Test endpoints directly
- Authenticate with JWT tokens

---

## 📝 Example: Complete Workflow

### 1. Login
```bash
curl -X POST http://localhost:3001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme"}'
```

### 2. List Files
```bash
curl -X GET http://localhost:3001/api/files/list \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 3. Upload File
```bash
curl -X POST http://localhost:3001/api/files/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@document.pdf" \
  -F "path=/"
```

### 4. Download File
```bash
curl -X GET "http://localhost:3001/api/files/download?path=/document.pdf" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -o document.pdf
```

---

## 🔐 Security Considerations

### Token Security
- Tokens expire after 12 hours (configurable)
- Store tokens securely (localStorage, secure cookies)
- Never commit tokens to version control
- Use HTTPS in production

### Password Requirements
- Minimum 8 characters (recommended)
- Change default passwords immediately
- Use strong, unique passwords

### Rate Limiting
_(Not yet implemented - see TODO.md)_

---

## 🐞 Error Handling

All errors follow this format:

```json
{
  "detail": "Human-readable error message",
  "error": "Technical error details"
}
```

**Example:**
```json
{
  "detail": "Quota exceeded",
  "error": "Upload would exceed storage quota of 5 GB"
}
```

---

## 📚 Additional Resources

- [Main Documentation](../README.md)
- [User Guide](../getting-started/USER_GUIDE.md)
- [Architecture Documentation](../ARCHITECTURE.md)
- [Contributing Guidelines](../../CONTRIBUTING.md)

---

**Last Updated:** January 2026
**API Version:** 1.4.2
**Base Path:** `/api`
