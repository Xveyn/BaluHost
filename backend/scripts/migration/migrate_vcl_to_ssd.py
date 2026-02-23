#!/usr/bin/env python3
"""
VCL Blob Storage Migration: HDD -> SSD

Migriert VCL-Blob-Dateien von der HDD auf die SSD und aktualisiert
die Datenbank-Pfade entsprechend. Resumable und verifizierbar.

Usage:
    # Dry-run (keine Aenderungen)
    python migrate_vcl_to_ssd.py --source /mnt/md1/.system/versions \
                                  --dest /mnt/cache-vcl/vcl --dry-run

    # Migration ausfuehren
    python migrate_vcl_to_ssd.py --source /mnt/md1/.system/versions \
                                  --dest /mnt/cache-vcl/vcl

    # Migration + Integritaetspruefung
    python migrate_vcl_to_ssd.py --source /mnt/md1/.system/versions \
                                  --dest /mnt/cache-vcl/vcl --verify

    # Nach erfolgreicher Migration: Quelldateien loeschen
    python migrate_vcl_to_ssd.py --source /mnt/md1/.system/versions \
                                  --dest /mnt/cache-vcl/vcl --cleanup

Requires:
    DATABASE_URL environment variable or .env file with database connection.
"""

import argparse
import hashlib
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

# Add backend to path for imports
_script_dir = Path(__file__).resolve().parent
_backend_dir = _script_dir.parent.parent
sys.path.insert(0, str(_backend_dir))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _sha256_file(path: Path) -> str:
    """Calculate SHA256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _get_db_session():
    """Create a database session using app config."""
    os.environ.setdefault("SKIP_APP_INIT", "1")

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings

    db_url = settings.database_url
    if not db_url:
        if settings.database_type == "sqlite":
            db_url = "sqlite:///./baluhost.db"
        else:
            raise RuntimeError(
                "DATABASE_URL not set. Provide it via environment variable or .env file."
            )

    engine = create_engine(str(db_url))
    Session = sessionmaker(bind=engine)
    return Session()


def migrate_blobs(
    source: Path,
    dest: Path,
    dry_run: bool = False,
) -> dict:
    """
    Copy blob files from source to dest.

    Resumable: skips files that already exist at dest with matching size.

    Returns:
        Summary dict with copied, skipped, failed counts and total bytes.
    """
    source_blobs = source / "blobs"
    dest_blobs = dest / "blobs"

    if not source_blobs.exists():
        logger.error("Source blobs directory not found: %s", source_blobs)
        return {"copied": 0, "skipped": 0, "failed": 0, "total_bytes": 0}

    if not dry_run:
        dest_blobs.mkdir(parents=True, exist_ok=True)

    blob_files = sorted(source_blobs.glob("*.gz"))
    total = len(blob_files)
    logger.info("Found %d blob files in %s", total, source_blobs)

    copied = 0
    skipped = 0
    failed = 0
    total_bytes = 0

    for i, src_file in enumerate(blob_files, 1):
        dst_file = dest_blobs / src_file.name
        src_size = src_file.stat().st_size
        total_bytes += src_size

        # Resumable: skip if dest already exists with same size
        if dst_file.exists() and dst_file.stat().st_size == src_size:
            skipped += 1
            if i % 100 == 0:
                logger.info(
                    "  Progress: %d/%d (copied=%d, skipped=%d)", i, total, copied, skipped
                )
            continue

        if dry_run:
            copied += 1
            continue

        try:
            shutil.copy2(str(src_file), str(dst_file))
            copied += 1
        except OSError as e:
            logger.error("  Failed to copy %s: %s", src_file.name, e)
            failed += 1

        if i % 100 == 0:
            logger.info(
                "  Progress: %d/%d (copied=%d, skipped=%d, failed=%d)",
                i, total, copied, skipped, failed,
            )

    logger.info(
        "Blob copy %s: copied=%d, skipped=%d, failed=%d, total_bytes=%d",
        "simulated (dry-run)" if dry_run else "complete",
        copied, skipped, failed, total_bytes,
    )
    return {
        "copied": copied,
        "skipped": skipped,
        "failed": failed,
        "total_bytes": total_bytes,
    }


def update_db_paths(
    source: Path,
    dest: Path,
    dry_run: bool = False,
) -> int:
    """
    Bulk update VersionBlob.storage_path in the database.

    Replaces the source prefix with dest prefix for all matching blobs.

    Returns:
        Number of rows updated.
    """
    db = _get_db_session()
    try:
        from app.models.vcl import VersionBlob

        source_prefix = str(source)
        dest_prefix = str(dest)

        # Find all blobs with source prefix
        blobs = (
            db.query(VersionBlob)
            .filter(VersionBlob.storage_path.like(f"{source_prefix}%"))
            .all()
        )

        count = len(blobs)
        logger.info("Found %d blobs with source prefix '%s'", count, source_prefix)

        if dry_run:
            # Show a few examples
            for blob in blobs[:5]:
                old_path = str(blob.storage_path)
                new_path = old_path.replace(source_prefix, dest_prefix, 1)
                logger.info("  [DRY-RUN] %s -> %s", old_path, new_path)
            if count > 5:
                logger.info("  ... and %d more", count - 5)
            return count

        updated = 0
        for blob in blobs:
            old_path = str(blob.storage_path)
            new_path = old_path.replace(source_prefix, dest_prefix, 1)
            blob.storage_path = new_path
            updated += 1

        db.commit()
        logger.info("Updated %d blob paths in database", updated)
        return updated
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def verify_migration(dest: Path) -> dict:
    """
    Verify migration integrity: cross-check DB paths vs filesystem.

    For each blob in the DB with the dest prefix, checks:
    - File exists on disk
    - File size matches DB compressed_size

    Returns:
        Summary dict with verified, missing, size_mismatch counts.
    """
    db = _get_db_session()
    try:
        from app.models.vcl import VersionBlob

        dest_prefix = str(dest)
        blobs = (
            db.query(VersionBlob)
            .filter(VersionBlob.storage_path.like(f"{dest_prefix}%"))
            .all()
        )

        total = len(blobs)
        logger.info("Verifying %d blobs at destination '%s'", total, dest_prefix)

        verified = 0
        missing = 0
        size_mismatch = 0
        errors = []

        for blob in blobs:
            blob_path = Path(str(blob.storage_path))
            if not blob_path.exists():
                missing += 1
                errors.append(f"MISSING: {blob_path}")
                continue

            disk_size = blob_path.stat().st_size
            db_size = int(blob.compressed_size)
            if disk_size != db_size:
                size_mismatch += 1
                errors.append(
                    f"SIZE_MISMATCH: {blob_path} (disk={disk_size}, db={db_size})"
                )
                continue

            verified += 1

        # Print errors
        for err in errors[:20]:
            logger.warning("  %s", err)
        if len(errors) > 20:
            logger.warning("  ... and %d more errors", len(errors) - 20)

        result = {
            "total": total,
            "verified": verified,
            "missing": missing,
            "size_mismatch": size_mismatch,
        }

        if missing == 0 and size_mismatch == 0:
            logger.info("Verification PASSED: all %d blobs verified", verified)
        else:
            logger.error(
                "Verification FAILED: verified=%d, missing=%d, size_mismatch=%d",
                verified, missing, size_mismatch,
            )

        return result
    finally:
        db.close()


def cleanup_source(source: Path, dry_run: bool = False) -> int:
    """
    Remove blob files from source that have been successfully migrated.

    Only removes files that exist at the destination with matching size.
    Requires explicit --cleanup flag (never called by default).

    Returns:
        Number of files removed.
    """
    source_blobs = source / "blobs"
    if not source_blobs.exists():
        logger.info("Source blobs directory does not exist, nothing to clean up")
        return 0

    # We need the dest path to verify before deleting
    # This is called after migration, so we read dest from DB
    db = _get_db_session()
    try:
        from app.models.vcl import VersionBlob

        # Get all blobs to find destination prefix
        first_blob = db.query(VersionBlob).first()
        if not first_blob:
            logger.info("No blobs in database, nothing to clean up")
            return 0

        dest_prefix = str(first_blob.storage_path)
        # Derive dest blobs dir from first blob path
        dest_blobs = Path(dest_prefix).parent
    finally:
        db.close()

    blob_files = sorted(source_blobs.glob("*.gz"))
    total = len(blob_files)
    logger.info(
        "Cleanup: checking %d source blob files against dest '%s'", total, dest_blobs
    )

    removed = 0
    kept = 0

    for src_file in blob_files:
        dst_file = dest_blobs / src_file.name
        src_size = src_file.stat().st_size

        # Only remove if dest exists with matching size
        if dst_file.exists() and dst_file.stat().st_size == src_size:
            if dry_run:
                removed += 1
            else:
                try:
                    src_file.unlink()
                    removed += 1
                except OSError as e:
                    logger.error("  Failed to remove %s: %s", src_file.name, e)
                    kept += 1
        else:
            kept += 1
            logger.warning(
                "  Kept %s (dest missing or size mismatch)", src_file.name
            )

    logger.info(
        "Cleanup %s: removed=%d, kept=%d",
        "simulated (dry-run)" if dry_run else "complete",
        removed, kept,
    )
    return removed


def main():
    parser = argparse.ArgumentParser(
        description="Migrate VCL blob storage from HDD to SSD",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry-run to see what would happen
  python migrate_vcl_to_ssd.py --source /mnt/md1/.system/versions \\
                                --dest /mnt/cache-vcl/vcl --dry-run

  # Perform migration
  python migrate_vcl_to_ssd.py --source /mnt/md1/.system/versions \\
                                --dest /mnt/cache-vcl/vcl

  # Verify after migration
  python migrate_vcl_to_ssd.py --source /mnt/md1/.system/versions \\
                                --dest /mnt/cache-vcl/vcl --verify

  # Cleanup source after verification
  python migrate_vcl_to_ssd.py --source /mnt/md1/.system/versions \\
                                --dest /mnt/cache-vcl/vcl --cleanup
        """,
    )
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Source VCL storage path (e.g. /mnt/md1/.system/versions)",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        required=True,
        help="Destination SSD storage path (e.g. /mnt/cache-vcl/vcl)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate migration without making changes",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify migration integrity (DB paths vs filesystem)",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove source blobs after successful migration (requires verification first)",
    )
    parser.add_argument(
        "--skip-copy",
        action="store_true",
        help="Skip file copy step (only update DB paths)",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Skip DB path update step (only copy files)",
    )

    args = parser.parse_args()

    prefix = "[DRY-RUN] " if args.dry_run else ""
    logger.info("%s=== VCL Blob Migration: HDD -> SSD ===", prefix)
    logger.info("Source: %s", args.source)
    logger.info("Dest:   %s", args.dest)

    # Validate paths
    if not args.source.exists():
        logger.error("Source path does not exist: %s", args.source)
        sys.exit(1)

    if not args.dry_run and not args.verify:
        # Check dest is writable
        try:
            args.dest.mkdir(parents=True, exist_ok=True)
            test_file = args.dest / ".migration_test"
            test_file.write_text("test")
            test_file.unlink()
        except OSError as e:
            logger.error("Destination path not writable: %s (%s)", args.dest, e)
            sys.exit(1)

    # Check available space
    if not args.dry_run and not args.skip_copy and not args.verify and not args.cleanup:
        source_blobs = args.source / "blobs"
        if source_blobs.exists():
            source_size = sum(f.stat().st_size for f in source_blobs.glob("*.gz"))
            dest_usage = shutil.disk_usage(str(args.dest))
            headroom = int(source_size * 1.05)  # 5% headroom

            logger.info(
                "Source size: %.2f GB, Dest available: %.2f GB",
                source_size / (1024**3),
                dest_usage.free / (1024**3),
            )

            if dest_usage.free < headroom:
                logger.error(
                    "Insufficient space at destination. Need %.2f GB, have %.2f GB",
                    headroom / (1024**3),
                    dest_usage.free / (1024**3),
                )
                sys.exit(1)

    start_time = time.time()

    if args.cleanup:
        # Cleanup mode
        if args.dry_run:
            logger.info("--- Simulating cleanup ---")
        else:
            logger.info("--- Cleaning up source blobs ---")
            logger.warning(
                "This will DELETE source blob files! Press Ctrl+C within 5s to abort."
            )
            try:
                time.sleep(5)
            except KeyboardInterrupt:
                logger.info("Aborted by user.")
                sys.exit(0)

        removed = cleanup_source(args.source, dry_run=args.dry_run)
        logger.info("Cleanup result: %d files removed", removed)

    elif args.verify:
        # Verify-only mode
        logger.info("--- Verifying migration ---")
        result = verify_migration(args.dest)
        if result["missing"] > 0 or result["size_mismatch"] > 0:
            sys.exit(1)

    else:
        # Migration mode
        copy_result = {"copied": 0, "skipped": 0, "failed": 0}
        db_updated = 0

        if not args.skip_copy:
            logger.info("--- Step 1/2: Copying blob files ---")
            copy_result = migrate_blobs(args.source, args.dest, dry_run=args.dry_run)

            if copy_result["failed"] > 0 and not args.dry_run:
                logger.error(
                    "%d files failed to copy. Fix issues and re-run (resumable).",
                    copy_result["failed"],
                )
                sys.exit(1)

        if not args.skip_db:
            logger.info("--- Step 2/2: Updating database paths ---")
            db_updated = update_db_paths(args.source, args.dest, dry_run=args.dry_run)

        elapsed = time.time() - start_time
        logger.info("--- Migration %s ---", "simulated" if args.dry_run else "complete")
        logger.info("Files copied:  %d", copy_result["copied"])
        logger.info("Files skipped: %d (already at dest)", copy_result["skipped"])
        logger.info("DB rows updated: %d", db_updated)
        logger.info("Duration: %.1fs", elapsed)

        if not args.dry_run:
            logger.info("")
            logger.info("Next steps:")
            logger.info("  1. Set VCL_STORAGE_PATH=%s in .env.production", args.dest)
            logger.info("  2. Restart backend: sudo systemctl restart baluhost-backend")
            logger.info(
                "  3. Verify: python %s --source %s --dest %s --verify",
                __file__, args.source, args.dest,
            )
            logger.info(
                "  4. Cleanup (optional): python %s --source %s --dest %s --cleanup",
                __file__, args.source, args.dest,
            )


if __name__ == "__main__":
    main()
