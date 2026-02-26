"""VCL File Tracking Service.

Manages per-file/pattern tracking rules for automatic/manual VCL modes.
In automatic mode: all files are versioned except excluded ones.
In manual mode: only explicitly tracked files are versioned.
"""
import fnmatch
import time
from typing import Optional, Dict, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.vcl import VCLSettings, VCLFileTracking
from app.models.file_metadata import FileMetadata


# Simple in-memory cache for user tracking rules
_rules_cache: Dict[int, Tuple[float, list]] = {}  # user_id -> (timestamp, rules)
_CACHE_TTL = 30  # seconds


def _invalidate_cache(user_id: int) -> None:
    """Remove cached rules for a user."""
    _rules_cache.pop(user_id, None)


class VCLTrackingService:
    """Manages VCL file tracking rules per user."""

    def __init__(self, db: Session):
        self.db = db

    def _get_user_mode(self, user_id: int) -> str:
        """Get VCL mode for user ('automatic' or 'manual')."""
        settings = self.db.query(VCLSettings.vcl_mode).filter(
            VCLSettings.user_id == user_id
        ).first()
        return str(settings[0]) if settings else "automatic"

    def _get_rules_cached(self, user_id: int) -> list:
        """Get tracking rules for user with caching."""
        now = time.time()
        cached = _rules_cache.get(user_id)
        if cached and (now - cached[0]) < _CACHE_TTL:
            return cached[1]

        rules = (
            self.db.query(VCLFileTracking)
            .filter(VCLFileTracking.user_id == user_id)
            .all()
        )
        _rules_cache[user_id] = (now, rules)
        return rules

    def is_file_tracked(self, file: FileMetadata, user_id: int) -> bool:
        """Check if a file should be versioned based on tracking rules.

        Resolution order:
        1. Explicit file_id match
        2. Parent directory rules (walk path upward)
        3. Glob pattern matches
        4. Default based on vcl_mode (automatic=True, manual=False)
        """
        mode = self._get_user_mode(user_id)
        rules = self._get_rules_cached(user_id)

        if not rules:
            # No rules: automatic means track everything, manual means track nothing
            return mode == "automatic"

        file_path = str(file.path)
        file_id_val = int(file.id) if file.id else None  # type: ignore

        # 1. Explicit file_id match
        for rule in rules:
            if rule.file_id and file_id_val and int(rule.file_id) == file_id_val:
                return str(rule.action) == "track"

        # 2. Parent directory rules (walk upward)
        path_parts = file_path.split("/")
        for i in range(len(path_parts) - 1, 0, -1):
            parent_path = "/".join(path_parts[:i])
            for rule in rules:
                if rule.file_id and rule.is_directory:
                    # Check if this rule's file is a parent directory
                    rule_file = self.db.query(FileMetadata.path).filter(
                        FileMetadata.id == rule.file_id
                    ).first()
                    if rule_file and file_path.startswith(str(rule_file[0]) + "/"):
                        return str(rule.action) == "track"

        # 3. Glob pattern matches (most specific pattern wins)
        for rule in rules:
            pattern = rule.path_pattern
            if not pattern:
                continue
            pattern_str = str(pattern)
            file_name = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
            # Match against both full path and filename
            if fnmatch.fnmatch(file_path, pattern_str) or fnmatch.fnmatch(file_name, pattern_str):
                return str(rule.action) == "track"

        # 4. Default based on mode
        return mode == "automatic"

    def get_tracking_status(self, file_id: int, user_id: int) -> dict:
        """Get tracking status and reason for a file."""
        file = self.db.query(FileMetadata).filter(FileMetadata.id == file_id).first()
        if not file:
            return {"file_id": file_id, "file_path": "", "is_tracked": False, "reason": "File not found"}

        mode = self._get_user_mode(user_id)
        rules = self._get_rules_cached(user_id)
        file_path = str(file.path)
        file_id_val = int(file.id)  # type: ignore

        # Check explicit file_id match
        for rule in rules:
            if rule.file_id and int(rule.file_id) == file_id_val:
                action = str(rule.action)
                return {
                    "file_id": file_id,
                    "file_path": file_path,
                    "is_tracked": action == "track",
                    "reason": f"Explicit {action} rule",
                }

        # Check directory rules
        for rule in rules:
            if rule.file_id and rule.is_directory:
                rule_file = self.db.query(FileMetadata.path).filter(
                    FileMetadata.id == rule.file_id
                ).first()
                if rule_file and file_path.startswith(str(rule_file[0]) + "/"):
                    action = str(rule.action)
                    return {
                        "file_id": file_id,
                        "file_path": file_path,
                        "is_tracked": action == "track",
                        "reason": f"Inherited from directory rule ({rule_file[0]})",
                    }

        # Check pattern matches
        file_name = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
        for rule in rules:
            pattern = rule.path_pattern
            if not pattern:
                continue
            pattern_str = str(pattern)
            if fnmatch.fnmatch(file_path, pattern_str) or fnmatch.fnmatch(file_name, pattern_str):
                action = str(rule.action)
                return {
                    "file_id": file_id,
                    "file_path": file_path,
                    "is_tracked": action == "track",
                    "reason": f"Pattern match: {pattern_str}",
                }

        # Default
        is_tracked = mode == "automatic"
        return {
            "file_id": file_id,
            "file_path": file_path,
            "is_tracked": is_tracked,
            "reason": f"Default ({mode} mode)",
        }

    def set_file_tracking(
        self, user_id: int, file_id: int, action: str, is_directory: bool = False
    ) -> VCLFileTracking:
        """Set tracking rule for a specific file/directory."""
        existing = self.db.query(VCLFileTracking).filter(
            VCLFileTracking.user_id == user_id,
            VCLFileTracking.file_id == file_id,
        ).first()

        if existing:
            existing.action = action  # type: ignore
            existing.is_directory = is_directory  # type: ignore
        else:
            existing = VCLFileTracking(
                user_id=user_id,
                file_id=file_id,
                action=action,
                is_directory=is_directory,
            )
            self.db.add(existing)

        self.db.flush()
        _invalidate_cache(user_id)
        return existing

    def remove_file_tracking(self, user_id: int, rule_id: int) -> bool:
        """Remove a tracking rule by ID."""
        deleted = self.db.query(VCLFileTracking).filter(
            VCLFileTracking.id == rule_id,
            VCLFileTracking.user_id == user_id,
        ).delete(synchronize_session=False)
        if deleted:
            _invalidate_cache(user_id)
        return deleted > 0

    def add_pattern_rule(self, user_id: int, pattern: str, action: str) -> VCLFileTracking:
        """Add a glob pattern rule."""
        rule = VCLFileTracking(
            user_id=user_id,
            path_pattern=pattern,
            action=action,
        )
        self.db.add(rule)
        self.db.flush()
        _invalidate_cache(user_id)
        return rule

    def get_user_tracking_rules(self, user_id: int) -> list:
        """Get all tracking rules for a user."""
        return (
            self.db.query(VCLFileTracking)
            .filter(VCLFileTracking.user_id == user_id)
            .order_by(VCLFileTracking.created_at.desc())
            .all()
        )

    def cleanup_for_transferred_files(
        self, old_owner_id: int, file_ids: list[int]
    ) -> int:
        """Remove tracking entries for files that were transferred away."""
        deleted = self.db.query(VCLFileTracking).filter(
            VCLFileTracking.user_id == old_owner_id,
            VCLFileTracking.file_id.in_(file_ids),
        ).delete(synchronize_session=False)
        if deleted:
            _invalidate_cache(old_owner_id)
        return deleted
