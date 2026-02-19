"""
Tests for the ShareService (services/files/shares.py).

Covers:
- Share link CRUD (create, read, update, delete)
- Password-protected links
- Expiration and download limits
- File shares between users (permissions)
- Ownership checks and statistics
"""

import pytest
from datetime import datetime, timedelta, timezone

from app.models.file_metadata import FileMetadata
from app.models.user import User
from app.services.files.shares import ShareService
from app.schemas.shares import (
    ShareLinkCreate,
    ShareLinkUpdate,
    FileShareCreate,
    FileShareUpdate,
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
# Share Link Tests
# ============================================================================

class TestShareLinkCRUD:
    """Test ShareLink create/read/update/delete."""

    def test_create_share_link(self, db_session, regular_user, file_for_sharing):
        data = ShareLinkCreate(file_id=file_for_sharing.id)
        link = ShareService.create_share_link(db_session, regular_user.id, data)

        assert link.id is not None
        assert link.token is not None
        assert len(link.token) > 0
        assert link.file_id == file_for_sharing.id
        assert link.owner_id == regular_user.id
        assert link.download_count == 0

    def test_create_share_link_with_options(self, db_session, regular_user, file_for_sharing):
        expires = datetime.now(timezone.utc) + timedelta(days=7)
        data = ShareLinkCreate(
            file_id=file_for_sharing.id,
            max_downloads=10,
            expires_at=expires,
            description="Test link",
            allow_download=True,
            allow_preview=False,
        )
        link = ShareService.create_share_link(db_session, regular_user.id, data)

        assert link.max_downloads == 10
        assert link.description == "Test link"
        assert link.allow_download is True
        assert link.allow_preview is False

    def test_create_share_link_file_not_found(self, db_session, regular_user):
        data = ShareLinkCreate(file_id=999999)
        with pytest.raises(ValueError, match="File not found"):
            ShareService.create_share_link(db_session, regular_user.id, data)

    def test_create_share_link_not_owner(self, db_session, another_user, file_for_sharing):
        data = ShareLinkCreate(file_id=file_for_sharing.id)
        with pytest.raises(PermissionError, match="don't own"):
            ShareService.create_share_link(db_session, another_user.id, data)

    def test_get_share_link_by_id(self, db_session, regular_user, file_for_sharing):
        data = ShareLinkCreate(file_id=file_for_sharing.id)
        created = ShareService.create_share_link(db_session, regular_user.id, data)

        fetched = ShareService.get_share_link(db_session, created.id, regular_user.id)
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_share_link_wrong_owner(self, db_session, regular_user, another_user, file_for_sharing):
        data = ShareLinkCreate(file_id=file_for_sharing.id)
        created = ShareService.create_share_link(db_session, regular_user.id, data)

        fetched = ShareService.get_share_link(db_session, created.id, another_user.id)
        assert fetched is None

    def test_get_share_link_by_token(self, db_session, regular_user, file_for_sharing):
        data = ShareLinkCreate(file_id=file_for_sharing.id)
        created = ShareService.create_share_link(db_session, regular_user.id, data)

        fetched = ShareService.get_share_link_by_token(db_session, created.token)
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_share_link_by_token_not_found(self, db_session):
        fetched = ShareService.get_share_link_by_token(db_session, "nonexistent-token")
        assert fetched is None

    def test_list_user_share_links(self, db_session, regular_user, file_for_sharing, second_file):
        ShareService.create_share_link(
            db_session, regular_user.id, ShareLinkCreate(file_id=file_for_sharing.id)
        )
        ShareService.create_share_link(
            db_session, regular_user.id, ShareLinkCreate(file_id=second_file.id)
        )

        links = ShareService.get_user_share_links(db_session, regular_user.id)
        assert len(links) == 2

    def test_list_user_share_links_excludes_expired(self, db_session, regular_user, file_for_sharing, second_file):
        # Create non-expired link
        ShareService.create_share_link(
            db_session, regular_user.id, ShareLinkCreate(file_id=file_for_sharing.id)
        )
        # Create expired link
        ShareService.create_share_link(
            db_session, regular_user.id,
            ShareLinkCreate(
                file_id=second_file.id,
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            ),
        )

        active = ShareService.get_user_share_links(db_session, regular_user.id, include_expired=False)
        assert len(active) == 1

        all_links = ShareService.get_user_share_links(db_session, regular_user.id, include_expired=True)
        assert len(all_links) == 2

    def test_update_share_link(self, db_session, regular_user, file_for_sharing):
        data = ShareLinkCreate(file_id=file_for_sharing.id, description="Original")
        created = ShareService.create_share_link(db_session, regular_user.id, data)

        updated = ShareService.update_share_link(
            db_session, created.id, regular_user.id,
            ShareLinkUpdate(description="Updated", max_downloads=5),
        )
        assert updated.description == "Updated"
        assert updated.max_downloads == 5

    def test_update_share_link_not_found(self, db_session, regular_user):
        with pytest.raises(ValueError, match="not found"):
            ShareService.update_share_link(
                db_session, 999999, regular_user.id,
                ShareLinkUpdate(description="Nope"),
            )

    def test_delete_share_link(self, db_session, regular_user, file_for_sharing):
        data = ShareLinkCreate(file_id=file_for_sharing.id)
        created = ShareService.create_share_link(db_session, regular_user.id, data)

        result = ShareService.delete_share_link(db_session, created.id, regular_user.id)
        assert result is True

        fetched = ShareService.get_share_link(db_session, created.id, regular_user.id)
        assert fetched is None

    def test_delete_share_link_not_found(self, db_session, regular_user):
        result = ShareService.delete_share_link(db_session, 999999, regular_user.id)
        assert result is False


class TestShareLinkPassword:
    """Test password-protected share links."""

    def test_create_with_password(self, db_session, regular_user, file_for_sharing):
        data = ShareLinkCreate(file_id=file_for_sharing.id, password="secret123")
        link = ShareService.create_share_link(db_session, regular_user.id, data)

        assert link.hashed_password is not None
        assert link.hashed_password != "secret123"  # Should be hashed

    def test_verify_correct_password(self, db_session, regular_user, file_for_sharing):
        data = ShareLinkCreate(file_id=file_for_sharing.id, password="secret123")
        link = ShareService.create_share_link(db_session, regular_user.id, data)

        assert ShareService.verify_share_link_password(link, "secret123") is True

    def test_verify_wrong_password(self, db_session, regular_user, file_for_sharing):
        data = ShareLinkCreate(file_id=file_for_sharing.id, password="secret123")
        link = ShareService.create_share_link(db_session, regular_user.id, data)

        assert ShareService.verify_share_link_password(link, "wrong") is False

    def test_verify_no_password_required(self, db_session, regular_user, file_for_sharing):
        data = ShareLinkCreate(file_id=file_for_sharing.id)
        link = ShareService.create_share_link(db_session, regular_user.id, data)

        assert ShareService.verify_share_link_password(link, None) is True

    def test_verify_password_required_but_not_provided(self, db_session, regular_user, file_for_sharing):
        data = ShareLinkCreate(file_id=file_for_sharing.id, password="secret123")
        link = ShareService.create_share_link(db_session, regular_user.id, data)

        assert ShareService.verify_share_link_password(link, None) is False

    def test_update_removes_password(self, db_session, regular_user, file_for_sharing):
        data = ShareLinkCreate(file_id=file_for_sharing.id, password="secret123")
        link = ShareService.create_share_link(db_session, regular_user.id, data)

        updated = ShareService.update_share_link(
            db_session, link.id, regular_user.id,
            ShareLinkUpdate(password=""),
        )
        assert updated.hashed_password is None


class TestShareLinkDownloads:
    """Test download counting."""

    def test_increment_download_count(self, db_session, regular_user, file_for_sharing):
        data = ShareLinkCreate(file_id=file_for_sharing.id)
        link = ShareService.create_share_link(db_session, regular_user.id, data)

        assert link.download_count == 0

        ShareService.increment_download_count(db_session, link)
        assert link.download_count == 1

        ShareService.increment_download_count(db_session, link)
        assert link.download_count == 2

    def test_increment_updates_last_accessed(self, db_session, regular_user, file_for_sharing):
        data = ShareLinkCreate(file_id=file_for_sharing.id)
        link = ShareService.create_share_link(db_session, regular_user.id, data)

        assert link.last_accessed_at is None

        ShareService.increment_download_count(db_session, link)
        assert link.last_accessed_at is not None


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
        share = ShareService.create_file_share(db_session, regular_user.id, data)

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
        share = ShareService.create_file_share(db_session, regular_user.id, data)

        assert share.can_read is True
        assert share.can_write is True
        assert share.can_delete is True
        assert share.can_share is True

    def test_create_file_share_file_not_found(self, db_session, regular_user, another_user):
        data = FileShareCreate(file_id=999999, shared_with_user_id=another_user.id)
        with pytest.raises(ValueError, match="File not found"):
            ShareService.create_file_share(db_session, regular_user.id, data)

    def test_create_file_share_not_owner(self, db_session, another_user, regular_user, file_for_sharing):
        data = FileShareCreate(
            file_id=file_for_sharing.id,
            shared_with_user_id=regular_user.id,
        )
        with pytest.raises(PermissionError, match="don't own"):
            ShareService.create_file_share(db_session, another_user.id, data)

    def test_create_file_share_target_user_not_found(self, db_session, regular_user, file_for_sharing):
        data = FileShareCreate(file_id=file_for_sharing.id, shared_with_user_id=999999)
        with pytest.raises(ValueError, match="Target user not found"):
            ShareService.create_file_share(db_session, regular_user.id, data)

    def test_create_duplicate_share_rejected(self, db_session, regular_user, another_user, file_for_sharing):
        data = FileShareCreate(
            file_id=file_for_sharing.id,
            shared_with_user_id=another_user.id,
        )
        ShareService.create_file_share(db_session, regular_user.id, data)

        with pytest.raises(ValueError, match="already shared"):
            ShareService.create_file_share(db_session, regular_user.id, data)

    def test_get_files_shared_with_user(self, db_session, regular_user, another_user, file_for_sharing):
        ShareService.create_file_share(
            db_session, regular_user.id,
            FileShareCreate(file_id=file_for_sharing.id, shared_with_user_id=another_user.id),
        )

        shares = ShareService.get_files_shared_with_user(db_session, another_user.id)
        assert len(shares) == 1
        assert shares[0].file_id == file_for_sharing.id

    def test_get_files_shared_by_user(self, db_session, regular_user, another_user, file_for_sharing):
        ShareService.create_file_share(
            db_session, regular_user.id,
            FileShareCreate(file_id=file_for_sharing.id, shared_with_user_id=another_user.id),
        )

        shares = ShareService.get_files_shared_by_user(db_session, regular_user.id)
        assert len(shares) == 1

    def test_update_file_share(self, db_session, regular_user, another_user, file_for_sharing):
        share = ShareService.create_file_share(
            db_session, regular_user.id,
            FileShareCreate(file_id=file_for_sharing.id, shared_with_user_id=another_user.id),
        )

        updated = ShareService.update_file_share(
            db_session, share.id, regular_user.id,
            FileShareUpdate(can_write=True, can_delete=True),
        )
        assert updated.can_write is True
        assert updated.can_delete is True
        assert updated.can_read is True  # Unchanged

    def test_update_file_share_not_found(self, db_session, regular_user):
        with pytest.raises(ValueError, match="not found"):
            ShareService.update_file_share(
                db_session, 999999, regular_user.id,
                FileShareUpdate(can_write=True),
            )

    def test_delete_file_share(self, db_session, regular_user, another_user, file_for_sharing):
        share = ShareService.create_file_share(
            db_session, regular_user.id,
            FileShareCreate(file_id=file_for_sharing.id, shared_with_user_id=another_user.id),
        )

        result = ShareService.delete_file_share(db_session, share.id, regular_user.id)
        assert result is True

    def test_delete_file_share_not_found(self, db_session, regular_user):
        result = ShareService.delete_file_share(db_session, 999999, regular_user.id)
        assert result is False


class TestCheckUserFileAccess:
    """Test file access checking via shares."""

    def test_user_has_access(self, db_session, regular_user, another_user, file_for_sharing):
        ShareService.create_file_share(
            db_session, regular_user.id,
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

        assert stats.total_share_links == 0
        assert stats.active_share_links == 0
        assert stats.expired_share_links == 0
        assert stats.total_downloads == 0
        assert stats.total_file_shares == 0
        assert stats.active_file_shares == 0
        assert stats.files_shared_with_me == 0

    def test_statistics_with_data(self, db_session, regular_user, another_user, file_for_sharing):
        # Create a share link
        ShareService.create_share_link(
            db_session, regular_user.id,
            ShareLinkCreate(file_id=file_for_sharing.id),
        )
        # Create a file share
        ShareService.create_file_share(
            db_session, regular_user.id,
            FileShareCreate(file_id=file_for_sharing.id, shared_with_user_id=another_user.id),
        )

        stats = ShareService.get_share_statistics(db_session, regular_user.id)
        assert stats.total_share_links == 1
        assert stats.active_share_links == 1
        assert stats.total_file_shares == 1
        assert stats.active_file_shares == 1
