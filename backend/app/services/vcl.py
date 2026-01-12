"""Version Control Light (VCL) Core Service.

Handles version creation, blob storage, deduplication, and compression.
"""
import hashlib
import gzip
import shutil
from pathlib import Path
from typing import Optional, Tuple, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, select, update

from app.models.vcl import FileVersion, VersionBlob, VCLSettings, VCLStats
from app.models.file_metadata import FileMetadata
from app.core.config import settings


class VCLService:
    """Core service for Version Control Light operations."""
    
    # Constants
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
    COMPRESSION_LEVEL = 6  # gzip compression level (balance)
    
    def __init__(self, db: Session):
        self.db = db
        self.storage_base = Path(settings.nas_storage_path) / "versions"
        self.blobs_path = self.storage_base / "blobs"
        self._ensure_storage_dirs()
    
    def _ensure_storage_dirs(self):
        """Ensure version storage directories exist."""
        self.blobs_path.mkdir(parents=True, exist_ok=True)
    
    # ========== Checksum Operations ==========
    
    @staticmethod
    def calculate_checksum(content: bytes) -> str:
        """
        Calculate SHA256 checksum of file content.
        
        Args:
            content: File content as bytes
            
        Returns:
            Lowercase hex digest (64 chars)
        """
        return hashlib.sha256(content).hexdigest()
    
    @staticmethod
    def calculate_checksum_from_file(file_path: Path) -> str:
        """
        Calculate SHA256 checksum from file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Lowercase hex digest (64 chars)
        """
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            # Read in 64KB chunks for memory efficiency
            for chunk in iter(lambda: f.read(65536), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    # ========== Compression Operations ==========
    
    def compress_content(self, content: bytes, dest_path: Path) -> int:
        """
        Compress content with gzip and save to file.
        
        Args:
            content: Content to compress
            dest_path: Destination path for compressed file
            
        Returns:
            Compressed size in bytes
        """
        with gzip.open(dest_path, 'wb', compresslevel=self.COMPRESSION_LEVEL) as f_out:
            f_out.write(content)
        
        return dest_path.stat().st_size
    
    def compress_file(self, source_path: Path, dest_path: Path) -> int:
        """
        Compress file with gzip.
        
        Args:
            source_path: Source file path
            dest_path: Destination path for compressed file
            
        Returns:
            Compressed size in bytes
        """
        with open(source_path, 'rb') as f_in:
            with gzip.open(dest_path, 'wb', compresslevel=self.COMPRESSION_LEVEL) as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        return dest_path.stat().st_size
    
    def decompress_file(self, compressed_path: Path, dest_path: Path) -> int:
        """
        Decompress gzip file.
        
        Args:
            compressed_path: Compressed file path
            dest_path: Destination path for decompressed file
            
        Returns:
            Decompressed size in bytes
        """
        with gzip.open(compressed_path, 'rb') as f_in:
            with open(dest_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        return dest_path.stat().st_size
    
    def read_compressed_content(self, compressed_path: Path) -> bytes:
        """
        Read and decompress content.
        
        Args:
            compressed_path: Path to compressed file
            
        Returns:
            Decompressed content as bytes
        """
        with gzip.open(compressed_path, 'rb') as f:
            return f.read()
    
    def decompress_content(self, compressed_content: bytes) -> bytes:
        """
        Decompress gzip-compressed bytes.
        
        Args:
            compressed_content: Compressed content as bytes
            
        Returns:
            Decompressed content as bytes
        """
        return gzip.decompress(compressed_content)
    
    # ========== Blob Operations (Deduplication) ==========
    
    def get_blob_path(self, checksum: str) -> Path:
        """Get storage path for blob by checksum."""
        return self.blobs_path / f"{checksum}.gz"
    
    def find_blob_by_checksum(self, checksum: str) -> Optional[VersionBlob]:
        """
        Find existing blob by checksum (deduplication).
        
        Args:
            checksum: SHA256 checksum
            
        Returns:
            VersionBlob if exists, None otherwise
        """
        return self.db.query(VersionBlob).filter(
            VersionBlob.checksum == checksum
        ).first()
    
    def create_blob(
        self,
        content: bytes,
        checksum: str
    ) -> VersionBlob:
        """
        Create new blob with content.
        
        Args:
            content: File content to store
            checksum: SHA256 checksum
            
        Returns:
            Created VersionBlob
        """
        # Store compressed blob
        blob_path = self.get_blob_path(checksum)
        compressed_size = self.compress_content(content, blob_path)
        
        # Create blob record
        blob = VersionBlob(
            checksum=checksum,
            storage_path=str(blob_path),
            original_size=len(content),
            compressed_size=compressed_size,
            reference_count=0,
            created_at=datetime.now(timezone.utc)
        )
        
        self.db.add(blob)
        self.db.flush()
        
        return blob
    
    def increment_blob_reference(self, blob: VersionBlob):
        """Increment blob reference count."""
        # Use SQL update to avoid Column assignment issues
        self.db.execute(
            update(VersionBlob).
            where(VersionBlob.id == blob.id).
            values(
                reference_count=VersionBlob.reference_count + 1,
                last_accessed=datetime.now(timezone.utc)
            )
        )
        self.db.flush()
        # Refresh the SQLAlchemy object so in-memory attributes reflect DB update
        try:
            self.db.refresh(blob)
        except Exception:
            pass
    
    def decrement_blob_reference(self, blob: VersionBlob):
        """
        Decrement blob reference count.
        Mark for deletion if reaches zero.
        """
        # Use SQL update to avoid Column assignment issues
        new_count = max(0, int(blob.reference_count) - 1)  # type: ignore
        self.db.execute(
            update(VersionBlob).
            where(VersionBlob.id == blob.id).
            values(
                reference_count=new_count,
                can_delete=(new_count == 0)
            )
        )
        self.db.flush()
    
    def delete_blob(self, blob: VersionBlob):
        """
        Delete blob file and database record.
        Only if reference count is 0.
        """
        ref_count: int = int(blob.reference_count)  # type: ignore
        if ref_count > 0:
            raise ValueError(f"Cannot delete blob {blob.id} with {ref_count} references")
        
        # Delete physical file
        storage_path: str = str(blob.storage_path)  # type: ignore
        blob_path = Path(storage_path)
        if blob_path.exists():
            blob_path.unlink()
        
        # Delete database record
        self.db.delete(blob)
    
    def get_or_create_blob(self, content: bytes, checksum: str) -> Tuple[VersionBlob, bool]:
        """
        Get existing blob or create new one (deduplication).
        
        Args:
            content: File content
            checksum: SHA256 checksum
            
        Returns:
            Tuple of (blob, was_created)
        """
        # Try to find existing blob
        existing_blob = self.find_blob_by_checksum(checksum)
        
        if existing_blob:
            # Deduplication: reuse existing blob
            self.increment_blob_reference(existing_blob)
            return existing_blob, False
        else:
            # Create new blob
            new_blob = self.create_blob(content, checksum)
            self.increment_blob_reference(new_blob)
            return new_blob, True
    
    # ========== Version Operations ==========
    
    def should_create_version(
        self,
        file: FileMetadata,
        new_checksum: str,
        user_id: int
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if version should be created.
        
        Args:
            file: File metadata
            new_checksum: New file checksum
            user_id: User ID
            
        Returns:
            Tuple of (should_create, reason_if_not)
        """
        # 1. Check file size
        if file.size_bytes > self.MAX_FILE_SIZE:
            return False, f"File too large ({file.size_bytes} > {self.MAX_FILE_SIZE})"
        
        # 2. Check if checksum changed
        last_version = self.db.query(FileVersion).filter(
            FileVersion.file_id == file.id
        ).order_by(FileVersion.version_number.desc()).first()
        
        if last_version:
            last_checksum: str = str(last_version.checksum)  # type: ignore
            if last_checksum == new_checksum:
                return False, "Content unchanged (same checksum)"
        
        # 3. Check user quota
        user_settings = self.get_user_settings(user_id)
        
        # Cast Columns for conditionals
        is_enabled: bool = bool(user_settings.is_enabled)  # type: ignore
        if not is_enabled:
            return False, "VCL disabled for user"
        
        current_usage: int = int(user_settings.current_usage_bytes)  # type: ignore
        max_size: int = int(user_settings.max_size_bytes)  # type: ignore
        if current_usage >= max_size:
            return False, "User quota exceeded"
        
        return True, None
    
    def get_next_version_number(self, file_id: int) -> int:
        """Get next version number for file."""
        max_version = self.db.query(func.max(FileVersion.version_number)).filter(
            FileVersion.file_id == file_id
        ).scalar()
        
        return (max_version or 0) + 1
    
    def create_version(
        self,
        file: FileMetadata,
        content: bytes,
        user_id: int,
        checksum: Optional[str] = None,
        is_high_priority: bool = False,
        change_type: str = "update",
        comment: Optional[str] = None,
        was_cached: bool = False,
        cache_duration: Optional[int] = None
    ) -> FileVersion:
        """
        Create new file version.
        
        Args:
            file: File metadata
            content: File content
            user_id: User ID
            checksum: Optional pre-calculated checksum
            is_high_priority: High priority flag
            change_type: Type of change (create, update, overwrite, batched)
            comment: Optional comment
            was_cached: Was this version from cache?
            cache_duration: Seconds in cache
            
        Returns:
            Created FileVersion
        """
        # Calculate checksum if not provided
        if checksum is None:
            checksum = self.calculate_checksum(content)
        
        # Get or create blob (deduplication)
        blob, was_created = self.get_or_create_blob(content, checksum)
        
        # Determine storage type
        storage_type = 'stored' if was_created else 'reference'
        
        # Calculate compression ratio - cast Column to int
        blob_orig: int = int(blob.original_size)  # type: ignore
        blob_comp: int = int(blob.compressed_size)  # type: ignore
        compression_ratio = blob_orig / blob_comp if blob_comp > 0 else 1.0
        
        # Get next version number
        version_number = self.get_next_version_number(file.id)
        
        # Create version record
        version = FileVersion(
            file_id=file.id,
            user_id=user_id,
            version_number=version_number,
            blob_id=blob.id,
            storage_type=storage_type,
            file_size=len(content),
            compressed_size=blob_comp,
            compression_ratio=compression_ratio,
            checksum=checksum,
            is_high_priority=is_high_priority,
            change_type=change_type,
            comment=comment,
            was_cached=was_cached,
            cache_duration=cache_duration,
            created_at=datetime.now(timezone.utc)
        )
        
        self.db.add(version)
        self.db.flush()
        
        # Update user quota
        delta_bytes = blob_comp if was_created else 0
        self._update_user_usage(user_id, delta_bytes)
        
        # Update global stats
        self._update_stats(
            version_created=True,
            size_bytes=len(content),
            compressed_bytes=blob_comp,
            blob_created=was_created,
            is_priority=is_high_priority,
            was_cached=was_cached
        )
        
        return version
    
    def get_quota_status(self, user_id: int) -> tuple[float, Optional[str]]:
        """
        Get quota usage percentage and warning status.
        
        Args:
            user_id: User ID
            
        Returns:
            Tuple of (usage_percent, warning_level)
            warning_level: None | 'warning' (>80%) | 'critical' (>95%)
        """
        settings = self.get_or_create_settings(user_id)
        
        if settings.max_size_bytes <= 0:
            return 0.0, None
        
        usage_percent = (settings.current_usage_bytes / settings.max_size_bytes) * 100
        
        warning = None
        if usage_percent >= 95:
            warning = 'critical'
        elif usage_percent >= 80:
            warning = 'warning'
        
        return usage_percent, warning
    
    def get_version_content(self, version: FileVersion) -> bytes:
        """
        Get decompressed content of a version.
        
        Args:
            version: FileVersion
            
        Returns:
            Decompressed content as bytes
        """
        if not version.blob:
            raise ValueError(f"Version {version.id} has no associated blob")
        
        blob_path = Path(version.blob.storage_path)
        if not blob_path.exists():
            raise FileNotFoundError(f"Blob file not found: {blob_path}")
        
        return self.read_compressed_content(blob_path)
    
    def delete_version(self, version: FileVersion) -> int:
        """
        Delete a version.
        
        Args:
            version: FileVersion to delete
            
        Returns:
            Bytes freed
        """
        freed_bytes = 0
        
        # Decrement blob reference
        if version.blob:
            self.decrement_blob_reference(version.blob)
            
            # If blob can be deleted, delete it
            blob_can_delete: bool = bool(version.blob.can_delete)  # type: ignore
            if blob_can_delete:
                freed_bytes = int(version.blob.compressed_size)  # type: ignore
                self.delete_blob(version.blob)
        
        # Delete version record
        self.db.delete(version)
        
        # Cast Columns for parameter types
        vers_user_id: int = int(version.user_id)  # type: ignore
        vers_file_size: int = int(version.file_size)  # type: ignore
        vers_is_priority: bool = bool(version.is_high_priority)  # type: ignore
        
        # Update user quota
        if freed_bytes > 0:
            self._update_user_usage(vers_user_id, -freed_bytes)
        
        # Update stats
        self._update_stats(
            version_deleted=True,
            size_bytes=-vers_file_size,
            compressed_bytes=-freed_bytes,
            blob_deleted=freed_bytes > 0,
            is_priority=vers_is_priority
        )
        
        return freed_bytes
    
    # ========== Settings & Quota ==========
    
    def get_user_settings(self, user_id: int) -> VCLSettings:
        """
        Get VCL settings for user (or global if not exists).
        
        Args:
            user_id: User ID
            
        Returns:
            VCLSettings
        """
        # Try user-specific settings
        user_settings = self.db.query(VCLSettings).filter(
            VCLSettings.user_id == user_id
        ).first()
        
        if user_settings:
            return user_settings
        
        # Fallback to global settings
        global_settings = self.db.query(VCLSettings).filter(
            VCLSettings.user_id == None
        ).first()
        
        if global_settings:
            return global_settings
        
        # Create default global settings if none exist
        default_settings = VCLSettings(
            user_id=None,
            max_size_bytes=10737418240,  # 10 GB
            current_usage_bytes=0,
            depth=5,
            headroom_percent=10,
            is_enabled=True,
            compression_enabled=True,
            dedupe_enabled=True,
            debounce_window_seconds=30,
            max_batch_window_seconds=300
        )
        self.db.add(default_settings)
        self.db.flush()
        
        return default_settings
    
    def get_or_create_user_settings(self, user_id: int) -> VCLSettings:
        """Get or create user-specific VCL settings."""
        user_settings = self.db.query(VCLSettings).filter(
            VCLSettings.user_id == user_id
        ).first()
        
        if user_settings:
            return user_settings
        
        # Get global settings as template
        global_settings = self.get_user_settings(user_id)
        
        # Create user-specific settings
        new_settings = VCLSettings(
            user_id=user_id,
            max_size_bytes=global_settings.max_size_bytes,
            current_usage_bytes=0,
            depth=global_settings.depth,
            headroom_percent=global_settings.headroom_percent,
            is_enabled=global_settings.is_enabled,
            compression_enabled=global_settings.compression_enabled,
            dedupe_enabled=global_settings.dedupe_enabled,
            debounce_window_seconds=global_settings.debounce_window_seconds,
            max_batch_window_seconds=global_settings.max_batch_window_seconds
        )
        
        self.db.add(new_settings)
        self.db.flush()
        
        return new_settings
    
    def _update_user_usage(self, user_id: int, delta_bytes: int):
        """Update user's current usage (internal) using SQL update."""
        settings = self.get_or_create_user_settings(user_id)
        current_usage: int = int(settings.current_usage_bytes)  # type: ignore
        new_usage = max(0, current_usage + delta_bytes)
        
        self.db.execute(
            update(VCLSettings).
            where(VCLSettings.user_id == user_id).
            values(current_usage_bytes=new_usage)
        )
        self.db.flush()
    
    # ========== Statistics ==========
    
    def get_stats(self) -> VCLStats:
        """Get global VCL statistics."""
        stats = self.db.query(VCLStats).filter(VCLStats.id == 1).first()
        
        if not stats:
            # Create default stats
            stats = VCLStats(id=1)
            self.db.add(stats)
            self.db.flush()
        
        return stats
    
    def _update_stats(
        self,
        version_created: bool = False,
        version_deleted: bool = False,
        size_bytes: int = 0,
        compressed_bytes: int = 0,
        blob_created: bool = False,
        blob_deleted: bool = False,
        is_priority: bool = False,
        was_cached: bool = False
    ):
        """Update global statistics (internal) using SQL update."""
        stats = self.get_stats()
        
        # Build update values dict
        updates = {}
        
        if version_created:
            total_versions: int = int(stats.total_versions)  # type: ignore
            total_size: int = int(stats.total_size_bytes)  # type: ignore
            total_compressed: int = int(stats.total_compressed_bytes)  # type: ignore
            priority_count: int = int(stats.priority_count)  # type: ignore
            cached_count: int = int(stats.cached_versions_count)  # type: ignore
            
            updates['total_versions'] = total_versions + 1
            updates['total_size_bytes'] = total_size + size_bytes
            updates['total_compressed_bytes'] = total_compressed + compressed_bytes
            
            if is_priority:
                updates['priority_count'] = priority_count + 1
            
            if was_cached:
                updates['cached_versions_count'] = cached_count + 1
        
        if version_deleted:
            total_versions: int = int(stats.total_versions)  # type: ignore
            total_size: int = int(stats.total_size_bytes)  # type: ignore
            total_compressed: int = int(stats.total_compressed_bytes)  # type: ignore
            priority_count: int = int(stats.priority_count)  # type: ignore
            
            updates['total_versions'] = max(0, total_versions - 1)
            updates['total_size_bytes'] = max(0, total_size + size_bytes)  # size_bytes is negative
            updates['total_compressed_bytes'] = max(0, total_compressed + compressed_bytes)
            
            if is_priority:
                updates['priority_count'] = max(0, priority_count - 1)
        
        if blob_created:
            total_blobs: int = int(stats.total_blobs)  # type: ignore
            unique_blobs: int = int(stats.unique_blobs)  # type: ignore
            updates['total_blobs'] = total_blobs + 1
            updates['unique_blobs'] = unique_blobs + 1
        
        if blob_deleted:
            total_blobs: int = int(stats.total_blobs)  # type: ignore
            unique_blobs: int = int(stats.unique_blobs)  # type: ignore
            updates['total_blobs'] = max(0, total_blobs - 1)
            updates['unique_blobs'] = max(0, unique_blobs - 1)
        
        # Calculate savings
        total_size: int = int(updates.get('total_size_bytes', stats.total_size_bytes))  # type: ignore
        total_compressed: int = int(updates.get('total_compressed_bytes', stats.total_compressed_bytes))  # type: ignore
        if total_size > 0:
            updates['compression_savings_bytes'] = total_size - total_compressed
        
        # Apply updates if any
        if updates:
            self.db.execute(
                update(VCLStats).
                where(VCLStats.id == 1).
                values(**updates)
            )
            self.db.flush()
    
    def recalculate_stats(self):
        """Recalculate all statistics from scratch."""
        # Get or create stats WITHOUT flush
        stats = self.db.query(VCLStats).first()
        if not stats:
            stats = VCLStats(id=1)
            self.db.add(stats)
        
        # Count versions
        total_versions: int = self.db.query(func.count(FileVersion.id)).scalar() or 0
        total_size: int = self.db.query(func.sum(FileVersion.file_size)).scalar() or 0
        total_compressed: int = self.db.query(func.sum(FileVersion.compressed_size)).scalar() or 0
        priority_count: int = self.db.query(func.count(FileVersion.id)).filter(FileVersion.is_high_priority == True).scalar() or 0
        cached_count: int = self.db.query(func.count(FileVersion.id)).filter(FileVersion.was_cached == True).scalar() or 0
        
        # Count blobs
        total_blobs: int = self.db.query(func.count(VersionBlob.id)).scalar() or 0
        unique_blobs: int = self.db.query(func.count(VersionBlob.id)).filter(VersionBlob.reference_count > 0).scalar() or 0
        
        # Calculate savings
        compression_savings: int = total_size - total_compressed
        
        # Use SQL update to avoid Column assignment issues
        self.db.execute(
            update(VCLStats).
            where(VCLStats.id == 1).
            values(
                total_versions=total_versions,
                total_size_bytes=total_size,
                total_compressed_bytes=total_compressed,
                priority_count=priority_count,
                cached_versions_count=cached_count,
                total_blobs=total_blobs,
                unique_blobs=unique_blobs,
                compression_savings_bytes=compression_savings
            )
        )
        self.db.flush()
        
        # Already set in values above - no need for separate assignment
        
        # Deduplication savings: sum of (original_size * (reference_count - 1))
        dedup_savings: int = self.db.query(
            func.sum(VersionBlob.original_size * (VersionBlob.reference_count - 1))
        ).filter(VersionBlob.reference_count > 1).scalar() or 0
        
        # Update dedup savings
        self.db.execute(
            update(VCLStats).
            where(VCLStats.id == 1).
            values(deduplication_savings_bytes=dedup_savings)
        )
        self.db.flush()
    
    # ========== Utility Methods ==========
    
    def get_file_versions(
        self,
        file_id: int,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[FileVersion]:
        """Get all versions of a file."""
        query = self.db.query(FileVersion).filter(
            FileVersion.file_id == file_id
        ).order_by(FileVersion.version_number.desc())
        
        if limit:
            query = query.limit(limit).offset(offset)
        
        return query.all()
    
    def get_user_versions(
        self,
        user_id: int,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[FileVersion]:
        """Get all versions owned by user."""
        query = self.db.query(FileVersion).filter(
            FileVersion.user_id == user_id
        ).order_by(FileVersion.created_at.desc())
        
        if limit:
            query = query.limit(limit).offset(offset)
        
        return query.all()
