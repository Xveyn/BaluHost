"""VCL Ownership Reconciliation Service.

Scans for mismatches between FileVersion.user_id and FileMetadata.owner_id,
and bulk-updates ownership + rebalances quotas.
"""
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func, update as sql_update

from app.models.vcl import FileVersion, VCLSettings
from app.models.file_metadata import FileMetadata
from app.models.user import User


class VCLReconciliation:
    """Admin tool to reconcile VCL version ownership with file ownership."""

    def __init__(self, db: Session):
        self.db = db

    def scan_mismatches(self, user_id: Optional[int] = None) -> list[dict]:
        """Find FileVersions where user_id != file owner_id.

        Returns list of mismatch dicts with file/version/user info.
        """
        query = (
            self.db.query(
                FileVersion.id.label("version_id"),
                FileVersion.file_id,
                FileVersion.version_number,
                FileVersion.user_id.label("version_user_id"),
                FileVersion.compressed_size,
                FileVersion.storage_type,
                FileMetadata.path.label("file_path"),
                FileMetadata.owner_id.label("file_owner_id"),
            )
            .join(FileMetadata, FileVersion.file_id == FileMetadata.id)
            .filter(FileVersion.user_id != FileMetadata.owner_id)
        )

        if user_id is not None:
            query = query.filter(
                (FileVersion.user_id == user_id) | (FileMetadata.owner_id == user_id)
            )

        # Filter out deleted users by joining
        query = query.join(
            User, FileMetadata.owner_id == User.id
        )

        return [row._asdict() for row in query.all()]

    def reconcile(
        self,
        dry_run: bool = True,
        user_id: Optional[int] = None,
        force_over_quota: bool = False,
    ) -> dict:
        """Reconcile version ownership to match file ownership.

        Args:
            dry_run: If True, only preview changes.
            user_id: Scope to a specific user.
            force_over_quota: Allow reconciliation even if it exceeds quota.

        Returns:
            Dict with reconciled_versions, skipped_due_to_quota, quota_transfers, message.
        """
        mismatches = self.scan_mismatches(user_id)

        if not mismatches:
            return {
                "success": True,
                "reconciled_versions": 0,
                "skipped_due_to_quota": 0,
                "quota_transfers": [],
                "message": "No mismatches found",
            }

        # Build username cache
        user_ids = set()
        for m in mismatches:
            user_ids.add(m["version_user_id"])
            user_ids.add(m["file_owner_id"])
        username_map = {
            u.id: u.username
            for u in self.db.query(User.id, User.username).filter(User.id.in_(user_ids)).all()
        }

        # Group by (old_user, new_user) and calculate quota deltas
        # Only 'stored' versions affect quota
        quota_deltas: Dict[int, int] = {}  # user_id -> delta (positive = gaining)
        version_ids_to_update: list[int] = []
        skipped = 0

        for m in mismatches:
            old_uid = m["version_user_id"]
            new_uid = m["file_owner_id"]
            compressed = m["compressed_size"] if m["storage_type"] == "stored" else 0

            if compressed > 0:
                quota_deltas[old_uid] = quota_deltas.get(old_uid, 0) - compressed
                quota_deltas[new_uid] = quota_deltas.get(new_uid, 0) + compressed

            version_ids_to_update.append(m["version_id"])

        # Check quota for receivers if not forcing
        if not force_over_quota:
            # Get settings for users gaining quota
            gaining_users = {uid for uid, delta in quota_deltas.items() if delta > 0}
            settings_map = {
                s.user_id: s
                for s in self.db.query(VCLSettings)
                .filter(VCLSettings.user_id.in_(gaining_users))
                .all()
            }

            skip_user_ids = set()
            for uid in gaining_users:
                s = settings_map.get(uid)
                if s:
                    new_usage = int(s.current_usage_bytes) + quota_deltas[uid]
                    if new_usage > int(s.max_size_bytes):
                        skip_user_ids.add(uid)

            if skip_user_ids:
                # Filter out versions going to over-quota users
                new_version_ids = []
                new_quota_deltas: Dict[int, int] = {}
                for m in mismatches:
                    if m["file_owner_id"] in skip_user_ids:
                        skipped += 1
                        continue
                    new_version_ids.append(m["version_id"])
                    old_uid = m["version_user_id"]
                    new_uid = m["file_owner_id"]
                    compressed = m["compressed_size"] if m["storage_type"] == "stored" else 0
                    if compressed > 0:
                        new_quota_deltas[old_uid] = new_quota_deltas.get(old_uid, 0) - compressed
                        new_quota_deltas[new_uid] = new_quota_deltas.get(new_uid, 0) + compressed

                version_ids_to_update = new_version_ids
                quota_deltas = new_quota_deltas

        # Build quota transfer records
        quota_transfers = []
        # Group transfers by (old, new) pairs
        transfer_map: Dict[tuple, int] = {}
        for m in mismatches:
            if m["version_id"] not in version_ids_to_update:
                continue
            compressed = m["compressed_size"] if m["storage_type"] == "stored" else 0
            if compressed > 0:
                key = (m["version_user_id"], m["file_owner_id"])
                transfer_map[key] = transfer_map.get(key, 0) + compressed

        for (from_uid, to_uid), bytes_transferred in transfer_map.items():
            quota_transfers.append({
                "from_user_id": from_uid,
                "from_username": username_map.get(from_uid, "unknown"),
                "to_user_id": to_uid,
                "to_username": username_map.get(to_uid, "unknown"),
                "bytes_transferred": bytes_transferred,
            })

        reconciled = len(version_ids_to_update)

        if dry_run or reconciled == 0:
            return {
                "success": True,
                "reconciled_versions": reconciled,
                "skipped_due_to_quota": skipped,
                "quota_transfers": quota_transfers,
                "message": f"[DRY RUN] Would reconcile {reconciled} versions"
                if dry_run
                else "No versions to reconcile",
            }

        # Apply changes
        # 1. Update FileVersion.user_id to match file owner
        for m in mismatches:
            if m["version_id"] in version_ids_to_update:
                self.db.execute(
                    sql_update(FileVersion)
                    .where(FileVersion.id == m["version_id"])
                    .values(user_id=m["file_owner_id"])
                )

        # 2. Rebalance VCL quota
        for uid, delta in quota_deltas.items():
            if delta == 0:
                continue
            settings = self.db.query(VCLSettings).filter(
                VCLSettings.user_id == uid
            ).first()
            if settings:
                new_usage = max(0, int(settings.current_usage_bytes) + delta)
                self.db.execute(
                    sql_update(VCLSettings)
                    .where(VCLSettings.user_id == uid)
                    .values(current_usage_bytes=new_usage)
                )
            elif delta > 0:
                # Create settings for user who didn't have one
                from app.services.versioning.vcl import VCLService
                vcl_service = VCLService(self.db)
                new_settings = vcl_service.get_or_create_user_settings(uid)
                new_usage = int(new_settings.current_usage_bytes) + delta
                self.db.execute(
                    sql_update(VCLSettings)
                    .where(VCLSettings.user_id == uid)
                    .values(current_usage_bytes=new_usage)
                )

        self.db.flush()

        return {
            "success": True,
            "reconciled_versions": reconciled,
            "skipped_due_to_quota": skipped,
            "quota_transfers": quota_transfers,
            "message": f"Reconciled {reconciled} versions",
        }
