from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class FileItem(BaseModel):
    name: str
    path: str
    size: int
    type: Literal["file", "directory"]
    modified_at: datetime
    owner_id: str | None = None


class FileListResponse(BaseModel):
    files: list[FileItem]


class FileOperationResponse(BaseModel):
    message: str


class FileUploadResponse(FileOperationResponse):
    uploaded: int


class FolderCreateRequest(BaseModel):
    path: str | None = ""
    name: str


class RenameRequest(BaseModel):
    old_path: str
    new_name: str


class MoveRequest(BaseModel):
    source_path: str
    target_path: str
