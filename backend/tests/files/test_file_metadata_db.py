"""
Tests for database-backed file metadata service.
"""
import pytest
from sqlalchemy.orm import Session

from app.models.file_metadata import FileMetadata
from app.services import file_metadata_db as metadata_service


def test_create_metadata(db_session: Session, regular_user):
    """Test creating file metadata."""
    metadata = metadata_service.create_metadata(
        relative_path="test/file.txt",
        name="file.txt",
        owner_id=regular_user.id,
        size_bytes=1024,
        is_directory=False,
        mime_type="text/plain",
        db=db_session
    )
    
    assert metadata.path == "test/file.txt"
    assert metadata.name == "file.txt"
    assert metadata.owner_id == regular_user.id
    assert metadata.size_bytes == 1024
    assert not metadata.is_directory
    assert metadata.mime_type == "text/plain"
    assert metadata.parent_path == "test"


def test_get_metadata(db_session: Session, sample_file_metadata):
    """Test retrieving file metadata."""
    metadata = metadata_service.get_metadata(sample_file_metadata.path, db=db_session)
    
    assert metadata is not None
    assert metadata.id == sample_file_metadata.id
    assert metadata.path == sample_file_metadata.path
    assert metadata.name == sample_file_metadata.name


def test_get_metadata_not_found(db_session: Session):
    """Test retrieving non-existent metadata."""
    metadata = metadata_service.get_metadata("nonexistent.txt", db=db_session)
    assert metadata is None


def test_update_metadata(db_session: Session, sample_file_metadata):
    """Test updating file metadata."""
    updated = metadata_service.update_metadata(
        sample_file_metadata.path,
        size_bytes=2048,
        mime_type="application/octet-stream",
        db=db_session
    )
    
    assert updated is not None
    assert updated.size_bytes == 2048
    assert updated.mime_type == "application/octet-stream"
    assert updated.updated_at is not None


def test_delete_metadata(db_session: Session, sample_file_metadata):
    """Test deleting file metadata."""
    result = metadata_service.delete_metadata(sample_file_metadata.path, db=db_session)
    assert result is True
    
    # Verify it's deleted
    metadata = metadata_service.get_metadata(sample_file_metadata.path, db=db_session)
    assert metadata is None


def test_delete_metadata_not_found(db_session: Session):
    """Test deleting non-existent metadata."""
    result = metadata_service.delete_metadata("nonexistent.txt", db=db_session)
    assert result is False


def test_rename_metadata(db_session: Session, sample_file_metadata):
    """Test renaming/moving file metadata."""
    renamed = metadata_service.rename_metadata(
        old_path=sample_file_metadata.path,
        new_path="moved/renamed_file.txt",
        new_name="renamed_file.txt",
        db=db_session
    )
    
    assert renamed is not None
    assert renamed.path == "moved/renamed_file.txt"
    assert renamed.name == "renamed_file.txt"
    assert renamed.parent_path == "moved"
    assert renamed.updated_at is not None


def test_list_children_root(db_session: Session, regular_user):
    """Test listing files in root directory."""
    # Create root-level files
    metadata_service.create_metadata("file1.txt", "file1.txt", regular_user.id, db=db_session)
    metadata_service.create_metadata("file2.txt", "file2.txt", regular_user.id, db=db_session)
    metadata_service.create_metadata("dir1", "dir1", regular_user.id, is_directory=True, db=db_session)
    
    # Create nested file (should not appear in root)
    metadata_service.create_metadata("dir1/nested.txt", "nested.txt", regular_user.id, db=db_session)
    
    children = metadata_service.list_children("", db=db_session)
    
    assert len(children) == 3
    child_names = {c.name for c in children}
    assert child_names == {"file1.txt", "file2.txt", "dir1"}


def test_list_children_subdirectory(db_session: Session, regular_user):
    """Test listing files in subdirectory."""
    # Create directory structure
    metadata_service.create_metadata("docs", "docs", regular_user.id, is_directory=True, db=db_session)
    metadata_service.create_metadata("docs/readme.txt", "readme.txt", regular_user.id, db=db_session)
    metadata_service.create_metadata("docs/guide.pdf", "guide.pdf", regular_user.id, db=db_session)
    
    children = metadata_service.list_children("docs", db=db_session)
    
    assert len(children) == 2
    child_names = {c.name for c in children}
    assert child_names == {"readme.txt", "guide.pdf"}


def test_get_owner_id(db_session: Session, sample_file_metadata):
    """Test getting owner ID."""
    owner_id = metadata_service.get_owner_id(sample_file_metadata.path, db=db_session)
    assert owner_id == sample_file_metadata.owner_id


def test_get_owner_id_not_found(db_session: Session):
    """Test getting owner ID for non-existent file."""
    owner_id = metadata_service.get_owner_id("nonexistent.txt", db=db_session)
    assert owner_id is None


def test_set_owner_id(db_session: Session, sample_file_metadata, another_user):
    """Test setting owner ID."""
    result = metadata_service.set_owner_id(
        sample_file_metadata.path,
        another_user.id,
        db=db_session
    )
    
    assert result is True
    
    # Verify owner changed
    metadata = metadata_service.get_metadata(sample_file_metadata.path, db=db_session)
    assert metadata.owner_id == another_user.id


def test_set_owner_id_not_found(db_session: Session, another_user):
    """Test setting owner ID for non-existent file."""
    result = metadata_service.set_owner_id("nonexistent.txt", another_user.id, db=db_session)
    assert result is False


def test_path_normalization(db_session: Session, regular_user):
    """Test that paths are normalized correctly."""
    # Create with leading/trailing slashes
    metadata = metadata_service.create_metadata(
        relative_path="/some/path/file.txt/",
        name="file.txt",
        owner_id=regular_user.id,
        db=db_session
    )
    
    # Should be normalized
    assert metadata.path == "some/path/file.txt"
    
    # Should be retrievable with different path formats
    found = metadata_service.get_metadata("some/path/file.txt", db=db_session)
    assert found is not None
    assert found.id == metadata.id
    
    found = metadata_service.get_metadata("/some/path/file.txt/", db=db_session)
    assert found is not None
    assert found.id == metadata.id


def test_directory_metadata(db_session: Session, regular_user):
    """Test creating directory metadata."""
    metadata = metadata_service.create_metadata(
        relative_path="my_folder",
        name="my_folder",
        owner_id=regular_user.id,
        is_directory=True,
        db=db_session
    )
    
    assert metadata.is_directory
    assert metadata.mime_type is None
    assert metadata.size_bytes == 0


def test_legacy_get_owner(db_session: Session, sample_file_metadata):
    """Test legacy get_owner function (returns string)."""
    owner = metadata_service.get_owner(sample_file_metadata.path, db=db_session)
    assert owner == str(sample_file_metadata.owner_id)


def test_legacy_set_owner(db_session: Session, sample_file_metadata, another_user):
    """Test legacy set_owner function (accepts string)."""
    metadata_service.set_owner(
        sample_file_metadata.path,
        str(another_user.id),
        db=db_session
    )
    
    # Verify owner changed
    metadata = metadata_service.get_metadata(sample_file_metadata.path, db=db_session)
    assert metadata.owner_id == another_user.id
