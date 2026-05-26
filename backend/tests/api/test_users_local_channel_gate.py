"""Tests verifying destructive user endpoints require local channel."""


def test_bulk_delete_blocked_on_remote(remote_client, admin_headers):
    resp = remote_client.post(
        "/api/users/bulk-delete",
        json=["99999"],
        headers=admin_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "local_channel_required"
