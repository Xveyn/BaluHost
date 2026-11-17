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

Any API process can serve any step: the session lives on disk
(`services/files/chunked_upload.py`), not in the memory of the worker that
handled ``init``. That session file is input, not a credential — every step
checks the authenticated user against it, and ``complete`` validates target
and file name again before it moves anything.
"""

import asyncio
import logging
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.exceptions import InsufficientStorageError
from app.schemas.user import UserPublic
from app.services import upload_activity
from app.services.files.chunked_upload import (
    ChunkedUploadSession,
    CompletedUpload,
    get_chunked_upload_manager,
    move_completed_upload,
)
from app.services.files.operations import (
    ROOT_DIR,
    FileAccessError,
    _resolve_path,
    _schedule_vcl_version,
    calculate_available_bytes_async,
    get_owner,
    is_in_shared_dir,
)
from app.services.files.storage_permissions import ensure_dir_with_permissions
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


def _safe_filename(raw: str) -> str | None:
    """The bare file name in *raw*, or None if there is none to use."""
    name = PurePosixPath(raw).name
    if not name or name in ('.', '..') or "\x00" in name:
        return None
    return name


async def _own_session(upload_id: str, user: UserPublic) -> ChunkedUploadSession:
    """The caller's session, or 404 / 403. Reads the session file off the loop."""
    session = await asyncio.to_thread(get_chunked_upload_manager().get_session, upload_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Upload session not found")
    if session.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not your upload session")
    return session


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
    safe_filename = _safe_filename(payload.filename)
    if safe_filename is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename",
        )

    # Space pre-check (quota-based in dev, real disk space in prod)
    available = await calculate_available_bytes_async()
    if payload.total_size > available:
        raise InsufficientStorageError(
            f"Not enough space. Need {payload.total_size} bytes, available {available}."
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
        upload_id=session.upload_id,
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
    await _own_session(upload_id, user)

    # Reported from whichever worker gets the chunk, before and after it:
    # idle detection must see the upload while the chunk is still coming in.
    upload_activity.touch(upload_id)
    try:
        received = await mgr.write_chunk_stream(upload_id, chunk_index, request.stream())
    except ValueError as exc:
        if await asyncio.to_thread(mgr.get_session, upload_id) is None:
            # The manager closed the session (a chunk beyond the declared
            # size) or an abort got there first: the upload is over.
            await get_upload_progress_manager().fail_unfinished([upload_id], str(exc))
            upload_activity.finish(upload_id)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    upload_activity.touch(upload_id)

    # Update SSE progress — only if this worker holds the progress session
    # (it lives in the memory of the worker that handled `init`).
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
    session = await _own_session(upload_id, user)
    progress_mgr = get_upload_progress_manager()

    try:
        # The session file is not trusted (see module docstring): validate
        # what it says about the destination exactly as `init` did, against
        # the user making THIS request and the permissions of right now.
        filename = _safe_filename(session.filename)
        if filename is None or filename != session.filename:
            await mgr.abort_session(upload_id)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
        try:
            target_path = _validate_target(session.target_path, user, db)
        except (PermissionDeniedError, FileAccessError) as exc:
            await mgr.abort_session(upload_id)
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        except HTTPException:
            await mgr.abort_session(upload_id)
            raise

        return await _finalise(upload_id, user, target_path, filename)
    except BaseException:
        # However this ends, the progress session must not stay "uploading".
        await progress_mgr.fail_unfinished([upload_id], "Upload failed")
        raise
    finally:
        # ... and the upload is over for idle detection and the status bar,
        # on whichever worker `init` and the chunks were served.
        upload_activity.finish(upload_id)


async def _finalise(
    upload_id: str,
    user: UserPublic,
    target_path: str,
    filename: str,
) -> ChunkedCompleteResponse:
    """Close the session and move its data to *target_path* / *filename*.

    Both are validated by the caller.
    """
    mgr = get_chunked_upload_manager()
    try:
        completed = await mgr.complete_session_checked(upload_id)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        return await _move_into_place(upload_id, user, target_path, filename, completed)
    finally:
        # Moved on success. After a failure nothing refers to the data any
        # more — the session is closed — so it goes now, not with the janitor.
        # unlink removes what is at the path itself, never a link's target.
        await asyncio.to_thread(lambda: completed.temp_path.unlink(missing_ok=True))


async def _move_into_place(
    upload_id: str,
    user: UserPublic,
    target_path: str,
    filename: str,
    completed: CompletedUpload,
) -> ChunkedCompleteResponse:
    """Move the received file to its destination; metadata, audit, VCL."""
    temp_path = completed.temp_path
    file_checksum = completed.sha256_hex
    # --- Move temp file to final destination ---
    target_dir = _resolve_path(target_path)
    ensure_dir_with_permissions(target_dir)
    destination = target_dir / filename
    ensure_dir_with_permissions(destination.parent)

    file_size = completed.size

    # Final space check (another upload could have consumed space in between)
    available = await calculate_available_bytes_async()
    existing_size = await asyncio.to_thread(lambda: destination.stat().st_size if destination.exists() else 0)
    needed = file_size - existing_size  # net new bytes (replacing existing file needs less)
    if needed > 0 and needed > available:
        temp_path.unlink(missing_ok=True)
        progress_mgr = get_upload_progress_manager()
        await progress_mgr.fail_upload(upload_id, "Not enough space")
        raise InsufficientStorageError(
            f"Not enough space. Need {needed} bytes, available {available}."
        )

    # Moves the file `complete` checked, or nothing: the upload directory is
    # writable by others, and the path could name something else by now.
    try:
        await asyncio.to_thread(move_completed_upload, completed, destination)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    relative_destination = str(destination.relative_to(ROOT_DIR).as_posix())

    # --- Metadata & audit ---
    from app.services.files import metadata_db as file_metadata_db
    from app.services.audit.logger_db import get_audit_logger_db

    audit = get_audit_logger_db()
    owner_id = user.id

    # Run metadata & audit in thread pool with db=None (own session)
    # to avoid blocking the event loop with synchronous db.commit().
    existing_meta = await asyncio.to_thread(
        file_metadata_db.get_metadata, relative_destination, db=None
    )
    if existing_meta:
        await asyncio.to_thread(
            file_metadata_db.update_metadata,
            relative_destination, size_bytes=file_size, checksum=file_checksum, db=None,
        )
    else:
        await asyncio.to_thread(
            file_metadata_db.create_metadata,
            relative_path=relative_destination,
            name=destination.name,
            owner_id=int(owner_id),
            size_bytes=file_size,
            is_directory=False,
            checksum=file_checksum,
            db=None,
        )

    await asyncio.to_thread(
        audit.log_file_access,
        user=user.username,
        action="upload",
        file_path=relative_destination,
        size_bytes=file_size,
        success=True,
        db=None,
    )

    # VCL: Check if a version is needed (fast), then schedule heavy work
    # in a background task. Skip for large files (>100 MB).
    VCL_SIZE_LIMIT = 100 * 1024 * 1024  # 100 MB
    if file_size <= VCL_SIZE_LIMIT:
        try:
            from app.services.versioning.vcl import VCLService
            file_meta = existing_meta or await asyncio.to_thread(
                file_metadata_db.get_metadata, relative_destination, db=None,
            )
            if file_meta:
                from app.core.database import SessionLocal as _VCLSessionLocal
                def _vcl_check():
                    with _VCLSessionLocal() as vcl_db:
                        return VCLService(vcl_db).should_create_version(
                            file_meta, file_checksum, int(owner_id)
                        )
                should_create, _reason = await asyncio.to_thread(_vcl_check)
                if should_create:
                    _schedule_vcl_version(
                        destination=destination,
                        file_meta_id=file_meta.id,
                        owner_id=int(owner_id),
                        checksum=file_checksum,
                        is_update=bool(existing_meta),
                    )
        except Exception as e:
            logger.warning("VCL check failed for chunked upload: %s", e)
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
    session = await asyncio.to_thread(mgr.get_session, upload_id)
    if session is None:
        # Nothing to abort — and nothing to report: without a session there
        # is no telling whose upload this id would be.
        return {"message": "Upload aborted"}
    if session.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not your upload session")

    await mgr.abort_session(upload_id)

    # Also mark SSE progress as failed (if this worker holds it), and the
    # upload as over for every worker.
    progress_mgr = get_upload_progress_manager()
    await progress_mgr.fail_unfinished([upload_id], "Upload aborted by user")
    upload_activity.finish(upload_id)

    return {"message": "Upload aborted"}
