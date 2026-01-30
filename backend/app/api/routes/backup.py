"""Backup API routes."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.power_rating import requires_power
from app.schemas.power import ServicePowerProperty
from app.schemas.user import UserPublic
from app.schemas.backup import (
    BackupCreate,
    BackupResponse,
    BackupListResponse,
    BackupRestoreRequest,
    BackupRestoreResponse
)
from app.services.backup import get_backup_service, BackupService


router = APIRouter()


@router.post("/", response_model=BackupResponse, status_code=status.HTTP_201_CREATED)
@requires_power(ServicePowerProperty.SURGE, timeout_seconds=3600, description="Creating system backup")
async def create_backup(
    backup_data: BackupCreate,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Create a new system backup (Admin only).

    This will create a compressed archive containing:
    - Database (if includes_database=True)
    - Files (if includes_files=True)
    - Configuration (if includes_config=True)

    The backup process may take several minutes depending on data size.
    """
    service = get_backup_service(db)
    
    try:
        backup = service.create_backup(
            backup_data=backup_data,
            creator_id=current_user.id,
            creator_username=current_user.username
        )
        return BackupResponse.from_db(backup)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create backup: {str(e)}"
        )


@router.get("/", response_model=BackupListResponse)
async def list_backups(
    _: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db)
):
    """
    List all backups (Admin only).
    
    Returns backups ordered by creation date (newest first).
    """
    service = get_backup_service(db)
    backups = service.list_backups()
    
    total_size = sum(b.size_bytes for b in backups)
    
    return BackupListResponse(
        backups=[BackupResponse.from_db(b) for b in backups],
        total_size_bytes=total_size,
        total_size_mb=round(total_size / (1024 * 1024), 2)
    )


@router.get("/{backup_id}", response_model=BackupResponse)
async def get_backup(
    backup_id: int,
    _: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db)
):
    """Get backup details by ID (Admin only)."""
    service = get_backup_service(db)
    backup = service.get_backup_by_id(backup_id)
    
    if not backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup not found"
        )
    
    return BackupResponse.from_db(backup)


@router.delete("/{backup_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_backup(
    backup_id: int,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Delete a backup by ID (Admin only).
    
    This will remove both the database record and the backup file.
    """
    service = get_backup_service(db)
    success = service.delete_backup(backup_id, current_user.username)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup not found"
        )
    
    return None


@router.post("/{backup_id}/restore", response_model=BackupRestoreResponse)
@requires_power(ServicePowerProperty.SURGE, timeout_seconds=3600, description="Restoring from backup")
async def restore_backup(
    backup_id: int,
    restore_request: BackupRestoreRequest,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Restore system from a backup (Admin only).

    ⚠️ WARNING: This will overwrite current data!

    - Database will be replaced if restore_database=True
    - Files will be replaced if restore_files=True
    - Config will be replaced if restore_config=True

    The confirmation flag must be set to true to proceed.
    """
    if not restore_request.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Restore operation must be confirmed (confirm=true)"
        )
    
    if restore_request.backup_id != backup_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Backup ID mismatch"
        )
    
    service = get_backup_service(db)
    
    try:
        success = service.restore_backup(
            backup_id=backup_id,
            user=current_user.username,
            restore_database=restore_request.restore_database,
            restore_files=restore_request.restore_files,
            restore_config=restore_request.restore_config
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Backup not found or invalid"
            )
        
        from datetime import datetime
        return BackupRestoreResponse(
            success=True,
            message="Backup restored successfully. Please restart the application.",
            backup_id=backup_id,
            restored_at=datetime.now()
        )
        
    except Exception as e:
        # If the service raised a RestoreLockedError, return 423 Locked with helpful message
        from app.services.backup import RestoreLockedError
        if isinstance(e, RestoreLockedError):
            raise HTTPException(
                status_code=423,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to restore backup: {str(e)}"
        )


@router.get("/{backup_id}/download")
async def download_backup(
    backup_id: int,
    _: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Download a backup file (Admin only).
    
    Returns the backup as a tar.gz file for download.
    """
    service = get_backup_service(db)
    filepath = service.download_backup(backup_id)
    
    if not filepath:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup not found or not available for download"
        )
    
    return FileResponse(
        path=str(filepath),
        filename=filepath.name,
        media_type="application/gzip"
    )
