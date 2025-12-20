import pytest

from app.core.config import settings


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
