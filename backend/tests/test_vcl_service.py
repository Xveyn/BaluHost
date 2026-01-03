"""Unit tests for VCL Service."""
import hashlib
import gzip
import pytest
from pathlib import Path
from sqlalchemy.orm import Session

from app.services.vcl import VCLService
from app.models.vcl import FileVersion, VersionBlob, VCLSettings, VCLStats
from app.models.file_metadata import FileMetadata
from app.models.user import User


@pytest.fixture
def vcl_service(db: Session):
    """Create VCL service instance."""
    return VCLService(db)


@pytest.fixture
def test_user(db: Session):
    """Create test user."""
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password="hashed",
        role="user",
        is_active=True
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def test_file(db: Session, test_user: User):
    """Create test file metadata."""
    file = FileMetadata(
        path="/test/file.txt",
        name="file.txt",
        owner_id=test_user.id,
        size_bytes=1024,
        is_directory=False,
        mime_type="text/plain"
    )
    db.add(file)
    db.commit()
    return file


class TestChecksumOperations:
    """Test checksum calculation."""
    
    def test_calculate_checksum_from_bytes(self, vcl_service: VCLService):
        """Test checksum calculation from bytes."""
        content = b"Hello World"
        expected = hashlib.sha256(content).hexdigest()
        
        checksum = vcl_service.calculate_checksum(content)
        
        assert checksum == expected
        assert len(checksum) == 64
    
    def test_calculate_checksum_from_file(self, vcl_service: VCLService, tmp_path: Path):
        """Test checksum calculation from file."""
        test_file = tmp_path / "test.txt"
        content = b"Test Content"
        test_file.write_bytes(content)
        
        expected = hashlib.sha256(content).hexdigest()
        checksum = vcl_service.calculate_checksum_from_file(test_file)
        
        assert checksum == expected
    
    def test_same_content_same_checksum(self, vcl_service: VCLService):
        """Test same content produces same checksum."""
        content = b"Same content"
        
        checksum1 = vcl_service.calculate_checksum(content)
        checksum2 = vcl_service.calculate_checksum(content)
        
        assert checksum1 == checksum2


class TestCompressionOperations:
    """Test compression/decompression."""
    
    def test_compress_content(self, vcl_service: VCLService, tmp_path: Path):
        """Test content compression."""
        content = b"Hello World" * 100
        dest = tmp_path / "test.gz"
        
        compressed_size = vcl_service.compress_content(content, dest)
        
        assert dest.exists()
        assert compressed_size < len(content)
        assert compressed_size == dest.stat().st_size
    
    def test_compress_file(self, vcl_service: VCLService, tmp_path: Path):
        """Test file compression."""
        source = tmp_path / "source.txt"
        dest = tmp_path / "compressed.gz"
        content = b"Test content\n" * 1000
        source.write_bytes(content)
        
        compressed_size = vcl_service.compress_file(source, dest)
        
        assert dest.exists()
        assert compressed_size < len(content)
    
    def test_decompress_file(self, vcl_service: VCLService, tmp_path: Path):
        """Test file decompression."""
        original_content = b"Original content\n" * 100
        compressed = tmp_path / "test.gz"
        decompressed = tmp_path / "output.txt"
        
        # Compress first
        vcl_service.compress_content(original_content, compressed)
        
        # Decompress
        decompressed_size = vcl_service.decompress_file(compressed, decompressed)
        
        assert decompressed.exists()
        assert decompressed_size == len(original_content)
        assert decompressed.read_bytes() == original_content
    
    def test_read_compressed_content(self, vcl_service: VCLService, tmp_path: Path):
        """Test reading compressed content."""
        original_content = b"Test content"
        compressed = tmp_path / "test.gz"
        
        vcl_service.compress_content(original_content, compressed)
        
        read_content = vcl_service.read_compressed_content(compressed)
        
        assert read_content == original_content
    
    def test_compression_reduces_size_text(self, vcl_service: VCLService, tmp_path: Path):
        """Test compression achieves good ratio for text."""
        text_content = b"Hello World\n" * 1000
        compressed = tmp_path / "text.gz"
        
        compressed_size = vcl_service.compress_content(text_content, compressed)
        
        # Text should compress well (>50% reduction)
        assert compressed_size < len(text_content) * 0.5


class TestBlobOperations:
    """Test blob storage and deduplication."""
    
    def test_create_blob(self, vcl_service: VCLService, db: Session):
        """Test blob creation."""
        content = b"Test blob content"
        checksum = vcl_service.calculate_checksum(content)
        
        blob = vcl_service.create_blob(content, checksum)
        
        assert blob.id is not None
        assert blob.checksum == checksum
        assert blob.original_size == len(content)
        assert blob.compressed_size > 0
        assert blob.compressed_size < blob.original_size
        assert blob.reference_count == 0
        
        # Check file exists
        blob_path = Path(blob.storage_path)
        assert blob_path.exists()
    
    def test_find_blob_by_checksum(self, vcl_service: VCLService, db: Session):
        """Test finding existing blob."""
        content = b"Test content"
        checksum = vcl_service.calculate_checksum(content)
        
        # Create blob
        blob1 = vcl_service.create_blob(content, checksum)
        db.commit()
        
        # Find it
        blob2 = vcl_service.find_blob_by_checksum(checksum)
        
        assert blob2 is not None
        assert blob2.id == blob1.id
    
    def test_get_or_create_blob_creates_new(self, vcl_service: VCLService, db: Session):
        """Test blob creation when doesn't exist."""
        content = b"New content"
        checksum = vcl_service.calculate_checksum(content)
        
        blob, was_created = vcl_service.get_or_create_blob(content, checksum)
        
        assert was_created is True
        assert blob.checksum == checksum
        assert blob.reference_count == 1
    
    def test_get_or_create_blob_reuses_existing(self, vcl_service: VCLService, db: Session):
        """Test blob reuse (deduplication)."""
        content = b"Duplicate content"
        checksum = vcl_service.calculate_checksum(content)
        
        # Create first
        blob1, created1 = vcl_service.get_or_create_blob(content, checksum)
        assert created1 is True
        assert blob1.reference_count == 1
        
        # Try to create again (should reuse)
        blob2, created2 = vcl_service.get_or_create_blob(content, checksum)
        
        assert created2 is False
        assert blob2.id == blob1.id
        assert blob2.reference_count == 2  # Incremented
    
    def test_increment_blob_reference(self, vcl_service: VCLService, db: Session):
        """Test reference counting."""
        content = b"Test"
        checksum = vcl_service.calculate_checksum(content)
        blob = vcl_service.create_blob(content, checksum)
        
        initial_count = blob.reference_count
        vcl_service.increment_blob_reference(blob)
        
        assert blob.reference_count == initial_count + 1
        assert blob.last_accessed is not None
    
    def test_decrement_blob_reference(self, vcl_service: VCLService, db: Session):
        """Test reference decrement."""
        content = b"Test"
        checksum = vcl_service.calculate_checksum(content)
        blob = vcl_service.create_blob(content, checksum)
        blob.reference_count = 2
        
        vcl_service.decrement_blob_reference(blob)
        
        assert blob.reference_count == 1
        assert blob.can_delete is False
    
    def test_decrement_marks_for_deletion_at_zero(self, vcl_service: VCLService, db: Session):
        """Test blob marked for deletion when refs reach 0."""
        content = b"Test"
        checksum = vcl_service.calculate_checksum(content)
        blob = vcl_service.create_blob(content, checksum)
        blob.reference_count = 1
        
        vcl_service.decrement_blob_reference(blob)
        
        assert blob.reference_count == 0
        assert blob.can_delete is True
    
    def test_delete_blob_removes_file_and_record(self, vcl_service: VCLService, db: Session):
        """Test blob deletion."""
        content = b"To delete"
        checksum = vcl_service.calculate_checksum(content)
        blob = vcl_service.create_blob(content, checksum)
        blob.reference_count = 0
        blob.can_delete = True
        blob_path = Path(blob.storage_path)
        blob_id = blob.id
        
        vcl_service.delete_blob(blob)
        db.commit()
        
        # File should be deleted
        assert not blob_path.exists()
        
        # Record should be deleted
        deleted_blob = db.query(VersionBlob).filter(VersionBlob.id == blob_id).first()
        assert deleted_blob is None
    
    def test_delete_blob_fails_with_references(self, vcl_service: VCLService, db: Session):
        """Test cannot delete blob with active references."""
        content = b"Referenced"
        checksum = vcl_service.calculate_checksum(content)
        blob = vcl_service.create_blob(content, checksum)
        blob.reference_count = 2
        
        with pytest.raises(ValueError, match="Cannot delete blob"):
            vcl_service.delete_blob(blob)


class TestVersionOperations:
    """Test version creation and management."""
    
    def test_should_create_version_respects_size_limit(
        self, vcl_service: VCLService, test_file: FileMetadata, test_user: User
    ):
        """Test size limit enforcement."""
        test_file.size_bytes = 101 * 1024 * 1024  # 101 MB
        
        should_create, reason = vcl_service.should_create_version(
            test_file, "checksum123", test_user.id
        )
        
        assert should_create is False
        assert "too large" in reason.lower()
    
    def test_should_create_version_detects_unchanged_checksum(
        self, vcl_service: VCLService, db: Session, test_file: FileMetadata, test_user: User
    ):
        """Test unchanged content detection."""
        content = b"Original content"
        checksum = vcl_service.calculate_checksum(content)
        
        # Create first version
        vcl_service.create_version(test_file, content, test_user.id, checksum=checksum)
        db.commit()
        
        # Try to create with same checksum
        should_create, reason = vcl_service.should_create_version(
            test_file, checksum, test_user.id
        )
        
        assert should_create is False
        assert "unchanged" in reason.lower()
    
    def test_create_version_success(
        self, vcl_service: VCLService, db: Session, test_file: FileMetadata, test_user: User
    ):
        """Test successful version creation."""
        content = b"Test version content"
        
        version = vcl_service.create_version(
            test_file, content, test_user.id, change_type="create"
        )
        
        assert version.id is not None
        assert version.file_id == test_file.id
        assert version.user_id == test_user.id
        assert version.version_number == 1
        assert version.file_size == len(content)
        assert version.checksum == vcl_service.calculate_checksum(content)
        assert version.storage_type == 'stored'
        assert version.change_type == "create"
    
    def test_create_multiple_versions_increments_number(
        self, vcl_service: VCLService, db: Session, test_file: FileMetadata, test_user: User
    ):
        """Test version numbering."""
        # Create 3 versions
        for i in range(3):
            content = f"Version {i}".encode()
            vcl_service.create_version(test_file, content, test_user.id)
            db.commit()
        
        versions = vcl_service.get_file_versions(test_file.id)
        
        assert len(versions) == 3
        assert versions[0].version_number == 3  # Newest first
        assert versions[1].version_number == 2
        assert versions[2].version_number == 1
    
    def test_create_version_with_deduplication(
        self, vcl_service: VCLService, db: Session, test_file: FileMetadata, test_user: User
    ):
        """Test deduplication across versions."""
        content = b"Shared content"
        checksum = vcl_service.calculate_checksum(content)
        
        # Create first version
        version1 = vcl_service.create_version(test_file, content, test_user.id, checksum=checksum)
        db.commit()
        
        # Create second file with different metadata but same content
        test_file2 = FileMetadata(
            path="/test/file2.txt",
            name="file2.txt",
            owner_id=test_user.id,
            size_bytes=len(content),
            is_directory=False
        )
        db.add(test_file2)
        db.commit()
        
        # Create version with same content
        version2 = vcl_service.create_version(test_file2, content, test_user.id, checksum=checksum)
        db.commit()
        
        # Should reuse same blob
        assert version1.blob_id == version2.blob_id
        assert version1.storage_type == 'stored'
        assert version2.storage_type == 'reference'  # Deduplicated
        
        # Blob should have 2 references
        assert version1.blob.reference_count == 2
    
    def test_get_version_content(
        self, vcl_service: VCLService, db: Session, test_file: FileMetadata, test_user: User
    ):
        """Test retrieving version content."""
        original_content = b"Version content to retrieve"
        
        version = vcl_service.create_version(test_file, original_content, test_user.id)
        db.commit()
        
        retrieved_content = vcl_service.get_version_content(version)
        
        assert retrieved_content == original_content
    
    def test_delete_version_frees_storage(
        self, vcl_service: VCLService, db: Session, test_file: FileMetadata, test_user: User
    ):
        """Test version deletion."""
        content = b"Version to delete"
        version = vcl_service.create_version(test_file, content, test_user.id)
        blob_id = version.blob_id
        db.commit()
        
        freed_bytes = vcl_service.delete_version(version)
        db.commit()
        
        assert freed_bytes > 0
        
        # Version should be deleted
        deleted_version = db.query(FileVersion).filter(FileVersion.id == version.id).first()
        assert deleted_version is None
        
        # Blob should be deleted (no other references)
        deleted_blob = db.query(VersionBlob).filter(VersionBlob.id == blob_id).first()
        assert deleted_blob is None


class TestSettingsAndQuota:
    """Test VCL settings and quota management."""
    
    def test_get_user_settings_creates_global_default(
        self, vcl_service: VCLService, db: Session, test_user: User
    ):
        """Test default settings creation."""
        settings = vcl_service.get_user_settings(test_user.id)
        
        assert settings is not None
        assert settings.user_id is None  # Global settings
        assert settings.max_size_bytes == 10737418240  # 10 GB
        assert settings.depth == 5
        assert settings.is_enabled is True
    
    def test_get_or_create_user_settings(
        self, vcl_service: VCLService, db: Session, test_user: User
    ):
        """Test user-specific settings creation."""
        settings = vcl_service.get_or_create_user_settings(test_user.id)
        
        assert settings.user_id == test_user.id
        assert settings.max_size_bytes > 0
    
    def test_update_user_usage(
        self, vcl_service: VCLService, db: Session, test_user: User
    ):
        """Test quota usage tracking."""
        settings = vcl_service.get_or_create_user_settings(test_user.id)
        initial_usage = settings.current_usage_bytes
        
        vcl_service._update_user_usage(test_user.id, 1024)
        db.commit()
        
        assert settings.current_usage_bytes == initial_usage + 1024
    
    def test_quota_enforcement_in_should_create_version(
        self, vcl_service: VCLService, db: Session, test_file: FileMetadata, test_user: User
    ):
        """Test quota enforcement."""
        # Set very low quota
        settings = vcl_service.get_or_create_user_settings(test_user.id)
        settings.max_size_bytes = 100
        settings.current_usage_bytes = 101
        db.commit()
        
        should_create, reason = vcl_service.should_create_version(
            test_file, "checksum", test_user.id
        )
        
        assert should_create is False
        assert "quota" in reason.lower()


class TestStatistics:
    """Test VCL statistics."""
    
    def test_get_stats_creates_default(self, vcl_service: VCLService, db: Session):
        """Test stats initialization."""
        stats = vcl_service.get_stats()
        
        assert stats.id == 1
        assert stats.total_versions == 0
        assert stats.total_size_bytes == 0
    
    def test_stats_updated_on_version_creation(
        self, vcl_service: VCLService, db: Session, test_file: FileMetadata, test_user: User
    ):
        """Test stats tracking."""
        stats = vcl_service.get_stats()
        initial_versions = stats.total_versions
        
        content = b"Test content"
        vcl_service.create_version(test_file, content, test_user.id)
        db.commit()
        
        assert stats.total_versions == initial_versions + 1
        assert stats.total_size_bytes >= len(content)
        assert stats.total_compressed_bytes > 0
    
    def test_recalculate_stats(
        self, vcl_service: VCLService, db: Session, test_file: FileMetadata, test_user: User
    ):
        """Test stats recalculation."""
        # Create some versions
        for i in range(3):
            content = f"Content {i}".encode()
            vcl_service.create_version(test_file, content, test_user.id)
        db.commit()
        
        # Manually reset stats
        stats = vcl_service.get_stats()
        stats.total_versions = 0
        stats.total_size_bytes = 0
        db.commit()
        
        # Recalculate
        vcl_service.recalculate_stats()
        db.commit()
        
        assert stats.total_versions == 3
        assert stats.total_size_bytes > 0
