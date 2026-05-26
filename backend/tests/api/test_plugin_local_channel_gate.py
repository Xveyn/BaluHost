"""Tests verifying plugin install/uninstall require local channel."""
import pytest


def test_plugins_uninstall_blocked_on_remote(remote_client, admin_headers):
    resp = remote_client.delete("/api/plugins/some-plugin", headers=admin_headers)
    # Either 403 local_channel_required OR 404 if the local-channel check fires
    # first (it should). Verify the structured error format.
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "local_channel_required"


def test_marketplace_install_blocked_on_remote(remote_client, admin_headers):
    resp = remote_client.post(
        "/api/plugins/marketplace/some-plugin/install",
        json={"version": "1.0.0"},
        headers=admin_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "local_channel_required"


def test_marketplace_uninstall_blocked_on_remote(remote_client, admin_headers):
    resp = remote_client.delete(
        "/api/plugins/marketplace/some-plugin",
        headers=admin_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "local_channel_required"
