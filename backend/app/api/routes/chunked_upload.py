"""Chunked file upload endpoints.

Large files (>= 50 MB on the client) are uploaded in fixed-size chunks
so that neither the browser nor the backend need to buffer the whole file
in memory at once.

Protocol
--------
1. ``POST /init``         — reserve an upload session
2. ``POST /{id}/chunk``   — send one chunk (sequential, 0-indexed)
3. ``POST /{id}/complete`` — finalise (move temp → target, metadata, audit)
4. ``DELETE /{id}``       — abort and clean up
"""

import logging
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api import deps
from app.core.config import settings
from app.core.database import get_db
from app.schemas.user import UserPublic
from app.services.files.chunked_upload import get_chunked_upload_manager
from app.services.files.operations import (
    ROOT_DIR,
    FileAccessError,
    QuotaExceededError,
    _resolve_path,
    calculate_available_bytes,
    calculate_used_bytes,
    get_owner,
    is_in_shared_dir,
)
from app.services.permissions import PermissionDeniedError, ensure_owner_or_privileged
from app.services.upload_progress import get_upload_progress_manager
from app.core.rate_limiter import user_limiter, get_limit

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChunkedInitRequest(BaseModel):
    filename: str
    total_size: int
    target_path: str = ""          # relative directory inside storage root


class ChunkedInitResponse(BaseModel):
    upload_id: str
    chunk_size: int


class ChunkedChunkResponse(BaseModel):
    received_bytes: int


class ChunkedCompleteResponse(BaseModel):
    path: str
    size: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_target(target_path: str, user: UserPublic, db: Session) -> str:
    """Validate and jail the target path, check permissions.

    Returns the sanitised relative path.
    """
    from app.api.routes.files import _jail_path
    jailed = _jail_path(target_path, user, db)

    # Resolve to make sure it is inside the sandbox
    _resolve_path(jailed)

    # If inside a non-shared directory, enforce ownership
    if jailed and not is_in_shared_dir(jailed):
        dest_owner = get_owner(jailed, db=db)
        ensure_owner_or_privileged(user, dest_owner)

    return jailed


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/upload/chunked/init", response_model=ChunkedInitResponse)
@user_limiter.limit(get_limit("file_chunked"))
async def chunked_init(
    request: Request,
    response: Response,
    payload: ChunkedInitRequest,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> ChunkedInitResponse:
    """Initialise a chunked upload session."""
    try:
        jailed_path = _validate_target(payload.target_path, user, db)
    except PermissionDeniedError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except FileAccessError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    # Sanitize filename: strip all directory components to prevent path traversal
    safe_filename = PurePosixPath(payload.filename).name
    if not safe_filename or safe_filename in ('.', '..'):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename",
        )

    # Space pre-check (quota-based in dev, real disk space in prod)
    available = calculate_available_bytes()
    if payload.total_size > available:
        raise HTTPException(
            status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=f"Not enough space. Need {payload.total_size} bytes, available {available}.",
        )

    mgr = get_chunked_upload_manager()
    session = await mgr.create_session(
        target_path=jailed_path,
        filename=safe_filename,
        total_size=payload.total_size,
        user_id=user.id,
        username=user.username,
    )

    # Also create an SSE progress session so the modal can track it
    progress_mgr = get_upload_progress_manager()
    progress_mgr.create_upload_session(
        filename=safe_filename,
        total_bytes=payload.total_size,
    )

    return ChunkedInitResponse(
        upload_id=session.upload_id,
        chunk_size=session.chunk_size,
    )


@router.post("/upload/chunked/{upload_id}/chunk", response_model=ChunkedChunkResponse)
@user_limiter.limit(get_limit("file_chunked"))
async def chunked_chunk(
    upload_id: str,
    request: Request,
    response: Response,
    chunk_index: int = Query(...),
    user: UserPublic = Depends(deps.get_current_user),
) -> ChunkedChunkResponse:
    """Receive a single chunk and stream it directly to disk.

    The client sends the raw chunk bytes as the request body
    (Content-Type: application/octet-stream) instead of multipart/form-data.
    This avoids buffering the entire chunk in server RAM.
    """
    mgr = get_chunked_upload_manager()
    session = mgr.get_session(upload_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Upload session not found")

    # Verify the session belongs to this user
    if session.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not your upload session")

    try:
        received = await mgr.write_chunk_stream(upload_id, chunk_index, request.stream())
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Update SSE progress
    progress_mgr = get_upload_progress_manager()
    progress = progress_mgr.get_progress(upload_id)
    if progress is not None:
        await progress_mgr.update_progress(upload_id, received)

    return ChunkedChunkResponse(received_bytes=received)


@router.post("/upload/chunked/{upload_id}/complete", response_model=ChunkedCompleteResponse)
@user_limiter.limit(get_limit("file_chunked"))
async def chunked_complete(
    request: Request,
    response: Response,
    upload_id: str,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> ChunkedCompleteResponse:
    """Finalise a chunked upload: move temp file to target, create metadata."""
    mgr = get_chunked_upload_manager()
    session = mgr.get_session(upload_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Upload session not found")
    if session.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not your upload session")

    try:
        temp_path = await mgr.complete_session(upload_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # --- Move temp file to final destination ---
    target_dir = _resolve_path(session.target_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / session.filename
    destination.parent.mkdir(parents=True, exist_ok=True)

    file_size = temp_path.stat().st_size

    # Final space check (another upload could have consumed space in between)
    available = calculate_available_bytes()
    existing_size = destination.stat().st_size if destination.exists() else 0
    needed = file_size - existing_size  # net new bytes (replacing existing file needs less)
    if needed > 0 and needed > available:
        temp_path.unlink(missing_ok=True)
        progress_mgr = get_upload_progress_manager()
        await progress_mgr.fail_upload(upload_id, "Not enough space")
        raise HTTPException(
            status.HTTP_507_INSUFFICIENT_STORAGE,
            detail=f"Not enough space. Need {needed} bytes, available {available}.",
        )

    import shutil
    import hashlib
    shutil.move(str(temp_path), str(destination))

    relative_destination = str(destination.relative_to(ROOT_DIR).as_posix())

    # --- Compute SHA-256 checksum ---
    sha256 = hashlib.sha256()
    with open(destination, 'rb') as f:
        while True:
            chunk = f.read(8 * 1024 * 1024)
            if not chunk:
                break
            sha256.update(chunk)
    file_checksum = sha256.hexdigest()

    # --- Metadata & audit ---
    from app.services.files import metadata_db as file_metadata_db
    from app.services.audit.logger_db import get_audit_logger_db

    audit = get_audit_logger_db()
    owner_id = user.id

    existing_meta = file_metadata_db.get_metadata(relative_destination, db=db)
    if existing_meta:
        file_metadata_db.update_metadata(relative_destination, size_bytes=file_size, checksum=file_checksum, db=db)
    else:
        file_metadata_db.create_metadata(
            relative_path=relative_destination,
            name=destination.name,
            owner_id=int(owner_id),
            size_bytes=file_size,
            is_directory=False,
            checksum=file_checksum,
            db=db,
        )

    audit.log_file_access(
        user=user.username,
        action="upload",
        file_path=relative_destination,
        size_bytes=file_size,
        success=True,
        db=db,
    )

    # VCL: create version from file on disk.
    # Skip VCL for large files (>100 MB) to avoid reading the entire file into RAM.
    VCL_SIZE_LIMIT = 100 * 1024 * 1024  # 100 MB
    if file_size <= VCL_SIZE_LIMIT:
        try:
            from app.services.versioning.vcl import VCLService
            vcl_service = VCLService(db)
            file_meta = existing_meta or file_metadata_db.get_metadata(relative_destination, db=db)
            if file_meta:
                checksum = VCLService.calculate_checksum_from_file(destination)
                should_create, _reason = vcl_service.should_create_version(file_meta, checksum, int(owner_id))
                if should_create:
                    content = destination.read_bytes()
                    change_type = "update" if existing_meta else "create"
                    vcl_service.create_version(
                        file=file_meta,
                        content=content,
                        user_id=int(owner_id),
                        checksum=checksum,
                        change_type=change_type,
                    )
                    db.commit()
        except Exception as e:
            logger.warning("VCL version creation failed for chunked upload: %s", e)
    else:
        logger.info("Skipping VCL for large file (%d bytes > %d limit)", file_size, VCL_SIZE_LIMIT)

    # Mark SSE progress as completed
    progress_mgr = get_upload_progress_manager()
    await progress_mgr.complete_upload(upload_id)

    # Emit plugin hook
    from app.plugins.emit import emit_hook
    emit_hook("on_file_uploaded", path=relative_destination, user_id=user.id, size=file_size, content_type=None)

    return ChunkedCompleteResponse(path=relative_destination, size=file_size)


@router.delete("/upload/chunked/{upload_id}")
@user_limiter.limit(get_limit("file_chunked"))
async def chunked_abort(
    request: Request,
    response: Response,
    upload_id: str,
    user: UserPublic = Depends(deps.get_current_user),
) -> dict:
    """Abort an in-progress chunked upload and clean up temp files."""
    mgr = get_chunked_upload_manager()
    session = mgr.get_session(upload_id)
    if session is not None and session.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not your upload session")

    await mgr.abort_session(upload_id)

    # Also mark SSE progress as failed
    progress_mgr = get_upload_progress_manager()
    await progress_mgr.fail_upload(upload_id, "Upload aborted by user")

    return {"message": "Upload aborted"}
