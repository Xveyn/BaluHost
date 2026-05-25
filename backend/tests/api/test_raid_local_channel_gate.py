"""Tests verifying destructive RAID endpoints require local channel."""


def test_delete_array_blocked_on_remote(remote_client, admin_headers):
    resp = remote_client.post(
        "/api/system/raid/delete-array",
        json={"array": "md0"},
        headers=admin_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "local_channel_required"


def test_create_array_blocked_on_remote(remote_client, admin_headers):
    resp = remote_client.post(
        "/api/system/raid/create-array",
        json={"name": "md_test", "level": "raid1", "devices": ["sdc", "sdd"]},
        headers=admin_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "local_channel_required"


def test_format_disk_blocked_on_remote(remote_client, admin_headers):
    resp = remote_client.post(
        "/api/system/raid/format-disk",
        json={"device": "sdc"},
        headers=admin_headers,
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "local_channel_required"
