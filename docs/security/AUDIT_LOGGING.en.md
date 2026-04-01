# Audit Logging

BaluHost automatically logs security-relevant actions to the database. Logs are viewable through the web interface.

## What is logged?

### Authentication
- Successful and failed logins
- Password changes
- 2FA activation/deactivation
- Token renewals

### File access
- Uploads, downloads, deletions
- Folder creation, moves, renames
- Share creation and deletion

### Administration
- User creation, editing, deletion
- RAID operations
- VPN client management
- Configuration changes

### System
- Server start and stop
- Backup operations
- Scheduler executions

## Logging Page

The Logging page is accessible under **Logging** in the sidebar (Admin area).

### Filters

| Filter | Options |
|--------|---------|
| **Time range** | 1 day, 7 days, 30 days, up to 365 days |
| **Event type** | FILE_ACCESS, AUTH, SYSTEM, ADMIN |
| **User** | Filter by username (admin only) |
| **Action** | upload, download, delete, login, etc. |
| **Status** | Successful / Failed |

### Pagination

Logs are displayed in pages (50 entries per page). Navigate using the page controls.

### Visibility by role

| Role | Visibility |
|------|-----------|
| **Admin** | All events, all users, full details |
| **User** | Limited events, anonymized usernames, no details |

## Each log entry contains

- **Timestamp** — When the action occurred
- **Event type** — Category (FILE_ACCESS, AUTH, SYSTEM, ADMIN)
- **User** — Who performed the action
- **Action** — What was done (upload, login, delete, etc.)
- **Resource** — Affected file or resource
- **Status** — Success or failure
- **Details** — Additional information (e.g., file size, target path)

## Storage

- Logs are stored in the PostgreSQL database (`audit_logs` table)
- Retention is configurable via monitoring configuration
- Sensitive data (passwords, tokens, private keys) is **never** logged

## API Access

Audit logs are also available via the REST API:

```
GET /api/logging/audit?days=7&page=1&page_size=50
```

Requires authentication. Admins see full logs, regular users see a restricted view.

---

**Version:** 1.23.0  
**Last updated:** April 2026
