"""VCL Cache System for intelligent version batching.

Implements debouncing and batching to prevent excessive version creation
from rapid file changes (e.g., auto-save, save-on-type).
"""
import asyncio
import time
from typing import Dict, Optional, TYPE_CHECKING
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.services.vcl import VCLService
    from app.models.file_metadata import FileMetadata
else:
    from app.services.vcl import VCLService
    from app.models.file_metadata import FileMetadata


@dataclass
class PendingVersion:
    """Represents a pending version in cache."""
    content: bytes
    checksum: str
    user_id: int
    file: FileMetadata
    first_modified: float  # Unix timestamp
    last_modified: float   # Unix timestamp
    is_high_priority: bool = False
    comment: Optional[str] = None


class VCLCache:
    """
    Intelligent caching system for VCL.
    
    Strategy:
    - Collect rapid changes for debounce_window seconds
    - Flush only final version after inactivity
    - Hard limit at max_batch_window to prevent data loss
    - Force flush on critical events (logout, shutdown)
    """
    
    # Class-level cache (singleton pattern)
    _pending_changes: Dict[int, PendingVersion] = {}
    _flush_tasks: Dict[int, asyncio.Task] = {}
    _lock = asyncio.Lock()
    
    # Default configuration (can be overridden per-user from settings)
    DEFAULT_DEBOUNCE_WINDOW = 30  # seconds
    DEFAULT_MAX_BATCH_WINDOW = 300  # 5 minutes
    
    @classmethod
    async def queue_version(
        cls,
        db: Session,
        file: FileMetadata,
        content: bytes,
        checksum: str,
        user_id: int,
        is_high_priority: bool = False,
        comment: Optional[str] = None,
        debounce_window: Optional[int] = None,
        max_batch_window: Optional[int] = None
    ):
        """
        Queue a potential version for batching.
        
        Args:
            db: Database session
            file: File metadata
            content: File content
            checksum: SHA256 checksum
            user_id: User ID
            is_high_priority: High priority flag
            comment: Optional comment
            debounce_window: Custom debounce window (seconds)
            max_batch_window: Custom max batch window (seconds)
        """
        async with cls._lock:
            now = time.time()
            file_id = file.id
            
            # Get user settings if not provided
            if debounce_window is None or max_batch_window is None:
                vcl_service = VCLService(db)
                settings = vcl_service.get_user_settings(user_id)
                # Cast to int - settings returns model with Column descriptors
                debounce_val: int = int(settings.debounce_window_seconds)  # type: ignore
                batch_val: int = int(settings.max_batch_window_seconds)  # type: ignore
                debounce_window = debounce_window or debounce_val
                max_batch_window = max_batch_window or batch_val
            
            if file_id in cls._pending_changes:
                # Update existing pending change
                pending = cls._pending_changes[file_id]
                pending.content = content
                pending.checksum = checksum
                pending.last_modified = now
                pending.is_high_priority = is_high_priority or pending.is_high_priority
                pending.comment = comment or pending.comment
                
                # Check hard limit
                time_in_cache = now - pending.first_modified
                if time_in_cache >= max_batch_window:
                    # Force flush immediately
                    await cls._flush_version_internal(db, file_id)
                    return
                
                # Cancel existing flush task
                if file_id in cls._flush_tasks and not cls._flush_tasks[file_id].done():
                    cls._flush_tasks[file_id].cancel()
            else:
                # New pending change
                cls._pending_changes[file_id] = PendingVersion(
                    content=content,
                    checksum=checksum,
                    user_id=user_id,
                    file=file,
                    first_modified=now,
                    last_modified=now,
                    is_high_priority=is_high_priority,
                    comment=comment
                )
            
            # Schedule debounced flush
            task = asyncio.create_task(
                cls._debounced_flush(db, file_id, debounce_window)
            )
            cls._flush_tasks[file_id] = task
    
    @classmethod
    async def _debounced_flush(cls, db: Session, file_id: int, debounce_window: int):
        """
        Wait for inactivity, then flush.
        
        Args:
            db: Database session
            file_id: File ID
            debounce_window: Seconds to wait for inactivity
        """
        try:
            await asyncio.sleep(debounce_window)
            
            async with cls._lock:
                if file_id not in cls._pending_changes:
                    return  # Already flushed
                
                pending = cls._pending_changes[file_id]
                
                # Check if there was recent activity
                time_since_last_change = time.time() - pending.last_modified
                
                if time_since_last_change >= debounce_window:
                    # Inactive long enough, flush now
                    await cls._flush_version_internal(db, file_id)
                else:
                    # More changes came in, reschedule
                    remaining_wait = debounce_window - time_since_last_change
                    task = asyncio.create_task(
                        cls._debounced_flush(db, file_id, int(remaining_wait) + 1)
                    )
                    cls._flush_tasks[file_id] = task
        
        except asyncio.CancelledError:
            # Task was cancelled (new change came in)
            pass
    
    @classmethod
    async def _flush_version_internal(cls, db: Session, file_id: int):
        """
        Internal method to flush a pending version.
        Must be called with lock held.
        
        Args:
            db: Database session
            file_id: File ID to flush
        """
        if file_id not in cls._pending_changes:
            return
        
        pending = cls._pending_changes.pop(file_id)
        
        # Clean up flush task
        if file_id in cls._flush_tasks:
            cls._flush_tasks.pop(file_id)
        
        # Calculate cache duration
        cache_duration = int(time.time() - pending.first_modified)
        
        # Create version
        vcl_service = VCLService(db)
        
        try:
            version = vcl_service.create_version(
                file=pending.file,
                content=pending.content,
                user_id=pending.user_id,
                checksum=pending.checksum,
                is_high_priority=pending.is_high_priority,
                change_type='batched',
                comment=pending.comment,
                was_cached=True,
                cache_duration=cache_duration
            )
            db.commit()
            
            print(f"✅ VCL: Flushed cached version for file {file_id} "
                  f"(cached for {cache_duration}s)")
        
        except Exception as e:
            db.rollback()
            print(f"❌ VCL Cache: Failed to flush version for file {file_id}: {e}")
            raise
    
    @classmethod
    async def flush_version(cls, db: Session, file_id: int):
        """
        Force flush a specific file's pending version.
        
        Args:
            db: Database session
            file_id: File ID to flush
        """
        async with cls._lock:
            await cls._flush_version_internal(db, file_id)
    
    @classmethod
    async def flush_all(cls, db: Session):
        """
        Force flush all pending versions.
        
        Use on:
        - System shutdown
        - User logout
        - Manual save request
        
        Args:
            db: Database session
        """
        async with cls._lock:
            file_ids = list(cls._pending_changes.keys())
            
            for file_id in file_ids:
                try:
                    await cls._flush_version_internal(db, file_id)
                except Exception as e:
                    print(f"⚠️ VCL Cache: Error flushing file {file_id}: {e}")
            
            print(f"✅ VCL Cache: Flushed {len(file_ids)} pending versions")
    
    @classmethod
    async def flush_user_versions(cls, db: Session, user_id: int):
        """
        Force flush all pending versions for a specific user.
        
        Use on user logout.
        
        Args:
            db: Database session
            user_id: User ID
        """
        async with cls._lock:
            file_ids_to_flush = [
                file_id
                for file_id, pending in cls._pending_changes.items()
                if pending.user_id == user_id
            ]
            
            for file_id in file_ids_to_flush:
                try:
                    await cls._flush_version_internal(db, file_id)
                except Exception as e:
                    print(f"⚠️ VCL Cache: Error flushing file {file_id}: {e}")
            
            if file_ids_to_flush:
                print(f"✅ VCL Cache: Flushed {len(file_ids_to_flush)} "
                      f"pending versions for user {user_id}")
    
    @classmethod
    def get_pending_count(cls) -> int:
        """Get number of pending versions in cache."""
        return len(cls._pending_changes)
    
    @classmethod
    def get_pending_for_file(cls, file_id: int) -> Optional[PendingVersion]:
        """Get pending version for a file."""
        return cls._pending_changes.get(file_id)
    
    @classmethod
    def has_pending(cls, file_id: int) -> bool:
        """Check if file has pending cached version."""
        return file_id in cls._pending_changes
    
    @classmethod
    def get_cache_info(cls) -> dict:
        """Get cache statistics."""
        now = time.time()
        
        if not cls._pending_changes:
            return {
                'pending_count': 0,
                'total_size_bytes': 0,
                'oldest_cache_seconds': 0,
                'pending_files': []
            }
        
        total_size = sum(len(p.content) for p in cls._pending_changes.values())
        oldest_cache = max(now - p.first_modified for p in cls._pending_changes.values())
        
        pending_files = [
            {
                'file_id': file_id,
                'user_id': pending.user_id,
                'cache_duration': int(now - pending.first_modified),
                'size_bytes': len(pending.content),
                'is_high_priority': pending.is_high_priority
            }
            for file_id, pending in cls._pending_changes.items()
        ]
        
        return {
            'pending_count': len(cls._pending_changes),
            'total_size_bytes': total_size,
            'oldest_cache_seconds': int(oldest_cache),
            'pending_files': pending_files
        }
    
    @classmethod
    async def clear_cache(cls):
        """
        Clear all pending versions without flushing.
        
        ⚠️ WARNING: This causes data loss! Only use for testing or emergency.
        """
        async with cls._lock:
            # Cancel all flush tasks
            for task in cls._flush_tasks.values():
                if not task.done():
                    task.cancel()
            
            cls._pending_changes.clear()
            cls._flush_tasks.clear()
            
            print("⚠️ VCL Cache: Cleared all pending versions (data lost)")


# ========== Synchronous Wrapper for Non-Async Contexts ==========

class VCLCacheSync:
    """Synchronous wrapper for VCLCache for use in non-async code."""
    
    @staticmethod
    def queue_version_sync(
        db: Session,
        file: FileMetadata,
        content: bytes,
        checksum: str,
        user_id: int,
        **kwargs
    ):
        """
        Queue version synchronously (creates event loop if needed).
        
        For use in synchronous endpoints or hooks.
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(
            VCLCache.queue_version(db, file, content, checksum, user_id, **kwargs)
        )
    
    @staticmethod
    def flush_all_sync(db: Session):
        """Flush all versions synchronously."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(VCLCache.flush_all(db))
    
    @staticmethod
    def flush_user_sync(db: Session, user_id: int):
        """Flush user versions synchronously."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(VCLCache.flush_user_versions(db, user_id))
