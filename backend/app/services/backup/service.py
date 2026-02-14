            # ...existing code...

"""Backup service for creating and restoring system backups."""
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import engine, DATABASE_URL
from app.models.backup import Backup
from app.schemas.backup import BackupCreate, BackupInDB
from app.services.audit_logger_db import AuditLoggerDB
import logging

logger = logging.getLogger(__name__)


class BackupService:
    """Service for managing system backups."""
    
    def __init__(self, db: Session):
        self.db = db
        self.default_backup_dir = Path(settings.nas_backup_path)
        self.default_backup_dir.mkdir(parents=True, exist_ok=True)
        # Public attribute used by tests and callers to override backup destination
        self.backup_dir = self.default_backup_dir
        
    def create_backup(
        self,
        backup_data: BackupCreate,
        creator_id: int,
        creator_username: str
    ) -> BackupInDB:
        """
        Create a full system backup including database and files.
        
        Args:
            backup_data: Backup configuration
            creator_id: User ID creating the backup
            creator_username: Username for audit logging
            
        Returns:
            BackupInDB: Created backup metadata
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{timestamp}.tar.gz"
        # Use optional path from request or the service's backup_dir
        backup_dir = Path(backup_data.backup_path) if backup_data.backup_path else self.backup_dir
        backup_dir.mkdir(parents=True, exist_ok=True)
        filepath = backup_dir / filename
        
        # Create backup record in database
        backup = Backup(
            filename=filename,
            filepath=str(filepath),
            size_bytes=0,
            backup_type=backup_data.backup_type,
            status="in_progress",
            creator_id=creator_id,
            includes_database=backup_data.includes_database,
            includes_files=backup_data.includes_files,
            includes_config=backup_data.includes_config,
        )
        self.db.add(backup)
        self.db.commit()
        self.db.refresh(backup)
        
        # Detailed logging for backup creation diagnostics
        logger = AuditLoggerDB()
        logger.log_event(
            event_type="BACKUP",
            action="start_backup",
            user=creator_username,
            resource=filename,
            success=True,
            details={"step": "init", "backup_type": backup_data.backup_type},
            db=self.db
        )
        try:
            # Create temporary directory for staging
            with tempfile.TemporaryDirectory(dir=str(backup_dir)) as temp_dir:
                temp_path = Path(temp_dir)
                logger.log_event(
                    event_type="BACKUP",
                    action="stage_temp_dir",
                    user=creator_username,
                    resource=filename,
                    success=True,
                    details={"step": "temp_dir_created", "temp_path": str(temp_path)},
                    db=self.db
                )

                # Copy database
                if backup_data.includes_database:
                    db_type, db_path = self._get_database_info()
                    db_backup_dir = temp_path / "database"
                    db_backup_dir.mkdir(parents=True, exist_ok=True)

                    if db_type == "sqlite":
                        # SQLite: Copy database file
                        if db_path and db_path.exists():
                            shutil.copy2(db_path, db_backup_dir / "baluhost.db")
                            logger.log_event(
                                event_type="BACKUP",
                                action="copy_database",
                                user=creator_username,
                                resource=filename,
                                success=True,
                                details={"step": "database_copied", "db_type": "sqlite", "db_path": str(db_path)},
                                db=self.db
                            )
                            # Also backup WAL files if they exist (SQLite)
                            for ext in ["-wal", "-shm"]:
                                wal_path = Path(str(db_path) + ext)
                                if wal_path.exists():
                                    shutil.copy2(wal_path, db_backup_dir / f"baluhost.db{ext}")
                                    logger.log_event(
                                        event_type="BACKUP",
                                        action="copy_wal",
                                        user=creator_username,
                                        resource=filename,
                                        success=True,
                                        details={"step": "wal_copied", "wal_path": str(wal_path)},
                                        db=self.db
                                    )

                    elif db_type == "postgresql":
                        # PostgreSQL: Use pg_dump
                        self._backup_postgres_database(db_backup_dir)
                        logger.log_event(
                            event_type="BACKUP",
                            action="pg_dump_database",
                            user=creator_username,
                            resource=filename,
                            success=True,
                            details={"step": "database_dumped", "db_type": "postgresql"},
                            db=self.db
                        )

                # Copy files
                if backup_data.includes_files:
                    storage_path = Path(settings.nas_storage_path)
                    if storage_path.exists():
                        files_backup_dir = temp_path / "files"
                        logger.log_event(
                            event_type="BACKUP",
                            action="stage_files",
                            user=creator_username,
                            resource=filename,
                            success=True,
                            details={"step": "files_stage", "storage_path": str(storage_path)},
                            db=self.db
                        )
                        if backup_data.backup_type == "incremental":
                            # Finde letztes completed Backup
                            last_backup = self.db.query(Backup).filter(
                                Backup.status == "completed",
                                Backup.includes_files == True
                            ).order_by(Backup.created_at.desc()).first()
                            last_files = set()
                            last_files_mtime = dict()
                            if last_backup and Path(last_backup.filepath).exists():
                                with tarfile.open(last_backup.filepath, "r:gz") as tar:
                                    for member in tar.getmembers():
                                        if member.name.startswith("backup/files/") and member.isfile():
                                            rel_path = member.name[len("backup/files/"):] 
                                            last_files.add(rel_path)
                                            last_files_mtime[rel_path] = member.mtime
                            # Vergleiche aktuelle Dateien mit letztem Backup
                            files_to_backup = []
                            for file in storage_path.rglob("*"):
                                if file.is_file():
                                    rel_path = str(file.relative_to(storage_path))
                                    mtime = int(file.stat().st_mtime)
                                    # Neu oder geändert?
                                    if rel_path not in last_files or mtime > last_files_mtime.get(rel_path, 0):
                                        files_to_backup.append((file, rel_path))
                            files_backup_dir.mkdir(parents=True, exist_ok=True)
                            for file, rel_path in files_to_backup:
                                dest = files_backup_dir / rel_path
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(file, dest)
                                logger.log_event(
                                    event_type="BACKUP",
                                    action="copy_file",
                                    user=creator_username,
                                    resource=filename,
                                    success=True,
                                    details={"step": "file_copied", "file": str(file)},
                                    db=self.db
                                )
                        else:
                            shutil.copytree(storage_path, files_backup_dir, symlinks=False)
                            logger.log_event(
                                event_type="BACKUP",
                                action="copy_files_full",
                                user=creator_username,
                                resource=filename,
                                success=True,
                                details={"step": "files_copied_full", "storage_path": str(storage_path)},
                                db=self.db
                            )

                # Copy config (optional)
                if backup_data.includes_config:
                    config_dir = temp_path / "config"
                    config_dir.mkdir(parents=True, exist_ok=True)
                    logger.log_event(
                        event_type="BACKUP",
                        action="copy_config",
                        user=creator_username,
                        resource=filename,
                        success=True,
                        details={"step": "config_staged"},
                        db=self.db
                    )
                    # TODO: Add config files if needed

                # Create tar.gz archive
                with tarfile.open(filepath, "w:gz") as tar:
                    tar.add(temp_path, arcname="backup")
                logger.log_event(
                    event_type="BACKUP",
                    action="archive_created",
                    user=creator_username,
                    resource=filename,
                    success=True,
                    details={"step": "archive_created", "filepath": str(filepath)},
                    db=self.db
                )
            
            # Update backup record with size and completion
            backup.size_bytes = filepath.stat().st_size
            backup.status = "completed"
            backup.completed_at = datetime.now()
            self.db.commit()
            self.db.refresh(backup)
            logger.log_event(
                event_type="BACKUP",
                action="create_backup",
                user=creator_username,
                resource=filename,
                success=True,
                details={"size_bytes": backup.size_bytes, "backup_type": backup.backup_type},
                db=self.db
            )
            # Cleanup old backups
            self._cleanup_old_backups()
            return BackupInDB.model_validate(backup)
        except Exception as e:
            # Mark backup as failed
            import traceback
            tb = traceback.format_exc()
            backup.status = "failed"
            backup.error_message = str(e)
            backup.completed_at = datetime.now()
            self.db.commit()
            logger.log_event(
                event_type="BACKUP",
                action="create_backup",
                user=creator_username,
                resource=filename,
                success=False,
                error_message=str(e),
                details={"traceback": tb},
                db=self.db
            )
            raise
    

    from cachetools import cached, TTLCache
    from functools import lru_cache

    _backups_cache = TTLCache(maxsize=16, ttl=60)  # 60 Sekunden Cache

    @cached(_backups_cache)
    def list_backups(self) -> list[BackupInDB]:
        """
        List all backups ordered by creation date (newest first).
        Memoized (TTL 60s) für Performance und aktuelle Daten.
        """
        backups = self.db.query(Backup).order_by(Backup.created_at.desc()).all()
        return [BackupInDB.model_validate(b) for b in backups]

    @lru_cache(maxsize=32)
    def get_backup_by_id(self, backup_id: int) -> Optional[BackupInDB]:
        """
        Holt Backup-Metadaten nach ID, cached nach backup_id für Performance.
        """
        backup = self.db.query(Backup).filter(Backup.id == backup_id).first()
        return BackupInDB.model_validate(backup) if backup else None
    
    def get_backup_by_id(self, backup_id: int) -> Optional[BackupInDB]:
        """Get backup by ID."""
        backup = self.db.query(Backup).filter(Backup.id == backup_id).first()
        return BackupInDB.model_validate(backup) if backup else None
    
    def delete_backup(self, backup_id: int, user: str) -> bool:
        """
        Delete a backup by ID.
        
        Args:
            backup_id: Backup ID to delete
            user: Username for audit logging
            
        Returns:
            bool: True if deleted successfully
        """
        backup = self.db.query(Backup).filter(Backup.id == backup_id).first()
        if not backup:
            return False
        
        # Delete file from filesystem
        filepath = Path(backup.filepath)
        if filepath.exists():
            filepath.unlink()
        
        # Delete database record
        filename = backup.filename
        self.db.delete(backup)
        self.db.commit()
        
        # Log audit event
        logger = AuditLoggerDB()
        logger.log_event(
            event_type="BACKUP",
            action="delete_backup",
            user=user,
            resource=filename,
            success=True,
            details={"backup_id": backup_id},
            db=self.db
        )
        
        return True
    
    def restore_backup(
        self,
        backup_id: int,
        user: str,
        restore_database: bool = True,
        restore_files: bool = True,
        restore_config: bool = False
    ) -> bool:
        """
        Restore system from a backup.
        
        WARNING: This will overwrite current data!
        
        Args:
            backup_id: Backup ID to restore
            user: Username for audit logging
            restore_database: Whether to restore database
            restore_files: Whether to restore files
            restore_config: Whether to restore config
            
        Returns:
            bool: True if restored successfully
        """
        backup = self.db.query(Backup).filter(Backup.id == backup_id).first()
        if not backup or backup.status != "completed":
            return False
        
        filepath = Path(backup.filepath)
        if not filepath.exists():
            return False
        
        try:
            # Extract backup to temporary directory
            with tempfile.TemporaryDirectory(dir=str(self.backup_dir)) as temp_dir:
                temp_path = Path(temp_dir)

                # Extract tar.gz
                with tarfile.open(filepath, "r:gz") as tar:
                    tar.extractall(temp_path)
                
                backup_root = temp_path / "backup"
                
                # Restore database
                if restore_database and backup.includes_database:
                    db_type, db_path = self._get_database_info()

                    # Close all connections before restore
                    engine.dispose()

                    if db_type == "sqlite":
                        # SQLite: Restore database file
                        db_backup = backup_root / "database" / "baluhost.db"
                        if db_backup.exists() and db_path:
                            shutil.copy2(db_backup, db_path)

                            # Restore WAL files if they exist
                            for ext in ["-wal", "-shm"]:
                                wal_backup = backup_root / "database" / f"baluhost.db{ext}"
                                if wal_backup.exists():
                                    shutil.copy2(wal_backup, Path(str(db_path) + ext))

                    elif db_type == "postgresql":
                        # PostgreSQL: Restore from pg_dump file
                        pg_backup = backup_root / "database" / "postgres_backup.sql.gz"
                        if not pg_backup.exists():
                            pg_backup = backup_root / "database" / "postgres_backup.sql"

                        if pg_backup.exists():
                            self._restore_postgres_database(pg_backup)
                        else:
                            raise FileNotFoundError("PostgreSQL backup file not found in backup archive")
                
                # Restore files
                if restore_files and backup.includes_files:
                    files_backup = backup_root / "files"
                    if files_backup.exists():
                        storage_path = Path(settings.nas_storage_path)
                        # Remove existing files
                        if storage_path.exists():
                            shutil.rmtree(storage_path)
                        # Copy backup files
                        shutil.copytree(files_backup, storage_path)
                
                # Restore config
                if restore_config and backup.includes_config:
                    config_backup = backup_root / "config"
                    if config_backup.exists():
                        # TODO: Implement config restore if needed
                        pass
            
            # Log audit event
            logger = AuditLoggerDB()
            logger.log_event(
                event_type="BACKUP",
                action="restore_backup",
                user=user,
                resource=backup.filename,
                success=True,
                details={"backup_id": backup_id, "restore_database": restore_database, "restore_files": restore_files},
                db=self.db
            )
            
            return True
            
        except Exception as e:
            # Log audit event
            logger = AuditLoggerDB()
            # Also log full exception traceback to help debugging
            logger_local = logging.getLogger(__name__)
            logger_local.exception("[BACKUP] Failed to restore backup %s: %s", backup_id, e)

            # If on Windows and file is locked with WinError 1224, raise a specific error
            win_err = getattr(e, "winerror", None)
            if win_err == 1224:
                # Record audit log and raise a specific exception so the route can return a helpful HTTP status
                logger.log_event(
                    event_type="BACKUP",
                    action="restore_backup",
                    user=user,
                    resource=backup.filename,
                    success=False,
                    error_message=str(e),
                    db=self.db
                )
                raise RestoreLockedError(
                    "Database file is currently locked by the running application.\n"
                    "Stop the application before restoring the database, or perform the restore without the database option."
                ) from e

            logger.log_event(
                event_type="BACKUP",
                action="restore_backup",
                user=user,
                resource=backup.filename,
                success=False,
                error_message=str(e),
                db=self.db
            )
            raise
    
    def download_backup(self, backup_id: int) -> Optional[Path]:
        """
        Get path to backup file for download.
        
        Args:
            backup_id: Backup ID
            
        Returns:
            Path to backup file or None if not found
        """
        backup = self.db.query(Backup).filter(Backup.id == backup_id).first()
        if not backup or backup.status != "completed":
            return None
        
        filepath = Path(backup.filepath)
        return filepath if filepath.exists() else None
    
    def _backup_postgres_database(self, backup_dir: Path) -> None:
        """
        Backup PostgreSQL database using pg_dump.

        Args:
            backup_dir: Directory to store the backup file
        """
        # Parse DATABASE_URL
        parsed_url = urlparse(DATABASE_URL)

        # Extract connection parameters
        host = parsed_url.hostname or "localhost"
        port = parsed_url.port or 5432
        database = parsed_url.path.lstrip('/')
        username = parsed_url.username
        password = parsed_url.password

        # Output file
        backup_file = backup_dir / "postgres_backup.sql"

        # Build pg_dump command
        pg_dump_cmd = [
            "pg_dump",
            "-h", host,
            "-p", str(port),
            "-U", username,
            "-d", database,
            "-F", "p",  # Plain text format
            "--no-owner",  # Don't output commands to set ownership
            "--no-acl",  # Don't output commands to set access privileges
            "-f", str(backup_file)
        ]

        # Set PGPASSWORD environment variable for authentication
        env = os.environ.copy()
        if password:
            env["PGPASSWORD"] = password

        try:
            # Execute pg_dump with 5 minute timeout
            result = subprocess.run(
                pg_dump_cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes
                check=True
            )

            # Compress the backup file
            import gzip
            compressed_file = backup_dir / "postgres_backup.sql.gz"
            with open(backup_file, 'rb') as f_in:
                with gzip.open(compressed_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Remove uncompressed file
            backup_file.unlink()

            logger.info(f"PostgreSQL database backed up successfully to {compressed_file}")

        except subprocess.TimeoutExpired:
            raise RuntimeError("PostgreSQL backup timed out after 5 minutes")
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            raise RuntimeError(f"PostgreSQL backup failed: {error_msg}")
        except FileNotFoundError:
            raise RuntimeError(
                "pg_dump command not found. Please ensure PostgreSQL client tools are installed. "
                "Ubuntu/Debian: apt-get install postgresql-client, "
                "RHEL/CentOS: yum install postgresql, "
                "macOS: brew install postgresql"
            )

    def _restore_postgres_database(self, backup_file: Path) -> None:
        """
        Restore PostgreSQL database from pg_dump backup.

        Args:
            backup_file: Path to the backup file (.sql or .sql.gz)
        """
        # Parse DATABASE_URL
        parsed_url = urlparse(DATABASE_URL)

        # Extract connection parameters
        host = parsed_url.hostname or "localhost"
        port = parsed_url.port or 5432
        database = parsed_url.path.lstrip('/')
        username = parsed_url.username
        password = parsed_url.password

        # Decompress if needed
        if str(backup_file).endswith('.gz'):
            import gzip
            decompressed_file = backup_file.parent / "postgres_backup_temp.sql"
            with gzip.open(backup_file, 'rb') as f_in:
                with open(decompressed_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            restore_file = decompressed_file
        else:
            restore_file = backup_file

        try:
            # Build psql command for restore
            psql_cmd = [
                "psql",
                "-h", host,
                "-p", str(port),
                "-U", username,
                "-d", database,
                "-f", str(restore_file)
            ]

            # Set PGPASSWORD environment variable
            env = os.environ.copy()
            if password:
                env["PGPASSWORD"] = password

            # Execute psql with 10 minute timeout
            result = subprocess.run(
                psql_cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes
                check=True
            )

            logger.info("PostgreSQL database restored successfully")

        except subprocess.TimeoutExpired:
            raise RuntimeError("PostgreSQL restore timed out after 10 minutes")
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            raise RuntimeError(f"PostgreSQL restore failed: {error_msg}")
        except FileNotFoundError:
            raise RuntimeError(
                "psql command not found. Please ensure PostgreSQL client tools are installed."
            )
        finally:
            # Clean up decompressed temp file if it was created
            if str(backup_file).endswith('.gz') and restore_file.exists():
                restore_file.unlink()

    def _get_database_info(self) -> tuple[str, Optional[Path]]:
        """
        Get database type and path information.

        Returns:
            tuple: (database_type, database_path)
                - database_type: "sqlite" or "postgresql"
                - database_path: Path to database file (SQLite only, None for PostgreSQL)
        """
        if DATABASE_URL.startswith("sqlite:///"):
            db_path = DATABASE_URL.replace("sqlite:///", "")
            return ("sqlite", Path(db_path))
        elif DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgresql+psycopg2://"):
            return ("postgresql", None)
        else:
            raise ValueError(f"Unsupported database type in URL: {DATABASE_URL}")

    def _get_database_path(self) -> Path:
        """Get path to SQLite database file (legacy method for compatibility)."""
        db_type, db_path = self._get_database_info()
        if db_type == "sqlite":
            return db_path
        raise ValueError("_get_database_path() only supports SQLite. Use _get_database_info() instead.")
    
    def _cleanup_old_backups(self) -> None:
        """Remove old backups based on retention policy."""
        # Get all completed backups
        backups = (
            self.db.query(Backup)
            .filter(Backup.status == "completed")
            .order_by(Backup.created_at.desc())
            .all()
        )
        
        # Remove backups exceeding max count
        if len(backups) > settings.nas_backup_max_count:
            for backup in backups[settings.nas_backup_max_count:]:
                filepath = Path(backup.filepath)
                if filepath.exists():
                    filepath.unlink()
                # Audit-Log
                logger = AuditLoggerDB()
                logger.log_event(
                    event_type="BACKUP",
                    action="retention_delete",
                    user="system",
                    resource=backup.filename,
                    success=True,
                    details={"reason": "max_count", "backup_id": backup.id},
                    db=self.db
                )
                self.db.delete(backup)
        
        # Remove backups older than retention period
        cutoff_date = datetime.now() - timedelta(days=settings.nas_backup_retention_days)
        old_backups = (
            self.db.query(Backup)
            .filter(
                Backup.status == "completed",
                Backup.created_at < cutoff_date
            )
            .all()
        )
        
        for backup in old_backups:
            filepath = Path(backup.filepath)
            if filepath.exists():
                filepath.unlink()
            # Audit-Log
            logger = AuditLoggerDB()
            logger.log_event(
                event_type="BACKUP",
                action="retention_delete",
                user="system",
                resource=backup.filename,
                success=True,
                details={"reason": "retention_days", "backup_id": backup.id},
                db=self.db
            )
            self.db.delete(backup)
        
        self.db.commit()


def get_backup_service(db: Session) -> BackupService:
    """Dependency to get backup service instance."""
    return BackupService(db)


class RestoreLockedError(Exception):
    """Raised when a restore cannot replace the database file because it's locked (Windows)."""
