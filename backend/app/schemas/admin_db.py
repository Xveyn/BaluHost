from typing import List, Optional, Any, Dict
from pydantic import BaseModel


class AdminTablesResponse(BaseModel):
    tables: List[str]


class AdminTableCategoriesResponse(BaseModel):
    categories: Dict[str, List[str]]


class AdminTableSchemaField(BaseModel):
    name: str
    type: str
    nullable: bool
    default: Optional[Any]


class AdminTableSchemaResponse(BaseModel):
    table: str
    columns: List[AdminTableSchemaField]


class AdminTableRowsResponse(BaseModel):
    table: str
    page: int
    page_size: int
    rows: List[dict]
    total: Optional[int]
    sort_by: Optional[str] = None
    sort_order: Optional[str] = None


# Database Info (Storage Analysis)
class TableSizeInfo(BaseModel):
    table_name: str
    row_count: int
    estimated_size_bytes: int


class DatabaseInfoResponse(BaseModel):
    database_type: str  # "sqlite" | "postgresql"
    total_size_bytes: int
    tables: List[TableSizeInfo]


# Database Health (Maintenance Tools)
class DatabaseHealthResponse(BaseModel):
    is_healthy: bool
    connection_status: str
    database_type: str
    # SQLite specific
    integrity_check: Optional[str] = None
    # PostgreSQL specific
    pool_size: Optional[int] = None
    pool_checked_in: Optional[int] = None
    pool_checked_out: Optional[int] = None
    pool_overflow: Optional[int] = None
