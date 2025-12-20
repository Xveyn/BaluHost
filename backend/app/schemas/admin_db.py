from typing import List, Optional, Any
from pydantic import BaseModel


class AdminTablesResponse(BaseModel):
    tables: List[str]


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
