"""Sync bandwidth limits, plus cleanup of leftover progressive-upload rows.

The progressive (chunked) upload feature itself was removed in #632: its
routes had no client, no ownership check and no destination-path validation.
Chunked uploads go through /api/files (routes/chunked_upload.py). What is
left here is the bandwidth-limit API and the expiry cleanup, which still
clears rows and .chunks/ directories created before the removal.
"""

from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.models.sync_progress import ChunkedUpload, SyncBandwidthLimit
from app.core.config import settings


class ProgressiveSyncService:
    """Bandwidth limits and leftover chunked-upload cleanup."""
    
    def __init__(self, db: Session):
        self.db = db
        self.storage_path = Path(settings.nas_storage_path)
    
    def _delete_upload(self, upload_id: str) -> bool:
        """Delete a leftover upload row and its chunk directory.

        Private on purpose: only the expiry cleanup calls it. The public
        route that used to (DELETE /sync/upload/{id}) had no ownership check.
        """
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
    
    def cleanup_expired_uploads(self):
        """Delete expired, incomplete uploads (driven by the upload_cleanup job)."""
        now = datetime.now(timezone.utc)
        expired = self.db.query(ChunkedUpload).filter(
            ChunkedUpload.expires_at < now,
            ChunkedUpload.is_completed == False
        ).all()
        
        for upload in expired:
            self._delete_upload(upload.upload_id)
