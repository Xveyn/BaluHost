from typing import List, Optional, Dict, Any
import re
import os

from sqlalchemy import inspect, select, Table, MetaData, text
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

    @classmethod
    def get_database_health(cls, db: Session) -> Dict[str, Any]:
        """Check database health status.

        Returns connection status, integrity info (SQLite), or pool status (PostgreSQL).
        """
        db_url = str(database.engine.url)
        is_sqlite = db_url.startswith("sqlite")
        is_postgres = db_url.startswith("postgresql")

        result = {
            "is_healthy": False,
            "connection_status": "unknown",
            "database_type": "sqlite" if is_sqlite else "postgresql" if is_postgres else "unknown",
        }

        try:
            # Test connection with a simple query
            db.execute(text("SELECT 1"))
            result["connection_status"] = "connected"
            result["is_healthy"] = True

            if is_sqlite:
                # SQLite: Run integrity check (quick mode)
                try:
                    integrity_result = db.execute(text("PRAGMA integrity_check(1)")).scalar()
                    result["integrity_check"] = integrity_result if integrity_result else "ok"
                    if result["integrity_check"] != "ok":
                        result["is_healthy"] = False
                except Exception as e:
                    result["integrity_check"] = f"error: {str(e)}"

            elif is_postgres:
                # PostgreSQL: Get connection pool status
                try:
                    pool = database.engine.pool
                    result["pool_size"] = pool.size()
                    result["pool_checked_in"] = pool.checkedin()
                    result["pool_checked_out"] = pool.checkedout()
                    result["pool_overflow"] = pool.overflow()
                except Exception:
                    # Pool stats not available
                    pass

        except Exception as e:
            result["connection_status"] = f"error: {str(e)}"
            result["is_healthy"] = False

        return result

    @classmethod
    def get_database_info(cls, db: Session) -> Dict[str, Any]:
        """Get database size information for all tables.

        Returns total size and per-table size estimates.
        """
        db_url = str(database.engine.url)
        is_sqlite = db_url.startswith("sqlite")

        inspector = inspect(database.engine)
        all_tables = inspector.get_table_names()

        tables_info = []
        total_size = 0

        for table_name in sorted(all_tables):
            try:
                # Get row count
                metadata = MetaData()
                table = Table(table_name, metadata, autoload_with=database.engine)
                from sqlalchemy import func
                count_stmt = select(func.count()).select_from(table)
                row_count = db.execute(count_stmt).scalar() or 0

                # Estimate size (rough approximation: ~100 bytes per row average)
                estimated_size = row_count * 100

                tables_info.append({
                    "table_name": table_name,
                    "row_count": row_count,
                    "estimated_size_bytes": estimated_size,
                })
                total_size += estimated_size
            except Exception:
                # Skip tables we can't inspect
                continue

        # For SQLite, try to get actual file size
        if is_sqlite:
            try:
                db_path = db_url.replace("sqlite:///", "")
                if os.path.exists(db_path):
                    total_size = os.path.getsize(db_path)
            except Exception:
                pass

        return {
            "database_type": "sqlite" if is_sqlite else "postgresql",
            "total_size_bytes": total_size,
            "tables": tables_info,
        }
