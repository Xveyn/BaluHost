"""Service for handling progressive/chunked syncs."""

import hashlib
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timedelta
from typing import Optional, BinaryIO
from sqlalchemy.orm import Session

from app.models.sync_progress import ChunkedUpload, SyncBandwidthLimit, SyncSchedule, SelectiveSync
from app.models.file_metadata import FileMetadata
from app.core.config import settings


class ProgressiveSyncService:
    """Handle chunked uploads, resumable transfers, and bandwidth throttling."""
    
    def __init__(self, db: Session):
        self.db = db
        self.storage_path = Path(settings.nas_storage_path)
        self.chunk_cleanup_days = 7
    
    def start_chunked_upload(
        self,
        user_id: int,
        device_id: str,
        file_path: str,
        file_name: str,
        total_size: int,
        chunk_size: int = 5 * 1024 * 1024
    ) -> dict:
        """
        Start a chunked upload session.
        
        Returns: upload_id, chunk_size, total_chunks, resume_token
        """
        upload_id = str(uuid4())
        total_chunks = (total_size + chunk_size - 1) // chunk_size
        
        # Create file metadata entry if not exists
        file_metadata = self.db.query(FileMetadata).filter(
            FileMetadata.path == file_path,
            FileMetadata.owner_id == user_id
        ).first()
        
        if not file_metadata:
            file_metadata = FileMetadata(
                path=file_path,
                name=file_name,
                owner_id=user_id,
                parent_path=str(Path(file_path).parent) if str(Path(file_path).parent) != "." else None,
                size_bytes=total_size,
                is_directory=False,
                mime_type="application/octet-stream"
            )
            self.db.add(file_metadata)
            self.db.flush()
        
        # Create upload session
        expires_at = datetime.utcnow() + timedelta(days=self.chunk_cleanup_days)
        upload = ChunkedUpload(
            upload_id=upload_id,
            file_metadata_id=file_metadata.id,
            user_id=user_id,
            device_id=device_id,
            file_name=file_name,
            file_path=file_path,
            total_size=total_size,
            chunk_size=chunk_size,
            total_chunks=total_chunks,
            expires_at=expires_at
        )
        self.db.add(upload)
        self.db.commit()
        
        return {
            "upload_id": upload_id,
            "chunk_size": chunk_size,
            "total_chunks": total_chunks,
            "resume_token": upload_id
        }
    
    def upload_chunk(
        self,
        upload_id: str,
        chunk_number: int,
        chunk_data: bytes,
        chunk_hash: str
    ) -> dict:
        """
        Upload a single chunk.
        
        chunk_hash: SHA256 of chunk for integrity check
        """
        upload = self.db.query(ChunkedUpload).filter(
            ChunkedUpload.upload_id == upload_id
        ).first()
        
        if not upload:
            return {"error": "Upload session not found"}
        
        if upload.is_completed:
            return {"error": "Upload already completed"}
        
        # Verify chunk integrity
        actual_hash = hashlib.sha256(chunk_data).hexdigest()
        if actual_hash != chunk_hash:
            return {"error": "Chunk integrity check failed"}
        
        # Save chunk
        chunk_dir = self.storage_path / ".chunks" / upload_id
        chunk_dir.mkdir(parents=True, exist_ok=True)
        chunk_file = chunk_dir / f"chunk_{chunk_number:06d}"
        
        chunk_file.write_bytes(chunk_data)
        
        # Update upload progress
        upload.completed_chunks += 1
        upload.uploaded_bytes += len(chunk_data)
        # updated_at is set automatically by onupdate
        
        # Check if upload complete
        if upload.completed_chunks == upload.total_chunks:
            upload.is_completed = True
            self._finalize_chunked_upload(upload)
        
        self.db.commit()
        
        return {
            "chunk_number": chunk_number,
            "completed_chunks": upload.completed_chunks,
            "total_chunks": upload.total_chunks,
            "progress_percent": (upload.completed_chunks / upload.total_chunks) * 100
        }
    
    def get_upload_progress(self, upload_id: str) -> Optional[dict]:
        """Get current progress of a chunked upload."""
        upload = self.db.query(ChunkedUpload).filter(
            ChunkedUpload.upload_id == upload_id
        ).first()
        
        if not upload:
            return None
        
        return {
            "upload_id": upload_id,
            "completed_chunks": upload.completed_chunks,
            "total_chunks": upload.total_chunks,
            "uploaded_bytes": upload.uploaded_bytes,
            "total_size": upload.total_size,
            "progress_percent": (upload.completed_chunks / upload.total_chunks) * 100,
            "is_completed": upload.is_completed,
            "updated_at": upload.updated_at.isoformat()
        }
    
    def resume_upload(self, upload_id: str) -> dict:
        """Resume a paused upload."""
        upload = self.db.query(ChunkedUpload).filter(
            ChunkedUpload.upload_id == upload_id
        ).first()
        
        if not upload:
            return {"error": "Upload not found"}
        
        if upload.is_completed:
            return {"error": "Upload already completed"}
        
        return {
            "upload_id": upload_id,
            "resume_from_chunk": upload.completed_chunks,
            "chunk_size": upload.chunk_size,
            "total_chunks": upload.total_chunks
        }
    
    def cancel_upload(self, upload_id: str) -> bool:
        """Cancel and cleanup an upload."""
        upload = self.db.query(ChunkedUpload).filter(
            ChunkedUpload.upload_id == upload_id
        ).first()
        
        if not upload:
            return False
        
        # Cleanup chunks
        chunk_dir = self.storage_path / ".chunks" / upload_id
        if chunk_dir.exists():
            import shutil
            shutil.rmtree(chunk_dir)
        
        self.db.delete(upload)
        self.db.commit()
        return True
    
    def set_bandwidth_limit(
        self,
        user_id: int,
        upload_speed_limit: Optional[int] = None,
        download_speed_limit: Optional[int] = None
    ) -> bool:
        """Set bandwidth limits (bytes/sec)."""
        limit = self.db.query(SyncBandwidthLimit).filter(
            SyncBandwidthLimit.user_id == user_id
        ).first()
        
        if not limit:
            limit = SyncBandwidthLimit(user_id=user_id)
            self.db.add(limit)
        
        limit.upload_speed_limit = upload_speed_limit
        limit.download_speed_limit = download_speed_limit
        self.db.commit()
        return True
    
    def get_bandwidth_limit(self, user_id: int) -> Optional[dict]:
        """Get user's bandwidth limits."""
        limit = self.db.query(SyncBandwidthLimit).filter(
            SyncBandwidthLimit.user_id == user_id
        ).first()
        
        if not limit:
            return None
        
        return {
            "upload_speed_limit": limit.upload_speed_limit,
            "download_speed_limit": limit.download_speed_limit,
            "throttle_enabled": limit.throttle_enabled,
            "throttle_start_hour": limit.throttle_start_hour,
            "throttle_end_hour": limit.throttle_end_hour
        }
    
    def _finalize_chunked_upload(self, upload: ChunkedUpload):
        """Assemble chunks into final file."""
        chunk_dir = self.storage_path / ".chunks" / upload.upload_id
        output_path = self.storage_path / upload.file_path.lstrip("/")
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "wb") as final_file:
            for i in range(upload.total_chunks):
                chunk_file = chunk_dir / f"chunk_{i:06d}"
                if chunk_file.exists():
                    final_file.write(chunk_file.read_bytes())
        
        # Update file metadata
        file_metadata = self.db.query(FileMetadata).filter(
            FileMetadata.id == upload.file_metadata_id
        ).first()
        
        if file_metadata:
            file_metadata.size_bytes = upload.total_size
            # updated_at is set automatically by onupdate
    
    def cleanup_expired_uploads(self):
        """Clean up old incomplete uploads."""
        now = datetime.utcnow()
        expired = self.db.query(ChunkedUpload).filter(
            ChunkedUpload.expires_at < now,
            ChunkedUpload.is_completed == False
        ).all()
        
        for upload in expired:
            self.cancel_upload(upload.upload_id)
