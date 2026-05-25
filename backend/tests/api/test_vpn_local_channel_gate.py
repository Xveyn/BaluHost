"""Tests verifying destructive VPN endpoints require local channel."""


def test_sync_server_keys_blocked_on_remote(remote_client, admin_headers):
    resp = remote_client.post("/api/vpn/sync-server-keys", headers=admin_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "local_channel_required"
