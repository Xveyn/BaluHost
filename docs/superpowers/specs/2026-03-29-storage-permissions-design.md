# Storage Permission Fix: Consistent File Permissions for Multi-User Upload

**Date:** 2026-03-29
**Status:** Approved

## Problem

When a privileged user (Admin) uploads files to another user's storage directory via the mobile app, the server returns HTTP 500 because the backend process gets `[Errno 13] Permission denied` writing to `/mnt/md1/<username>/...`.

**Root cause:** The backend creates directories and files using system default permissions (umask 022 -> dirs 755, files 644). Directories or files created by other processes (Samba, manual) may have restrictive ownership. The backend never calls `os.chmod()` or sets `os.umask()`, so it can't write to directories it doesn't own, even though the app-level permission check (`ensure_owner_or_privileged`) passes.

## Solution

Align backend file permission handling with the existing Samba configuration:

| Setting | Samba config | Backend (new) |
|---------|-------------|---------------|
| File permissions | `create mask = 0664` | `os.chmod(file, 0o0664)` |
| Directory permissions | `directory mask = 0775` | `os.chmod(dir, 0o2775)` |
| Umask | implicit 002 | `os.umask(0o002)` |

The setgid bit (`2xxx`) on directories ensures new subdirectories inherit the parent's group, so the server process always has group-write access.

## Changes

### 1. `backend/app/core/lifespan.py` - Server startup

Set `os.umask(0o002)` in the lifespan handler. Each uvicorn worker runs lifespan independently, so all 4 workers get the correct umask.

### 2. `backend/app/services/files/operations.py` - Upload & folder creation

In `save_uploads()`:
- After `target.mkdir(parents=True, exist_ok=True)` (line 305): chmod 2775 on target and parents
- After `subfolder.mkdir()` (line 372): chmod 2775
- After `destination.parent.mkdir()` (line 378): chmod 2775
- After file write completes (after line 400/412): chmod 0664 on written file

In `create_folder()`:
- After `folder.mkdir()` (line 617): chmod 2775

### 3. `backend/app/services/users.py` - Home directory creation

In `_create_home_directory()`:
- After `home_dir.mkdir()` (line 41): chmod 2775

### 4. `backend/app/services/files/chunked_upload.py` - Chunked uploads

After finalizing chunked upload (moving temp file to destination):
- chmod 0664 on the final file
- chmod 2775 on any created parent directories

## Multi-Worker Safety

- `os.umask()` is per-process, set once at startup in each worker's lifespan - no race condition
- `os.chmod()` is atomic on Linux - concurrent calls from different workers setting the same value are safe
- No shared mutable state involved

## No `os.chown()` Needed

All processes (backend, Samba) run as the same OS user via `force user = {service_user}`. NAS users are application-level only (DB records), not separate OS users for file ownership. The OS user created by `_ensure_system_user()` is solely for Samba authentication and shares the service user's group.

## Permission Constants

Define once, use everywhere:

```python
STORAGE_DIR_MODE = 0o2775   # rwxrwsr-x (setgid + group write)
STORAGE_FILE_MODE = 0o0664  # rw-rw-r--
STORAGE_UMASK = 0o002       # complement of 0775/0664
```
