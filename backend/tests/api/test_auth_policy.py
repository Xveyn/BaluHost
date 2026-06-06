from app.core.config import settings

URL = f"{settings.api_prefix}/admin/auth-policy"


def test_get_returns_defaults(client, admin_headers):
    r = client.get(URL, headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["pin_login_enabled"] is True
    assert body["pin_grace_window_seconds"] == 86400


def test_put_updates(client, admin_headers):
    r = client.put(URL, headers=admin_headers, json={"pin_grace_window_seconds": 3600, "pin_login_enabled": False})
    assert r.status_code == 200
    assert r.json()["pin_grace_window_seconds"] == 3600
    assert r.json()["pin_login_enabled"] is False


def test_put_rejects_over_cap(client, admin_headers):
    r = client.put(URL, headers=admin_headers, json={"pin_grace_window_seconds": 999999999})
    assert r.status_code == 422


def test_put_rejects_under_min(client, admin_headers):
    r = client.put(URL, headers=admin_headers, json={"pin_grace_window_seconds": 10})
    assert r.status_code == 422


def test_requires_admin(client, user_headers):
    assert client.get(URL, headers=user_headers).status_code == 403
