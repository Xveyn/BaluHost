"""Tests for the game libraries API route."""


def test_libraries_requires_auth(client):
    resp = client.get("/api/games/libraries")
    assert resp.status_code in (401, 403)


def test_libraries_returns_schema(client, auth_headers):
    resp = client.get("/api/games/libraries", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "libraries" in body
    assert "total_bytes" in body
    assert "available" in body
    assert isinstance(body["libraries"], list)
