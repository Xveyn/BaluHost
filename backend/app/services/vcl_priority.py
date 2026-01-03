"""VCL Priority Mode - Intelligent storage cleanup.

Implements automatic cleanup when storage quota is exceeded,
prioritizing deletion of low-priority, old versions while
preserving high-priority and recent versions.
"""
from typing import List, Tuple, Optional, TYPE_CHECKING
from datetime import datetime, timedelta
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.models.vcl import FileVersion, VersionBlob, VCLSettings, VCLStats
    from app.services.vcl import VCLService
else:
    from app.models.vcl import FileVersion, VersionBlob, VCLSettings, VCLStats
    from app.services.vcl import VCLService


class VCLPriorityMode:
    """
    Priority Mode cleanup algorithm.
    
    Triggered when: current_usage >= (max_size - headroom)
    
    Cleanup strategy:
    1. Never delete last version of a file
    2. Never delete high-priority versions (unless force_all=True)
    3. Delete oldest low-priority versions first (LRU)
    4. Delete orphaned blobs (reference_count = 0)
    5. Stop when: usage < (max_size - headroom)
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.vcl_service = VCLService(db)
    
    def needs_cleanup(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        Check if user needs cleanup.
        
        Args:
            user_id: User ID
            
        Returns:
            Tuple of (needs_cleanup, reason)
        """
        settings = self.vcl_service.get_user_settings(user_id)
        
        # Cast Column to bool for conditional
        is_enabled: bool = bool(settings.is_enabled)  # type: ignore
        if not is_enabled:
            return False, "VCL disabled"
        
        # Cast Columns to int for comparison
        current_usage: int = int(settings.current_usage_bytes)  # type: ignore
        max_size: int = int(settings.max_size_bytes)  # type: ignore
        headroom: int = int(settings.headroom_bytes)  # type: ignore
        
        is_over: bool = bool(settings.is_over_headroom)  # type: ignore
        if is_over:
            bytes_over = current_usage - (max_size - headroom)
            return True, f"Over headroom by {bytes_over} bytes"
        
        return False, None
    
    def calculate_target_reduction(self, user_id: int) -> int:
        """
        Calculate how many bytes need to be freed.
        
        Args:
            user_id: User ID
            
        Returns:
            Bytes to free
        """
        settings = self.vcl_service.get_user_settings(user_id)
        
        # Cast Columns to int for arithmetic
        max_size: int = int(settings.max_size_bytes)  # type: ignore
        headroom: int = int(settings.headroom_bytes)  # type: ignore
        current_usage: int = int(settings.current_usage_bytes)  # type: ignore
        
        # Target: max_size - headroom
        target_usage = max_size - headroom
        
        if current_usage <= target_usage:
            return 0
        
        bytes_to_free = current_usage - target_usage
        
        # Add 10% buffer to avoid immediate re-triggering
        return int(bytes_to_free * 1.1)
    
    def get_deletable_versions(
        self,
        user_id: int,
        include_high_priority: bool = False,
        min_age_hours: int = 0
    ) -> List[FileVersion]:
        """
        Get list of versions that can be deleted, ordered by priority.
        
        Deletion priority (lowest first):
        1. Low priority, oldest first
        2. High priority (only if include_high_priority=True)
        3. Never: Last version of any file
        
        Args:
            user_id: User ID
            include_high_priority: Include high-priority versions
            min_age_hours: Minimum age in hours
            
        Returns:
            List of deletable FileVersions, ordered by deletion priority
        """
        # Subquery: Get last version ID for each file
        last_version_subquery = (
            self.db.query(
                FileVersion.file_id,
                func.max(FileVersion.version_number).label('max_version')
            )
            .filter(FileVersion.user_id == user_id)
            .group_by(FileVersion.file_id)
            .subquery()
        )
        
        # Main query: Get deletable versions
        query = self.db.query(FileVersion).join(
            last_version_subquery,
            and_(
                FileVersion.file_id == last_version_subquery.c.file_id,
                FileVersion.version_number < last_version_subquery.c.max_version  # Not last version
            )
        ).filter(
            FileVersion.user_id == user_id
        )
        
        # Filter by priority
        if not include_high_priority:
            query = query.filter(FileVersion.is_high_priority == False)
        
        # Filter by age
        if min_age_hours > 0:
            cutoff_date = datetime.utcnow() - timedelta(hours=min_age_hours)
            query = query.filter(FileVersion.created_at < cutoff_date)
        
        # Order by deletion priority
        query = query.order_by(
            FileVersion.is_high_priority.asc(),  # Low priority first
            FileVersion.created_at.asc()          # Oldest first
        )
        
        return query.all()
    
    def cleanup_user_versions(
        self,
        user_id: int,
        target_bytes: Optional[int] = None,
        dry_run: bool = False,
        force_high_priority: bool = False
    ) -> dict:
        """
        Clean up user's versions to free storage.
        
        Args:
            user_id: User ID
            target_bytes: Target bytes to free (auto-calculated if None)
            dry_run: Simulate without actual deletion
            force_high_priority: Allow deletion of high-priority versions
            
        Returns:
            Dict with cleanup results
        """
        if target_bytes is None:
            target_bytes = self.calculate_target_reduction(user_id)
        
        if target_bytes <= 0:
            return {
                'needed_cleanup': False,
                'target_bytes': 0,
                'deleted_versions': 0,
                'freed_bytes': 0,
                'deleted_blobs': 0
            }
        
        # Get deletable versions
        deletable_versions = self.get_deletable_versions(
            user_id,
            include_high_priority=force_high_priority
        )
        
        deleted_versions = []
        freed_bytes = 0
        deleted_blobs = 0
        
        for version in deletable_versions:
            if freed_bytes >= target_bytes:
                break  # Target reached
            
            # Cast Column to int for size calculation
            version_size: int = int(version.compressed_size)  # type: ignore
            
            if not dry_run:
                # Actually delete
                freed = self.vcl_service.delete_version(version)
                if freed > 0:
                    deleted_blobs += 1
            else:
                # Simulate - check storage type
                storage_type: str = str(version.storage_type)  # type: ignore
                freed = version_size if storage_type == 'stored' else 0
            
            deleted_versions.append({
                'id': version.id,
                'file_id': version.file_id,
                'version_number': version.version_number,
                'size': version_size,
                'is_high_priority': version.is_high_priority,
                'created_at': version.created_at.isoformat()
            })
            
            freed_bytes += freed
        
        if not dry_run:
            self.db.commit()
            
            # Update stats - use SQL update
            from sqlalchemy import update
            self.db.execute(
                update(VCLStats).
                where(VCLStats.id == 1).
                values(last_priority_mode_at=datetime.utcnow())
            )
            self.db.commit()
        
        return {
            'needed_cleanup': True,
            'target_bytes': target_bytes,
            'deleted_versions': len(deleted_versions),
            'freed_bytes': freed_bytes,
            'deleted_blobs': deleted_blobs,
            'dry_run': dry_run,
            'versions_deleted': deleted_versions if dry_run else []
        }
    
    def cleanup_orphaned_blobs(self, dry_run: bool = False) -> dict:
        """
        Delete blobs with reference_count = 0.
        
        Args:
            dry_run: Simulate without actual deletion
            
        Returns:
            Dict with cleanup results
        """
        # Find orphaned blobs
        orphaned_blobs = self.db.query(VersionBlob).filter(
            or_(
                VersionBlob.reference_count == 0,
                VersionBlob.can_delete == True
            )
        ).all()
        
        deleted_blobs = []
        freed_bytes = 0
        
        for blob in orphaned_blobs:
            blob_size = blob.compressed_size
            
            if not dry_run:
                try:
                    self.vcl_service.delete_blob(blob)
                    deleted_blobs.append({
                        'id': blob.id,
                        'checksum': blob.checksum[:16] + '...',
                        'size': blob_size
                    })
                    freed_bytes += blob_size
                except Exception as e:
                    print(f"⚠️ Failed to delete blob {blob.id}: {e}")
            else:
                deleted_blobs.append({
                    'id': blob.id,
                    'checksum': blob.checksum[:16] + '...',
                    'size': blob_size
                })
                freed_bytes += blob_size
        
        if not dry_run and deleted_blobs:
            self.db.commit()
            
            # Stats are auto-updated by triggers
        
        return {
            'deleted_blobs': len(deleted_blobs),
            'freed_bytes': freed_bytes,
            'dry_run': dry_run,
            'blobs_deleted': deleted_blobs if dry_run else []
        }
    
    def enforce_depth_limit(self, user_id: int, dry_run: bool = False) -> dict:
        """
        Enforce max version depth per file.
        
        Deletes oldest versions exceeding the depth limit.
        
        Args:
            user_id: User ID
            dry_run: Simulate without actual deletion
            
        Returns:
            Dict with cleanup results
        """
        settings = self.vcl_service.get_user_settings(user_id)
        max_depth = settings.depth
        
        # Get all files with versions exceeding depth
        file_version_counts = (
            self.db.query(
                FileVersion.file_id,
                func.count(FileVersion.id).label('version_count')
            )
            .filter(FileVersion.user_id == user_id)
            .group_by(FileVersion.file_id)
            .having(func.count(FileVersion.id) > max_depth)
            .all()
        )
        
        deleted_versions = []
        freed_bytes = 0
        deleted_blobs = 0
        
        for file_id, version_count in file_version_counts:
            # How many to delete
            to_delete_count = version_count - max_depth
            
            # Get oldest versions (excluding high priority)
            versions_to_delete = (
                self.db.query(FileVersion)
                .filter(
                    FileVersion.file_id == file_id,
                    FileVersion.user_id == user_id,
                    FileVersion.is_high_priority == False
                )
                .order_by(FileVersion.version_number.asc())
                .limit(to_delete_count)
                .all()
            )
            
            for version in versions_to_delete:
                if not dry_run:
                    freed = self.vcl_service.delete_version(version)
                    if freed > 0:
                        deleted_blobs += 1
                    freed_bytes += freed
                else:
                    # Cast Columns for dry_run simulation
                    vers_comp_size: int = int(version.compressed_size)  # type: ignore
                    vers_storage_type: str = str(version.storage_type)  # type: ignore
                    freed_bytes += vers_comp_size if vers_storage_type == 'stored' else 0
                
                # Cast Columns for result dict
                vers_file_id: int = int(version.file_id)  # type: ignore
                vers_version_num: int = int(version.version_number)  # type: ignore
                vers_comp_size_dict: int = int(version.compressed_size)  # type: ignore
                
                deleted_versions.append({
                    'file_id': vers_file_id,
                    'version_number': vers_version_num,
                    'size': vers_comp_size_dict
                })
        
        if not dry_run and deleted_versions:
            self.db.commit()
        
        return {
            'max_depth': max_depth,
            'files_processed': len(file_version_counts),
            'deleted_versions': len(deleted_versions),
            'freed_bytes': freed_bytes,
            'deleted_blobs': deleted_blobs,
            'dry_run': dry_run
        }
    
    def auto_cleanup(self, user_id: int, dry_run: bool = False) -> dict:
        """
        Automatic cleanup workflow.
        
        1. Check if cleanup needed
        2. Enforce depth limit
        3. Clean up to free storage
        4. Clean up orphaned blobs
        
        Args:
            user_id: User ID
            dry_run: Simulate without actual deletion
            
        Returns:
            Dict with all cleanup results
        """
        results = {
            'started_at': datetime.utcnow().isoformat(),
            'user_id': user_id,
            'dry_run': dry_run
        }
        
        # 1. Check if needed
        needs_cleanup, reason = self.needs_cleanup(user_id)
        results['needs_cleanup'] = needs_cleanup
        results['reason'] = reason
        
        if not needs_cleanup:
            return results
        
        # 2. Enforce depth limit
        depth_results = self.enforce_depth_limit(user_id, dry_run)
        results['depth_enforcement'] = depth_results
        
        # 3. Priority mode cleanup
        cleanup_results = self.cleanup_user_versions(user_id, dry_run=dry_run)
        results['priority_cleanup'] = cleanup_results
        
        # 4. Orphaned blobs
        blob_results = self.cleanup_orphaned_blobs(dry_run)
        results['blob_cleanup'] = blob_results
        
        # Summary
        results['total_freed_bytes'] = (
            depth_results['freed_bytes'] +
            cleanup_results['freed_bytes'] +
            blob_results['freed_bytes']
        )
        results['total_deleted_versions'] = (
            depth_results['deleted_versions'] +
            cleanup_results['deleted_versions']
        )
        results['total_deleted_blobs'] = (
            depth_results['deleted_blobs'] +
            cleanup_results['deleted_blobs'] +
            blob_results['deleted_blobs']
        )
        
        results['completed_at'] = datetime.utcnow().isoformat()
        
        return results
    
    def global_cleanup(
        self,
        dry_run: bool = False,
        min_age_hours: int = 24
    ) -> dict:
        """
        Global cleanup across all users.
        
        Args:
            dry_run: Simulate without actual deletion
            min_age_hours: Minimum version age in hours
            
        Returns:
            Dict with cleanup results per user
        """
        # Get all users with VCL usage
        users_with_versions = (
            self.db.query(FileVersion.user_id)
            .distinct()
            .all()
        )
        
        results = {
            'started_at': datetime.utcnow().isoformat(),
            'dry_run': dry_run,
            'users_processed': 0,
            'total_freed_bytes': 0,
            'total_deleted_versions': 0,
            'total_deleted_blobs': 0,
            'per_user_results': []
        }
        
        for (user_id,) in users_with_versions:
            user_results = self.auto_cleanup(user_id, dry_run)
            
            if user_results.get('needs_cleanup'):
                results['users_processed'] += 1
                results['total_freed_bytes'] += user_results.get('total_freed_bytes', 0)
                results['total_deleted_versions'] += user_results.get('total_deleted_versions', 0)
                results['total_deleted_blobs'] += user_results.get('total_deleted_blobs', 0)
                results['per_user_results'].append(user_results)
        
        # Global orphaned blob cleanup
        blob_cleanup = self.cleanup_orphaned_blobs(dry_run)
        results['global_blob_cleanup'] = blob_cleanup
        results['total_freed_bytes'] += blob_cleanup['freed_bytes']
        results['total_deleted_blobs'] += blob_cleanup['deleted_blobs']
        
        results['completed_at'] = datetime.utcnow().isoformat()
        
        return results


# ========== Monitoring & Alerts ==========

class VCLMonitor:
    """Monitor VCL storage and trigger alerts."""
    
    def __init__(self, db: Session):
        self.db = db
        self.vcl_service = VCLService(db)
    
    def check_user_quota_status(self, user_id: int) -> dict:
        """Get user's quota status."""
        settings = self.vcl_service.get_user_settings(user_id)
        
        usage_percent = settings.usage_percent
        
        # Determine status
        if usage_percent >= 95:
            status = 'critical'
        elif usage_percent >= 90:
            status = 'warning'
        elif settings.is_over_headroom:
            status = 'approaching_limit'
        else:
            status = 'ok'
        
        return {
            'user_id': user_id,
            'status': status,
            'current_usage_bytes': settings.current_usage_bytes,
            'max_size_bytes': settings.max_size_bytes,
            'usage_percent': usage_percent,
            'available_bytes': settings.available_bytes,
            'is_over_headroom': settings.is_over_headroom,
            'headroom_bytes': settings.headroom_bytes
        }
    
    def get_users_needing_cleanup(self) -> List[dict]:
        """Get list of users exceeding quota."""
        users_with_settings = self.db.query(VCLSettings).filter(
            VCLSettings.user_id.isnot(None)
        ).all()
        
        users_needing_cleanup = []
        
        for settings in users_with_settings:
            if settings.is_over_headroom:
                # Type cast Column to int for function call
                user_id: int = settings.user_id  # type: ignore
                status = self.check_user_quota_status(user_id)
                users_needing_cleanup.append(status)
        
        return users_needing_cleanup
