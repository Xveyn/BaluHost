import logging

import pytest

from app.core.config import settings
from app.services.audit import admin_db as admin_db_module
from app.services.audit.admin_db import AdminDBService


def test_admin_tables_requires_admin(client, user_headers):
    # Non-admin should get 403
    res = client.get(f"{settings.api_prefix}/admin/db/tables", headers=user_headers)
    assert res.status_code == 403


def test_admin_tables_and_schema_and_rows(client, admin_headers, db_session):
    # Admin can list tables
    res = client.get("/api/admin/db/tables", headers=admin_headers)
    assert res.status_code == 200
    data = res.json()
    assert "tables" in data

    # Ensure users table exists and schema can be fetched
    if "users" in data["tables"]:
        res2 = client.get("/api/admin/db/table/users/schema", headers=admin_headers)
        assert res2.status_code == 200
        schema = res2.json()
        assert schema.get("table") == "users"

        # Request rows for users (at least admin user exists)
        res3 = client.get("/api/admin/db/table/users?page=1&page_size=10", headers=admin_headers)
        assert res3.status_code == 200
        rows_payload = res3.json()
        assert rows_payload.get("table") == "users"
        assert isinstance(rows_payload.get("rows"), list)


def test_row_count_failure_is_logged(db_session, monkeypatch, caplog):
    """A failed COUNT degrades to total=None — but must say so in the log (#308 follow-up)."""
    real_execute = db_session.execute
    calls = {"n": 0}

    def _flaky_execute(stmt, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:  # the COUNT query runs before the row query
            raise RuntimeError("count query blew up")
        return real_execute(stmt, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", _flaky_execute)

    with caplog.at_level(logging.WARNING, logger=admin_db_module.logger.name):
        result = AdminDBService.get_table_rows(db_session, "users", page=1, page_size=5)

    # Rows still come back; only the total is unknown.
    assert result.total is None
    assert isinstance(result.rows, list)

    messages = [
        r.getMessage() for r in caplog.records if r.name == admin_db_module.logger.name
    ]
    assert messages, "failed row count never reached the logger"
    assert any("count query blew up" in m for m in messages), messages
