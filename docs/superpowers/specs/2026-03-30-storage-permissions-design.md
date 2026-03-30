# Storage Permissions & Push Notifications Design Spec

**Date:** 2026-03-30
**Status:** Approved
**Approach:** Shared Group + setgid (Option B)

---

## Problem

The BaluHost backend (uvicorn running as user `sven`) creates files/folders on RAID mounts (`/mnt/md*`), but files created by other processes (initial data copy, Samba as root) end up owned by `root:root`. This causes `PermissionError` on file operations (mkdir, write, delete, rename, move), resulting in 500 errors.

The current `storage_permissions.py` sets `chmod 2775`/`0664` but never calls `chown` — the group infrastructure is missing entirely.

### Root Cause Chain

1. Data initially copied to RAID as root → files owned by `root:root`
2. Samba with `force group = sven` (user's primary group, not shared group)
3. Backend runs as `sven:sven` — cannot write to `root:root` files
4. `storage_permissions.py` only does `chmod`, no group alignment
5. OS `PermissionError` uncaught in most file operations → 500 instead of 403

---

## Solution: Shared Group + setgid

### Core Concept

Create a dedicated `baluhost` system group. All storage-writing processes (backend, Samba) share this group. The setgid bit (`2775`) on directories ensures new files inherit the group automatically.

```
Before:  sven:sven (backend) vs root:root (copied files) → PermissionError
After:   sven:baluhost (backend) + root:baluhost (files) → group write OK
```

### Why Not os.chown()?

Calling `os.chown()` in the web backend is a security anti-pattern for NAS systems:

- **Privilege escalation**: Requires `CAP_CHOWN` capability or root — grants the web process power to reassign any file's ownership
- **Symlink attacks (CWE-61)**: `os.chown(path)` follows symlinks; a malicious symlink in user-writable storage could redirect chown to system files
- **TOCTOU races**: Time gap between path validation (`_jail_path()`) and `chown()` call is exploitable
- **Blast radius**: A bug in chown logic could silently reassign ownership of the entire storage tree

The shared-group approach achieves the same result with zero additional privileges.

---

## Component Design

### 1. Linux Group Infrastructure (One-Time Setup)

```bash
# Create shared group
sudo groupadd baluhost

# Add service user to group
sudo usermod -aG baluhost sven

# Fix existing file ownership on all RAID mounts
sudo chown -R sven:baluhost /mnt/md1
sudo chown -R sven:baluhost /mnt/md2   # if additional mounts exist

# Set setgid + group-write on all directories
sudo find /mnt/md1 -type d -exec chmod 2775 {} +
sudo find /mnt/md1 -type f -exec chmod 0664 {} +
```

After this:
- All existing files: `sven:baluhost` with correct modes
- New directories: inherit `baluhost` group via setgid bit
- New files: inherit `baluhost` group from parent directory

### 2. systemd Service

Update `deploy/install/templates/baluhost-backend.service`:

```ini
# Change from:
Group=@@BALUHOST_USER@@
# To:
Group=baluhost
```

This ensures the uvicorn workers run with `baluhost` as their primary group, so all files they create have group `baluhost`.

### 3. Samba Configuration

**`backend/app/services/samba_service.py`** — change `force group`:

```python
# In regenerate_shares_config(), change:
force group = {service_user}
# To:
force group = {settings.storage_group}
```

**`deploy/samba/setup-samba.sh`** — update default:

```bash
STORAGE_GROUP="${STORAGE_GROUP:-baluhost}"
```

**`deploy/samba/smb.conf`** — no changes needed (per-share config is auto-generated).

### 4. Backend Configuration

**`backend/app/core/config.py`** — new setting:

```python
storage_group: str = "baluhost"
```

Used by `samba_service.py` for `force group` and available for future deploy scripts. No production validator needed — it's a group name, not a secret.

### 5. storage_permissions.py — No Changes

The existing modes are already correct:

```python
STORAGE_DIR_MODE = 0o2775    # rwxrwsr-x  (setgid + group write)
STORAGE_FILE_MODE = 0o0664   # rw-rw-r--
STORAGE_UMASK = 0o002
```

The `chmod` calls in `set_storage_dir_permissions()` and `set_storage_file_permissions()` continue to work as before. The missing piece was group alignment, which is now handled by the Linux group setup.

### 6. PermissionError Handling in operations.py

Currently only `create_folder` catches OS-level `PermissionError`. Six more operations need wrapping:

| Operation | Line | Vulnerable Call |
|---|---|---|
| `save_uploads` | ~417 | `open(destination, 'wb')` |
| `save_uploads` | ~436 | `destination.write_bytes(data)` |
| `delete_path` | ~593 | `target.rmdir()` |
| `delete_path` | ~606 | `target.unlink()` |
| `rename_path` | ~704 | `source.rename(target)` |
| `move_path` | ~767 | `source.rename(...)` |

Each gets a `try/except PermissionError` that:
1. Emits a push notification to admins (see Section 7)
2. Raises `PermissionDeniedError` with a user-facing message
3. Returns 403 instead of 500

### 7. Push Notifications for Storage Permission Errors

#### New EventType

In `backend/app/services/notifications/events.py`:

```python
class EventType(str, Enum):
    # ... existing events ...

    # System events
    STORAGE_PERMISSION_ERROR = "system.storage_permission"
```

#### Event Configuration

```python
EventType.STORAGE_PERMISSION_ERROR: EventConfig(
    priority=2,
    category="system",
    notification_type="warning",
    title_template="Speicherzugriff verweigert: {operation}",
    message_template=(
        "Dateioperation '{operation}' fehlgeschlagen auf Pfad '{path}': "
        "Keine Berechtigung. Benutzer: {username}. "
        "Mögliche Ursache: Datei/Ordner gehört einem anderen Systemprozess."
    ),
    action_url="/files",
),
```

#### Cooldown

```python
_COOLDOWN_SECONDS = {
    # ... existing ...
    "system.storage_permission": 300,   # 5 min per path
}
```

5-minute cooldown per path segment prevents notification spam (e.g., bulk Samba uploads all hitting the same directory).

#### Emission Helper

Central helper function in `operations.py` (avoids 7x inline imports):

```python
def _emit_permission_error(operation: str, path: str, username: str) -> None:
    """Emit storage permission error notification to admins."""
    from app.services.notifications.events import (
        get_event_emitter, EventType,
    )
    get_event_emitter().emit_for_admins_sync(
        EventType.STORAGE_PERMISSION_ERROR,
        cooldown_entity=path,
        operation=operation,
        path=path,
        username=username,
    )
```

#### Notification Flow

```
OS PermissionError
  → catch in operations.py
  → _emit_permission_error(operation, path, username)
    → EventEmitter.emit_for_admins_sync()
      → Cooldown check (5 min per path)
      → DB: Notification record (user_id=NULL → admin-only)
      → FCM: Push to all admin mobile devices (Firebase)
      → WebSocket: Real-time bell icon update in Web UI
  → raise PermissionDeniedError → 403 to user
```

#### Why Admin-Only?

- Storage permission errors are an **infrastructure problem** (wrong file ownership), not a user mistake
- Only admins can run `chown`/`chmod` on the server to fix it
- Regular users see the 403 error message in the UI — that's sufficient feedback

---

## Security Analysis

### What This Design Does NOT Do

- **No `os.chown()` in application code** — ownership managed exclusively via Linux groups + setgid
- **No `CAP_CHOWN` capability** — backend needs no additional privileges
- **No sudo** — no new sudoers entries needed
- **No new subprocess calls** — group setup is a one-time manual operation

### Security Properties Preserved

- `_jail_path()` continues to enforce per-user file isolation
- `ensure_owner_or_privileged()` ownership checks unchanged
- Setgid bit only affects group inheritance — does not grant cross-user access
- File permissions `0664` means group can read/write but not execute
- Directory permissions `2775` means group can list/create but setgid prevents ownership confusion

### Attack Surface Assessment

| Concern | Assessment |
|---|---|
| Group membership grants write access | Only `sven` (backend) and Samba system users are in `baluhost` group — both already have write access by design |
| Setgid on world-readable dirs | `0o2775` = others can read/traverse but not write. Same as current `0o0755` effective access for non-group users |
| Push notification spam | Cooldown (5 min per path) prevents flood. Admin-only target limits blast radius |
| Notification content leaks paths | Admin-only notification — admins already have full file system access |

---

## File Change Summary

| File | Change Type | Description |
|---|---|---|
| `backend/app/core/config.py` | New setting | `storage_group: str = "baluhost"` |
| `backend/app/services/samba_service.py` | Modify | `force group = {settings.storage_group}` |
| `backend/app/services/files/operations.py` | Modify | PermissionError catches at 6 new locations + `_emit_permission_error()` helper |
| `backend/app/services/notifications/events.py` | Add | `STORAGE_PERMISSION_ERROR` EventType, EventConfig, cooldown, sync convenience function |
| `deploy/install/templates/baluhost-backend.service` | Modify | `Group=baluhost` |
| `deploy/samba/setup-samba.sh` | Modify | `STORAGE_GROUP` variable |

### No Changes Required

| File | Reason |
|---|---|
| `storage_permissions.py` | Modes `0o2775`/`0o0664` already correct |
| `path_utils.py` | Path resolution unaffected |
| `api/routes/files.py` | Already catches `PermissionDeniedError` → 403 |
| `notifications/service.py` | Generic notification creation — no changes needed |
| `notifications/firebase.py` | FCM push dispatch — no changes needed |

---

## Deployment Sequence

1. **Create group and fix ownership** (on production server, before deploy):
   ```bash
   sudo groupadd baluhost
   sudo usermod -aG baluhost sven
   sudo chown -R sven:baluhost /mnt/md1
   sudo find /mnt/md1 -type d -exec chmod 2775 {} +
   sudo find /mnt/md1 -type f -exec chmod 0664 {} +
   ```
2. **Deploy code changes** (config, samba, operations, events)
3. **Update systemd service** (`Group=baluhost`)
4. **Restart services** (`systemctl restart baluhost-backend`)
5. **Restart Samba** (`systemctl restart smbd`) — picks up new `force group`

After deployment, new files from both backend and Samba will be created with group `baluhost` and correct permissions. The push notification system will alert admins if any permission issues remain.

---

## Testing Strategy

### Unit Tests

- `test_emit_permission_error`: Verify `_emit_permission_error()` calls `emit_for_admins_sync` with correct EventType and kwargs
- `test_permission_error_catches`: Each file operation (upload, delete, rename, move, create_folder) raises `PermissionDeniedError` on OS `PermissionError`
- `test_storage_permission_event_config`: Verify EventConfig has correct priority, category, templates
- `test_cooldown_suppression`: Second emit within 5 minutes for same path is suppressed

### Integration Tests

- `test_permission_error_returns_403`: API endpoint returns 403 (not 500) when underlying PermissionError occurs
- `test_notification_created_on_permission_error`: DB contains admin notification after PermissionError

### Manual Production Verification

After deployment:
```bash
# Verify group ownership
ls -la /mnt/md1/ | grep baluhost

# Verify setgid bit on directories
stat -c '%a %U:%G' /mnt/md1/Sven/

# Create test file via backend, verify group
touch /tmp/test && ls -la /tmp/test  # Compare with file created via API

# Verify Samba creates files with correct group
# (create file via SMB client, check ownership)
```
