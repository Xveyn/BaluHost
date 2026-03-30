"""Tests for PermissionError -> PermissionDeniedError conversion + notification.

Every file operation that touches the filesystem must:
1. Catch OS-level PermissionError
2. Emit a storage permission error notification to admins
3. Re-raise as PermissionDeniedError (which routes convert to 403)
"""
import os
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, call

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


def _mkdir_fail_on_new(storage_root):
    """Return a side_effect for Path.mkdir that only fails for non-existent dirs.

    ensure_dir_with_permissions calls mkdir(parents=True, exist_ok=True) on
    directories that already exist (the storage root).  The actual folder
    creation is the call that should fail.

    Note: patch.object side_effect does NOT receive 'self', so we track
    calls via a counter instead.
    """
    call_count = [0]

    def _side_effect(*args, **kwargs):
        call_count[0] += 1
        # First call is ensure_dir_with_permissions on the parent (exists).
        # Second call is the actual folder.mkdir() which should fail.
        if call_count[0] <= 1:
            return  # Let the ensure_dir call pass
        raise PermissionError("mock")

    return _side_effect


class TestCreateFolderPermissionError:
    """create_folder must catch PermissionError and emit notification."""

    def test_raises_permission_denied_error(self, storage_root, db_session, admin_public):
        with patch.object(Path, "mkdir", side_effect=_mkdir_fail_on_new(storage_root)):
            with pytest.raises(PermissionDeniedError):
                file_ops.create_folder("", "testdir", owner=admin_public, db=db_session)

    def test_emits_notification(self, storage_root, db_session, admin_public):
        with patch.object(Path, "mkdir", side_effect=_mkdir_fail_on_new(storage_root)), \
             patch("app.services.files.operations._emit_permission_error") as mock_emit:
            with pytest.raises(PermissionDeniedError):
                file_ops.create_folder("", "testdir", owner=admin_public, db=db_session)

            mock_emit.assert_called_once_with("create_folder", "", admin_public.username)


class TestDeletePathPermissionError:
    """delete_path must catch PermissionError on rmdir/unlink."""

    def test_file_permission_error(self, storage_root, db_session):
        file_path = storage_root / "locked.txt"
        file_path.write_text("locked")

        with patch.object(Path, "unlink", side_effect=PermissionError("mock")):
            with pytest.raises(PermissionDeniedError):
                file_ops.delete_path("locked.txt", user=None, db=db_session)

    def test_file_emits_notification(self, storage_root, db_session, admin_public):
        file_path = storage_root / "locked.txt"
        file_path.write_text("locked")

        with patch.object(Path, "unlink", side_effect=PermissionError("mock")), \
             patch("app.services.files.operations._emit_permission_error") as mock_emit:
            with pytest.raises(PermissionDeniedError):
                file_ops.delete_path("locked.txt", user=admin_public, db=db_session)

            mock_emit.assert_called_once_with("delete", "locked.txt", admin_public.username)

    def test_dir_permission_error(self, storage_root, db_session):
        dir_path = storage_root / "lockeddir"
        dir_path.mkdir()

        with patch.object(Path, "rmdir", side_effect=PermissionError("mock")):
            with pytest.raises(PermissionDeniedError):
                file_ops.delete_path("lockeddir", user=None, db=db_session)

    def test_dir_emits_notification(self, storage_root, db_session, admin_public):
        dir_path = storage_root / "lockeddir"
        dir_path.mkdir()

        with patch.object(Path, "rmdir", side_effect=PermissionError("mock")), \
             patch("app.services.files.operations._emit_permission_error") as mock_emit:
            with pytest.raises(PermissionDeniedError):
                file_ops.delete_path("lockeddir", user=admin_public, db=db_session)

            mock_emit.assert_called_once_with("delete", "lockeddir", admin_public.username)


class TestRenamePathPermissionError:
    """rename_path must catch PermissionError on rename."""

    def test_raises_permission_denied_error(self, storage_root, db_session):
        file_path = storage_root / "original.txt"
        file_path.write_text("content")

        with patch.object(Path, "rename", side_effect=PermissionError("mock")):
            with pytest.raises(PermissionDeniedError):
                file_ops.rename_path("original.txt", "newname.txt", user=None, db=db_session)

    def test_emits_notification(self, storage_root, db_session, admin_public):
        file_path = storage_root / "original.txt"
        file_path.write_text("content")

        with patch.object(Path, "rename", side_effect=PermissionError("mock")), \
             patch("app.services.files.operations._emit_permission_error") as mock_emit:
            with pytest.raises(PermissionDeniedError):
                file_ops.rename_path("original.txt", "newname.txt", user=admin_public, db=db_session)

            mock_emit.assert_called_once_with("rename", "original.txt", admin_public.username)


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

    def test_emits_notification(self, storage_root, db_session, admin_public):
        file_path = storage_root / "moveme.txt"
        file_path.write_text("content")
        target = storage_root / "dest"
        target.mkdir()

        with patch.object(Path, "rename", side_effect=PermissionError("mock")), \
             patch("app.services.files.operations._emit_permission_error") as mock_emit:
            with pytest.raises(PermissionDeniedError):
                file_ops.move_path("moveme.txt", "dest", user=admin_public, db=db_session)

            mock_emit.assert_called_once_with("move", "moveme.txt", admin_public.username)


class TestSaveUploadsPermissionError:
    """save_uploads must catch PermissionError during file write."""

    @pytest.mark.asyncio
    async def test_raises_permission_denied_error(self, storage_root, db_session, user_public, monkeypatch):
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
