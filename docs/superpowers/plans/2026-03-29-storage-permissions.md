# Storage Permission Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `[Errno 13] Permission denied` when uploading files to other users' directories by aligning backend file permissions with the Samba configuration.

**Architecture:** Add a `storage_permissions` module with constants and helpers (`STORAGE_DIR_MODE = 0o2775`, `STORAGE_FILE_MODE = 0o0664`, `STORAGE_UMASK = 0o002`). Set process umask at server startup. Call `chmod` after every `mkdir()` and file write in upload/folder operations. No `chown` needed — all processes share one OS user.

**Tech Stack:** Python 3.11+, FastAPI, pytest, asyncio

---

### Task 1: Create storage permissions module

**Files:**
- Create: `backend/app/services/files/storage_permissions.py`
- Test: `backend/tests/files/test_storage_permissions.py`

- [ ] **Step 1: Write tests for permission helpers**

Create `backend/tests/files/test_storage_permissions.py`:

```python
"""Tests for storage permission helpers."""
import os
import stat
from pathlib import Path

import pytest

from app.services.files.storage_permissions import (
    STORAGE_DIR_MODE,
    STORAGE_FILE_MODE,
    STORAGE_UMASK,
    set_storage_dir_permissions,
    set_storage_file_permissions,
    ensure_dir_with_permissions,
)


class TestConstants:
    def test_dir_mode_value(self):
        assert STORAGE_DIR_MODE == 0o2775

    def test_file_mode_value(self):
        assert STORAGE_FILE_MODE == 0o0664

    def test_umask_value(self):
        assert STORAGE_UMASK == 0o002


class TestSetStorageDirPermissions:
    def test_sets_permissions_on_directory(self, tmp_path):
        d = tmp_path / "testdir"
        d.mkdir(mode=0o700)

        set_storage_dir_permissions(d)

        actual = stat.S_IMODE(d.stat().st_mode)
        assert actual == STORAGE_DIR_MODE

    def test_ignores_nonexistent_path(self, tmp_path):
        missing = tmp_path / "missing"
        # Should not raise
        set_storage_dir_permissions(missing)


class TestSetStorageFilePermissions:
    def test_sets_permissions_on_file(self, tmp_path):
        f = tmp_path / "testfile.txt"
        f.write_text("hello")
        f.chmod(0o600)

        set_storage_file_permissions(f)

        actual = stat.S_IMODE(f.stat().st_mode)
        assert actual == STORAGE_FILE_MODE

    def test_ignores_nonexistent_path(self, tmp_path):
        missing = tmp_path / "missing.txt"
        set_storage_file_permissions(missing)


class TestEnsureDirWithPermissions:
    def test_creates_dir_with_correct_permissions(self, tmp_path):
        d = tmp_path / "a" / "b" / "c"

        ensure_dir_with_permissions(d)

        assert d.is_dir()
        actual = stat.S_IMODE(d.stat().st_mode)
        assert actual == STORAGE_DIR_MODE

    def test_existing_dir_gets_permissions_fixed(self, tmp_path):
        d = tmp_path / "existing"
        d.mkdir(mode=0o700)

        ensure_dir_with_permissions(d)

        actual = stat.S_IMODE(d.stat().st_mode)
        assert actual == STORAGE_DIR_MODE

    def test_parent_dirs_also_get_permissions(self, tmp_path):
        d = tmp_path / "parent" / "child"

        ensure_dir_with_permissions(d)

        parent_mode = stat.S_IMODE((tmp_path / "parent").stat().st_mode)
        child_mode = stat.S_IMODE(d.stat().st_mode)
        assert parent_mode == STORAGE_DIR_MODE
        assert child_mode == STORAGE_DIR_MODE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "D:/Programme (x86)/Baluhost/backend" && python -m pytest tests/files/test_storage_permissions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.files.storage_permissions'`

- [ ] **Step 3: Implement the module**

Create `backend/app/services/files/storage_permissions.py`:

```python
"""Storage permission constants and helpers.

Aligns backend file/directory permissions with the Samba configuration
(create mask = 0664, directory mask = 0775) so that all processes
(backend, Samba) can read/write files regardless of which one created them.

The setgid bit (2xxx) on directories ensures new subdirectories inherit
the parent's group automatically.
"""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

STORAGE_DIR_MODE = 0o2775    # rwxrwsr-x  (setgid + group write)
STORAGE_FILE_MODE = 0o0664   # rw-rw-r--
STORAGE_UMASK = 0o002        # complement of 0775/0664


def set_storage_dir_permissions(path: Path) -> None:
    """Set standard storage directory permissions (2775) on *path*.

    Silently skips non-existent paths (e.g. race with deletion).
    """
    try:
        os.chmod(path, STORAGE_DIR_MODE)
    except FileNotFoundError:
        pass


def set_storage_file_permissions(path: Path) -> None:
    """Set standard storage file permissions (0664) on *path*.

    Silently skips non-existent paths.
    """
    try:
        os.chmod(path, STORAGE_FILE_MODE)
    except FileNotFoundError:
        pass


def ensure_dir_with_permissions(path: Path) -> None:
    """Create *path* (and parents) with storage directory permissions.

    Equivalent to ``path.mkdir(parents=True, exist_ok=True)`` followed
    by ``chmod 2775`` on every newly created segment.
    """
    path.mkdir(parents=True, exist_ok=True)

    # Walk from the deepest new directory upward and fix permissions.
    # Stop at the first directory that already has the correct mode to
    # avoid unnecessary syscalls on long-existing parent directories.
    current = path
    while True:
        try:
            mode = os.stat(current).st_mode & 0o7777
            if mode != STORAGE_DIR_MODE:
                os.chmod(current, STORAGE_DIR_MODE)
            else:
                break  # already correct — parents are likely fine too
        except FileNotFoundError:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "D:/Programme (x86)/Baluhost/backend" && python -m pytest tests/files/test_storage_permissions.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
cd "D:/Programme (x86)/Baluhost"
git add backend/app/services/files/storage_permissions.py backend/tests/files/test_storage_permissions.py
git commit -m "feat(storage): add storage permission constants and helpers

Aligns with Samba config: dirs 2775, files 0664, umask 002."
```

---

### Task 2: Set process umask at server startup

**Files:**
- Modify: `backend/app/core/lifespan.py:258-262`

- [ ] **Step 1: Add umask to `_startup()`**

In `backend/app/core/lifespan.py`, add the umask call at the very beginning of `_startup()`, before any file operations (before `init_db()`):

```python
# At the top of _startup(), right after the line:
#     global _discovery_service, _websocket_manager, _plugin_manager, IS_PRIMARY_WORKER, _smart_device_manager
# Add:

    # Set process umask so all new files/dirs are group-writable,
    # consistent with Samba's create mask (0664) and directory mask (0775).
    from app.services.files.storage_permissions import STORAGE_UMASK
    old_umask = os.umask(STORAGE_UMASK)
    logger.info("Storage umask set to %04o (was %04o)", STORAGE_UMASK, old_umask)
```

The import of `os` is already present at the top of `lifespan.py`.

- [ ] **Step 2: Verify server starts without errors**

Run: `cd "D:/Programme (x86)/Baluhost/backend" && python -c "from app.services.files.storage_permissions import STORAGE_UMASK; print(f'UMASK={oct(STORAGE_UMASK)}')"`
Expected: `UMASK=0o2`

- [ ] **Step 3: Commit**

```bash
cd "D:/Programme (x86)/Baluhost"
git add backend/app/core/lifespan.py
git commit -m "feat(storage): set umask 002 at server startup

Each uvicorn worker runs lifespan independently, so all workers
get the correct umask for group-writable files."
```

---

### Task 3: Apply permissions in `save_uploads()`

**Files:**
- Modify: `backend/app/services/files/operations.py:269-527`
- Test: `backend/tests/files/test_files_operations.py` (add new test)

- [ ] **Step 1: Write test for file permissions after upload**

Add to `backend/tests/files/test_files_operations.py`, inside `class TestSaveUploads`:

```python
    @pytest.mark.asyncio
    async def test_save_upload_sets_file_permissions(self, storage_root, db_session, user_public):
        """Test that uploaded files get 0664 permissions."""
        import stat
        from app.services.files.storage_permissions import STORAGE_FILE_MODE

        upload = MagicMock(spec=UploadFile)
        upload.filename = "perms.txt"
        upload.read = AsyncMock(return_value=b"test data")
        upload.close = AsyncMock()

        saved = await file_ops.save_uploads(
            relative_path="",
            uploads=[upload],
            user=user_public,
            db=db_session,
        )

        dest = storage_root / "perms.txt"
        actual = stat.S_IMODE(dest.stat().st_mode)
        assert actual == STORAGE_FILE_MODE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/Programme (x86)/Baluhost/backend" && python -m pytest tests/files/test_files_operations.py::TestSaveUploads::test_save_upload_sets_file_permissions -v`
Expected: FAIL (permissions will be default, not 0664)

- [ ] **Step 3: Add permission calls to `save_uploads()`**

In `backend/app/services/files/operations.py`, add the import at the top with the other imports (after the existing `from app.services.files.folder_size import ...` line):

```python
from app.services.files.storage_permissions import (
    ensure_dir_with_permissions,
    set_storage_file_permissions,
)
```

Then make these changes in `save_uploads()`:

**Change 1** — Replace `target.mkdir(parents=True, exist_ok=True)` (line 305) with:

```python
    ensure_dir_with_permissions(target)
```

**Change 2** — Replace `subfolder.mkdir(parents=True, exist_ok=True)` (line 372) with:

```python
                subfolder.mkdir(parents=True, exist_ok=True)
                set_storage_dir_permissions(subfolder)
```

(Also add `set_storage_dir_permissions` to the import above.)

**Change 3** — Replace `await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)` (line 378) with:

```python
        await asyncio.to_thread(ensure_dir_with_permissions, destination.parent)
```

**Change 4** — After the streaming write block that ends with `file_checksum = hasher.hexdigest()` (line 402), add:

```python
                await asyncio.to_thread(set_storage_file_permissions, destination)
```

**Change 5** — After the small-file fallback `file_checksum = await asyncio.to_thread(_write_and_hash_small)` (line 412), add:

```python
                await asyncio.to_thread(set_storage_file_permissions, destination)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "D:/Programme (x86)/Baluhost/backend" && python -m pytest tests/files/test_files_operations.py -v`
Expected: All tests PASS (including the new one)

- [ ] **Step 5: Commit**

```bash
cd "D:/Programme (x86)/Baluhost"
git add backend/app/services/files/operations.py backend/tests/files/test_files_operations.py
git commit -m "fix(storage): set dir/file permissions after upload

Dirs get 2775 (setgid + group write), files get 0664.
Fixes Permission denied when admin uploads to other user dirs."
```

---

### Task 4: Apply permissions in `create_folder()`

**Files:**
- Modify: `backend/app/services/files/operations.py:602-633`
- Test: `backend/tests/files/test_files_operations.py` (add new test)

- [ ] **Step 1: Write test for folder permissions**

Add to `backend/tests/files/test_files_operations.py`, inside `class TestCreateFolder`:

```python
    def test_create_folder_sets_permissions(self, storage_root, db_session, user_public):
        """Test that created folders get 2775 permissions."""
        import stat
        from app.services.files.storage_permissions import STORAGE_DIR_MODE

        result = file_ops.create_folder("", "permtest", owner=user_public, db=db_session)

        actual = stat.S_IMODE(result.stat().st_mode)
        assert actual == STORAGE_DIR_MODE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "D:/Programme (x86)/Baluhost/backend" && python -m pytest tests/files/test_files_operations.py::TestCreateFolder::test_create_folder_sets_permissions -v`
Expected: FAIL

- [ ] **Step 3: Add permission calls to `create_folder()`**

In `create_folder()` in `operations.py`:

**Change 1** — Replace `base.mkdir(parents=True, exist_ok=True)` (line 607) with:

```python
    ensure_dir_with_permissions(base)
```

**Change 2** — Replace `folder.mkdir(parents=True, exist_ok=True)` (line 617) with:

```python
    folder.mkdir(parents=True, exist_ok=True)
    set_storage_dir_permissions(folder)
```

(The imports from Task 3 already cover `set_storage_dir_permissions`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "D:/Programme (x86)/Baluhost/backend" && python -m pytest tests/files/test_files_operations.py::TestCreateFolder -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd "D:/Programme (x86)/Baluhost"
git add backend/app/services/files/operations.py backend/tests/files/test_files_operations.py
git commit -m "fix(storage): set 2775 permissions on created folders"
```

---

### Task 5: Apply permissions in chunked upload finalization

**Files:**
- Modify: `backend/app/api/routes/chunked_upload.py:217-238`

- [ ] **Step 1: Add permission calls to `chunked_complete()`**

In `backend/app/api/routes/chunked_upload.py`, add the import near the top imports:

```python
from app.services.files.storage_permissions import (
    ensure_dir_with_permissions,
    set_storage_file_permissions,
)
```

Then in `chunked_complete()`:

**Change 1** — Replace lines 219-221:

```python
    target_dir = _resolve_path(session.target_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / session.filename
    destination.parent.mkdir(parents=True, exist_ok=True)
```

with:

```python
    target_dir = _resolve_path(session.target_path)
    ensure_dir_with_permissions(target_dir)
    destination = target_dir / session.filename
    ensure_dir_with_permissions(destination.parent)
```

**Change 2** — After `await asyncio.to_thread(shutil.move, str(temp_path), str(destination))` (line 238), add:

```python
    await asyncio.to_thread(set_storage_file_permissions, destination)
```

- [ ] **Step 2: Run existing tests to verify nothing broke**

Run: `cd "D:/Programme (x86)/Baluhost/backend" && python -m pytest tests/ -v -k "chunked or upload" --timeout=30`
Expected: All existing tests PASS

- [ ] **Step 3: Commit**

```bash
cd "D:/Programme (x86)/Baluhost"
git add backend/app/api/routes/chunked_upload.py
git commit -m "fix(storage): set permissions after chunked upload finalization"
```

---

### Task 6: Apply permissions in home directory creation

**Files:**
- Modify: `backend/app/services/users.py:32-53`

- [ ] **Step 1: Add permission call to `_create_home_directory()`**

In `backend/app/services/users.py`, add the import near the top:

```python
from app.services.files.storage_permissions import set_storage_dir_permissions
```

Then in `_create_home_directory()`, after `home_dir.mkdir(parents=True, exist_ok=True)` (line 41), add:

```python
    set_storage_dir_permissions(home_dir)
```

- [ ] **Step 2: Also update `ensure_user_home_directories()` for the Shared folder**

In the same file, in `ensure_user_home_directories()`, after `shared_dir.mkdir(parents=True, exist_ok=True)` (line 69), add:

```python
        set_storage_dir_permissions(shared_dir)
```

- [ ] **Step 3: Run existing tests to verify nothing broke**

Run: `cd "D:/Programme (x86)/Baluhost/backend" && python -m pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
cd "D:/Programme (x86)/Baluhost"
git add backend/app/services/users.py
git commit -m "fix(storage): set 2775 on home dirs and Shared folder"
```

---

### Task 7: Full test suite and final verification

**Files:**
- None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `cd "D:/Programme (x86)/Baluhost/backend" && python -m pytest tests/ -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 2: Verify the permission module is importable from all call sites**

Run:
```bash
cd "D:/Programme (x86)/Baluhost/backend"
python -c "
from app.services.files.storage_permissions import (
    STORAGE_DIR_MODE, STORAGE_FILE_MODE, STORAGE_UMASK,
    set_storage_dir_permissions, set_storage_file_permissions,
    ensure_dir_with_permissions,
)
print(f'DIR={oct(STORAGE_DIR_MODE)} FILE={oct(STORAGE_FILE_MODE)} UMASK={oct(STORAGE_UMASK)}')
print('All imports OK')
"
```
Expected: `DIR=0o2775 FILE=0o664 UMASK=0o2` and `All imports OK`

- [ ] **Step 3: Final commit with all changes**

If any uncommitted changes remain:

```bash
cd "D:/Programme (x86)/Baluhost"
git status
# Commit any remaining changes
```
