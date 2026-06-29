"""Recovery-code management endpoints (generate with step-up, status)."""
from app.core.config import settings

PREFIX = settings.api_prefix
# user_headers logs in as testuser / Testpass123! (conftest)
USER_PW = "Testpass123!"


class TestRecoveryCodeManagement:
    def test_status_unconfigured_then_generate_with_password_stepup(self, client, user_headers):
        s = client.get(f"{PREFIX}/auth/recovery-codes/status", headers=user_headers)
        assert s.status_code == 200
        assert s.json() == {"configured": False, "remaining": 0}

        # testuser has no 2FA → step-up is current_password
        g = client.post(f"{PREFIX}/auth/recovery-codes",
                        json={"current_password": USER_PW}, headers=user_headers)
        assert g.status_code == 200
        assert len(g.json()["recovery_codes"]) == 10

        s2 = client.get(f"{PREFIX}/auth/recovery-codes/status", headers=user_headers)
        assert s2.json() == {"configured": True, "remaining": 10}

    def test_generate_wrong_password_denied(self, client, user_headers):
        g = client.post(f"{PREFIX}/auth/recovery-codes",
                        json={"current_password": "WrongPass9x"}, headers=user_headers)
        assert g.status_code == 401

    def test_generate_requires_auth(self, client):
        assert client.post(f"{PREFIX}/auth/recovery-codes", json={}).status_code == 401
