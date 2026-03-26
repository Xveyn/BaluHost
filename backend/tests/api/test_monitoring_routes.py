"""
API integration tests for monitoring routes.

Tests:
- CPU, Memory, Network, Disk I/O current and history endpoints
- Process tracking endpoints
- Monitoring status endpoint
- Admin-only retention configuration
"""
import pytest
from fastapi.testclient import TestClient


class TestMonitoringStatusEndpoint:
    """Tests for GET /api/monitoring/status."""

    def test_status_requires_auth(self, client: TestClient):
        """Test that status endpoint requires authentication."""
        response = client.get("/api/monitoring/status")
        assert response.status_code == 401

    def test_status_returns_data(self, client: TestClient, user_headers: dict):
        """Test that status endpoint returns monitoring data."""
        response = client.get("/api/monitoring/status", headers=user_headers)
        assert response.status_code == 200

        data = response.json()
        assert "is_running" in data
        assert "sample_count" in data
        assert "sample_interval" in data
        assert "collectors" in data


class TestCpuEndpoints:
    """Tests for CPU monitoring endpoints."""

    def test_cpu_current_requires_auth(self, client: TestClient):
        """Test that CPU current requires authentication."""
        response = client.get("/api/monitoring/cpu/current")
        assert response.status_code == 401

    def test_cpu_current_returns_data_or_503(self, client: TestClient, user_headers: dict):
        """Test CPU current endpoint returns data or 503 if not ready."""
        response = client.get("/api/monitoring/cpu/current", headers=user_headers)
        # May return 503 if no samples collected yet, or 200 with data
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "timestamp" in data
            assert "usage_percent" in data

    def test_cpu_history_requires_auth(self, client: TestClient):
        """Test that CPU history requires authentication."""
        response = client.get("/api/monitoring/cpu/history")
        assert response.status_code == 401

    def test_cpu_history_returns_data(self, client: TestClient, user_headers: dict):
        """Test CPU history endpoint returns list."""
        response = client.get("/api/monitoring/cpu/history", headers=user_headers)
        assert response.status_code == 200

        data = response.json()
        assert "samples" in data
        assert "sample_count" in data
        assert "source" in data

    def test_cpu_history_with_time_range(self, client: TestClient, user_headers: dict):
        """Test CPU history with time_range parameter."""
        response = client.get(
            "/api/monitoring/cpu/history",
            params={"time_range": "1h"},
            headers=user_headers
        )
        assert response.status_code == 200


class TestMemoryEndpoints:
    """Tests for Memory monitoring endpoints."""

    def test_memory_current_requires_auth(self, client: TestClient):
        """Test that memory current requires authentication."""
        response = client.get("/api/monitoring/memory/current")
        assert response.status_code == 401

    def test_memory_current_returns_data_or_503(self, client: TestClient, user_headers: dict):
        """Test memory current endpoint returns data or 503 if not ready."""
        response = client.get("/api/monitoring/memory/current", headers=user_headers)
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "timestamp" in data
            assert "used_bytes" in data
            assert "total_bytes" in data

    def test_memory_history_returns_data(self, client: TestClient, user_headers: dict):
        """Test memory history endpoint returns list."""
        response = client.get("/api/monitoring/memory/history", headers=user_headers)
        assert response.status_code == 200

        data = response.json()
        assert "samples" in data
        assert "sample_count" in data


class TestNetworkEndpoints:
    """Tests for Network monitoring endpoints."""

    def test_network_current_requires_auth(self, client: TestClient):
        """Test that network current requires authentication."""
        response = client.get("/api/monitoring/network/current")
        assert response.status_code == 401

    def test_network_current_returns_data_or_503(self, client: TestClient, user_headers: dict):
        """Test network current endpoint returns data or 503 if not ready."""
        response = client.get("/api/monitoring/network/current", headers=user_headers)
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "timestamp" in data
            assert "download_mbps" in data
            assert "upload_mbps" in data

    def test_network_history_returns_data(self, client: TestClient, user_headers: dict):
        """Test network history endpoint returns list."""
        response = client.get("/api/monitoring/network/history", headers=user_headers)
        assert response.status_code == 200

        data = response.json()
        assert "samples" in data
        assert "sample_count" in data


class TestDiskIoEndpoints:
    """Tests for Disk I/O monitoring endpoints."""

    def test_disk_io_current_requires_auth(self, client: TestClient):
        """Test that disk I/O current requires authentication."""
        response = client.get("/api/monitoring/disk-io/current")
        assert response.status_code == 401

    def test_disk_io_current_returns_data(self, client: TestClient, user_headers: dict):
        """Test disk I/O current endpoint returns disk list."""
        response = client.get("/api/monitoring/disk-io/current", headers=user_headers)
        assert response.status_code == 200

        data = response.json()
        assert "disks" in data

    def test_disk_io_history_returns_data(self, client: TestClient, user_headers: dict):
        """Test disk I/O history endpoint returns data."""
        response = client.get("/api/monitoring/disk-io/history", headers=user_headers)
        assert response.status_code == 200

        data = response.json()
        assert "disks" in data
        assert "available_disks" in data
        assert "sample_count" in data


class TestProcessEndpoints:
    """Tests for process monitoring endpoints."""

    def test_processes_current_requires_auth(self, client: TestClient):
        """Test that processes current requires authentication."""
        response = client.get("/api/monitoring/processes/current")
        assert response.status_code == 401

    def test_processes_current_returns_data(self, client: TestClient, user_headers: dict):
        """Test processes current endpoint returns process list."""
        response = client.get("/api/monitoring/processes/current", headers=user_headers)
        assert response.status_code == 200

        data = response.json()
        assert "processes" in data

    def test_processes_history_returns_data(self, client: TestClient, user_headers: dict):
        """Test processes history endpoint returns data."""
        response = client.get("/api/monitoring/processes/history", headers=user_headers)
        assert response.status_code == 200

        data = response.json()
        assert "processes" in data
        assert "sample_count" in data


class TestRetentionConfigEndpoints:
    """Tests for retention configuration endpoints (admin only)."""

    def test_retention_config_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that retention config requires admin."""
        response = client.get("/api/monitoring/config/retention", headers=user_headers)
        assert response.status_code == 403

    def test_retention_config_returns_data(self, client: TestClient, admin_headers: dict):
        """Test retention config endpoint returns configs."""
        response = client.get("/api/monitoring/config/retention", headers=admin_headers)
        assert response.status_code == 200

        data = response.json()
        assert "configs" in data
        assert isinstance(data["configs"], list)

    def test_update_retention_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that updating retention config requires admin."""
        response = client.put(
            "/api/monitoring/config/retention/cpu",
            json={"retention_hours": 48},
            headers=user_headers
        )
        assert response.status_code == 403

    def test_update_retention_invalid_metric(self, client: TestClient, admin_headers: dict):
        """Test updating retention with invalid metric type."""
        response = client.put(
            "/api/monitoring/config/retention/invalid_metric",
            json={"retention_hours": 48},
            headers=admin_headers
        )
        assert response.status_code == 400


class TestDatabaseStatsEndpoint:
    """Tests for database statistics endpoint (admin only)."""

    def test_database_stats_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that database stats requires admin."""
        response = client.get("/api/monitoring/stats/database", headers=user_headers)
        assert response.status_code == 403

    def test_database_stats_returns_data(self, client: TestClient, admin_headers: dict):
        """Test database stats endpoint returns stats."""
        response = client.get("/api/monitoring/stats/database", headers=admin_headers)
        assert response.status_code == 200

        data = response.json()
        assert "metrics" in data
        assert "total_samples" in data
        assert "total_size_bytes" in data


class TestUptimeEndpoints:
    """Tests for uptime monitoring endpoints."""

    def test_uptime_current_requires_auth(self, client: TestClient):
        """Test that uptime current requires authentication."""
        response = client.get("/api/monitoring/uptime/current")
        assert response.status_code == 401

    def test_uptime_current_returns_data(self, client: TestClient, user_headers: dict):
        """Test uptime current always returns data (live computation fallback)."""
        response = client.get("/api/monitoring/uptime/current", headers=user_headers)
        assert response.status_code == 200

        data = response.json()
        assert "timestamp" in data
        assert "server_uptime_seconds" in data
        assert "system_uptime_seconds" in data
        assert "server_start_time" in data
        assert "system_boot_time" in data
        assert data["server_uptime_seconds"] >= 0
        assert data["system_uptime_seconds"] >= 0

    def test_uptime_history_requires_auth(self, client: TestClient):
        """Test that uptime history requires authentication."""
        response = client.get("/api/monitoring/uptime/history")
        assert response.status_code == 401

    def test_uptime_history_returns_data(self, client: TestClient, user_headers: dict):
        """Test uptime history returns data (with live fallback)."""
        response = client.get("/api/monitoring/uptime/history", headers=user_headers)
        assert response.status_code == 200

        data = response.json()
        assert "samples" in data
        assert "sample_count" in data
        assert "source" in data

    def test_uptime_history_never_empty(self, client: TestClient, user_headers: dict):
        """Test uptime history is never empty thanks to live fallback."""
        for tr in ["10m", "1h", "24h", "7d"]:
            response = client.get(
                "/api/monitoring/uptime/history",
                params={"time_range": tr},
                headers=user_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["sample_count"] > 0, f"Expected samples for time_range={tr}"
            # Source should indicate where data came from
            assert data["source"] in [
                "memory", "database", "database (fallback)",
                "memory (fallback)", "live (computed)",
            ]

    def test_uptime_history_samples_have_correct_fields(self, client: TestClient, user_headers: dict):
        """Test that uptime history samples contain all required fields."""
        response = client.get(
            "/api/monitoring/uptime/history",
            params={"time_range": "10m"},
            headers=user_headers,
        )
        assert response.status_code == 200

        data = response.json()
        if data["samples"]:
            sample = data["samples"][0]
            assert "timestamp" in sample
            assert "server_uptime_seconds" in sample
            assert "system_uptime_seconds" in sample
            assert "server_start_time" in sample
            assert "system_boot_time" in sample

    def test_uptime_history_with_all_time_ranges(self, client: TestClient, user_headers: dict):
        """Test uptime history accepts all valid time ranges."""
        for tr in ["10m", "1h", "24h", "7d"]:
            response = client.get(
                "/api/monitoring/uptime/history",
                params={"time_range": tr},
                headers=user_headers,
            )
            assert response.status_code == 200


class TestUptimeSleepEvents:
    """Tests for sleep events in uptime history."""

    def test_uptime_history_includes_sleep_events_field(self, client: TestClient, user_headers: dict):
        """Test that uptime history response contains sleep_events field."""
        response = client.get(
            "/api/monitoring/uptime/history",
            params={"time_range": "1h"},
            headers=user_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "sleep_events" in data
        assert isinstance(data["sleep_events"], list)

    def test_uptime_history_sleep_events_have_correct_fields(self, client: TestClient, user_headers: dict, db_session):
        """Test that sleep events contain all required fields."""
        from app.models.sleep import SleepStateLog

        # Insert a test sleep event
        log_entry = SleepStateLog(
            previous_state="awake",
            new_state="soft_sleep",
            reason="test",
            triggered_by="manual",
            duration_seconds=120.0,
        )
        db_session.add(log_entry)
        db_session.commit()

        response = client.get(
            "/api/monitoring/uptime/history",
            params={"time_range": "1h"},
            headers=user_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["sleep_events"]) >= 1

        event = data["sleep_events"][0]
        assert "timestamp" in event
        assert event["previous_state"] == "awake"
        assert event["new_state"] == "soft_sleep"
        assert "duration_seconds" in event


class TestCleanupEndpoint:
    """Tests for cleanup trigger endpoint (admin only)."""

    def test_cleanup_requires_admin(self, client: TestClient, user_headers: dict):
        """Test that cleanup trigger requires admin."""
        response = client.post("/api/monitoring/cleanup", headers=user_headers)
        assert response.status_code == 403

    def test_cleanup_succeeds(self, client: TestClient, admin_headers: dict):
        """Test cleanup trigger returns success."""
        response = client.post("/api/monitoring/cleanup", headers=admin_headers)
        assert response.status_code == 200

        data = response.json()
        assert "message" in data
        assert "deleted" in data
        assert "total" in data
