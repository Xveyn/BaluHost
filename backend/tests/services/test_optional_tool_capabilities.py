"""Optional external tools degrade uniformly (#543, second step).

mdadm was the only one that broke at import time (fixed separately). VPN and
cloud import resolve their tool at call time -- but failed opaquely: a missing
wireguard-tools produced HTTP 500 "Failed to generate VPN configuration", and a
missing rclone a raw FileNotFoundError on the import job.
"""
import shutil

import pytest

from app.core.capabilities import ToolUnavailableError, require_tool
from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError


class TestRequireTool:
    def test_returns_path_when_present(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _b: "/usr/bin/thing")
        assert require_tool("thing", "Thing") == "/usr/bin/thing"

    def test_raises_503_naming_feature_and_package(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda _b: None)
        with pytest.raises(ToolUnavailableError) as exc:
            require_tool("wg", "WireGuard VPN", "wireguard-tools")
        assert exc.value.http_status == 503
        assert "WireGuard VPN" in str(exc.value)
        assert "wireguard-tools" in str(exc.value)
        assert isinstance(exc.value, ServiceUnavailableError)


class TestVpnWithoutWireguardTools:
    def test_keypair_raises_tool_unavailable_not_runtime_error(self, monkeypatch):
        """Must NOT be a RuntimeError.

        routes/vpn.py catches RuntimeError and answers 500 "Failed to generate
        VPN configuration". Staying outside that type is what lets the global
        ServiceError handler answer 503 with the real reason -- so the check
        also has to sit before the blanket ``except Exception -> RuntimeError``
        inside the generator.
        """
        from app.services.vpn.service import VPNService

        monkeypatch.setattr(settings, "is_dev_mode", False)
        monkeypatch.setattr(shutil, "which", lambda _b: None)

        with pytest.raises(ToolUnavailableError) as exc:
            VPNService.generate_wireguard_keypair()
        assert not isinstance(exc.value, RuntimeError)
        assert "wireguard-tools" in str(exc.value)

    def test_preshared_key_raises_tool_unavailable(self, monkeypatch):
        from app.services.vpn.service import VPNService

        monkeypatch.setattr(settings, "is_dev_mode", False)
        monkeypatch.setattr(shutil, "which", lambda _b: None)

        with pytest.raises(ToolUnavailableError):
            VPNService.generate_preshared_key()

    def test_dev_mode_still_mocks_keys(self, monkeypatch):
        """Dev mode never needed the binary and must stay that way."""
        from app.services.vpn.service import VPNService

        monkeypatch.setattr(settings, "is_dev_mode", True)
        monkeypatch.setattr(shutil, "which", lambda _b: None)

        private_key, public_key = VPNService.generate_wireguard_keypair()
        assert private_key and public_key and private_key != public_key


class TestRcloneWithoutBinary:
    @pytest.mark.asyncio
    async def test_run_rclone_raises_tool_unavailable(self, monkeypatch):
        """The job record shows this string (export_service stores str(e)),
        so it must read as a reason, not as "[Errno 2] ... 'rclone'".
        """
        from app.services.cloud.adapters.rclone import RcloneAdapter

        adapter = RcloneAdapter.__new__(RcloneAdapter)
        monkeypatch.setattr(shutil, "which", lambda _b: None)

        with pytest.raises(ToolUnavailableError) as exc:
            await adapter._run_rclone("lsjson", "remote:")
        assert "rclone" in str(exc.value)
