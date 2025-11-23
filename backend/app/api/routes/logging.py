"""Logging API endpoints."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.schemas.user import UserPublic
from app.schemas.audit_log import AuditLogResponse
from app.services.audit_logger_db import get_audit_logger_db
from app.services.disk_monitor import get_disk_io_history

logger = logging.getLogger(__name__)

router = APIRouter()


def _generate_mock_disk_io_data(hours: int = 24) -> Dict[str, List[Dict]]:
    """Generate mock disk I/O data for development mode."""
    import random
    
    disks = ["PhysicalDrive0", "PhysicalDrive1"]
    now = datetime.now(timezone.utc)
    mock_data = {}
    
    for disk in disks:
        samples = []
        for i in range(hours * 60):  # One sample per minute
            timestamp = now - timedelta(minutes=hours * 60 - i)
            timestamp_ms = int(timestamp.timestamp() * 1000)
            
            # Simulate varying activity patterns
            hour = timestamp.hour
            base_activity = 0.3 if 2 <= hour <= 6 else 1.0  # Lower at night
            
            samples.append({
                "timestamp": timestamp_ms,
                "readMbps": round(random.uniform(0.5, 50.0) * base_activity, 2),
                "writeMbps": round(random.uniform(0.5, 30.0) * base_activity, 2),
                "readIops": round(random.uniform(10, 500) * base_activity, 2),
                "writeIops": round(random.uniform(10, 300) * base_activity, 2),
                "avgResponseMs": round(random.uniform(0.5, 15.0), 2),
                "activeTimePercent": round(random.uniform(5, 85) * base_activity, 2)
            })
        
        mock_data[disk] = samples
    
    return mock_data


def _generate_mock_file_access_logs(days: int = 1, limit: int = 100) -> List[Dict[str, Any]]:
    """Generate mock file access logs for development mode."""
    import random
    
    actions = ["read", "write", "upload", "download", "delete", "create", "move", "copy"]
    users = ["admin", "user1", "user2", "guest"]
    files = [
        "/documents/report.pdf",
        "/media/video.mp4",
        "/images/photo.jpg",
        "/backup/archive.zip",
        "/config/settings.json",
        "/data/database.db",
        "/logs/system.log",
        "/temp/cache.tmp"
    ]
    
    now = datetime.now(timezone.utc)
    logs = []
    
    for i in range(limit):
        timestamp = now - timedelta(seconds=random.randint(0, days * 24 * 3600))
        action = random.choice(actions)
        
        # Determine file size based on action
        size_bytes = None
        if action in ["upload", "write", "create"]:
            size_bytes = random.randint(1024, 100 * 1024 * 1024)  # 1KB to 100MB
        elif action in ["download", "read"]:
            size_bytes = random.randint(1024, 100 * 1024 * 1024)
        
        log_entry = {
            "timestamp": timestamp.isoformat(),
            "event_type": "FILE_ACCESS",
            "user": random.choice(users),
            "action": action,
            "resource": random.choice(files),
            "success": random.random() > 0.05,  # 95% success rate
            "details": {}
        }
        
        if size_bytes:
            log_entry["details"]["size_bytes"] = size_bytes
        
        if random.random() > 0.9:  # 10% have duration
            log_entry["details"]["duration_ms"] = random.randint(10, 5000)
        
        if not log_entry["success"]:
            log_entry["error"] = random.choice([
                "Permission denied",
                "File not found",
                "Disk full",
                "I/O error"
            ])
        
        logs.append(log_entry)
    
    # Sort by timestamp (most recent first)
    logs.sort(key=lambda x: x["timestamp"], reverse=True)
    return logs


@router.get("/disk-io")
async def get_disk_io_logs(
    hours: int = Query(default=24, ge=1, le=168),  # 1 hour to 1 week
    current_user: UserPublic = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get disk I/O activity logs.
    
    Args:
        hours: Number of hours of history to return (default: 24)
        current_user: Current authenticated user
    
    Returns:
        Disk I/O history for all monitored disks
    """
    if settings.is_dev_mode:
        # Return mock data in dev mode
        logger.info("Returning mock disk I/O data (dev mode)")
        return {
            "dev_mode": True,
            "disks": _generate_mock_disk_io_data(hours=min(hours, 24))
        }
    
    # Get real data from disk monitor
    disk_data = get_disk_io_history()
    
    # Filter by time range if needed
    cutoff_ms = int((datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp() * 1000)
    filtered_data = {}
    
    for disk, samples in disk_data.items():
        filtered_samples = [s for s in samples if s["timestamp"] >= cutoff_ms]
        filtered_data[disk] = filtered_samples
    
    return {
        "dev_mode": False,
        "disks": filtered_data
    }


@router.get("/file-access")
async def get_file_access_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    days: int = Query(default=1, ge=1, le=30),
    action: Optional[str] = Query(default=None),
    user: Optional[str] = Query(default=None),
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get file access logs from database.
    
    Args:
        limit: Maximum number of logs to return (default: 100)
        days: Number of days to look back (default: 1)
        action: Filter by action type (optional)
        user: Filter by username (optional)
        current_user: Current authenticated user
        db: Database session
    
    Returns:
        File access log entries
    """
    # Get audit logs from database
    audit = get_audit_logger_db()
    logs = audit.get_logs(
        limit=limit,
        event_type="FILE_ACCESS",
        action=action,
        user=user,
        days=days,
        db=db
    )
    
    return {
        "total": len(logs),
        "logs": logs
    }


@router.get("/stats")
async def get_logging_stats(
    days: int = Query(default=7, ge=1, le=30),
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get logging statistics and summary from database.
    
    Args:
        days: Number of days to analyze (default: 7)
        current_user: Current authenticated user
        db: Database session
    
    Returns:
        Statistics about disk I/O and file access
    """
    # Get audit logs from database
    audit = get_audit_logger_db()
    logs = audit.get_logs(limit=10000, event_type="FILE_ACCESS", days=days, db=db)
    
    # Calculate statistics
    total_ops = len(logs)
    by_action = {}
    by_user = {}
    success_count = 0
    
    for log in logs:
        action = log.get("action", "unknown")
        user = log.get("user", "unknown")
        
        by_action[action] = by_action.get(action, 0) + 1
        by_user[user] = by_user.get(user, 0) + 1
        
        if log.get("success", True):
            success_count += 1
    
    success_rate = success_count / total_ops if total_ops > 0 else 1.0
    
    return {
        "period_days": days,
        "file_access": {
            "total_operations": total_ops,
            "by_action": by_action,
            "by_user": by_user,
            "success_rate": round(success_rate, 3)
        }
    }


@router.get("/audit")
async def get_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    event_type: Optional[str] = Query(default=None),
    user: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    success: Optional[bool] = Query(default=None),
    days: int = Query(default=7, ge=1, le=365),
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> AuditLogResponse:
    """
    Get paginated audit logs with filtering.
    
    Args:
        page: Page number (1-indexed)
        page_size: Number of logs per page
        event_type: Filter by event type
        user: Filter by username
        action: Filter by action
        success: Filter by success status
        days: Number of days to look back
        current_user: Current authenticated user
        db: Database session
    
    Returns:
        Paginated audit log entries
    """
    audit = get_audit_logger_db()
    result = audit.get_logs_paginated(
        page=page,
        page_size=page_size,
        event_type=event_type,
        user=user,
        action=action,
        success=success,
        days=days,
        db=db
    )
    
    return AuditLogResponse(**result)
