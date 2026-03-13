"""Pydantic schemas for Firebase configuration management."""

import json
from typing import Optional
from pydantic import BaseModel, field_validator


class FirebaseStatusResponse(BaseModel):
    """Firebase configuration status (no secrets exposed)."""
    configured: bool
    initialized: bool
    project_id: Optional[str] = None
    client_email: Optional[str] = None
    credentials_source: Optional[str] = None  # "file" | "env_var" | None
    file_exists: bool
    uploaded_at: Optional[str] = None  # ISO timestamp of file mtime
    sdk_installed: bool


class FirebaseUploadRequest(BaseModel):
    """Request to upload Firebase credentials JSON."""
    credentials_json: str

    @field_validator("credentials_json")
    @classmethod
    def validate_credentials_json(cls, v: str) -> str:
        try:
            data = json.loads(v)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")

        required_fields = ["type", "project_id", "private_key", "client_email"]
        missing = [f for f in required_fields if f not in data]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

        if data.get("type") != "service_account":
            raise ValueError("Field 'type' must be 'service_account'")

        return v


class FirebaseUploadResponse(BaseModel):
    """Response after uploading Firebase credentials."""
    success: bool
    project_id: Optional[str] = None
    message: str


class FirebaseDeleteResponse(BaseModel):
    """Response after deleting Firebase credentials."""
    success: bool
    message: str


class FirebaseTestRequest(BaseModel):
    """Request to send a test push notification."""
    device_id: Optional[str] = None  # If None, send to all admin's devices
    title: Optional[str] = None
    body: Optional[str] = None


class FirebaseTestResponse(BaseModel):
    """Response after sending a test notification."""
    success: bool
    message: str
    sent_to: int = 0
    message_id: Optional[str] = None
