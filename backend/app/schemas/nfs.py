"""Pydantic models for NFS export management."""
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.services.nfs_service import validate_clients, validate_export_path


class NfsExportBase(BaseModel):
    path: str = Field(default="", description="Path relative to storage root; empty = whole root")
    clients: str = Field(..., description="Allowed clients: IP, CIDR, hostname, or *")
    read_only: bool = False
    root_squash: bool = True
    enabled: bool = True
    comment: Optional[str] = None

    @field_validator("clients")
    @classmethod
    def _validate_clients(cls, v: str) -> str:
        return validate_clients(v)

    @field_validator("path")
    @classmethod
    def _validate_path(cls, v: str) -> str:
        validate_export_path(v)  # raises ValueError on traversal/escape/invalid chars
        return (v or "").strip().strip("/")


class NfsExportCreate(NfsExportBase):
    pass


class NfsExportUpdate(NfsExportBase):
    pass


class NfsExportResponse(BaseModel):
    id: int
    path: str
    clients: str
    read_only: bool
    root_squash: bool
    enabled: bool
    comment: Optional[str] = None
    mount_target: str

    model_config = {"from_attributes": True}


class NfsExportsResponse(BaseModel):
    exports: list[NfsExportResponse]


class NfsStatusResponse(BaseModel):
    is_running: bool
    version: Optional[str] = None
    exports_count: int = 0
