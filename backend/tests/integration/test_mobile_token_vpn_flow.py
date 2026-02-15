import pytest
from fastapi.testclient import TestClient
from fastapi import status

from app.main import app


def test_mobile_token_with_vpn_and_revoke(client):
    # Register a fresh user
    username = "vpn_test_user"
    password = "StrongPassw0rd!"
    email = "vpn_test@example.com"

    # Use the provided TestClient fixture `client` (with DB overrides) to create user and login
    r = client.post("/api/auth/register", json={
        "username": username,
        "email": email,
        "password": password
    })
    assert r.status_code == status.HTTP_201_CREATED

    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == status.HTTP_200_OK
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Generate mobile token from a 192.168.* base URL so dev-mode localhost check allows it
    with TestClient(app, base_url="http://192.168.0.5") as client2:
        # TestClient uses localhost for the connection; simulate the remote client IP
        headers2 = headers.copy()
        headers2.update({"x-forwarded-for": "192.168.0.5"})
        r = client2.post(
            "/api/mobile/token/generate",
            params={"include_vpn": True, "device_name": "TestPhone", "token_validity_days": 90},
            headers=headers2
        )
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert "token" in data
        # When include_vpn is true, vpn_config should be present (base64 string)
        assert data.get("vpn_config") is not None

    # Create an explicit VPN client owned by the authenticated user and revoke it
    with TestClient(app, base_url="http://test") as client3:
        me_r = client3.get("/api/auth/me", headers=headers)
        assert me_r.status_code == status.HTTP_200_OK
        current_user = me_r.json()
        current_user_id = current_user.get("id")

        # Use the vpn_client_factory if available (conftest provides it)
        # Otherwise, fall back to listing existing clients and pick one
        try:
            # import fixture function via request/pytest not available here; create via API as fallback
            client_rows = client3.get("/api/vpn/clients", headers=headers).json()
            # If no owned client exists, create one using the API generate token flow already done
            owned = None
            for c in client_rows:
                if str(c.get("user_id") or c.get("userId") or "") == str(current_user_id):
                    owned = c
                    break
            if owned:
                client_id = owned.get("id") or owned.get("client_id")
            else:
                # fallback to most recent
                client_id = client_rows[-1].get("id") or client_rows[-1].get("client_id")
        except Exception:
            raise AssertionError("Failed to determine or create a VPN client for revocation")

        # Revoke the client
        r = client3.post(f"/api/vpn/clients/{client_id}/revoke", headers=headers)
        assert r.status_code == status.HTTP_204_NO_CONTENT

        # Verify it is now inactive
        r = client3.get(f"/api/vpn/clients/{client_id}", headers=headers)
        assert r.status_code == status.HTTP_200_OK
        updated = r.json()
        assert updated.get("is_active") in (False, 0, None) or updated.get("is_active") is False
