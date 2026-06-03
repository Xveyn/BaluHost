"""Tests for SSH host-key pinning (TOFU) in ssh_service.

Verifies the security-relevant behaviour added to replace AutoAddPolicy:
- managed known_hosts path resolution,
- first-contact pinning fetches + stores the host key,
- an already-pinned host does NOT re-fetch,
- connections use RejectPolicy (never AutoAddPolicy).
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import paramiko
import pytest

from app.services import ssh_service
from app.services.ssh_service import (
    _connect,
    _ensure_host_pinned,
    _hostkey_entry,
    _known_hosts_path,
)


@pytest.fixture(scope="module")
def sample_key() -> paramiko.RSAKey:
    """A real RSA key so HostKeys.load() can parse the written line."""
    return paramiko.RSAKey.generate(2048)


def test_hostkey_entry_formatting():
    assert _hostkey_entry("host", 22) == "host"
    assert _hostkey_entry("host", 2222) == "[host]:2222"


def test_known_hosts_path_override(monkeypatch, tmp_path):
    target = tmp_path / "custom" / "known_hosts"
    monkeypatch.setattr(ssh_service.settings, "ssh_known_hosts_path", str(target))
    assert _known_hosts_path() == target


def test_known_hosts_path_default_under_system(monkeypatch, tmp_path):
    monkeypatch.setattr(ssh_service.settings, "ssh_known_hosts_path", "")
    monkeypatch.setattr(ssh_service.settings, "nas_storage_path", str(tmp_path))
    assert _known_hosts_path() == tmp_path / ".system" / "ssh" / "known_hosts"


def test_ensure_host_pinned_first_contact_writes_key(monkeypatch, tmp_path, sample_key):
    kh = tmp_path / "known_hosts"
    monkeypatch.setattr(ssh_service.settings, "ssh_known_hosts_path", str(kh))

    fake_transport = MagicMock()
    fake_transport.get_remote_server_key.return_value = sample_key
    with patch.object(ssh_service.paramiko, "Transport", return_value=fake_transport) as mk_t:
        _ensure_host_pinned("10.0.0.5", 22)

    mk_t.assert_called_once_with(("10.0.0.5", 22))
    fake_transport.start_client.assert_called_once()
    fake_transport.close.assert_called_once()

    # The host is now parseable from the managed file.
    keys = paramiko.HostKeys(str(kh))
    assert keys.lookup("10.0.0.5") is not None


def test_ensure_host_pinned_skips_when_already_pinned(monkeypatch, tmp_path, sample_key):
    kh = tmp_path / "known_hosts"
    kh.write_text(f"10.0.0.5 {sample_key.get_name()} {sample_key.get_base64()}\n")
    monkeypatch.setattr(ssh_service.settings, "ssh_known_hosts_path", str(kh))

    with patch.object(ssh_service.paramiko, "Transport") as mk_t:
        _ensure_host_pinned("10.0.0.5", 22)

    mk_t.assert_not_called()  # no re-fetch for an already-trusted host


def test_connect_uses_reject_policy(monkeypatch, tmp_path):
    kh = tmp_path / "known_hosts"
    kh.write_text("")  # exists but empty
    monkeypatch.setattr(ssh_service.settings, "ssh_known_hosts_path", str(kh))
    monkeypatch.setattr(ssh_service, "_ensure_host_pinned", lambda host, port: None)

    fake_client = MagicMock()
    with patch.object(ssh_service.paramiko, "SSHClient", return_value=fake_client):
        _connect("10.0.0.5", 22, "user", MagicMock())

    fake_client.load_host_keys.assert_called_once_with(str(kh))
    policy = fake_client.set_missing_host_key_policy.call_args.args[0]
    assert isinstance(policy, paramiko.RejectPolicy)
    fake_client.connect.assert_called_once()
