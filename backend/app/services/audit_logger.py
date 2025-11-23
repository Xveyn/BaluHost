"""Audit logging service for file operations and system events."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class AuditLogger:
    """Central audit logging service."""
    
    def __init__(self):
        self._enabled = not settings.is_dev_mode
        self._audit_log_dir = Path(settings.nas_temp_path).expanduser().resolve() / "audit"
        self._setup_audit_log()
    
    def _get_daily_log_file(self) -> Path:
        """Get the log file path for the current day."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._audit_log_dir / f"audit_{today}.log"
    
    def _setup_audit_log(self) -> None:
        """Setup audit log file and directory."""
        if self._enabled:
            self._audit_log_dir.mkdir(parents=True, exist_ok=True)
    
    def log_event(
        self,
        event_type: str,
        user: Optional[str],
        action: str,
        resource: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> None:
        """
        Log an audit event.
        
        Args:
            event_type: Type of event (FILE_ACCESS, FILE_MODIFY, DISK_MONITOR, SYSTEM)
            user: Username who performed the action
            action: Action performed (read, write, delete, create, etc.)
            resource: Resource affected (file path, disk name, etc.)
            details: Additional details about the event
            success: Whether the operation succeeded
            error_message: Error message if operation failed
        """
        if not self._enabled:
            return
        
        timestamp = datetime.now(timezone.utc).isoformat()
        
        log_entry = {
            "timestamp": timestamp,
            "event_type": event_type,
            "user": user,
            "action": action,
            "resource": resource,
            "success": success,
            "details": details or {},
        }
        
        if error_message:
            log_entry["error"] = error_message
        
        try:
            log_file = self._get_daily_log_file()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
    
    def log_file_access(
        self,
        user: Optional[str],
        action: str,
        file_path: str,
        success: bool = True,
        error_message: Optional[str] = None,
        **kwargs
    ) -> None:
        """Log file access/modification event."""
        self.log_event(
            event_type="FILE_ACCESS",
            user=user,
            action=action,
            resource=file_path,
            details=kwargs,
            success=success,
            error_message=error_message
        )
    
    def log_disk_monitor(
        self,
        action: str,
        disk_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> None:
        """Log disk monitor event."""
        self.log_event(
            event_type="DISK_MONITOR",
            user="system",
            action=action,
            resource=disk_name,
            details=details,
            success=success,
            error_message=error_message
        )
    
    def log_system_event(
        self,
        action: str,
        user: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> None:
        """Log system event."""
        self.log_event(
            event_type="SYSTEM",
            user=user or "system",
            action=action,
            details=details,
            success=success,
            error_message=error_message
        )
    
    def log_security_event(
        self,
        action: str,
        user: Optional[str] = None,
        resource: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = False,
        error_message: Optional[str] = None
    ) -> None:
        """Log security-related event (unauthorized access, permission denied, etc.)."""
        self.log_event(
            event_type="SECURITY",
            user=user or "anonymous",
            action=action,
            resource=resource,
            details=details,
            success=success,
            error_message=error_message
        )
    
    def log_authentication_attempt(
        self,
        username: str,
        success: bool,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Log authentication attempt (login)."""
        details = {}
        if ip_address:
            details["ip_address"] = ip_address
        if user_agent:
            details["user_agent"] = user_agent
        
        self.log_security_event(
            action="login_attempt",
            user=username,
            details=details,
            success=success,
            error_message=error_message
        )
    
    def log_authorization_failure(
        self,
        user: Optional[str],
        action: str,
        resource: Optional[str] = None,
        required_permission: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> None:
        """Log authorization failure (permission denied)."""
        details = {}
        if required_permission:
            details["required_permission"] = required_permission
        if ip_address:
            details["ip_address"] = ip_address
        
        self.log_security_event(
            action=action,
            user=user or "anonymous",
            resource=resource,
            details=details,
            success=False,
            error_message="Permission denied"
        )
    
    def is_enabled(self) -> bool:
        """Check if audit logging is enabled."""
        return self._enabled
    
    def get_logs(
        self,
        limit: int = 100,
        event_type: Optional[str] = None,
        user: Optional[str] = None,
        days: int = 1
    ) -> list[Dict[str, Any]]:
        """
        Retrieve audit logs.
        
        Args:
            limit: Maximum number of logs to return
            event_type: Filter by event type
            user: Filter by user
            days: Number of days to look back (default: 1 = today only)
            
        Returns:
            List of log entries
        """
        if not self._enabled:
            return []
        
        logs = []
        
        # Get log files for the last N days
        from datetime import timedelta
        for day_offset in range(days):
            date = datetime.now(timezone.utc) - timedelta(days=day_offset)
            date_str = date.strftime("%Y-%m-%d")
            log_file = self._audit_log_dir / f"audit_{date_str}.log"
            
            if not log_file.exists():
                continue
            
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            
                            # Apply filters
                            if event_type and entry.get("event_type") != event_type:
                                continue
                            if user and entry.get("user") != user:
                                continue
                            
                            logs.append(entry)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.error(f"Failed to read audit log {log_file}: {e}")
        
        # Sort by timestamp (most recent first) and limit
        logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return logs[:limit]


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
