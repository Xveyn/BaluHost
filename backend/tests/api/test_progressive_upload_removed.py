"""The progressive-sync upload routes are gone (#632).

/api/sync/upload/* had no client (BaluDesk, BaluApp, web UI, TUI and tray
use none of them) and two access-control gaps: no ownership check on the
upload_id routes, and an unvalidated destination path on /upload/start.
Removing them closes both; hardening an unused feature would only keep
attack surface alive.

The expiry cleanup stays: the scheduler's `upload_cleanup` job still
deletes rows and chunk directories left over from before the removal.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.models.file_metadata import FileMetadata
from app.models.sync_progress import ChunkedUpload
from app.services.sync.progressive import ProgressiveSyncService

UPLOAD_ID = "00000000-0000-4000-8000-000000000632"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/sync/upload/start?device_id=dev-1"),
        ("post", f"/sync/upload/{UPLOAD_ID}/chunk/0?chunk_hash={hashlib.sha256(b'x').hexdigest()}"),
        ("get", f"/sync/upload/{UPLOAD_ID}/progress"),
        ("post", f"/sync/upload/{UPLOAD_ID}/resume"),
        ("delete", f"/sync/upload/{UPLOAD_ID}"),
    ],
)
def test_progressive_upload_routes_no_longer_exist(client, user_headers, method, path):
    kwargs = {"headers": user_headers}
    if path.startswith("/sync/upload/start"):
        kwargs["json"] = {"file_path": "a.bin", "file_name": "a.bin", "total_size": 1}
    if "/chunk/" in path:
        kwargs["files"] = {"chunk_file": ("c", b"x")}

    response = getattr(client, method)(f"{settings.api_prefix}{path}", **kwargs)

    # "Not Found" is FastAPI's answer for a missing route. The old handlers
    # also answered 404 for an unknown upload_id ("Upload not found"), so the
    # status code alone would pass against the vulnerable code.
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


@pytest.mark.parametrize(
    "name", ["start_chunked_upload", "upload_chunk", "get_upload_progress", "resume_upload"]
)
def test_service_has_no_upload_write_path(name):
    """No caller may re-grow the feature through the service either."""
    assert not hasattr(ProgressiveSyncService, name)


def test_expired_leftover_upload_is_still_cleaned_up(db_session, regular_user, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "nas_storage_path", str(tmp_path))
    meta = FileMetadata(
        path="old.bin", name="old.bin", owner_id=regular_user.id,
        size_bytes=1, is_directory=False, mime_type="application/octet-stream",
    )
    db_session.add(meta)
    db_session.flush()
    db_session.add(ChunkedUpload(
        upload_id=UPLOAD_ID, file_metadata_id=meta.id, user_id=regular_user.id,
        device_id="dev-1", file_name="old.bin", file_path="old.bin",
        total_size=1, chunk_size=1, total_chunks=1,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    ))
    db_session.commit()
    chunk_dir = tmp_path / ".chunks" / UPLOAD_ID
    chunk_dir.mkdir(parents=True)
    (chunk_dir / "chunk_000000").write_bytes(b"x")

    ProgressiveSyncService(db_session).cleanup_expired_uploads()

    assert db_session.query(ChunkedUpload).filter_by(upload_id=UPLOAD_ID).first() is None
    assert not chunk_dir.exists()
