from typing import List, Optional
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import inspect, select, Table, MetaData
from sqlalchemy.orm import Session
from starlette import status

from app.api import deps
from app.schemas.admin_db import (
    AdminTablesResponse,
    AdminTableCategoriesResponse,
    AdminTableSchemaResponse,
    AdminTableRowsResponse,
    DatabaseHealthResponse,
    DatabaseInfoResponse,
)
from app.services.admin_db import AdminDBService

router = APIRouter()


@router.get("/admin/db/tables", response_model=AdminTablesResponse, tags=["admin"])
def list_tables(current_user=Depends(deps.get_current_admin)) -> AdminTablesResponse:
    """List whitelisted database tables (admin only)."""
    tables = AdminDBService.list_tables()
    return AdminTablesResponse(tables=tables)


@router.get("/admin/db/tables/categories", response_model=AdminTableCategoriesResponse, tags=["admin"])
def list_table_categories(current_user=Depends(deps.get_current_admin)) -> AdminTableCategoriesResponse:
    """List whitelisted database tables grouped by category (admin only)."""
    categories = AdminDBService.list_tables_with_categories()
    return AdminTableCategoriesResponse(categories=categories)


@router.get("/admin/db/table/{table_name}/schema", response_model=AdminTableSchemaResponse, tags=["admin"])
def table_schema(table_name: str, current_user=Depends(deps.get_current_admin)) -> AdminTableSchemaResponse:
    """Return column metadata for a whitelisted table."""
    try:
        schema = AdminDBService.get_table_schema(table_name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return AdminTableSchemaResponse(table=table_name, columns=schema)


@router.get("/admin/db/table/{table_name}", response_model=AdminTableRowsResponse, tags=["admin"])
def table_rows(
    table_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    fields: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("asc", regex="^(asc|desc)$"),
    filters: Optional[str] = Query(None),
    db: Session = Depends(deps.get_db),
    current_user=Depends(deps.get_current_admin),
) -> AdminTableRowsResponse:
    """Return paginated rows from a whitelisted table.

    - `fields` is a comma-separated list of column names to return.
    - `q` is a simple text filter applied to string columns.
    - `sort_by` is the column name to sort by.
    - `sort_order` is "asc" or "desc".
    - `filters` is a JSON string: {"col": {"op": "contains", "value": "..."}, ...}
    """
    field_list: Optional[List[str]] = None
    if fields:
        field_list = [f.strip() for f in fields.split(",") if f.strip()]

    # Parse filters JSON
    parsed_filters = None
    if filters:
        try:
            parsed_filters = json.loads(filters)
            if not isinstance(parsed_filters, dict):
                raise ValueError("filters must be a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid filters: {exc}")

    try:
        result = AdminDBService.get_table_rows(
            db, table_name,
            page=page,
            page_size=page_size,
            fields=field_list,
            q=q,
            sort_by=sort_by,
            sort_order=sort_order,
            filters=parsed_filters,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return result


@router.get("/admin/db/health", response_model=DatabaseHealthResponse, tags=["admin"])
def database_health(
    db: Session = Depends(deps.get_db),
    current_user=Depends(deps.get_current_admin),
) -> DatabaseHealthResponse:
    """Check database health status (admin only).

    Returns connection status, integrity check (SQLite), or pool status (PostgreSQL).
    """
    result = AdminDBService.get_database_health(db)
    return DatabaseHealthResponse(**result)


@router.get("/admin/db/info", response_model=DatabaseInfoResponse, tags=["admin"])
def database_info(
    db: Session = Depends(deps.get_db),
    current_user=Depends(deps.get_current_admin),
) -> DatabaseInfoResponse:
    """Get database storage information (admin only).

    Returns total size and per-table size estimates.
    """
    result = AdminDBService.get_database_info(db)
    return DatabaseInfoResponse(**result)
