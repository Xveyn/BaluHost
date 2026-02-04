"""Database-backed audit logging service for file operations and system events."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, List

from sqlalchemy import select, desc, and_, not_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

# Event types that should be hidden from non-admin users
ADMIN_ONLY_EVENTS = {'USER_MANAGEMENT', 'ADMIN', 'SYSTEM_CONFIG', 'RAID_OPERATION'}


class AuditLoggerDB:
    """Database-backed audit logging service."""
    
    def __init__(self):
        self._enabled = True  # Always enabled, even in dev mode
    
    def log_event(
        self,
        event_type: str,
        user: Optional[str],
        action: str,
        resource: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Optional[AuditLog]:
        """
        Log an audit event to the database.
        
        Args:
            event_type: Type of event (FILE_ACCESS, FILE_MODIFY, DISK_MONITOR, SYSTEM, SECURITY)
            user: Username who performed the action
            action: Action performed (read, write, delete, create, etc.)
            resource: Resource affected (file path, disk name, etc.)
            details: Additional details about the event
            success: Whether the operation succeeded
            error_message: Error message if operation failed
            ip_address: IP address of the requester
            user_agent: User agent of the requester
            db: Optional database session (if not provided, creates new one)
            
        Returns:
            Created AuditLog entry or None if failed
        """
        if not self._enabled:
            return None
        
        # Serialize details to JSON if provided
        details_json = json.dumps(details) if details else None
        
        audit_entry = AuditLog(
            event_type=event_type,
            user=user,
            action=action,
            resource=resource,
            success=success,
            error_message=error_message,
            details=details_json,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        # Use provided session or create a new one
        should_close = False
        if db is None:
            db = next(get_db())
            should_close = True
        
        try:
            db.add(audit_entry)
            db.commit()
            db.refresh(audit_entry)
            return audit_entry
        except Exception as e:
            logger.error(f"Failed to write audit log to database: {e}")
            db.rollback()
            return None
        finally:
            if should_close:
                db.close()
    
    def log_file_access(
        self,
        user: Optional[str],
        action: str,
        file_path: str,
        success: bool = True,
        error_message: Optional[str] = None,
        db: Optional[Session] = None,
        **kwargs
    ) -> Optional[AuditLog]:
        """Log file access/modification event."""
        return self.log_event(
            event_type="FILE_ACCESS",
            user=user,
            action=action,
            resource=file_path,
            details=kwargs,
            success=success,
            error_message=error_message,
            db=db
        )
    
    def log_disk_monitor(
        self,
        action: str,
        disk_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Optional[AuditLog]:
        """Log disk monitor event."""
        return self.log_event(
            event_type="DISK_MONITOR",
            user="system",
            action=action,
            resource=disk_name,
            details=details,
            success=success,
            error_message=error_message,
            db=db
        )
    
    def log_system_event(
        self,
        action: str,
        user: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Optional[AuditLog]:
        """Log system event."""
        return self.log_event(
            event_type="SYSTEM",
            user=user or "system",
            action=action,
            details=details,
            success=success,
            error_message=error_message,
            db=db
        )
    
    def log_security_event(
        self,
        action: str,
        user: Optional[str] = None,
        resource: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = False,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Optional[AuditLog]:
        """Log security-related event (unauthorized access, permission denied, etc.)."""
        return self.log_event(
            event_type="SECURITY",
            user=user or "anonymous",
            action=action,
            resource=resource,
            details=details,
            success=success,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent,
            db=db
        )
    
    def log_authentication_attempt(
        self,
        username: str,
        success: bool,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        error_message: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Optional[AuditLog]:
        """Log authentication attempt (login)."""
        details = {}
        if ip_address:
            details["ip_address"] = ip_address
        if user_agent:
            details["user_agent"] = user_agent
        
        return self.log_security_event(
            action="login_attempt",
            user=username,
            details=details,
            success=success,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent,
            db=db
        )
    
    def log_authorization_failure(
        self,
        user: Optional[str],
        action: str,
        resource: Optional[str] = None,
        required_permission: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Optional[AuditLog]:
        """Log authorization failure (permission denied)."""
        details = {}
        if required_permission:
            details["required_permission"] = required_permission
        if ip_address:
            details["ip_address"] = ip_address
        
        return self.log_security_event(
            action=action,
            user=user or "anonymous",
            resource=resource,
            details=details,
            success=False,
            error_message="Permission denied",
            ip_address=ip_address,
            user_agent=user_agent,
            db=db
        )
    
    def log_file_share_created(
        self,
        user_id: int,
        username: str,
        file_path: str,
        share_type: str,
        shared_with: Optional[str] = None,
        ip_address: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Optional[AuditLog]:
        """Log file share creation."""
        details = {
            "user_id": user_id,
            "share_type": share_type
        }
        if shared_with:
            details["shared_with"] = shared_with
        
        return self.log_event(
            event_type="FILE_ACCESS",
            user=username,
            action="share_created",
            resource=file_path,
            details=details,
            success=True,
            ip_address=ip_address,
            db=db
        )
    
    def log_file_action(
        self,
        action: str,
        user_id: int,
        username: str,
        file_path: str,
        success: bool = True,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Optional[AuditLog]:
        """Log generic file action."""
        details = {"user_id": user_id}
        
        return self.log_event(
            event_type="FILE_ACCESS",
            user=username,
            action=action,
            resource=file_path,
            details=details,
            success=success,
            error_message=error_message,
            ip_address=ip_address,
            db=db
        )
    
    def is_enabled(self) -> bool:
        """Check if audit logging is enabled."""
        return self._enabled
    
    def get_logs(
        self,
        limit: int = 100,
        event_type: Optional[str] = None,
        user: Optional[str] = None,
        action: Optional[str] = None,
        success: Optional[bool] = None,
        days: int = 1,
        db: Optional[Session] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit logs from the database.
        
        Args:
            limit: Maximum number of logs to return
            event_type: Filter by event type
            user: Filter by user
            action: Filter by action
            success: Filter by success status
            days: Number of days to look back (default: 1)
            db: Optional database session
            
        Returns:
            List of log entries as dictionaries
        """
        if not self._enabled:
            return []
        
        # Use provided session or create a new one
        should_close = False
        if db is None:
            db = next(get_db())
            should_close = True
        
        try:
            # Build query with filters
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
            
            stmt = select(AuditLog).where(AuditLog.timestamp >= cutoff_time)
            
            if event_type:
                stmt = stmt.where(AuditLog.event_type == event_type)
            if user:
                stmt = stmt.where(AuditLog.user == user)
            if action:
                stmt = stmt.where(AuditLog.action == action)
            if success is not None:
                stmt = stmt.where(AuditLog.success == success)
            
            # Order by timestamp descending and limit
            stmt = stmt.order_by(desc(AuditLog.timestamp)).limit(limit)
            
            result = db.execute(stmt)
            logs = result.scalars().all()
            
            # Convert to dictionaries
            return [self._audit_log_to_dict(log) for log in logs]
        
        except Exception as e:
            logger.error(f"Failed to retrieve audit logs from database: {e}")
            return []
        finally:
            if should_close:
                db.close()
    
    def get_logs_paginated(
        self,
        page: int = 1,
        page_size: int = 50,
        event_type: Optional[str] = None,
        user: Optional[str] = None,
        action: Optional[str] = None,
        success: Optional[bool] = None,
        days: int = 7,
        db: Optional[Session] = None,
        is_admin: bool = True
    ) -> Dict[str, Any]:
        """
        Retrieve paginated audit logs from the database with role-based filtering.

        Args:
            page: Page number (1-indexed)
            page_size: Number of logs per page
            event_type: Filter by event type
            user: Filter by user
            action: Filter by action
            success: Filter by success status
            days: Number of days to look back
            db: Optional database session
            is_admin: Whether the requesting user is an admin (affects visibility)

        Returns:
            Dictionary with logs, total count, and pagination info.
            Non-admin users see filtered results with anonymized usernames
            and no admin-only events.
        """
        if not self._enabled:
            return {"logs": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0}

        should_close = False
        if db is None:
            db = next(get_db())
            should_close = True

        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

            # Build base query
            base_stmt = select(AuditLog).where(AuditLog.timestamp >= cutoff_time)

            # For non-admins, exclude admin-only event types
            if not is_admin:
                base_stmt = base_stmt.where(
                    not_(AuditLog.event_type.in_(ADMIN_ONLY_EVENTS))
                )
                # Non-admins cannot filter by specific user
                user = None

            if event_type:
                base_stmt = base_stmt.where(AuditLog.event_type == event_type)
            if user:
                base_stmt = base_stmt.where(AuditLog.user == user)
            if action:
                base_stmt = base_stmt.where(AuditLog.action == action)
            if success is not None:
                base_stmt = base_stmt.where(AuditLog.success == success)

            # Get total count
            from sqlalchemy import func
            count_stmt = select(func.count()).select_from(base_stmt.subquery())
            total = db.execute(count_stmt).scalar() or 0

            # Get paginated results
            offset = (page - 1) * page_size
            stmt = base_stmt.order_by(desc(AuditLog.timestamp)).limit(page_size).offset(offset)

            result = db.execute(stmt)
            logs = result.scalars().all()

            total_pages = (total + page_size - 1) // page_size

            # Convert logs with role-based filtering
            filtered_logs = []
            for log in logs:
                log_dict = self._audit_log_to_dict_filtered(log, is_admin=is_admin)
                if log_dict is not None:
                    filtered_logs.append(log_dict)

            return {
                "logs": filtered_logs,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages
            }

        except Exception as e:
            logger.error(f"Failed to retrieve paginated audit logs: {e}")
            return {"logs": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0}
        finally:
            if should_close:
                db.close()
    
    def log_user_management(
        self,
        action: str,
        admin_user: str,
        target_user: str,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Optional[AuditLog]:
        """Log user management operations (create, update, delete, role changes)."""
        return self.log_event(
            event_type="USER_MANAGEMENT",
            user=admin_user,
            action=action,
            resource=target_user,
            details=details,
            success=success,
            error_message=error_message,
            db=db
        )

    def log_raid_operation(
        self,
        action: str,
        user: str,
        raid_array: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Optional[AuditLog]:
        """Log RAID array operations (create, delete, manage)."""
        return self.log_event(
            event_type="RAID_OPERATION",
            user=user,
            action=action,
            resource=raid_array,
            details=details,
            success=success,
            error_message=error_message,
            db=db
        )

    def log_vpn_operation(
        self,
        action: str,
        user: str,
        vpn_client: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Optional[AuditLog]:
        """Log VPN configuration operations (add client, remove client, config changes)."""
        return self.log_event(
            event_type="VPN_OPERATION",
            user=user,
            action=action,
            resource=vpn_client,
            details=details,
            success=success,
            error_message=error_message,
            db=db
        )

    def log_system_config_change(
        self,
        action: str,
        user: str,
        config_key: str,
        old_value: Optional[Any] = None,
        new_value: Optional[Any] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Optional[AuditLog]:
        """Log system configuration changes."""
        details = {}
        if old_value is not None:
            details["old_value"] = str(old_value)
        if new_value is not None:
            details["new_value"] = str(new_value)

        return self.log_event(
            event_type="SYSTEM_CONFIG",
            user=user,
            action=action,
            resource=config_key,
            details=details,
            success=success,
            error_message=error_message,
            db=db
        )

    def _audit_log_to_dict(self, log: AuditLog) -> Dict[str, Any]:
        """Convert AuditLog model to dictionary."""
        details = {}
        if log.details:
            try:
                details = json.loads(log.details)
            except json.JSONDecodeError:
                details = {"raw": log.details}

        result = {
            "id": log.id,
            "timestamp": log.timestamp.isoformat(),
            "event_type": log.event_type,
            "user": log.user,
            "action": log.action,
            "resource": log.resource,
            "success": log.success,
            "details": details
        }

        if log.error_message:
            result["error"] = log.error_message
        if log.ip_address:
            result["ip_address"] = log.ip_address
        if log.user_agent:
            result["user_agent"] = log.user_agent

        return result

    def _audit_log_to_dict_filtered(
        self,
        log: AuditLog,
        is_admin: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Convert AuditLog to dict with role-based filtering.

        For non-admin users:
        - Admin-only events are hidden (returns None)
        - Usernames are anonymized to "user"
        - Details JSON is empty (no sensitive data)
        - IP address and user agent are excluded

        Args:
            log: AuditLog model instance
            is_admin: Whether the requesting user is an admin

        Returns:
            Dictionary representation or None if event should be hidden
        """
        if is_admin:
            return self._audit_log_to_dict(log)

        # Hide admin-only events from non-admins
        if log.event_type in ADMIN_ONLY_EVENTS:
            return None

        result = {
            "id": log.id,
            "timestamp": log.timestamp.isoformat(),
            "event_type": log.event_type,
            "user": "user",  # Anonymized for non-admins
            "action": log.action,
            "resource": log.resource,
            "success": log.success,
            "details": {}  # Empty for non-admins (may contain sensitive paths/IPs)
        }

        if log.error_message:
            result["error"] = log.error_message
        # ip_address and user_agent excluded for non-admins

        return result


# Global audit logger instance
_audit_logger_db: Optional[AuditLoggerDB] = None


def get_audit_logger_db() -> AuditLoggerDB:
    """Get the global database-backed audit logger instance."""
    global _audit_logger_db
    if _audit_logger_db is None:
        _audit_logger_db = AuditLoggerDB()
    return _audit_logger_db
