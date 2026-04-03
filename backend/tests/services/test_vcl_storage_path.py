"""Tests for VCL configurable storage path."""
import pytest
from pathlib import Path
from unittest.mock import patch
from sqlalchemy.orm import Session

from app.services.versioning.vcl import VCLService
from app.models.user import User
from app.models.file_metadata import FileMetadata


@pytest.fixture
def test_user(db: Session):
    """Create test user."""
    user = User(
        username="vcl_path_user",
        email="vclpath@example.com",
        hashed_password="hashed",
        role="user",
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def test_file(db: Session, test_user: User):
    """Create test file metadata."""
    file = FileMetadata(
        path="/test/storage_path_test.txt",
        name="storage_path_test.txt",
        owner_id=test_user.id,
        size_bytes=512,
        is_directory=False,
        mime_type="text/plain",
    )
    db.add(file)
    db.commit()
    return file


class TestVCLStoragePathConfig:
    """Test configurable VCL storage path."""

    def test_default_path_uses_nas_storage(self, db: Session, tmp_path: Path):
        """When vcl_storage_path is empty, use nas_storage_path/.system/versions."""
        with patch("app.services.versioning.vcl.settings") as mock_settings:
            mock_settings.vcl_storage_path = ""
            mock_settings.nas_storage_path = str(tmp_path / "nas")

            service = VCLService(db)

            expected = tmp_path / "nas" / ".system" / "versions"
            assert service.storage_base == expected
            assert service.blobs_path == expected / "blobs"

    def test_custom_path_overrides_default(self, db: Session, tmp_path: Path):
        """When vcl_storage_path is set, use it directly."""
        custom_path = tmp_path / "custom-vcl"
        with patch("app.services.versioning.vcl.settings") as mock_settings:
            mock_settings.vcl_storage_path = str(custom_path)
            mock_settings.nas_storage_path = str(tmp_path / "nas")

            service = VCLService(db)

            assert service.storage_base == custom_path
            assert service.blobs_path == custom_path / "blobs"

    def test_whitespace_only_path_treated_as_empty(self, db: Session, tmp_path: Path):
        """Whitespace-only vcl_storage_path falls back to default."""
        with patch("app.services.versioning.vcl.settings") as mock_settings:
            mock_settings.vcl_storage_path = "   "
            mock_settings.nas_storage_path = str(tmp_path / "nas")

            service = VCLService(db)

            expected = tmp_path / "nas" / ".system" / "versions"
            assert service.storage_base == expected

    def test_ensure_storage_dirs_creates_directories(self, db: Session, tmp_path: Path):
        """_ensure_storage_dirs creates blobs directory."""
        custom_path = tmp_path / "vcl-new"
        with patch("app.services.versioning.vcl.settings") as mock_settings:
            mock_settings.vcl_storage_path = str(custom_path)
            mock_settings.nas_storage_path = str(tmp_path / "nas")

            service = VCLService(db)

            assert (custom_path / "blobs").exists()
            assert (custom_path / "blobs").is_dir()

    def test_blob_stored_at_custom_path(
        self, db: Session, tmp_path: Path, test_user: User, test_file: FileMetadata
    ):
        """Blobs are written to the custom storage path."""
        custom_path = tmp_path / "vcl-store"
        with patch("app.services.versioning.vcl.settings") as mock_settings:
            mock_settings.vcl_storage_path = str(custom_path)
            mock_settings.nas_storage_path = str(tmp_path / "nas")

            service = VCLService(db)
            content = b"Test blob at custom path"
            checksum = service.calculate_checksum(content)

            blob = service.create_blob(content, checksum)

            blob_file = custom_path / "blobs" / f"{checksum}.gz"
            assert blob_file.exists()
            assert str(blob.storage_path) == str(blob_file)

    def test_version_content_readable_from_custom_path(
        self, db: Session, tmp_path: Path, test_user: User, test_file: FileMetadata
    ):
        """Version content can be read back from custom storage path."""
        custom_path = tmp_path / "vcl-read"
        with patch("app.services.versioning.vcl.settings") as mock_settings:
            mock_settings.vcl_storage_path = str(custom_path)
            mock_settings.nas_storage_path = str(tmp_path / "nas")

            service = VCLService(db)
            original = b"Content to retrieve from SSD"

            version = service.create_version(
                test_file, original, test_user.id, change_type="create"
            )
            db.commit()

            retrieved = service.get_version_content(version)
            assert retrieved == original
