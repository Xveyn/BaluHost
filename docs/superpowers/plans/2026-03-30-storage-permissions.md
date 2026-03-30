# Storage Permissions & Push Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix RAID mount PermissionErrors by adding shared-group infrastructure, catch OS-level PermissionError in all file operations (returning 403 instead of 500), and push-notify admins when storage permission errors occur.

**Architecture:** Shared `baluhost` Linux group with setgid on RAID directories. No `os.chown()` in application code — group alignment handled entirely at OS level. New `STORAGE_PERMISSION_ERROR` event type plugs into the existing EventEmitter/Firebase push notification pipeline. All file operations in `operations.py` catch OS `PermissionError`, emit an admin notification, and re-raise as `PermissionDeniedError` (→ 403).

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, Firebase Cloud Messaging, pytest

**Spec:** `docs/superpowers/specs/2026-03-30-storage-permissions-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `backend/app/services/notifications/events.py` | Modify | New `STORAGE_PERMISSION_ERROR` EventType, EventConfig, cooldown, sync helper |
| `backend/app/core/config.py` | Modify | New `storage_group: str` setting |
| `backend/app/services/files/operations.py` | Modify | `_emit_permission_error()` helper + PermissionError catches in 5 operations |
| `backend/app/services/samba_service.py` | Modify | `force group` uses `settings.storage_group`; `_ensure_system_user` uses storage group |
| `deploy/install/templates/baluhost-backend.service` | Modify | `Group=baluhost` |
| `deploy/samba/setup-samba.sh` | Modify | `STORAGE_GROUP` variable |
| `backend/tests/services/test_storage_permission_events.py` | Create | Tests for new EventType, config, cooldown |
| `backend/tests/files/test_permission_error_handling.py` | Create | Tests for PermissionError → PermissionDeniedError + notification in all file ops |
| `backend/tests/services/test_samba_service.py` | Modify | Test `force group` uses `storage_group` setting |

---

### Task 1: Add STORAGE_PERMISSION_ERROR Event Type

**Files:**
- Modify: `backend/app/services/notifications/events.py`
- Create: `backend/tests/services/test_storage_permission_events.py`

- [ ] **Step 1: Write the tests**

Create `backend/tests/services/test_storage_permission_events.py`:

```python
"""Tests for STORAGE_PERMISSION_ERROR event type and helpers."""

import time as _time
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.user import User
from app.services.notifications.events import (
    EventType,
    EventConfig,
    EVENT_CONFIGS,
    EventEmitter,
    _cooldown_cache,
    _COOLDOWN_SECONDS,
    emit_storage_permission_error_sync,
)


class TestStoragePermissionEventType:
    """Verify the new event type is correctly defined."""

    def test_event_type_value(self):
        assert EventType.STORAGE_PERMISSION_ERROR == "system.storage_permission"

    def test_event_config_exists(self):
        config = EVENT_CONFIGS.get(EventType.STORAGE_PERMISSION_ERROR)
        assert config is not None

    def test_event_config_fields(self):
        config = EVENT_CONFIGS[EventType.STORAGE_PERMISSION_ERROR]
        assert config.priority == 2
        assert config.category == "system"
        assert config.notification_type == "warning"
        assert config.action_url == "/files"

    def test_title_template_formats(self):
        config = EVENT_CONFIGS[EventType.STORAGE_PERMISSION_ERROR]
        title = config.title_template.format(operation="upload")
        assert "upload" in title

    def test_message_template_formats(self):
        config = EVENT_CONFIGS[EventType.STORAGE_PERMISSION_ERROR]
        msg = config.message_template.format(
            operation="upload",
            path="Sven/test.txt",
            username="testuser",
        )
        assert "upload" in msg
        assert "Sven/test.txt" in msg
        assert "testuser" in msg

    def test_cooldown_configured(self):
        assert "system.storage_permission" in _COOLDOWN_SECONDS
        assert _COOLDOWN_SECONDS["system.storage_permission"] == 300


class TestStoragePermissionCooldown:
    """Verify cooldown suppresses repeated events."""

    @pytest.fixture(autouse=True)
    def _clear_cooldown(self):
        _cooldown_cache.clear()
        yield
        _cooldown_cache.clear()

    def test_first_emit_not_suppressed(self, db_session: Session, admin_user: User):
        emitter = EventEmitter()
        emitter.set_db_session_factory(lambda: db_session)

        emitter.emit_for_admins_sync(
            EventType.STORAGE_PERMISSION_ERROR,
            cooldown_entity="Sven/test",
            operation="upload",
            path="Sven/test",
            username="testuser",
        )

        notif = db_session.query(Notification).filter(
            Notification.extra_data["event_type"].as_string() == "system.storage_permission"
        ).first()
        assert notif is not None

    def test_second_emit_within_cooldown_suppressed(self, db_session: Session, admin_user: User):
        emitter = EventEmitter()
        emitter.set_db_session_factory(lambda: db_session)

        # First emit
        emitter.emit_for_admins_sync(
            EventType.STORAGE_PERMISSION_ERROR,
            cooldown_entity="Sven/test",
            operation="upload",
            path="Sven/test",
            username="testuser",
        )

        # Second emit — should be suppressed
        emitter.emit_for_admins_sync(
            EventType.STORAGE_PERMISSION_ERROR,
            cooldown_entity="Sven/test",
            operation="upload",
            path="Sven/test",
            username="testuser",
        )

        count = db_session.query(Notification).filter(
            Notification.extra_data["event_type"].as_string() == "system.storage_permission"
        ).count()
        assert count == 1

    def test_different_paths_not_suppressed(self, db_session: Session, admin_user: User):
        emitter = EventEmitter()
        emitter.set_db_session_factory(lambda: db_session)

        emitter.emit_for_admins_sync(
            EventType.STORAGE_PERMISSION_ERROR,
            cooldown_entity="Sven/path1",
            operation="upload",
            path="Sven/path1",
            username="testuser",
        )
        emitter.emit_for_admins_sync(
            EventType.STORAGE_PERMISSION_ERROR,
            cooldown_entity="Sven/path2",
            operation="upload",
            path="Sven/path2",
            username="testuser",
        )

        count = db_session.query(Notification).filter(
            Notification.extra_data["event_type"].as_string() == "system.storage_permission"
        ).count()
        assert count == 2


class TestConvenienceFunction:
    """Verify the sync convenience function."""

    @pytest.fixture(autouse=True)
    def _clear_cooldown(self):
        _cooldown_cache.clear()
        yield
        _cooldown_cache.clear()

    def test_emit_storage_permission_error_sync_calls_emitter(self):
        with patch("app.services.notifications.events.get_event_emitter") as mock_get:
            mock_emitter = MagicMock()
            mock_get.return_value = mock_emitter

            emit_storage_permission_error_sync(
                operation="delete",
                path="Sven/file.txt",
                username="testuser",
            )

            mock_emitter.emit_for_admins_sync.assert_called_once_with(
                EventType.STORAGE_PERMISSION_ERROR,
                cooldown_entity="Sven/file.txt",
                operation="delete",
                path="Sven/file.txt",
                username="testuser",
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_storage_permission_events.py -v`
Expected: ImportError for `emit_storage_permission_error_sync` and `STORAGE_PERMISSION_ERROR`

- [ ] **Step 3: Add EventType, EventConfig, cooldown, and convenience function**

In `backend/app/services/notifications/events.py`, add to the `EventType` enum (after the existing system events around line 91):

```python
    STORAGE_PERMISSION_ERROR = "system.storage_permission"
```

Add to `_COOLDOWN_SECONDS` dict (around line 29):

```python
    "system.storage_permission": 300,  # 5min per path
```

Add to `EVENT_CONFIGS` dict (after the `TEMPERATURE_CRITICAL` entry, around line 265):

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

Add sync convenience function at the bottom of the file (after `emit_brute_force_detected_sync`):

```python
def emit_storage_permission_error_sync(operation: str, path: str, username: str) -> None:
    """Emit storage permission error event (sync)."""
    get_event_emitter().emit_for_admins_sync(
        EventType.STORAGE_PERMISSION_ERROR,
        cooldown_entity=path,
        operation=operation,
        path=path,
        username=username,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_storage_permission_events.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/notifications/events.py backend/tests/services/test_storage_permission_events.py
git commit -m "feat(notifications): add STORAGE_PERMISSION_ERROR event type

Add new event type for storage permission errors with warning priority,
5-minute cooldown per path, and German notification templates. Includes
sync convenience function for use in synchronous file operations."
```

---

### Task 2: Add `storage_group` Config Setting

**Files:**
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Add the setting**

In `backend/app/core/config.py`, add after the `nas_backup_path` setting (around line 99):

```python
    # Linux group for shared storage ownership (backend + Samba)
    storage_group: str = "baluhost"
```

- [ ] **Step 2: Verify setting loads**

Run: `cd backend && python -c "from app.core.config import settings; print(settings.storage_group)"`
Expected: `baluhost`

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/config.py
git commit -m "feat(config): add storage_group setting for shared Linux group"
```

---

### Task 3: Add PermissionError Catches and Notification Emission in operations.py

**Files:**
- Modify: `backend/app/services/files/operations.py`
- Create: `backend/tests/files/test_permission_error_handling.py`

- [ ] **Step 1: Write the tests**

Create `backend/tests/files/test_permission_error_handling.py`:

```python
"""Tests for PermissionError → PermissionDeniedError conversion + notification.

Every file operation that touches the filesystem must:
1. Catch OS-level PermissionError
2. Emit a storage permission error notification to admins
3. Re-raise as PermissionDeniedError (which routes convert to 403)
"""
import os
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserPublic
from app.services import users as user_service
import app.services.files.operations as file_ops
import app.services.files.path_utils as path_utils
import app.services.files.storage as file_storage
from app.services.permissions import PermissionDeniedError


@pytest.fixture(autouse=True)
def _patch_session_local(db_session, monkeypatch):
    """Patch SessionLocal so service code that bypasses DI uses the test DB."""
    from sqlalchemy.orm import sessionmaker
    test_engine = db_session.get_bind()
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr("app.core.database.SessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.services.files.metadata_db.SessionLocal", TestSessionLocal)
    monkeypatch.setattr("app.services.files.ownership.SessionLocal", TestSessionLocal)


@pytest.fixture
def storage_root(tmp_path, monkeypatch):
    """Create temporary storage root for testing."""
    storage = tmp_path / "storage"
    storage.mkdir()
    monkeypatch.setattr(path_utils, "ROOT_DIR", storage)
    monkeypatch.setattr(file_ops, "ROOT_DIR", storage)
    file_storage._used_bytes_cache.clear()
    return storage


@pytest.fixture
def user_public(regular_user: User) -> UserPublic:
    return user_service.serialize_user(regular_user)


@pytest.fixture
def admin_public(admin_user: User) -> UserPublic:
    return user_service.serialize_user(admin_user)


class TestCreateFolderPermissionError:
    """create_folder must catch PermissionError and emit notification."""

    def test_raises_permission_denied_error(self, storage_root, db_session, user_public):
        with patch.object(Path, "mkdir", side_effect=PermissionError("mock")):
            with pytest.raises(PermissionDeniedError):
                file_ops.create_folder("", "testdir", owner=user_public, db=db_session)

    def test_emits_notification(self, storage_root, db_session, user_public):
        with patch.object(Path, "mkdir", side_effect=PermissionError("mock")), \
             patch("app.services.files.operations._emit_permission_error") as mock_emit:
            with pytest.raises(PermissionDeniedError):
                file_ops.create_folder("", "testdir", owner=user_public, db=db_session)

            mock_emit.assert_called_once_with("create_folder", "", user_public.username)


class TestDeletePathPermissionError:
    """delete_path must catch PermissionError on rmdir/unlink."""

    def test_file_permission_error(self, storage_root, db_session):
        file_path = storage_root / "locked.txt"
        file_path.write_text("locked")

        with patch.object(Path, "unlink", side_effect=PermissionError("mock")):
            with pytest.raises(PermissionDeniedError):
                file_ops.delete_path("locked.txt", user=None, db=db_session)

    def test_file_emits_notification(self, storage_root, db_session, user_public):
        file_path = storage_root / "locked.txt"
        file_path.write_text("locked")

        with patch.object(Path, "unlink", side_effect=PermissionError("mock")), \
             patch("app.services.files.operations._emit_permission_error") as mock_emit:
            with pytest.raises(PermissionDeniedError):
                file_ops.delete_path("locked.txt", user=user_public, db=db_session)

            mock_emit.assert_called_once_with("delete", "locked.txt", user_public.username)

    def test_dir_permission_error(self, storage_root, db_session):
        dir_path = storage_root / "lockeddir"
        dir_path.mkdir()

        with patch.object(Path, "rmdir", side_effect=PermissionError("mock")):
            with pytest.raises(PermissionDeniedError):
                file_ops.delete_path("lockeddir", user=None, db=db_session)

    def test_dir_emits_notification(self, storage_root, db_session, user_public):
        dir_path = storage_root / "lockeddir"
        dir_path.mkdir()

        with patch.object(Path, "rmdir", side_effect=PermissionError("mock")), \
             patch("app.services.files.operations._emit_permission_error") as mock_emit:
            with pytest.raises(PermissionDeniedError):
                file_ops.delete_path("lockeddir", user=user_public, db=db_session)

            mock_emit.assert_called_once_with("delete", "lockeddir", user_public.username)


class TestRenamePathPermissionError:
    """rename_path must catch PermissionError on rename."""

    def test_raises_permission_denied_error(self, storage_root, db_session):
        file_path = storage_root / "original.txt"
        file_path.write_text("content")

        with patch.object(Path, "rename", side_effect=PermissionError("mock")):
            with pytest.raises(PermissionDeniedError):
                file_ops.rename_path("original.txt", "newname.txt", user=None, db=db_session)

    def test_emits_notification(self, storage_root, db_session, user_public):
        file_path = storage_root / "original.txt"
        file_path.write_text("content")

        with patch.object(Path, "rename", side_effect=PermissionError("mock")), \
             patch("app.services.files.operations._emit_permission_error") as mock_emit:
            with pytest.raises(PermissionDeniedError):
                file_ops.rename_path("original.txt", "newname.txt", user=user_public, db=db_session)

            mock_emit.assert_called_once_with("rename", "original.txt", user_public.username)


class TestMovePathPermissionError:
    """move_path must catch PermissionError on rename."""

    def test_raises_permission_denied_error(self, storage_root, db_session):
        file_path = storage_root / "moveme.txt"
        file_path.write_text("content")
        target = storage_root / "dest"
        target.mkdir()

        with patch.object(Path, "rename", side_effect=PermissionError("mock")):
            with pytest.raises(PermissionDeniedError):
                file_ops.move_path("moveme.txt", "dest", user=None, db=db_session)

    def test_emits_notification(self, storage_root, db_session, user_public):
        file_path = storage_root / "moveme.txt"
        file_path.write_text("content")
        target = storage_root / "dest"
        target.mkdir()

        with patch.object(Path, "rename", side_effect=PermissionError("mock")), \
             patch("app.services.files.operations._emit_permission_error") as mock_emit:
            with pytest.raises(PermissionDeniedError):
                file_ops.move_path("moveme.txt", "dest", user=user_public, db=db_session)

            mock_emit.assert_called_once_with("move", "moveme.txt", user_public.username)


class TestSaveUploadsPermissionError:
    """save_uploads must catch PermissionError during file write."""

    @pytest.mark.asyncio
    async def test_raises_permission_denied_error(self, storage_root, db_session, user_public, monkeypatch):
        # Bypass quota check
        monkeypatch.setattr(file_storage, "calculate_available_bytes", lambda: 10 * 1024 * 1024 * 1024)

        upload = UploadFile(filename="test.txt", file=BytesIO(b"hello"))

        with patch("builtins.open", side_effect=PermissionError("mock")):
            with pytest.raises(PermissionDeniedError):
                await file_ops.save_uploads("", [upload], user=user_public, db=db_session)

    @pytest.mark.asyncio
    async def test_emits_notification(self, storage_root, db_session, user_public, monkeypatch):
        monkeypatch.setattr(file_storage, "calculate_available_bytes", lambda: 10 * 1024 * 1024 * 1024)

        upload = UploadFile(filename="test.txt", file=BytesIO(b"hello"))

        with patch("builtins.open", side_effect=PermissionError("mock")), \
             patch("app.services.files.operations._emit_permission_error") as mock_emit:
            with pytest.raises(PermissionDeniedError):
                await file_ops.save_uploads("", [upload], user=user_public, db=db_session)

            mock_emit.assert_called_once()
            call_args = mock_emit.call_args
            assert call_args[0][0] == "upload"
            assert call_args[0][2] == user_public.username
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/files/test_permission_error_handling.py -v`
Expected: Tests fail — `_emit_permission_error` not defined, PermissionError not caught in delete/rename/move/upload

- [ ] **Step 3: Add `_emit_permission_error` helper**

In `backend/app/services/files/operations.py`, add after the `logger` assignment (around line 83):

```python
def _emit_permission_error(operation: str, path: str, username: str) -> None:
    """Emit storage permission error notification to admins.

    Called from PermissionError catch blocks before re-raising as
    PermissionDeniedError. Uses sync emit since file operations
    are called from synchronous contexts.
    """
    try:
        from app.services.notifications.events import emit_storage_permission_error_sync
        emit_storage_permission_error_sync(
            operation=operation,
            path=path,
            username=username,
        )
    except Exception:
        # Never let notification failure mask the original error
        logger.debug("Failed to emit storage permission error notification", exc_info=True)
```

- [ ] **Step 4: Update `create_folder` to emit notification**

In `backend/app/services/files/operations.py`, update the existing PermissionError catch in `create_folder` (around line 647):

```python
    except PermissionError as exc:
        _emit_permission_error("create_folder", parent_path, owner.username if owner else "system")
        raise PermissionDeniedError(
            f"No write permission on '{parent_path}'"
        ) from exc
```

- [ ] **Step 5: Add PermissionError catch in `save_uploads`**

In `backend/app/services/files/operations.py`, in the `save_uploads` function, add a `PermissionError` catch **before** the existing `except Exception` (around line 546):

```python
        except PermissionError as exc:
            _emit_permission_error("upload", relative_path, user.username)
            if upload_ids and idx < len(upload_ids):
                await progress_manager.fail_upload(upload_ids[idx], str(exc))
            raise PermissionDeniedError(
                f"No write permission on '{relative_path}'"
            ) from exc
        except Exception as e:
            # Mark upload as failed
            if upload_ids and idx < len(upload_ids):
                await progress_manager.fail_upload(upload_ids[idx], str(e))
            raise
```

- [ ] **Step 6: Add PermissionError catches in `delete_path`**

In `backend/app/services/files/operations.py`, wrap `target.rmdir()` (around line 593):

```python
        try:
            target.rmdir()
        except PermissionError as exc:
            _emit_permission_error("delete", path_utils._relative_posix(target), user.username if user else "system")
            raise PermissionDeniedError(
                f"No delete permission on '{relative_path}'"
            ) from exc
```

And wrap `target.unlink()` (around line 606):

```python
        try:
            target.unlink()
        except PermissionError as exc:
            _emit_permission_error("delete", file_relative, user.username if user else "system")
            raise PermissionDeniedError(
                f"No delete permission on '{relative_path}'"
            ) from exc
```

- [ ] **Step 7: Add PermissionError catch in `rename_path`**

In `backend/app/services/files/operations.py`, wrap `source.rename(target)` (around line 704):

```python
    try:
        source.rename(target)
    except PermissionError as exc:
        _emit_permission_error("rename", source_relative, user.username if user else "system")
        raise PermissionDeniedError(
            f"No write permission on '{source_relative}'"
        ) from exc
```

- [ ] **Step 8: Add PermissionError catch in `move_path`**

In `backend/app/services/files/operations.py`, wrap `source.rename(final_target_resolved)` (around line 767):

```python
    try:
        source.rename(final_target_resolved)
    except PermissionError as exc:
        _emit_permission_error("move", source_relative, user.username if user else "system")
        raise PermissionDeniedError(
            f"No write permission on '{source_relative}'"
        ) from exc
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/files/test_permission_error_handling.py -v`
Expected: All tests PASS

- [ ] **Step 10: Run existing file operation tests to verify no regressions**

Run: `cd backend && python -m pytest tests/files/test_files_operations.py -v`
Expected: All existing tests PASS

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/files/operations.py backend/tests/files/test_permission_error_handling.py
git commit -m "feat(files): catch PermissionError in all file operations

Wrap mkdir, open/write, unlink, rmdir, and rename calls with
PermissionError handlers that emit admin push notifications and
re-raise as PermissionDeniedError (403 instead of 500)."
```

---

### Task 4: Update Samba Service to Use `storage_group`

**Files:**
- Modify: `backend/app/services/samba_service.py`
- Modify: `backend/tests/services/test_samba_service.py`

- [ ] **Step 1: Write the test**

Add to `backend/tests/services/test_samba_service.py` (add `from pathlib import Path` to existing imports):

```python
class TestStorageGroupConfig:
    """Verify Samba uses settings.storage_group for force group."""

    @pytest.mark.asyncio
    async def test_regenerate_uses_storage_group(self, db_session, admin_user, tmp_path, monkeypatch):
        """In non-dev mode, force group should use storage_group setting."""
        from sqlalchemy.orm import sessionmaker
        from app.core.config import settings

        # Patch SessionLocal so samba_service uses the test DB
        test_engine = db_session.get_bind()
        TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
        monkeypatch.setattr("app.services.samba_service.SessionLocal", TestSessionLocal)

        # Enable SMB for the admin user
        admin_user.smb_enabled = True
        db_session.commit()

        # Non-dev mode with custom storage group
        monkeypatch.setattr(settings, "is_dev_mode", False)
        monkeypatch.setattr(settings, "storage_group", "testgroup")

        # Write to temp file instead of /etc/samba/
        conf_path = str(tmp_path / "shares.conf")
        monkeypatch.setattr(samba_service, "SAMBA_SHARES_CONF", conf_path)

        result = await samba_service.regenerate_shares_config()
        assert result is True

        content = Path(conf_path).read_text()
        assert "force group = testgroup" in content
        assert "force group = sven" not in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_samba_service.py::TestStorageGroupConfig -v`
Expected: FAIL — `force group = sven` still in output

- [ ] **Step 3: Update `regenerate_shares_config`**

In `backend/app/services/samba_service.py`, in `regenerate_shares_config()`, change both occurrences of `force group = {service_user}` (lines 195 and 211):

```python
# Line 195 (admin share):
f"   force group = {settings.storage_group}",

# Line 211 (user share):
f"   force group = {settings.storage_group}",
```

- [ ] **Step 4: Update `_ensure_system_user`**

In `backend/app/services/samba_service.py`, in `_ensure_system_user()`, change the `--group` argument (around line 73):

```python
    rc, stdout, stderr = await _run_cmd([
        "sudo", "useradd",
        "--system",
        "--no-create-home",
        "--shell", "/usr/sbin/nologin",
        "--group", settings.storage_group,
        username,
    ])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/services/test_samba_service.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/samba_service.py backend/tests/services/test_samba_service.py
git commit -m "feat(samba): use storage_group setting for force group

Samba shares now use settings.storage_group (default: baluhost)
instead of the service user name for force group. New system users
created for Samba auth are also added to the storage group."
```

---

### Task 5: Update Deploy Templates

**Files:**
- Modify: `deploy/install/templates/baluhost-backend.service`
- Modify: `deploy/samba/setup-samba.sh`

- [ ] **Step 1: Update systemd service template**

In `deploy/install/templates/baluhost-backend.service`, change line 9:

```ini
Group=baluhost
```

- [ ] **Step 2: Update Samba setup script**

In `deploy/samba/setup-samba.sh`, add `STORAGE_GROUP` variable after `SERVICE_USER` (line 11):

```bash
STORAGE_GROUP="${STORAGE_GROUP:-baluhost}"
```

Change the shares config ownership (line 30):

```bash
chown "$SERVICE_USER:$STORAGE_GROUP" "$SHARES_CONF"
```

- [ ] **Step 3: Commit**

```bash
git add deploy/install/templates/baluhost-backend.service deploy/samba/setup-samba.sh
git commit -m "deploy: configure baluhost group for systemd and Samba setup

systemd service runs with Group=baluhost. Samba setup script uses
STORAGE_GROUP variable (default: baluhost) for shares config ownership."
```

---

### Task 6: Run Full Test Suite and Final Verification

**Files:** None (verification only)

- [ ] **Step 1: Run all new tests**

Run: `cd backend && python -m pytest tests/services/test_storage_permission_events.py tests/files/test_permission_error_handling.py -v`
Expected: All new tests PASS

- [ ] **Step 2: Run file-related test suite**

Run: `cd backend && python -m pytest tests/files/ tests/services/test_samba_service.py tests/services/test_firebase_push.py tests/services/test_notification_service.py -v`
Expected: All tests PASS

- [ ] **Step 3: Run full test suite**

Run: `cd backend && python -m pytest --tb=short -q`
Expected: All tests PASS, no regressions

- [ ] **Step 4: Commit if any fixes were needed**

Only if previous steps required adjustments:
```bash
git add -u
git commit -m "fix: address test failures from storage permissions changes"
```
