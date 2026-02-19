"""
Tests for file ownership transfer service.
"""
import os
import shutil
import tempfile
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models.file_metadata import FileMetadata
from app.models.file_share import FileShare
from app.models.share_link import ShareLink
from app.models.user import User
from app.services.files import ownership
from app.services.files import metadata_db as file_metadata_db


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    """Create a temporary storage root."""
    return tmp_path


@pytest.fixture
def second_user(db_session: Session) -> User:
    """Create a second test user."""
    user = User(
        username="seconduser",
        email="second@test.com",
        hashed_password="hashed",
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def third_user(db_session: Session) -> User:
    """Create a third test user."""
    user = User(
        username="thirduser",
        email="third@test.com",
        hashed_password="hashed",
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def user_with_file(
    db_session: Session, regular_user: User, storage_root: Path, monkeypatch
) -> tuple[User, FileMetadata, Path]:
    """Create a user with a file in their home directory."""
    # Patch ROOT_DIR
    monkeypatch.setattr(ownership, "ROOT_DIR", storage_root)
    
    # Create user's home directory
    home_dir = storage_root / regular_user.username
    home_dir.mkdir(parents=True, exist_ok=True)
    
    # Create home dir metadata
    home_meta = file_metadata_db.create_metadata(
        relative_path=regular_user.username,
        name=regular_user.username,
        owner_id=regular_user.id,
        is_directory=True,
        db=db_session,
    )
    
    # Create a test file
    test_file = home_dir / "testfile.txt"
    test_file.write_text("Hello World")
    
    # Create file metadata
    file_meta = file_metadata_db.create_metadata(
        relative_path=f"{regular_user.username}/testfile.txt",
        name="testfile.txt",
        owner_id=regular_user.id,
        size_bytes=11,
        is_directory=False,
        db=db_session,
    )
    
    return regular_user, file_meta, test_file


class TestTransferOwnership:
    """Tests for transfer_ownership function."""

    def test_transfer_file_to_new_owner(
        self,
        db_session: Session,
        user_with_file: tuple[User, FileMetadata, Path],
        second_user: User,
        storage_root: Path,
        monkeypatch,
    ):
        """Test transferring a file to a new owner moves it physically."""
        monkeypatch.setattr(ownership, "ROOT_DIR", storage_root)
        old_owner, file_meta, old_path = user_with_file
        
        # Create second user's home directory
        (storage_root / second_user.username).mkdir(parents=True, exist_ok=True)
        file_metadata_db.create_metadata(
            relative_path=second_user.username,
            name=second_user.username,
            owner_id=second_user.id,
            is_directory=True,
            db=db_session,
        )
        
        result = ownership.transfer_ownership(
            path=file_meta.path,
            new_owner_id=second_user.id,
            requesting_user_id=old_owner.id,
            requesting_user_is_admin=False,
            db=db_session,
            recursive=True,
            conflict_strategy="rename",
        )
        
        assert result.success
        assert result.transferred_count == 1
        assert result.new_path == f"{second_user.username}/testfile.txt"
        
        # Verify old path doesn't exist
        assert not old_path.exists()
        
        # Verify new path exists
        new_path = storage_root / second_user.username / "testfile.txt"
        assert new_path.exists()
        assert new_path.read_text() == "Hello World"
        
        # Verify metadata was updated
        updated_meta = file_metadata_db.get_metadata(result.new_path, db=db_session)
        assert updated_meta is not None
        assert updated_meta.owner_id == second_user.id

    def test_transfer_same_owner_noop(
        self,
        db_session: Session,
        user_with_file: tuple[User, FileMetadata, Path],
        storage_root: Path,
        monkeypatch,
    ):
        """Test transferring to the same owner is a no-op."""
        monkeypatch.setattr(ownership, "ROOT_DIR", storage_root)
        old_owner, file_meta, old_path = user_with_file
        
        result = ownership.transfer_ownership(
            path=file_meta.path,
            new_owner_id=old_owner.id,
            requesting_user_id=old_owner.id,
            requesting_user_is_admin=False,
            db=db_session,
        )
        
        assert result.success
        assert result.transferred_count == 0
        assert result.message == "No transfer needed - already owned by target user"
        
        # File should still be in original location
        assert old_path.exists()

    def test_transfer_unauthorized(
        self,
        db_session: Session,
        user_with_file: tuple[User, FileMetadata, Path],
        second_user: User,
        third_user: User,
        storage_root: Path,
        monkeypatch,
    ):
        """Test that non-owner non-admin cannot transfer."""
        monkeypatch.setattr(ownership, "ROOT_DIR", storage_root)
        old_owner, file_meta, old_path = user_with_file
        
        # third_user tries to transfer old_owner's file
        result = ownership.transfer_ownership(
            path=file_meta.path,
            new_owner_id=second_user.id,
            requesting_user_id=third_user.id,
            requesting_user_is_admin=False,
            db=db_session,
        )
        
        assert not result.success
        assert result.error == "UNAUTHORIZED"
        
        # File should still be in original location
        assert old_path.exists()

    def test_transfer_admin_can_transfer_any(
        self,
        db_session: Session,
        user_with_file: tuple[User, FileMetadata, Path],
        second_user: User,
        third_user: User,
        storage_root: Path,
        monkeypatch,
    ):
        """Test that admin can transfer anyone's file."""
        monkeypatch.setattr(ownership, "ROOT_DIR", storage_root)
        old_owner, file_meta, old_path = user_with_file
        
        # Create second user's home directory
        (storage_root / second_user.username).mkdir(parents=True, exist_ok=True)
        file_metadata_db.create_metadata(
            relative_path=second_user.username,
            name=second_user.username,
            owner_id=second_user.id,
            is_directory=True,
            db=db_session,
        )
        
        # third_user as admin transfers old_owner's file
        result = ownership.transfer_ownership(
            path=file_meta.path,
            new_owner_id=second_user.id,
            requesting_user_id=third_user.id,
            requesting_user_is_admin=True,  # Admin!
            db=db_session,
        )
        
        assert result.success
        assert result.transferred_count == 1

    def test_transfer_with_name_conflict_rename(
        self,
        db_session: Session,
        user_with_file: tuple[User, FileMetadata, Path],
        second_user: User,
        storage_root: Path,
        monkeypatch,
    ):
        """Test conflict resolution with rename strategy."""
        monkeypatch.setattr(ownership, "ROOT_DIR", storage_root)
        old_owner, file_meta, old_path = user_with_file
        
        # Create second user's home directory with a file of the same name
        second_home = storage_root / second_user.username
        second_home.mkdir(parents=True, exist_ok=True)
        (second_home / "testfile.txt").write_text("Existing file")
        
        file_metadata_db.create_metadata(
            relative_path=second_user.username,
            name=second_user.username,
            owner_id=second_user.id,
            is_directory=True,
            db=db_session,
        )
        
        result = ownership.transfer_ownership(
            path=file_meta.path,
            new_owner_id=second_user.id,
            requesting_user_id=old_owner.id,
            requesting_user_is_admin=False,
            db=db_session,
            conflict_strategy="rename",
        )
        
        assert result.success
        assert result.transferred_count == 1
        assert "testfile (2).txt" in result.new_path
        assert len(result.conflicts) == 1
        assert result.conflicts[0].action == "renamed"

    def test_transfer_with_name_conflict_skip(
        self,
        db_session: Session,
        user_with_file: tuple[User, FileMetadata, Path],
        second_user: User,
        storage_root: Path,
        monkeypatch,
    ):
        """Test conflict resolution with skip strategy."""
        monkeypatch.setattr(ownership, "ROOT_DIR", storage_root)
        old_owner, file_meta, old_path = user_with_file
        
        # Create second user's home directory with a file of the same name
        second_home = storage_root / second_user.username
        second_home.mkdir(parents=True, exist_ok=True)
        (second_home / "testfile.txt").write_text("Existing file")
        
        file_metadata_db.create_metadata(
            relative_path=second_user.username,
            name=second_user.username,
            owner_id=second_user.id,
            is_directory=True,
            db=db_session,
        )
        
        result = ownership.transfer_ownership(
            path=file_meta.path,
            new_owner_id=second_user.id,
            requesting_user_id=old_owner.id,
            requesting_user_is_admin=False,
            db=db_session,
            conflict_strategy="skip",
        )
        
        assert result.success
        assert result.transferred_count == 0
        assert result.skipped_count == 1
        assert len(result.conflicts) == 1
        assert result.conflicts[0].action == "skipped"
        
        # Original file should still exist
        assert old_path.exists()

    def test_cannot_transfer_home_directory(
        self,
        db_session: Session,
        regular_user: User,
        second_user: User,
        storage_root: Path,
        monkeypatch,
    ):
        """Test that home directories cannot be transferred."""
        monkeypatch.setattr(ownership, "ROOT_DIR", storage_root)
        
        # Create user's home directory metadata
        home_dir = storage_root / regular_user.username
        home_dir.mkdir(parents=True, exist_ok=True)
        
        file_metadata_db.create_metadata(
            relative_path=regular_user.username,
            name=regular_user.username,
            owner_id=regular_user.id,
            is_directory=True,
            db=db_session,
        )
        
        result = ownership.transfer_ownership(
            path=regular_user.username,
            new_owner_id=second_user.id,
            requesting_user_id=regular_user.id,
            requesting_user_is_admin=False,
            db=db_session,
        )
        
        assert not result.success
        assert result.error == "HOME_DIRECTORY"


class TestResidencyEnforcement:
    """Tests for residency enforcement functions."""

    def test_scan_no_violations(
        self,
        db_session: Session,
        user_with_file: tuple[User, FileMetadata, Path],
        storage_root: Path,
        monkeypatch,
    ):
        """Test scan with no violations."""
        monkeypatch.setattr(ownership, "ROOT_DIR", storage_root)
        old_owner, file_meta, _ = user_with_file
        
        violations = ownership.scan_residency_violations(db=db_session)
        
        # File is in owner's directory - no violations
        assert len(violations) == 0

    def test_scan_finds_violations(
        self,
        db_session: Session,
        regular_user: User,
        second_user: User,
        storage_root: Path,
        monkeypatch,
    ):
        """Test scan finds files in wrong directories."""
        monkeypatch.setattr(ownership, "ROOT_DIR", storage_root)
        
        # Create file metadata claiming second_user owns a file in regular_user's dir
        file_metadata_db.create_metadata(
            relative_path=f"{regular_user.username}/wrong_owner_file.txt",
            name="wrong_owner_file.txt",
            owner_id=second_user.id,  # Wrong! File is in regular_user's dir
            size_bytes=100,
            is_directory=False,
            db=db_session,
        )
        
        violations = ownership.scan_residency_violations(db=db_session)
        
        assert len(violations) == 1
        assert violations[0].path == f"{regular_user.username}/wrong_owner_file.txt"
        assert violations[0].current_owner_username == second_user.username
        assert violations[0].actual_directory == regular_user.username
        assert violations[0].expected_directory == second_user.username

    def test_shared_dir_not_violation(
        self,
        db_session: Session,
        regular_user: User,
        storage_root: Path,
        monkeypatch,
    ):
        """Test files in Shared/ are not counted as violations."""
        monkeypatch.setattr(ownership, "ROOT_DIR", storage_root)
        
        # Create file in Shared owned by regular_user
        file_metadata_db.create_metadata(
            relative_path="Shared/public_file.txt",
            name="public_file.txt",
            owner_id=regular_user.id,
            size_bytes=100,
            is_directory=False,
            db=db_session,
        )
        
        violations = ownership.scan_residency_violations(db=db_session)
        
        # Shared files are exempt from residency rules
        assert len(violations) == 0


class TestConflictResolution:
    """Tests for conflict resolution helper."""

    def test_no_conflict(self, tmp_path: Path):
        """Test when no conflict exists."""
        resolved, conflict_info = ownership._resolve_name_conflict(
            tmp_path, "newfile.txt", "rename"
        )
        
        assert resolved == "newfile.txt"
        assert conflict_info.action == "no_conflict"

    def test_rename_conflict(self, tmp_path: Path):
        """Test rename strategy creates numbered copies."""
        (tmp_path / "file.txt").touch()
        
        resolved, conflict_info = ownership._resolve_name_conflict(
            tmp_path, "file.txt", "rename"
        )
        
        assert resolved == "file (2).txt"
        assert conflict_info.action == "renamed"

    def test_skip_conflict(self, tmp_path: Path):
        """Test skip strategy returns None."""
        (tmp_path / "file.txt").touch()
        
        resolved, conflict_info = ownership._resolve_name_conflict(
            tmp_path, "file.txt", "skip"
        )
        
        assert resolved is None
        assert conflict_info.action == "skipped"

    def test_overwrite_conflict(self, tmp_path: Path):
        """Test overwrite strategy returns original name."""
        (tmp_path / "file.txt").touch()
        
        resolved, conflict_info = ownership._resolve_name_conflict(
            tmp_path, "file.txt", "overwrite"
        )
        
        assert resolved == "file.txt"
        assert conflict_info.action == "overwritten"
