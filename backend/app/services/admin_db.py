from typing import List, Optional, Dict, Any
import re

from sqlalchemy import inspect, select, Table, MetaData
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core import database


REDACT_PATTERN = re.compile(r"password|secret|token|private_key|api_key", re.IGNORECASE)


class AdminDBService:
    """Service providing safe, read-only access to selected DB metadata and rows.

    This service implements a whitelist of tables and redaction rules. It must
    never execute arbitrary SQL supplied by clients.
    """

    # Default whitelist of tables we allow admins to view. Adjust as needed.
    _WHITELIST = {"users", "file_metadata", "audit_log", "share_link", "file_share", "backup", "vpn"}

    @classmethod
    def list_tables(cls) -> List[str]:
        inspector = inspect(database.engine)
        all_tables = inspector.get_table_names()
        return [t for t in sorted(all_tables) if t in cls._WHITELIST]

    @classmethod
    def get_table_schema(cls, table_name: str) -> List[Dict[str, Any]]:
        if table_name not in cls._WHITELIST:
            raise ValueError(f"Table not allowed: {table_name}")

        inspector = inspect(database.engine)
        try:
            cols = inspector.get_columns(table_name)
        except Exception:
            raise ValueError(f"Table not found: {table_name}")

        schema = []
        for c in cols:
            schema.append({
                "name": c.get("name"),
                "type": str(c.get("type")),
                "nullable": bool(c.get("nullable")),
                "default": c.get("default"),
            })
        return schema

    @classmethod
    def _redact_row(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        out = {}
        for k, v in row.items():
            if REDACT_PATTERN.search(k):
                out[k] = "<redacted>"
            else:
                out[k] = v
        return out

    @classmethod
    def get_table_rows(
        cls,
        db: Session,
        table_name: str,
        page: int = 1,
        page_size: int = 50,
        fields: Optional[List[str]] = None,
        q: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return paginated rows. `fields` restricts returned columns.

        `q` is a simple text match applied across string columns.
        """
        if table_name not in cls._WHITELIST:
            raise ValueError(f"Table not allowed: {table_name}")

        metadata = MetaData()
        try:
            table = Table(table_name, metadata, autoload_with=database.engine)
        except Exception:
            raise ValueError(f"Table not found: {table_name}")

        # Validate requested fields
        available_cols = [c.name for c in table.columns]
        if fields:
            for f in fields:
                if f not in available_cols:
                    raise ValueError(f"Unknown column: {f}")

        offset = (page - 1) * page_size
        stmt = select(table)
        if fields:
            # build select of specific columns
            cols = [table.c[f] for f in fields]
            stmt = select(*cols)

        # Simple text filter: apply ILIKE/%-match on any string-like column
        if q:
            q_clauses = []
            for col in table.columns:
                try:
                    if hasattr(col.type, "python_type") and col.type.python_type is str:
                        q_clauses.append(col.ilike(f"%{q}%"))
                except Exception:
                    # ignore columns that can't be inspected
                    continue
            if q_clauses:
                from sqlalchemy import or_

                stmt = stmt.where(or_(*q_clauses))

        total = None
        try:
            # Count total rows
            from sqlalchemy import func
            count_stmt = select(func.count()).select_from(table)
            if q:
                # Apply same filter to count
                q_clauses = []
                for col in table.columns:
                    try:
                        if hasattr(col.type, "python_type") and col.type.python_type is str:
                            q_clauses.append(col.ilike(f"%{q}%"))
                    except Exception:
                        continue
                if q_clauses:
                    from sqlalchemy import or_
                    count_stmt = count_stmt.where(or_(*q_clauses))
            total = db.execute(count_stmt).scalar()
        except Exception as e:
            # fallback: None
            print(f"[ADMIN_DB] Failed to count rows: {e}")
            total = None

        stmt = stmt.limit(page_size).offset(offset)
        res = db.execute(stmt)
        rows = []
        for r in res.mappings().all():
            row = dict(r)
            row = cls._redact_row(row)
            rows.append(row)

        return {"table": table_name, "page": page, "page_size": page_size, "rows": rows, "total": total}
