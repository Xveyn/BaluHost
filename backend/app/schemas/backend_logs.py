"""Pydantic schemas for backend application log streaming."""

from typing import List, Optional

from pydantic import BaseModel, Field


class LogEntryResponse(BaseModel):
    """A single buffered log entry."""
    id: int = Field(..., description="Monotonic log entry ID")
    timestamp: str = Field(..., description="ISO 8601 timestamp (UTC)")
    level: str = Field(..., description="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    logger_name: str = Field(..., description="Python logger name (e.g. 'app.services.files')")
    message: str = Field(..., description="Log message (sensitive values redacted)")
    exc_info: Optional[str] = Field(None, description="Exception traceback if present")


class BackendLogsResponse(BaseModel):
    """Response for the backend logs history endpoint."""
    entries: List[LogEntryResponse] = Field(default_factory=list, description="Log entries matching filters")
    latest_id: int = Field(0, description="ID of the most recent entry in the buffer")
    total_buffered: int = Field(0, description="Total entries currently in the ring buffer")
