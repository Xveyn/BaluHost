# Uses the central `client` (TestClient) and `user_headers` fixtures from
# backend/tests/conftest.py — do NOT define a local client fixture.


def test_storage_put_get_delete_roundtrip(client, user_headers):
    base = "/api/plugins/storage_analytics/_storage"
    put = client.put(f"{base}/units", headers=user_headers, json={"value": {"t": "C"}})
    assert put.status_code in (200, 204)
    got = client.get(f"{base}/units", headers=user_headers)
    assert got.status_code == 200 and got.json()["value"] == {"t": "C"}
    keys = client.get(base, headers=user_headers)
    assert "units" in keys.json()["keys"]
    dele = client.delete(f"{base}/units", headers=user_headers)
    assert dele.status_code == 204
    missing = client.get(f"{base}/units", headers=user_headers)
    assert missing.status_code == 404


def test_storage_requires_auth(client):
    resp = client.get("/api/plugins/storage_analytics/_storage/units")
    assert resp.status_code in (401, 403)


def test_storage_put_over_quota_returns_413(client, user_headers):
    big = "x" * (64 * 1024 + 10)
    resp = client.put(
        "/api/plugins/storage_analytics/_storage/big",
        headers=user_headers,
        json={"value": big},
    )
    assert resp.status_code == 413
