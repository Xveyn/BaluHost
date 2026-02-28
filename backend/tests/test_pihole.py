"""Tests for Pi-hole DNS integration.

Tests cover:
- DevPiholeBackend mock data
- PiholeService config management
- API routes (admin-only, with dev backend)
- Connection error handling (503 responses)
- PiholeApiClient SHM session sharing
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

os.environ.setdefault("NAS_MODE", "dev")
os.environ.setdefault("NAS_QUOTA_BYTES", str(10 * 1024 * 1024 * 1024))

from app.core.config import settings


def _run(coro):
    """Run an async coroutine from sync test code."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ============================================================================
# DevPiholeBackend Tests
# ============================================================================

class TestDevPiholeBackend:
    """Test DevPiholeBackend returns valid mock data."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.services.pihole.dev_backend import DevPiholeBackend
        self.backend = DevPiholeBackend()

    def test_get_status(self):
        status = _run(self.backend.get_status())
        assert status["connected"] is True
        assert status["container_running"] is True
        assert "version" in status
        assert "container_status" in status

    def test_get_summary(self):
        summary = _run(self.backend.get_summary())
        assert "total_queries" in summary
        assert "blocked_queries" in summary
        assert "percent_blocked" in summary
        assert "unique_domains" in summary
        assert summary["total_queries"] > 0

    def test_get_blocking(self):
        result = _run(self.backend.get_blocking())
        assert "blocking" in result
        assert result["blocking"] in ("enabled", "disabled")

    def test_set_blocking(self):
        result = _run(self.backend.set_blocking(False))
        assert result["blocking"] == "disabled"
        result = _run(self.backend.set_blocking(True))
        assert result["blocking"] == "enabled"

    def test_get_queries(self):
        result = _run(self.backend.get_queries(limit=10, offset=0))
        assert "queries" in result
        assert "total" in result
        assert len(result["queries"]) <= 10
        if result["queries"]:
            q = result["queries"][0]
            assert "domain" in q
            assert "client" in q
            assert "timestamp" in q
            assert "status" in q

    def test_get_top_domains(self):
        result = _run(self.backend.get_top_domains(count=5))
        assert "top_permitted" in result
        assert len(result["top_permitted"]) <= 5
        if result["top_permitted"]:
            d = result["top_permitted"][0]
            assert "domain" in d
            assert "count" in d

    def test_get_top_blocked(self):
        result = _run(self.backend.get_top_blocked(count=5))
        assert "top_blocked" in result

    def test_get_top_clients(self):
        result = _run(self.backend.get_top_clients(count=5))
        assert "top_clients" in result
        if result["top_clients"]:
            c = result["top_clients"][0]
            assert "client" in c
            assert "count" in c

    def test_get_history(self):
        result = _run(self.backend.get_history())
        assert "history" in result
        assert len(result["history"]) > 0
        h = result["history"][0]
        assert "timestamp" in h
        assert "total" in h
        assert "blocked" in h

    def test_get_domains(self):
        result = _run(self.backend.get_domains("deny", "exact"))
        assert "domains" in result

    def test_add_and_remove_domain(self):
        result = _run(self.backend.add_domain("deny", "exact", "test-block.example.com"))
        assert result.get("success") is True

        domains = _run(self.backend.get_domains("deny", "exact"))
        domain_names = [d["domain"] for d in domains["domains"]]
        assert "test-block.example.com" in domain_names

        result = _run(self.backend.remove_domain("deny", "exact", "test-block.example.com"))
        assert result.get("success") is True

    def test_get_adlists(self):
        result = _run(self.backend.get_adlists())
        assert "lists" in result
        if result["lists"]:
            al = result["lists"][0]
            assert "url" in al

    def test_add_and_remove_adlist(self):
        url = "https://test.example.com/adlist.txt"
        result = _run(self.backend.add_adlist(url, "test list"))
        assert result.get("success") is True

        lists = _run(self.backend.get_adlists())
        urls = [al["url"] for al in lists["lists"]]
        assert url in urls

        added = [al for al in lists["lists"] if al["url"] == url]
        assert len(added) > 0
        result = _run(self.backend.remove_adlist(added[0]["url"]))
        assert result.get("success") is True

    def test_get_local_dns(self):
        result = _run(self.backend.get_local_dns())
        assert "records" in result

    def test_add_and_remove_local_dns(self):
        result = _run(self.backend.add_local_dns("test.local", "192.168.1.200"))
        assert result.get("success") is True

        records = _run(self.backend.get_local_dns())
        domains = [r["domain"] for r in records["records"]]
        assert "test.local" in domains

        result = _run(self.backend.remove_local_dns("test.local", "192.168.1.200"))
        assert result.get("success") is True

    def test_restart_dns(self):
        result = _run(self.backend.restart_dns())
        assert result.get("success") is True

    def test_deploy_container(self):
        result = _run(self.backend.deploy_container({}))
        assert "success" in result or "message" in result

    def test_container_logs(self):
        result = _run(self.backend.get_container_logs(lines=10))
        assert "logs" in result
        assert isinstance(result["logs"], str)


# ============================================================================
# DisabledPiholeBackend Tests
# ============================================================================

class TestDisabledPiholeBackend:
    """Test DisabledPiholeBackend returns null/empty data."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.services.pihole.disabled_backend import DisabledPiholeBackend
        self.backend = DisabledPiholeBackend()

    def test_get_status(self):
        status = _run(self.backend.get_status())
        assert status["mode"] == "disabled"
        assert status["connected"] is False
        assert status["blocking_enabled"] is False
        assert status["container_running"] is False
        assert status["version"] is None

    def test_get_summary(self):
        summary = _run(self.backend.get_summary())
        assert summary["total_queries"] == 0
        assert summary["blocked_queries"] == 0
        assert summary["percent_blocked"] == 0
        assert summary["clients_seen"] == 0
        assert summary["gravity_last_updated"] is None

    def test_get_queries(self):
        result = _run(self.backend.get_queries(limit=10))
        assert result["queries"] == []
        assert result["total"] == 0

    def test_get_top_domains(self):
        result = _run(self.backend.get_top_domains(count=5))
        assert result["top_permitted"] == []

    def test_get_top_blocked(self):
        result = _run(self.backend.get_top_blocked(count=5))
        assert result["top_blocked"] == []

    def test_get_top_clients(self):
        result = _run(self.backend.get_top_clients(count=5))
        assert result["top_clients"] == []

    def test_get_history(self):
        result = _run(self.backend.get_history())
        assert result["history"] == []

    def test_get_blocking(self):
        result = _run(self.backend.get_blocking())
        assert result["blocking"] == "disabled"

    def test_set_blocking_rejected(self):
        result = _run(self.backend.set_blocking(True))
        assert result["success"] is False
        assert "disabled" in result["message"].lower()

    def test_container_ops_rejected(self):
        for method in ("deploy_container", "start_container", "stop_container",
                        "remove_container", "update_container"):
            if method == "deploy_container":
                result = _run(getattr(self.backend, method)({}))
            else:
                result = _run(getattr(self.backend, method)())
            assert result["success"] is False

    def test_domain_ops_rejected(self):
        result = _run(self.backend.add_domain("deny", "exact", "example.com"))
        assert result["success"] is False
        result = _run(self.backend.remove_domain("deny", "exact", "example.com"))
        assert result["success"] is False

    def test_get_domains_empty(self):
        result = _run(self.backend.get_domains("deny", "exact"))
        assert result["domains"] == []

    def test_get_adlists_empty(self):
        result = _run(self.backend.get_adlists())
        assert result["lists"] == []

    def test_get_local_dns_empty(self):
        result = _run(self.backend.get_local_dns())
        assert result["records"] == []

    def test_container_logs_empty(self):
        result = _run(self.backend.get_container_logs())
        assert result["logs"] == ""
        assert result["lines"] == 0


# ============================================================================
# PiholeService Tests
# ============================================================================

class TestPiholeService:
    """Test PiholeService config and backend management."""

    def test_get_config_default(self, db_session: Session):
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        config = svc.get_config()
        assert config.mode == "disabled"
        assert config.upstream_dns == "1.1.1.1;1.0.0.1"

    def test_update_config(self, db_session: Session):
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        svc.update_config(upstream_dns="8.8.8.8;8.8.4.4", web_port=9090)
        config = svc.get_config()
        assert config.upstream_dns == "8.8.8.8;8.8.4.4"
        assert config.web_port == 9090

    def test_update_config_mode(self, db_session: Session):
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        svc.update_config(mode="docker")
        config = svc.get_config()
        assert config.mode == "docker"

    def test_update_config_password_encrypted(self, db_session: Session):
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        svc.update_config(password="my-secret-password")
        from app.models.pihole import PiholeConfig
        row = db_session.query(PiholeConfig).first()
        assert row is not None
        assert row.password_encrypted is not None
        assert row.password_encrypted != "my-secret-password"

    def test_get_vpn_dns_disabled(self, db_session: Session):
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        dns = svc.get_vpn_dns()
        assert dns == "1.1.1.1"

    def test_get_vpn_dns_active(self, db_session: Session):
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        svc.update_config(mode="docker", use_as_vpn_dns=True)
        dns = svc.get_vpn_dns()
        assert dns == "10.8.0.1"

    def test_get_vpn_dns_active_but_opt_out(self, db_session: Session):
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        svc.update_config(mode="docker", use_as_vpn_dns=False)
        dns = svc.get_vpn_dns()
        assert dns == "1.1.1.1"

    def test_get_backend_dev_mode(self, db_session: Session):
        from app.services.pihole.service import PiholeService
        from app.services.pihole.dev_backend import DevPiholeBackend
        svc = PiholeService(db_session)
        backend = svc.backend
        assert isinstance(backend, DevPiholeBackend)

    def test_deploy_container_persists_password(self, db_session: Session):
        """After deploy_container(), the generated password is saved encrypted in the DB."""
        from app.services.pihole.service import PiholeService
        from app.services.vpn_encryption import VPNEncryption

        svc = PiholeService(db_session)

        # Mock backend returns success with a password
        mock_backend = AsyncMock()
        mock_backend.deploy_container.return_value = {
            "success": True,
            "password": "test-deploy-secret-123",
            "message": "Container deployed",
        }

        with patch.object(type(svc), "backend", new=property(lambda self: mock_backend)):
            result = _run(svc.deploy_container({"image_tag": "latest"}))

        assert result["success"] is True

        # Verify password was persisted encrypted in DB
        config = svc.get_config()
        assert config.password_encrypted is not None
        decrypted = VPNEncryption.decrypt_key(config.password_encrypted)
        assert decrypted == "test-deploy-secret-123"

    def test_deploy_container_no_password_no_persist(self, db_session: Session):
        """If deploy result has no password key, DB is not touched."""
        from app.services.pihole.service import PiholeService

        svc = PiholeService(db_session)

        mock_backend = AsyncMock()
        mock_backend.deploy_container.return_value = {
            "success": True,
            "message": "Already running",
        }

        with patch.object(type(svc), "backend", new=property(lambda self: mock_backend)):
            result = _run(svc.deploy_container({}))

        assert result["success"] is True
        config = svc.get_config()
        assert config.password_encrypted is None

    def test_deploy_persists_password_before_wait(self, db_session: Session):
        """Password must be in DB BEFORE wait_for_ready is called.

        This prevents other workers from reading the old password during the
        13-60s window while wait_for_ready polls Pi-hole.
        """
        from app.services.pihole.service import PiholeService
        from app.services.vpn_encryption import VPNEncryption
        import app.services.pihole.service as svc_mod

        svc = PiholeService(db_session)

        # Track the order of operations
        call_order: list[str] = []

        async def fake_deploy(config):
            call_order.append("deploy")
            return {"success": True, "password": "new-secret-pw", "message": "ok"}

        async def fake_wait_for_ready(timeout=60):
            call_order.append("wait_for_ready")
            # At this point, password MUST already be in DB
            cfg = svc.get_config()
            assert cfg.password_encrypted is not None, (
                "password_encrypted must be set BEFORE wait_for_ready"
            )
            decrypted = VPNEncryption.decrypt_key(cfg.password_encrypted)
            assert decrypted == "new-secret-pw"
            # Deploy signal must also be written already
            from app.services.monitoring.shm import read_shm
            from app.services.pihole.service import PIHOLE_DEPLOY_TS_FILE
            deploy_data = read_shm(PIHOLE_DEPLOY_TS_FILE, max_age_seconds=60)
            assert deploy_data is not None, (
                "deploy signal must be written BEFORE wait_for_ready"
            )
            # Singleton must be reset already
            assert svc_mod._backend is None, (
                "backend singleton must be reset BEFORE wait_for_ready"
            )

        mock_backend = AsyncMock()
        mock_backend.deploy_container = AsyncMock(side_effect=fake_deploy)
        mock_backend.wait_for_ready = AsyncMock(side_effect=fake_wait_for_ready)

        # Pre-set singleton to verify it gets cleared
        svc_mod._backend = mock_backend
        svc_mod._backend_mode = "docker"

        with patch.object(type(svc), "backend", new=property(lambda self: mock_backend)):
            result = _run(svc.deploy_container({"image_tag": "latest"}))

        assert result["success"] is True
        assert call_order == ["deploy", "wait_for_ready"]

    def test_create_backend_uses_config_web_port(self, db_session: Session):
        """_create_backend uses the DB config web_port, not the static setting."""
        from app.services.pihole.service import PiholeService, _create_backend

        svc = PiholeService(db_session)
        svc.update_config(mode="docker", web_port=9090)

        backend = _create_backend("docker", pihole_url="", password="test", web_port=9090)
        assert backend._pihole_url == "http://localhost:9090"
        # Explicit URL takes precedence
        backend2 = _create_backend("docker", pihole_url="http://10.0.0.5:80", password="", web_port=9090)
        assert backend2._pihole_url == "http://10.0.0.5:80"

    def test_deploy_resets_backend_singleton(self, db_session: Session):
        """After deploy_container(), the backend singleton is reset."""
        from app.services.pihole.service import PiholeService, _backend, _backend_mode
        import app.services.pihole.service as svc_mod

        svc = PiholeService(db_session)

        mock_backend = AsyncMock()
        mock_backend.deploy_container.return_value = {
            "success": True,
            "password": "new-pass",
            "message": "deployed",
        }

        # Pre-set the singleton to simulate a cached backend
        svc_mod._backend = mock_backend
        svc_mod._backend_mode = "docker"

        with patch.object(type(svc), "backend", new=property(lambda self: mock_backend)):
            _run(svc.deploy_container({"image_tag": "latest"}))

        # Singleton should be reset
        assert svc_mod._backend is None
        assert svc_mod._backend_mode is None

    def test_service_status(self, db_session: Session):
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        status = svc.get_service_status()
        assert "is_running" in status


# ============================================================================
# API Route Tests
# ============================================================================

class TestPiholeAPI:
    """Test Pi-hole API endpoints (admin-only)."""

    def test_summary_requires_auth(self, client: TestClient):
        response = client.get(f"{settings.api_prefix}/pihole/summary")
        assert response.status_code == 401

    def test_summary_requires_admin(self, client: TestClient, user_headers: dict):
        response = client.get(
            f"{settings.api_prefix}/pihole/summary",
            headers=user_headers,
        )
        assert response.status_code == 403

    def test_summary_admin(self, client: TestClient, admin_headers: dict):
        response = client.get(
            f"{settings.api_prefix}/pihole/summary",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_queries" in data
        assert "blocked_queries" in data

    def test_status_admin(self, client: TestClient, admin_headers: dict):
        response = client.get(
            f"{settings.api_prefix}/pihole/status",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "connected" in data
        assert "container_running" in data

    def test_blocking_get(self, client: TestClient, admin_headers: dict):
        response = client.get(
            f"{settings.api_prefix}/pihole/blocking",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert "blocking" in response.json()

    def test_blocking_toggle(self, client: TestClient, admin_headers: dict):
        response = client.post(
            f"{settings.api_prefix}/pihole/blocking",
            headers=admin_headers,
            json={"enabled": False},
        )
        assert response.status_code == 200
        assert response.json()["blocking"] == "disabled"

    def test_queries(self, client: TestClient, admin_headers: dict):
        response = client.get(
            f"{settings.api_prefix}/pihole/queries?limit=5",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "queries" in data
        assert "total" in data

    def test_top_domains(self, client: TestClient, admin_headers: dict):
        response = client.get(
            f"{settings.api_prefix}/pihole/top-domains?count=3",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert "top_permitted" in response.json()

    def test_top_clients(self, client: TestClient, admin_headers: dict):
        response = client.get(
            f"{settings.api_prefix}/pihole/top-clients?count=3",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert "top_clients" in response.json()

    def test_history(self, client: TestClient, admin_headers: dict):
        response = client.get(
            f"{settings.api_prefix}/pihole/history",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert "history" in response.json()

    def test_domains_list(self, client: TestClient, admin_headers: dict):
        response = client.get(
            f"{settings.api_prefix}/pihole/domains?list_type=deny&kind=exact",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert "domains" in response.json()

    def test_domains_add_remove(self, client: TestClient, admin_headers: dict):
        # Add (returns 201)
        response = client.post(
            f"{settings.api_prefix}/pihole/domains",
            headers=admin_headers,
            json={
                "list_type": "deny",
                "kind": "exact",
                "domain": "block-test.example.com",
            },
        )
        assert response.status_code == 201

        # Remove
        response = client.request(
            "DELETE",
            f"{settings.api_prefix}/pihole/domains",
            headers=admin_headers,
            json={
                "list_type": "deny",
                "kind": "exact",
                "domain": "block-test.example.com",
            },
        )
        assert response.status_code == 200

    def test_adlists(self, client: TestClient, admin_headers: dict):
        response = client.get(
            f"{settings.api_prefix}/pihole/lists",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert "lists" in response.json()

    def test_local_dns(self, client: TestClient, admin_headers: dict):
        response = client.get(
            f"{settings.api_prefix}/pihole/dns-records",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert "records" in response.json()

    def test_local_dns_add_remove(self, client: TestClient, admin_headers: dict):
        # Add (returns 201)
        response = client.post(
            f"{settings.api_prefix}/pihole/dns-records",
            headers=admin_headers,
            json={"domain": "mytest.local", "ip": "10.0.0.99"},
        )
        assert response.status_code == 201

        # Remove
        response = client.request(
            "DELETE",
            f"{settings.api_prefix}/pihole/dns-records",
            headers=admin_headers,
            json={"domain": "mytest.local", "ip": "10.0.0.99"},
        )
        assert response.status_code == 200

    def test_config_get(self, client: TestClient, admin_headers: dict):
        response = client.get(
            f"{settings.api_prefix}/pihole/config",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "mode" in data
        assert "upstream_dns" in data

    def test_config_update(self, client: TestClient, admin_headers: dict):
        response = client.put(
            f"{settings.api_prefix}/pihole/config",
            headers=admin_headers,
            json={"upstream_dns": "9.9.9.9"},
        )
        assert response.status_code == 200

        # Verify
        response = client.get(
            f"{settings.api_prefix}/pihole/config",
            headers=admin_headers,
        )
        assert response.json()["upstream_dns"] == "9.9.9.9"

    def test_restart_dns(self, client: TestClient, admin_headers: dict):
        response = client.post(
            f"{settings.api_prefix}/pihole/restart-dns",
            headers=admin_headers,
        )
        assert response.status_code == 200

    def test_container_logs(self, client: TestClient, admin_headers: dict):
        response = client.get(
            f"{settings.api_prefix}/pihole/container/logs",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert "logs" in response.json()

    def test_failover_status(self, client: TestClient, admin_headers: dict):
        response = client.get(
            f"{settings.api_prefix}/pihole/failover-status",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "remote_configured" in data
        assert "remote_connected" in data
        assert "failover_active" in data
        assert "active_source" in data
        assert data["active_source"] in ("remote", "local")

    def test_failover_status_requires_admin(self, client: TestClient, user_headers: dict):
        response = client.get(
            f"{settings.api_prefix}/pihole/failover-status",
            headers=user_headers,
        )
        assert response.status_code == 403

    def test_config_has_failover_fields(self, client: TestClient, admin_headers: dict):
        response = client.get(
            f"{settings.api_prefix}/pihole/config",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "remote_pihole_url" in data
        assert "health_check_interval" in data
        assert "failover_active" in data

    def test_config_has_password_field(self, client: TestClient, admin_headers: dict):
        """Config response includes has_password indicator."""
        # Initially no password set
        response = client.get(
            f"{settings.api_prefix}/pihole/config",
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "has_password" in data
        assert "has_remote_password" in data
        assert data["has_password"] is False
        assert data["has_remote_password"] is False

        # Set a password
        response = client.put(
            f"{settings.api_prefix}/pihole/config",
            headers=admin_headers,
            json={"password": "test-secret-123"},
        )
        assert response.status_code == 200

        # Now has_password should be True
        response = client.get(
            f"{settings.api_prefix}/pihole/config",
            headers=admin_headers,
        )
        data = response.json()
        assert data["has_password"] is True
        assert data["has_remote_password"] is False

    def test_config_update_remote_pihole(self, client: TestClient, admin_headers: dict):
        response = client.put(
            f"{settings.api_prefix}/pihole/config",
            headers=admin_headers,
            json={"remote_pihole_url": "http://192.168.1.50:80"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["remote_pihole_url"] == "http://192.168.1.50:80"

        # Verify failover status now shows configured
        response = client.get(
            f"{settings.api_prefix}/pihole/failover-status",
            headers=admin_headers,
        )
        data = response.json()
        assert data["remote_configured"] is True


# ============================================================================
# Failover Service Tests
# ============================================================================

class TestPiholeFailover:
    """Test Pi-hole failover logic."""

    def test_has_remote_pi_false(self, db_session: Session):
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        assert svc.has_remote_pi() is False

    def test_has_remote_pi_true(self, db_session: Session):
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        svc.update_config(remote_pihole_url="http://192.168.1.50:80")
        assert svc.has_remote_pi() is True

    def test_failover_status_no_remote(self, db_session: Session):
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        status = _run(svc.get_failover_status())
        assert status["remote_configured"] is False
        assert status["failover_active"] is False
        assert status["active_source"] == "local"

    def test_failover_status_with_remote(self, db_session: Session):
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        svc.update_config(remote_pihole_url="http://192.168.1.50:80")
        status = _run(svc.get_failover_status())
        assert status["remote_configured"] is True
        # Remote won't actually connect in tests
        assert status["remote_connected"] is False
        assert status["active_source"] in ("remote", "local")

    def test_config_default_failover_fields(self, db_session: Session):
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        config = svc.get_config()
        assert config.remote_pihole_url is None
        assert config.failover_active is False
        assert config.health_check_interval == 30
        assert config.last_failover_at is None

    def test_update_health_check_interval(self, db_session: Session):
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        svc.update_config(health_check_interval=60)
        config = svc.get_config()
        assert config.health_check_interval == 60

    def test_service_status_includes_failover(self, db_session: Session):
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        status = svc.get_service_status()
        assert "failover_active" in status
        assert "remote_configured" in status

    def test_check_health_no_remote_is_noop(self, db_session: Session):
        """Health check does nothing when no remote is configured."""
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        # Should not raise
        _run(svc.check_health_and_failover())
        config = svc.get_config()
        assert config.failover_active is False


# ============================================================================
# Connection Error Handling Tests
# ============================================================================

class TestPiholeConnectionErrors:
    """Test that unreachable backends produce clean 503 / fallback responses."""

    def _make_failing_backend(self):
        """Create a mock backend whose methods raise httpx.ConnectError."""
        backend = AsyncMock()
        err = httpx.ConnectError("Connection refused")
        backend.get_status.side_effect = err
        backend.get_summary.side_effect = err
        backend.get_blocking.side_effect = err
        backend.set_blocking.side_effect = err
        backend.get_queries.side_effect = err
        backend.get_top_domains.side_effect = err
        backend.get_top_blocked.side_effect = err
        backend.get_top_clients.side_effect = err
        backend.get_history.side_effect = err
        backend.get_domains.side_effect = err
        backend.add_domain.side_effect = err
        backend.remove_domain.side_effect = err
        backend.get_adlists.side_effect = err
        backend.add_adlist.side_effect = err
        backend.remove_adlist.side_effect = err
        backend.update_gravity.side_effect = err
        backend.get_local_dns.side_effect = err
        backend.add_local_dns.side_effect = err
        backend.remove_local_dns.side_effect = err
        backend.restart_dns.side_effect = err
        backend.deploy_container.side_effect = err
        backend.start_container.side_effect = err
        backend.stop_container.side_effect = err
        backend.remove_container.side_effect = err
        backend.update_container.side_effect = err
        backend.get_container_logs.side_effect = err
        return backend

    def test_get_status_returns_fallback_on_connect_error(self, db_session: Session):
        """get_status returns fallback dict with connected=False instead of crashing."""
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        failing = self._make_failing_backend()

        with patch.object(svc, "_get_active_backend", return_value=failing):
            result = _run(svc.get_status())

        assert result["connected"] is False
        assert result["container_status"] == "unreachable"
        assert result["version"] is None

    def test_get_summary_raises_503_on_connect_error(self, db_session: Session):
        """get_summary raises HTTPException(503) when backend is unreachable."""
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        failing = self._make_failing_backend()

        with patch.object(svc, "_get_active_backend", return_value=failing):
            with pytest.raises(HTTPException) as exc_info:
                _run(svc.get_summary())
            assert exc_info.value.status_code == 503
            assert "unreachable" in exc_info.value.detail.lower()

    def test_get_blocking_raises_503_on_connect_error(self, db_session: Session):
        """get_blocking raises HTTPException(503) when backend is unreachable."""
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        failing = self._make_failing_backend()

        with patch.object(svc, "_get_active_backend", return_value=failing):
            with pytest.raises(HTTPException) as exc_info:
                _run(svc.get_blocking())
            assert exc_info.value.status_code == 503

    def test_set_blocking_raises_503_on_connect_error(self, db_session: Session):
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        failing = self._make_failing_backend()

        with patch.object(svc, "_get_active_backend", return_value=failing):
            with pytest.raises(HTTPException) as exc_info:
                _run(svc.set_blocking(True))
            assert exc_info.value.status_code == 503

    def test_container_ops_raise_503_on_connect_error(self, db_session: Session):
        """Container operations raise 503 when Docker is unreachable."""
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        failing = self._make_failing_backend()

        with patch.object(type(svc), "backend", new=property(lambda self: failing)):
            for method_name, args in [
                ("deploy_container", ({"image_tag": "latest"},)),
                ("start_container", ()),
                ("stop_container", ()),
                ("remove_container", ()),
                ("update_container", ()),
                ("get_container_logs", ()),
            ]:
                with pytest.raises(HTTPException) as exc_info:
                    _run(getattr(svc, method_name)(*args))
                assert exc_info.value.status_code == 503, f"{method_name} should return 503"

    def test_safe_call_catches_oserror(self, db_session: Session):
        """_safe_call also catches OSError (e.g. network unreachable)."""
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)

        async def failing_coro():
            raise OSError("Network is unreachable")

        with pytest.raises(HTTPException) as exc_info:
            _run(svc._safe_call(failing_coro()))
        assert exc_info.value.status_code == 503

    def test_safe_call_catches_runtime_error(self, db_session: Session):
        """_safe_call catches RuntimeError (e.g. docker package not installed)."""
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)

        async def failing_coro():
            raise RuntimeError("docker package not installed")

        with pytest.raises(HTTPException) as exc_info:
            _run(svc._safe_call(failing_coro()))
        assert exc_info.value.status_code == 503

    def test_get_status_catches_runtime_error(self, db_session: Session):
        """get_status returns fallback when RuntimeError is raised (missing docker)."""
        from app.services.pihole.service import PiholeService
        svc = PiholeService(db_session)
        failing = AsyncMock()
        failing.get_status.side_effect = RuntimeError("docker package not installed")

        with patch.object(svc, "_get_active_backend", return_value=failing):
            result = _run(svc.get_status())

        assert result["connected"] is False
        assert result["container_status"] == "unreachable"


# ============================================================================
# PiholeApiClient Auth Validation Tests
# ============================================================================

class TestPiholeApiClientAuth:
    """Test PiholeApiClient session.valid validation."""

    def test_auth_rejects_valid_false(self):
        """Auth with valid=false raises ValueError, not silent success."""
        import httpx
        from app.services.pihole.api_client import PiholeApiClient

        client = PiholeApiClient("http://localhost:8053", "wrong-password")

        # Pi-hole v6 returns 200 with valid=false for wrong passwords
        mock_response = httpx.Response(
            200,
            json={"session": {"valid": False, "sid": "some-sid-value"}},
            request=httpx.Request("POST", "http://localhost:8053/api/auth"),
        )

        with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(ValueError, match="invalid credentials"):
                _run(client._authenticate())

        # SID should NOT have been stored
        assert client._sid is None

    def test_auth_accepts_valid_true(self):
        """Auth with valid=true stores the SID normally."""
        import httpx
        from app.services.pihole.api_client import PiholeApiClient

        client = PiholeApiClient("http://localhost:8053", "correct-password")

        mock_response = httpx.Response(
            200,
            json={"session": {"valid": True, "sid": "good-sid-123"}},
            request=httpx.Request("POST", "http://localhost:8053/api/auth"),
        )

        with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
            _run(client._authenticate())

        assert client._sid == "good-sid-123"

    def test_auth_rejects_missing_valid_field(self):
        """Auth without valid field defaults to false → rejected."""
        import httpx
        from app.services.pihole.api_client import PiholeApiClient

        client = PiholeApiClient("http://localhost:8053", "password")

        mock_response = httpx.Response(
            200,
            json={"session": {"sid": "some-sid"}},
            request=httpx.Request("POST", "http://localhost:8053/api/auth"),
        )

        with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(ValueError, match="invalid credentials"):
                _run(client._authenticate())

    def test_safe_call_catches_value_error(self, db_session: Session):
        """_safe_call catches ValueError and returns 503."""
        from app.services.pihole.service import PiholeService

        svc = PiholeService(db_session)

        async def failing_coro():
            raise ValueError("Pi-hole authentication failed: invalid credentials")

        with pytest.raises(HTTPException) as exc_info:
            _run(svc._safe_call(failing_coro()))
        assert exc_info.value.status_code == 503


# ============================================================================
# Docker Volume Removal Tests
# ============================================================================

class TestDockerVolumeRemoval:
    """Test that deploy() removes pihole_config volume for clean password state."""

    def test_deploy_removes_volume(self):
        """deploy() calls volume.remove() before creating container."""
        from app.services.pihole.docker_backend import ContainerManager

        mgr = ContainerManager()

        mock_volume = AsyncMock()
        mock_container = AsyncMock()
        mock_container.attrs = {"State": {"Running": True, "Status": "running"}}

        mock_client = AsyncMock()
        mock_client.images.pull = AsyncMock()
        mock_client.containers.get.side_effect = [mock_container, None]  # first: existing, second: not found after remove
        mock_client.containers.run = AsyncMock(return_value=mock_container)
        mock_client.volumes.get = AsyncMock(return_value=mock_volume)

        mgr._client = mock_client

        # Patch _run_sync to call functions directly (sync mock)
        async def fake_run_sync(fn, *args, **kwargs):
            if callable(fn):
                result = fn(*args, **kwargs)
                # Handle coroutines from AsyncMock
                if asyncio.iscoroutine(result):
                    return await result
                return result
            return fn

        with patch.object(mgr, "_run_sync", side_effect=fake_run_sync):
            result = _run(mgr.deploy(password="test123", web_port=8053))

        assert result["success"] is True
        # Volume should have been fetched and removed
        mock_client.volumes.get.assert_called_once_with("pihole_config")
        mock_volume.remove.assert_called_once()

    def test_deploy_ignores_missing_volume(self):
        """deploy() doesn't fail if pihole_config volume doesn't exist yet."""
        from app.services.pihole.docker_backend import ContainerManager

        mgr = ContainerManager()

        mock_container = AsyncMock()
        mock_container.attrs = {"State": {"Running": True, "Status": "running"}}

        mock_client = AsyncMock()
        mock_client.images.pull = AsyncMock()
        mock_client.containers.get.side_effect = [None]  # no existing container
        mock_client.containers.run = AsyncMock(return_value=mock_container)
        mock_client.volumes.get = AsyncMock(side_effect=Exception("Not found"))

        mgr._client = mock_client

        async def fake_run_sync(fn, *args, **kwargs):
            if callable(fn):
                result = fn(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    return await result
                return result
            return fn

        with patch.object(mgr, "_run_sync", side_effect=fake_run_sync):
            result = _run(mgr.deploy(password="test123", web_port=8053))

        assert result["success"] is True


# ============================================================================
# PiholeApiClient Session Sharing Tests
# ============================================================================

class TestPiholeApiClientSessionSharing:
    """Test SHM-based SID sharing across workers."""

    @pytest.fixture(autouse=True)
    def _setup_shm(self, tmp_path):
        """Redirect SHM_DIR to a temp directory for test isolation."""
        self.shm_dir = tmp_path / "shm"
        self.shm_dir.mkdir()
        with patch("app.services.pihole.api_client.SHM_DIR", self.shm_dir), \
             patch("app.services.pihole.api_client.write_shm", side_effect=self._write_shm), \
             patch("app.services.pihole.api_client.read_shm", side_effect=self._read_shm):
            yield

    def _write_shm(self, filename: str, data) -> None:
        """Write JSON to tmp shm dir (mirrors real write_shm)."""
        target = self.shm_dir / filename
        with open(target, "w") as f:
            json.dump(data, f)

    def _read_shm(self, filename: str, max_age_seconds: float = 30.0):
        """Read JSON from tmp shm dir (mirrors real read_shm, no staleness check)."""
        target = self.shm_dir / filename
        if not target.exists():
            return None
        with open(target, "r") as f:
            return json.load(f)

    def _make_auth_response(self, sid: str = "test-sid-abc") -> httpx.Response:
        return httpx.Response(
            200,
            json={"session": {"valid": True, "sid": sid}},
            request=httpx.Request("POST", "http://localhost:8053/api/auth"),
        )

    def test_authenticate_writes_shared_sid(self):
        """After successful auth, SID is written to SHM file."""
        from app.services.pihole.api_client import PiholeApiClient

        client = PiholeApiClient("http://localhost:8053", "password")
        mock_resp = self._make_auth_response("fresh-sid-001")

        with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            _run(client._authenticate())

        assert client._sid == "fresh-sid-001"

        # SHM file should exist with the SID
        shm_file = self.shm_dir / client._sid_filename()
        assert shm_file.exists()
        data = json.loads(shm_file.read_text())
        assert data["sid"] == "fresh-sid-001"
        assert data["base_url"] == "http://localhost:8053"

    def test_ensure_auth_reads_shared_sid(self):
        """_ensure_auth picks up SID from SHM without calling _authenticate."""
        from app.services.pihole.api_client import PiholeApiClient

        client = PiholeApiClient("http://localhost:8053", "password")
        assert client._sid is None

        # Pre-populate SHM with a SID from "another worker"
        shm_file = self.shm_dir / client._sid_filename()
        shm_file.write_text(json.dumps({"sid": "shared-sid-from-worker2", "base_url": "http://localhost:8053"}))

        with patch.object(client, "_authenticate", new_callable=AsyncMock) as mock_auth:
            _run(client._ensure_auth())

        # Should have loaded from SHM, not authenticated
        assert client._sid == "shared-sid-from-worker2"
        mock_auth.assert_not_called()

    def test_401_uses_refreshed_sid_from_other_worker(self):
        """On 401, if SHM has a newer SID, use it instead of re-authenticating."""
        from app.services.pihole.api_client import PiholeApiClient

        client = PiholeApiClient("http://localhost:8053", "password")
        client._sid = "stale-sid"

        # Pre-populate SHM with refreshed SID from another worker
        shm_file = self.shm_dir / client._sid_filename()
        shm_file.write_text(json.dumps({"sid": "refreshed-sid-from-worker3", "base_url": "http://localhost:8053"}))

        # First call returns 401, retry succeeds
        resp_401 = httpx.Response(401, request=httpx.Request("GET", "http://localhost:8053/api/stats/summary"))
        resp_200 = httpx.Response(200, json={"queries": {}}, request=httpx.Request("GET", "http://localhost:8053/api/stats/summary"))

        call_count = 0

        async def mock_request(method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return resp_401
            return resp_200

        with patch.object(client._client, "request", side_effect=mock_request), \
             patch.object(client, "_authenticate", new_callable=AsyncMock) as mock_auth, \
             patch.object(client, "_logout", new_callable=AsyncMock) as mock_logout:
            _run(client._request("GET", "/api/stats/summary"))

        # Should have adopted the SHM SID, not re-authenticated
        assert client._sid == "refreshed-sid-from-worker3"
        mock_auth.assert_not_called()
        mock_logout.assert_not_called()

    def test_close_calls_logout(self):
        """close() calls _logout to free the session seat."""
        from app.services.pihole.api_client import PiholeApiClient

        client = PiholeApiClient("http://localhost:8053", "password")
        client._sid = "active-sid"

        with patch.object(client, "_logout", new_callable=AsyncMock) as mock_logout, \
             patch.object(client._client, "aclose", new_callable=AsyncMock):
            _run(client.close())

        mock_logout.assert_called_once_with("active-sid")

    def test_shared_sid_ignored_for_different_base_url(self):
        """SHM SID is ignored if base_url doesn't match (different Pi-hole instance)."""
        from app.services.pihole.api_client import PiholeApiClient

        client = PiholeApiClient("http://localhost:8053", "password")
        assert client._sid is None

        # Write SHM with a different base_url
        shm_file = self.shm_dir / client._sid_filename()
        shm_file.write_text(json.dumps({"sid": "wrong-instance-sid", "base_url": "http://192.168.1.50:80"}))

        mock_resp = self._make_auth_response("correct-sid")
        with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_resp):
            _run(client._ensure_auth())

        # Should have authenticated fresh, not used the mismatched SHM SID
        assert client._sid == "correct-sid"


# ============================================================================
# Deploy Signal & Cross-Worker Invalidation Tests
# ============================================================================

class TestDeploySignal:
    """Test cross-worker singleton invalidation via SHM deploy signal."""

    @pytest.fixture(autouse=True)
    def _setup_shm(self, tmp_path):
        """Redirect SHM_DIR to a temp directory for test isolation."""
        self.shm_dir = tmp_path / "shm"
        self.shm_dir.mkdir()
        self._shm_store: dict[str, Any] = {}

        def fake_write(filename: str, data) -> None:
            self._shm_store[filename] = data
            target = self.shm_dir / filename
            with open(target, "w") as f:
                json.dump(data, f)

        def fake_read(filename: str, max_age_seconds: float = 30.0):
            return self._shm_store.get(filename)

        self._patches = [
            patch("app.services.pihole.service.read_shm", side_effect=fake_read),
            patch("app.services.pihole.service.write_shm", side_effect=fake_write),
            patch("app.services.pihole.service.SHM_DIR", self.shm_dir),
        ]
        for p in self._patches:
            p.start()
        yield
        for p in self._patches:
            p.stop()

    @pytest.fixture(autouse=True)
    def _reset_singletons(self):
        """Reset module-level singletons before and after each test."""
        import app.services.pihole.service as svc_mod
        svc_mod._backend = None
        svc_mod._backend_mode = None
        svc_mod._backend_created_at = 0.0
        yield
        svc_mod._backend = None
        svc_mod._backend_mode = None
        svc_mod._backend_created_at = 0.0

    def test_deploy_writes_shm_signal(self, db_session: Session):
        """deploy_container writes a deploy timestamp to SHM."""
        from app.services.pihole.service import PiholeService, PIHOLE_DEPLOY_TS_FILE

        svc = PiholeService(db_session)
        mock_backend = AsyncMock()
        mock_backend.deploy_container.return_value = {"success": True, "password": "new-pw"}

        with patch.object(type(svc), "backend", new=property(lambda self: mock_backend)):
            _run(svc.deploy_container({"image_tag": "latest"}))

        # SHM deploy signal should have been written
        assert PIHOLE_DEPLOY_TS_FILE in self._shm_store
        assert "ts" in self._shm_store[PIHOLE_DEPLOY_TS_FILE]
        assert self._shm_store[PIHOLE_DEPLOY_TS_FILE]["ts"] > 0

    def test_get_backend_invalidates_after_deploy_signal(self, db_session: Session):
        """Singleton is re-created when SHM deploy_ts > creation time."""
        import app.services.pihole.service as svc_mod
        from app.services.pihole.service import PiholeService, PIHOLE_DEPLOY_TS_FILE

        svc = PiholeService(db_session)
        # Simulate an existing cached backend created at time 100
        old_backend = object()
        svc_mod._backend = old_backend
        svc_mod._backend_mode = "dev"
        svc_mod._backend_created_at = 100.0

        # Write a deploy signal with a newer timestamp
        self._shm_store[PIHOLE_DEPLOY_TS_FILE] = {"ts": 200.0}

        result = svc._get_backend()

        # Should have created a new backend, not returned the old one
        assert result is not old_backend
        assert svc_mod._backend_created_at > 100.0

    def test_get_backend_keeps_singleton_without_deploy_signal(self, db_session: Session):
        """Singleton is reused when no deploy signal exists."""
        import app.services.pihole.service as svc_mod
        from app.services.pihole.service import PiholeService

        svc = PiholeService(db_session)
        # Simulate an existing cached backend
        old_backend = object()
        svc_mod._backend = old_backend
        svc_mod._backend_mode = "dev"
        svc_mod._backend_created_at = 100.0

        result = svc._get_backend()

        # Should return the same backend
        assert result is old_backend

    def test_deploy_cleans_stale_shm_sid_files(self, db_session: Session):
        """deploy_container removes old pihole_sid_*.json files."""
        from app.services.pihole.service import PiholeService

        svc = PiholeService(db_session)

        # Create fake stale SID files in the SHM dir
        (self.shm_dir / "pihole_sid_abc12345.json").write_text('{"sid":"old"}')
        (self.shm_dir / "pihole_sid_def67890.json").write_text('{"sid":"old2"}')
        (self.shm_dir / "other_file.json").write_text('{"keep":"me"}')

        mock_backend = AsyncMock()
        mock_backend.deploy_container.return_value = {"success": True, "password": "pw"}

        with patch.object(type(svc), "backend", new=property(lambda self: mock_backend)):
            _run(svc.deploy_container({"image_tag": "latest"}))

        # SID files should be removed, other files should remain
        assert not (self.shm_dir / "pihole_sid_abc12345.json").exists()
        assert not (self.shm_dir / "pihole_sid_def67890.json").exists()
        assert (self.shm_dir / "other_file.json").exists()


class TestAuthenticate401Diagnostics:
    """Test that _authenticate logs 401 response body for diagnostics."""

    def test_authenticate_logs_401_body(self):
        """401 from auth endpoint includes response body in error message."""
        from app.services.pihole.api_client import PiholeApiClient

        client = PiholeApiClient("http://localhost:8053", "password")

        resp_401 = httpx.Response(
            401,
            text='{"error":{"key":"unauthorized","message":"Session limit reached"}}',
            request=httpx.Request("POST", "http://localhost:8053/api/auth"),
        )

        with patch.object(client._client, "post", new_callable=AsyncMock, return_value=resp_401):
            with pytest.raises(httpx.HTTPStatusError, match="Pi-hole auth rejected"):
                _run(client._authenticate())

    def test_authenticate_401_preserves_no_sid(self):
        """401 during auth should not set any SID."""
        from app.services.pihole.api_client import PiholeApiClient

        client = PiholeApiClient("http://localhost:8053", "password")

        resp_401 = httpx.Response(
            401,
            text="Unauthorized",
            request=httpx.Request("POST", "http://localhost:8053/api/auth"),
        )

        with patch.object(client._client, "post", new_callable=AsyncMock, return_value=resp_401):
            with pytest.raises(httpx.HTTPStatusError):
                _run(client._authenticate())

        assert client._sid is None
