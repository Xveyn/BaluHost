from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.api import deps
from app.schemas.files import (
    FileListResponse,
    FileOperationResponse,
    FileUploadResponse,
    FolderCreateRequest,
    MoveRequest,
    RenameRequest,
)
from app.schemas.user import UserPublic
from app.services import files as file_service
from app.services.permissions import PermissionDeniedError

router = APIRouter()


@router.get("/list", response_model=FileListResponse)
async def list_files(
    path: str = "",
    user: UserPublic = Depends(deps.get_current_user),
) -> FileListResponse:
    try:
        entries = list(file_service.list_directory(path, user=user))
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return FileListResponse(files=entries)


@router.get("/download/{resource_path:path}")
async def download_file(
    resource_path: str,
    user: UserPublic = Depends(deps.get_current_user),
) -> FileResponse:
    try:
        file_service.ensure_can_view(resource_path, user)
        file_path = file_service.get_absolute_path(resource_path)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path=file_path, filename=file_path.name)


@router.post("/upload", response_model=FileUploadResponse)
async def upload_files(
    files: list[UploadFile] = File(...),
    path: str = Form(""),
    user: UserPublic = Depends(deps.get_current_user),
) -> FileUploadResponse:
    # folder_paths is optional and sent as individual form fields
    # FastAPI will collect them automatically if present
    try:
        saved = await file_service.save_uploads(path, files, user=user, folder_paths=None)
    except file_service.QuotaExceededError as exc:
        raise HTTPException(status_code=status.HTTP_507_INSUFFICIENT_STORAGE, detail=str(exc)) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return FileUploadResponse(message="Files uploaded", uploaded=saved)


@router.get("/storage/available")
async def get_available_storage(
    user: UserPublic = Depends(deps.get_current_user),
) -> dict[str, int | None]:
    """Get remaining storage capacity in bytes. Returns None if no quota is set."""
    available = file_service.calculate_available_bytes()
    used = file_service.calculate_used_bytes()
    quota = file_service.settings.nas_quota_bytes
    return {
        "available_bytes": available,
        "used_bytes": used,
        "quota_bytes": quota,
    }


@router.delete("/{resource_path:path}", response_model=FileOperationResponse)
async def delete_path(
    resource_path: str,
    user: UserPublic = Depends(deps.get_current_user),
) -> FileOperationResponse:
    try:
        file_service.delete_path(resource_path, user=user)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return FileOperationResponse(message="Deleted")


@router.post("/folder", response_model=FileOperationResponse)
async def create_folder(
    payload: FolderCreateRequest,
    user: UserPublic = Depends(deps.get_current_user),
) -> FileOperationResponse:
    if not payload.name:
        raise HTTPException(status_code=400, detail="Folder name required")

    try:
        file_service.create_folder(payload.path or "", payload.name, owner=user)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return FileOperationResponse(message="Folder created")


@router.put("/rename", response_model=FileOperationResponse)
async def rename_path(
    payload: RenameRequest,
    user: UserPublic = Depends(deps.get_current_user),
) -> FileOperationResponse:
    try:
        file_service.rename_path(payload.old_path, payload.new_name, user=user)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return FileOperationResponse(message="Renamed")


@router.put("/move", response_model=FileOperationResponse)
async def move_path(
    payload: MoveRequest,
    user: UserPublic = Depends(deps.get_current_user),
) -> FileOperationResponse:
    try:
        file_service.move_path(payload.source_path, payload.target_path, user=user)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return FileOperationResponse(message="Moved")
