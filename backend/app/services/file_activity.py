"""
File Activity Tracking Service.

Provides:
- Recording file activities (server-side and client-reported)
- Querying recent activities with filtering and pagination
- Querying recent files (deduplicated by path)
- Deduplication of repeated client-reported actions
- Retention cleanup (90 days default, 7 days for low-value actions)
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func, and_, delete
from sqlalchemy.orm import Session

from app.models.file_activity import FileActivity
from app.schemas.file_activity import (
    VALID_ACTION_TYPES,
    SHORT_RETENTION_ACTIONS,
    ActivityItem,
    RecentFileItem,
)

logger = logging.getLogger(__name__)

# Deduplication window: same user + path + action within this window → update
DEDUP_WINDOW_SECONDS = 300  # 5 minutes

# Retention defaults (days)
DEFAULT_RETENTION_DAYS = 90
SHORT_RETENTION_DAYS = 7


class FileActivityService:
    """Service for file activity tracking."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------
    def record(
        self,
        user_id: int,
        action_type: str,
        file_path: str,
        file_name: str,
        *,
        is_directory: bool = False,
        file_size: Optional[int] = None,
        mime_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        device_id: Optional[str] = None,
        source: str = "server",
        occurred_at: Optional[datetime] = None,
    ) -> Optional[FileActivity]:
        """Record a single file activity.

        Returns the created/updated FileActivity, or None if deduplicated.
        """
        now = occurred_at or datetime.now(timezone.utc)

        # Deduplication: check for recent identical activity
        self.db.flush()  # ensure pending inserts are visible
        cutoff = now - timedelta(seconds=DEDUP_WINDOW_SECONDS)
        existing = (
            self.db.query(FileActivity)
            .filter(
                FileActivity.user_id == user_id,
                FileActivity.file_path == file_path,
                FileActivity.action_type == action_type,
                FileActivity.created_at >= cutoff,
            )
            .order_by(desc(FileActivity.created_at))
            .first()
        )
        if existing:
            # Update timestamp instead of creating duplicate
            existing.created_at = now
            if file_size is not None:
                existing.file_size = file_size
            return None  # deduplicated

        metadata_str = json.dumps(metadata) if metadata else None

        activity = FileActivity(
            user_id=user_id,
            device_id=device_id,
            action_type=action_type,
            file_path=file_path,
            file_name=file_name,
            is_directory=is_directory,
            file_size=file_size,
            mime_type=mime_type,
            metadata_json=metadata_str,
            source=source,
            created_at=now,
        )
        self.db.add(activity)
        return activity

    def record_and_commit(
        self,
        user_id: int,
        action_type: str,
        file_path: str,
        file_name: str,
        **kwargs: Any,
    ) -> None:
        """Record activity in its own transaction (fire-and-forget)."""
        try:
            self.record(
                user_id, action_type, file_path, file_name, **kwargs
            )
            self.db.commit()
        except Exception:
            logger.debug(
                "Failed to record activity %s for %s",
                action_type,
                file_path,
                exc_info=True,
            )
            self.db.rollback()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------
    def get_recent_activities(
        self,
        user_id: int,
        *,
        limit: int = 20,
        offset: int = 0,
        action_types: Optional[List[str]] = None,
        file_type: Optional[str] = None,
        since: Optional[datetime] = None,
        path_prefix: Optional[str] = None,
    ) -> tuple[List[ActivityItem], int]:
        """Query recent activities for a user.

        Returns (items, total_count).
        """
        query = self.db.query(FileActivity).filter(
            FileActivity.user_id == user_id
        )

        if action_types:
            query = query.filter(FileActivity.action_type.in_(action_types))

        if since:
            query = query.filter(FileActivity.created_at >= since)

        if path_prefix:
            prefix = path_prefix.rstrip("/") + "/"
            query = query.filter(FileActivity.file_path.like(f"{prefix}%"))

        if file_type:
            query = self._apply_file_type_filter(query, file_type)

        total = query.count()

        rows = (
            query.order_by(desc(FileActivity.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        items = [self._to_activity_item(r) for r in rows]
        return items, total

    def get_recent_files(
        self,
        user_id: int,
        *,
        limit: int = 10,
        actions: Optional[List[str]] = None,
    ) -> List[RecentFileItem]:
        """Get recently used *files* (deduplicated by path).

        Returns one entry per unique file with the latest action.
        """
        if actions is None:
            actions = ["file.open", "file.download", "file.upload", "file.edit"]

        # Subquery: latest activity per file_path
        subq = (
            self.db.query(
                FileActivity.file_path,
                func.max(FileActivity.created_at).label("last_at"),
                func.count(FileActivity.id).label("cnt"),
            )
            .filter(
                FileActivity.user_id == user_id,
                FileActivity.action_type.in_(actions),
            )
            .group_by(FileActivity.file_path)
            .subquery()
        )

        # Join back to get full row for each latest activity
        rows = (
            self.db.query(FileActivity, subq.c.cnt)
            .join(
                subq,
                and_(
                    FileActivity.file_path == subq.c.file_path,
                    FileActivity.created_at == subq.c.last_at,
                ),
            )
            .filter(
                FileActivity.user_id == user_id,
                FileActivity.action_type.in_(actions),
            )
            .order_by(desc(subq.c.last_at))
            .limit(limit)
            .all()
        )

        results: list[RecentFileItem] = []
        seen_paths: set[str] = set()
        for activity, count in rows:
            if activity.file_path in seen_paths:
                continue
            seen_paths.add(activity.file_path)
            results.append(
                RecentFileItem(
                    file_path=activity.file_path,
                    file_name=activity.file_name,
                    is_directory=activity.is_directory,
                    file_size=activity.file_size,
                    mime_type=activity.mime_type,
                    last_action=activity.action_type,
                    last_action_at=activity.created_at,
                    action_count=count,
                )
            )

        return results

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def cleanup(self) -> int:
        """Delete activities older than their retention period.

        Returns number of deleted rows.
        """
        now = datetime.now(timezone.utc)
        total_deleted = 0

        # Short-retention actions (7 days)
        if SHORT_RETENTION_ACTIONS:
            cutoff_short = now - timedelta(days=SHORT_RETENTION_DAYS)
            total_deleted += self.db.query(FileActivity).filter(
                FileActivity.action_type.in_(SHORT_RETENTION_ACTIONS),
                FileActivity.created_at < cutoff_short,
            ).delete(synchronize_session="fetch")

        # Default retention (90 days)
        cutoff_default = now - timedelta(days=DEFAULT_RETENTION_DAYS)
        total_deleted += self.db.query(FileActivity).filter(
            FileActivity.created_at < cutoff_default,
        ).delete(synchronize_session="fetch")

        self.db.commit()
        logger.info("File activity cleanup: deleted %d rows", total_deleted)
        return total_deleted

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _to_activity_item(row: FileActivity) -> ActivityItem:
        metadata = None
        if row.metadata_json:
            try:
                metadata = json.loads(row.metadata_json)
            except (json.JSONDecodeError, TypeError):
                pass

        return ActivityItem(
            id=row.id,
            action_type=row.action_type,
            file_path=row.file_path,
            file_name=row.file_name,
            is_directory=row.is_directory,
            file_size=row.file_size,
            mime_type=row.mime_type,
            source=row.source,
            device_id=row.device_id,
            metadata=metadata,
            created_at=row.created_at,
        )

    @staticmethod
    def _apply_file_type_filter(query, file_type: str):
        """Apply a high-level file type filter."""
        mime_map = {
            "image": "image/%",
            "video": "video/%",
            "document": "application/pdf",  # simplified
        }
        if file_type == "file":
            query = query.filter(FileActivity.is_directory.is_(False))
        elif file_type == "directory":
            query = query.filter(FileActivity.is_directory.is_(True))
        elif file_type in mime_map:
            query = query.filter(
                FileActivity.mime_type.like(mime_map[file_type])
            )
        return query


# ---------------------------------------------------------------------------
# Fire-and-forget helper for use in route handlers
# ---------------------------------------------------------------------------
def track_activity(
    user_id: int,
    action_type: str,
    file_path: str,
    file_name: Optional[str] = None,
    *,
    is_directory: bool = False,
    file_size: Optional[int] = None,
    mime_type: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    device_id: Optional[str] = None,
    source: str = "server",
) -> None:
    """Record a file activity in a background task (fire-and-forget).

    Creates its own DB session so it does not interfere with the
    caller's transaction.
    """
    import asyncio

    if file_name is None:
        file_name = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path

    kw: Dict[str, Any] = {
        "is_directory": is_directory,
        "file_size": file_size,
        "mime_type": mime_type,
        "metadata": metadata,
        "device_id": device_id,
        "source": source,
    }

    async def _do_track() -> None:
        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            svc = FileActivityService(db)
            svc.record_and_commit(
                user_id, action_type, file_path, file_name, **kw
            )
        except Exception:
            logger.debug("Background activity tracking failed", exc_info=True)
            db.rollback()
        finally:
            db.close()

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_do_track())
    except RuntimeError:
        # No event loop — fall back to synchronous recording
        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            svc = FileActivityService(db)
            svc.record_and_commit(
                user_id, action_type, file_path, file_name, **kw
            )
        except Exception:
            logger.debug("Sync activity tracking failed", exc_info=True)
            db.rollback()
        finally:
            db.close()
