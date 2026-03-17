"""File sync service for local network synchronization."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models.sync_state import SyncState, SyncMetadata, SyncFileVersion
from app.models.file_metadata import FileMetadata
from app.core.config import settings


class FileSyncService:
    """Handle file synchronization, versioning, and conflict resolution."""
    
    def __init__(self, db: Session):
        self.db = db
        self.storage_path = Path(settings.nas_storage_path)
    
    def calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file for change detection."""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except FileNotFoundError:
            return ""
    
    def register_device(self, user_id: int, device_id: str, device_name: str) -> SyncState:
        """Register a new device for sync."""
        sync_state = self.db.query(SyncState).filter(
            SyncState.user_id == user_id,
            SyncState.device_id == device_id
        ).first()
        
        if sync_state:
            sync_state.device_name = device_name
            sync_state.last_sync = datetime.now(timezone.utc)
            self.db.commit()
            return sync_state
        
        sync_state = SyncState(
            user_id=user_id,
            device_id=device_id,
            device_name=device_name
        )
        self.db.add(sync_state)
        self.db.commit()
        self.db.refresh(sync_state)
        return sync_state
    
    def get_sync_status(self, user_id: int, device_id: str) -> dict:
        """Get sync status for a device."""
        sync_state = self.db.query(SyncState).filter(
            SyncState.user_id == user_id,
            SyncState.device_id == device_id
        ).first()
        
        if not sync_state:
            return {"status": "not_registered"}
        
        pending_changes = self.db.query(SyncMetadata).filter(
            SyncMetadata.sync_state_id == sync_state.id,
            SyncMetadata.conflict_detected == False
        ).count()
        
        conflicts = self.db.query(SyncMetadata).filter(
            SyncMetadata.sync_state_id == sync_state.id,
            SyncMetadata.conflict_detected == True
        ).count()
        
        return {
            "status": "synced",
            "device_id": device_id,
            "device_name": sync_state.device_name,
            "last_sync": sync_state.last_sync.isoformat(),
            "pending_changes": pending_changes,
            "conflicts": conflicts,
            "change_token": sync_state.last_change_token
        }
    
    def detect_changes(self, user_id: int, device_id: str, file_list: list[dict]) -> dict:
        """
        Detect changes on client side.
        
        file_list format:
        [
            {
                "path": "/folder/file.txt",
                "hash": "sha256hash",
                "size": 1024,
                "modified_at": "2025-01-01T12:00:00Z"
            }
        ]
        """
        sync_state = self.db.query(SyncState).filter(
            SyncState.user_id == user_id,
            SyncState.device_id == device_id
        ).first()
        
        if not sync_state:
            return {"error": "Device not registered"}
        
        changes = {
            "to_download": [],      # Files client needs to download
            "to_delete": [],        # Files client needs to delete
            "conflicts": [],        # Conflicting files
            "change_token": None
        }
        
        client_files = {f["path"]: f for f in file_list}
        server_files = {
            fm.path: fm for fm in self.db.query(FileMetadata).filter(
                FileMetadata.owner_id == user_id
            ).all()
        }
        
        # Check for server changes
        for path, file_metadata in server_files.items():
            if path not in client_files:
                changes["to_download"].append({
                    "path": path,
                    "action": "add" if not file_metadata.is_directory else "mkdir",
                    "size": file_metadata.size_bytes,
                    "modified_at": file_metadata.updated_at.isoformat() if file_metadata.updated_at else None
                })
        
        # Check for client changes and conflicts
        for path, client_file in client_files.items():
            if path not in server_files:
                # File deleted on server
                changes["to_delete"].append({"path": path})
            else:
                server_file = server_files[path]
                sync_meta = self.db.query(SyncMetadata).filter(
                    SyncMetadata.file_metadata_id == server_file.id,
                    SyncMetadata.sync_state_id == sync_state.id
                ).first()
                
                if sync_meta and sync_meta.content_hash != client_file.get("hash"):
                    client_modified = client_file.get("modified_at")
                    if client_modified and sync_meta.server_modified_at.isoformat() > client_modified:
                        changes["conflicts"].append({
                            "path": path,
                            "client_hash": client_file.get("hash"),
                            "server_hash": sync_meta.content_hash,
                            "server_modified_at": sync_meta.server_modified_at.isoformat()
                        })
        
        sync_state.last_sync = datetime.now(timezone.utc)
        sync_state.last_change_token = self._generate_change_token()
        self.db.commit()
        
        changes["change_token"] = sync_state.last_change_token
        return changes
    
    def resolve_conflict(self, user_id: int, file_path: str, resolution: str) -> bool:
        """
        Resolve a conflict.
        
        resolution: 'keep_local', 'keep_server', 'create_version'
        """
        file_metadata = self.db.query(FileMetadata).filter(
            FileMetadata.path == file_path,
            FileMetadata.owner_id == user_id
        ).first()
        
        if not file_metadata:
            return False
        
        sync_meta = self.db.query(SyncMetadata).filter(
            SyncMetadata.file_metadata_id == file_metadata.id
        ).first()
        
        if not sync_meta:
            return False
        
        if resolution == "create_version":
            self._create_file_version(file_metadata, sync_meta, "conflict")
        
        sync_meta.conflict_detected = False
        sync_meta.conflict_resolution = resolution
        self.db.commit()
        return True
    
    def _create_file_version(self, file_metadata: FileMetadata, sync_meta: SyncMetadata, reason: str):
        """Create a version entry for a file."""
        actual_path = self.storage_path / file_metadata.path.lstrip("/")
        
        if not actual_path.exists():
            return
        
        version_count = self.db.query(SyncFileVersion).filter(
            SyncFileVersion.file_metadata_id == file_metadata.id
        ).count()
        
        version = SyncFileVersion(
            file_metadata_id=file_metadata.id,
            version_number=version_count + 1,
            file_path=str(actual_path),
            file_size=file_metadata.size_bytes,
            content_hash=sync_meta.content_hash,
            created_by_id=file_metadata.owner_id,
            change_reason=reason
        )
        self.db.add(version)
        self.db.commit()
    
    def _generate_change_token(self) -> str:
        """Generate a unique change token for delta sync."""
        import uuid
        return str(uuid.uuid4())

    # ===== Helpers used by sync routes =====

    def validate_registration_token(self, token: str, user_id: int):
        """Validate a one-time registration token.

        Returns the token record on success.
        Raises ValueError with a descriptive message on failure.
        """
        from app.models.mobile import MobileRegistrationToken

        record = (
            self.db.query(MobileRegistrationToken)
            .filter(MobileRegistrationToken.token == token)
            .first()
        )
        if not record:
            raise ValueError("Invalid registration token")
        if record.used:
            raise ValueError("Registration token already used")
        if record.expires_at < datetime.now(timezone.utc):
            raise ValueError("Registration token expired")
        if str(record.user_id) != str(user_id):
            raise ValueError("Registration token does not belong to the current user")
        return record

    def consume_registration_token(self, record) -> None:
        """Mark a registration token as used."""
        record.used = True
        self.db.commit()

    def get_existing_device(self, device_id: str, user_id: int) -> Optional[SyncState]:
        """Check if a device is already registered for a user."""
        return (
            self.db.query(SyncState)
            .filter(SyncState.device_id == device_id, SyncState.user_id == user_id)
            .first()
        )

    def get_file_version_history(self, file_path: str, owner_id: int) -> Optional[dict]:
        """Get version history for a file. Returns None if file not found."""
        file_metadata = (
            self.db.query(FileMetadata)
            .filter(FileMetadata.path == file_path, FileMetadata.owner_id == owner_id)
            .first()
        )
        if not file_metadata:
            return None

        versions = (
            self.db.query(SyncFileVersion)
            .filter(SyncFileVersion.file_metadata_id == file_metadata.id)
            .order_by(SyncFileVersion.version_number.desc())
            .all()
        )
        return {
            "file_path": file_path,
            "versions": [
                {
                    "version_number": v.version_number,
                    "size": v.file_size,
                    "hash": v.content_hash,
                    "created_at": v.created_at.isoformat(),
                    "reason": v.change_reason,
                }
                for v in versions
            ],
        }

    def get_user_files(self, user_id: int) -> list[FileMetadata]:
        """Get all file metadata records for a user."""
        return self.db.query(FileMetadata).filter(FileMetadata.owner_id == user_id).all()

    def report_sync_folders(
        self, user_id: int, device_id: str, device_name: str, platform: str, folders: list
    ) -> tuple[int, int]:
        """Report active sync folders from a client. Returns (accepted, deactivated)."""
        from app.models.desktop_sync_folder import DesktopSyncFolder
        from sqlalchemy.sql import func

        now = func.now()
        reported_paths: set[str] = set()
        accepted = 0

        for folder in folders:
            reported_paths.add(folder.remote_path)
            existing = (
                self.db.query(DesktopSyncFolder)
                .filter(
                    DesktopSyncFolder.device_id == device_id,
                    DesktopSyncFolder.remote_path == folder.remote_path,
                )
                .first()
            )
            if existing:
                existing.device_name = device_name
                existing.platform = platform
                existing.sync_direction = folder.sync_direction
                existing.is_active = True
                existing.last_reported_at = now
                existing.user_id = user_id
            else:
                self.db.add(
                    DesktopSyncFolder(
                        user_id=user_id,
                        device_id=device_id,
                        device_name=device_name,
                        platform=platform,
                        remote_path=folder.remote_path,
                        sync_direction=folder.sync_direction,
                        is_active=True,
                        last_reported_at=now,
                    )
                )
            accepted += 1

        # Deactivate folders no longer reported by this device
        deactivate_query = self.db.query(DesktopSyncFolder).filter(
            DesktopSyncFolder.device_id == device_id,
            DesktopSyncFolder.user_id == user_id,
            DesktopSyncFolder.is_active.is_(True),
        )
        if reported_paths:
            deactivate_query = deactivate_query.filter(
                DesktopSyncFolder.remote_path.notin_(reported_paths),
            )
        deactivated = 0
        for row in deactivate_query.all():
            row.is_active = False
            deactivated += 1

        self.db.commit()
        return accepted, deactivated

    def get_synced_folders(self, user_id: int, is_admin: bool, active_only: bool = True) -> list[dict]:
        """Get synced desktop folders. Admins see all, users see their own."""
        from app.models.desktop_sync_folder import DesktopSyncFolder
        from app.models.user import User

        query = self.db.query(DesktopSyncFolder)
        if active_only:
            query = query.filter(DesktopSyncFolder.is_active.is_(True))
        if not is_admin:
            query = query.filter(DesktopSyncFolder.user_id == user_id)
        folders = query.all()

        user_names: dict[int, str] = {}
        if is_admin:
            user_ids = {f.user_id for f in folders}
            if user_ids:
                users = self.db.query(User).filter(User.id.in_(user_ids)).all()
                user_names = {u.id: u.username for u in users}

        return [
            {
                "remote_path": f.remote_path,
                "device_id": f.device_id,
                "device_name": f.device_name,
                "platform": f.platform,
                "sync_direction": f.sync_direction,
                "is_active": f.is_active,
                "last_reported_at": f.last_reported_at.isoformat(),
                "username": user_names.get(f.user_id) if is_admin else None,
            }
            for f in folders
        ]
