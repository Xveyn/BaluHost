"""
Tests for the ShareService (services/files/shares.py).

Covers:
- File shares between users (permissions)
- Ownership checks and statistics
"""

import pytest
from datetime import datetime, timedelta, timezone

from app.models.file_metadata import FileMetadata
from app.models.user import User
from app.schemas.user import UserPublic
from app.services.files.shares import ShareService
from app.services.permissions import PermissionDeniedError
from app.schemas.shares import (
    FileShareCreate,
    FileShareUpdate,
)


def _to_user_public(user: User) -> UserPublic:
    """Convert ORM User to UserPublic schema for service calls."""
    return UserPublic(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        smb_enabled=getattr(user, "smb_enabled", False),
        created_at=str(user.created_at),
        updated_at=str(user.updated_at) if user.updated_at else None,
    )


# ============================================================================
# Helpers
# ============================================================================

@pytest.fixture
def file_for_sharing(db_session, regular_user) -> FileMetadata:
    """Create a file owned by regular_user for sharing tests."""
    meta = FileMetadata(
        path="shared_test_file.txt",
        name="shared_test_file.txt",
        owner_id=regular_user.id,
        size_bytes=2048,
        is_directory=False,
        mime_type="text/plain",
    )
    db_session.add(meta)
    db_session.commit()
    db_session.refresh(meta)
    return meta


@pytest.fixture
def second_file(db_session, regular_user) -> FileMetadata:
    """A second file for multi-share tests."""
    meta = FileMetadata(
        path="second_file.txt",
        name="second_file.txt",
        owner_id=regular_user.id,
        size_bytes=512,
        is_directory=False,
        mime_type="text/plain",
    )
    db_session.add(meta)
    db_session.commit()
    db_session.refresh(meta)
    return meta


# ============================================================================
# File Share Tests
# ============================================================================

class TestFileShareCRUD:
    """Test FileShare (user-to-user sharing) CRUD."""

    def test_create_file_share(self, db_session, regular_user, another_user, file_for_sharing):
        data = FileShareCreate(
            file_id=file_for_sharing.id,
            shared_with_user_id=another_user.id,
        )
        share = ShareService.create_file_share(db_session, _to_user_public(regular_user), data)

        assert share.id is not None
        assert share.file_id == file_for_sharing.id
        assert share.owner_id == regular_user.id
        assert share.shared_with_user_id == another_user.id
        assert share.can_read is True
        assert share.can_write is False

    def test_create_file_share_with_permissions(self, db_session, regular_user, another_user, file_for_sharing):
        data = FileShareCreate(
            file_id=file_for_sharing.id,
            shared_with_user_id=another_user.id,
            can_read=True,
            can_write=True,
            can_delete=True,
            can_share=True,
        )
        share = ShareService.create_file_share(db_session, _to_user_public(regular_user), data)

        assert share.can_read is True
        assert share.can_write is True
        assert share.can_delete is True
        assert share.can_share is True

    def test_create_file_share_file_not_found(self, db_session, regular_user, another_user):
        data = FileShareCreate(file_id=999999, shared_with_user_id=another_user.id)
        with pytest.raises(ValueError, match="File not found"):
            ShareService.create_file_share(db_session, _to_user_public(regular_user), data)

    def test_create_file_share_not_owner(self, db_session, another_user, regular_user, file_for_sharing):
        data = FileShareCreate(
            file_id=file_for_sharing.id,
            shared_with_user_id=regular_user.id,
        )
        with pytest.raises(PermissionError, match="don't own"):
            ShareService.create_file_share(db_session, _to_user_public(another_user), data)

    def test_create_file_share_target_user_not_found(self, db_session, regular_user, file_for_sharing):
        data = FileShareCreate(file_id=file_for_sharing.id, shared_with_user_id=999999)
        with pytest.raises(ValueError, match="Target user not found"):
            ShareService.create_file_share(db_session, _to_user_public(regular_user), data)

    def test_create_duplicate_share_rejected(self, db_session, regular_user, another_user, file_for_sharing):
        data = FileShareCreate(
            file_id=file_for_sharing.id,
            shared_with_user_id=another_user.id,
        )
        ShareService.create_file_share(db_session, _to_user_public(regular_user), data)

        with pytest.raises(ValueError, match="already shared"):
            ShareService.create_file_share(db_session, _to_user_public(regular_user), data)

    def test_get_files_shared_with_user(self, db_session, regular_user, another_user, file_for_sharing):
        ShareService.create_file_share(
            db_session, _to_user_public(regular_user),
            FileShareCreate(file_id=file_for_sharing.id, shared_with_user_id=another_user.id),
        )

        shares = ShareService.get_files_shared_with_user(db_session, another_user.id)
        assert len(shares) == 1
        assert shares[0].file_id == file_for_sharing.id

    def test_get_files_shared_by_user(self, db_session, regular_user, another_user, file_for_sharing):
        ShareService.create_file_share(
            db_session, _to_user_public(regular_user),
            FileShareCreate(file_id=file_for_sharing.id, shared_with_user_id=another_user.id),
        )

        shares = ShareService.get_files_shared_by_user(db_session, regular_user.id, _to_user_public(regular_user))
        assert len(shares) == 1

    def test_update_file_share(self, db_session, regular_user, another_user, file_for_sharing):
        share = ShareService.create_file_share(
            db_session, _to_user_public(regular_user),
            FileShareCreate(file_id=file_for_sharing.id, shared_with_user_id=another_user.id),
        )

        updated = ShareService.update_file_share(
            db_session, share.id, _to_user_public(regular_user),
            FileShareUpdate(can_write=True, can_delete=True),
        )
        assert updated.can_write is True
        assert updated.can_delete is True
        assert updated.can_read is True  # Unchanged

    def test_update_file_share_not_found(self, db_session, regular_user):
        with pytest.raises(ValueError, match="not found"):
            ShareService.update_file_share(
                db_session, 999999, _to_user_public(regular_user),
                FileShareUpdate(can_write=True),
            )

    def test_delete_file_share(self, db_session, regular_user, another_user, file_for_sharing):
        share = ShareService.create_file_share(
            db_session, _to_user_public(regular_user),
            FileShareCreate(file_id=file_for_sharing.id, shared_with_user_id=another_user.id),
        )

        result = ShareService.delete_file_share(db_session, share.id, _to_user_public(regular_user))
        assert result is True

    def test_delete_file_share_not_found(self, db_session, regular_user):
        result = ShareService.delete_file_share(db_session, 999999, _to_user_public(regular_user))
        assert result is False

    def test_admin_can_share_others_file(self, db_session, admin_user, regular_user, another_user, file_for_sharing):
        """Admin should be able to create a share for a file they don't own."""
        data = FileShareCreate(
            file_id=file_for_sharing.id,
            shared_with_user_id=another_user.id,
        )
        share = ShareService.create_file_share(db_session, _to_user_public(admin_user), data)

        assert share.id is not None
        assert share.file_id == file_for_sharing.id
        # Share is owned by the file owner, not the admin
        assert share.owner_id == regular_user.id
        assert share.shared_with_user_id == another_user.id


class TestCheckUserFileAccess:
    """Test file access checking via shares."""

    def test_user_has_access(self, db_session, regular_user, another_user, file_for_sharing):
        ShareService.create_file_share(
            db_session, _to_user_public(regular_user),
            FileShareCreate(file_id=file_for_sharing.id, shared_with_user_id=another_user.id),
        )

        result = ShareService.check_user_file_access(db_session, another_user.id, file_for_sharing.id)
        assert result is not None

    def test_user_has_no_access(self, db_session, another_user, file_for_sharing):
        result = ShareService.check_user_file_access(db_session, another_user.id, file_for_sharing.id)
        assert result is None


class TestShareStatistics:
    """Test share statistics aggregation."""

    def test_empty_statistics(self, db_session, regular_user):
        stats = ShareService.get_share_statistics(db_session, regular_user.id)

        assert stats.total_file_shares == 0
        assert stats.active_file_shares == 0
        assert stats.files_shared_with_me == 0

    def test_statistics_with_data(self, db_session, regular_user, another_user, file_for_sharing):
        # Create a file share
        ShareService.create_file_share(
            db_session, _to_user_public(regular_user),
            FileShareCreate(file_id=file_for_sharing.id, shared_with_user_id=another_user.id),
        )

        stats = ShareService.get_share_statistics(db_session, regular_user.id)
        assert stats.total_file_shares == 1
        assert stats.active_file_shares == 1
