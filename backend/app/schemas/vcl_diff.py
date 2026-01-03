"""VCL Diff Schemas."""
from typing import Optional, List
from pydantic import BaseModel


class DiffLine(BaseModel):
    """Single line in diff."""
    line_number_old: Optional[int] = None
    line_number_new: Optional[int] = None
    content: str
    type: str  # 'added', 'removed', 'unchanged', 'modified'


class VersionDiffResponse(BaseModel):
    """Response for version diff."""
    version_id_old: int
    version_id_new: int
    file_name: str
    is_binary: bool
    old_size: int
    new_size: int
    diff_lines: Optional[List[DiffLine]] = None
    message: Optional[str] = None  # For binary files or errors
