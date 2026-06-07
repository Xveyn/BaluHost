"""Route tests for /api/nfs (admin-only NFS export management)."""
from app.core.config import settings


def _create(client, headers, **over):
    body = {"path": "Media", "clients": "192.168.1.0/24", "read_only": False,
            "root_squash": True, "enabled": True, "comment": None}
    body.update(over)
    return client.post(f"{settings.api_prefix}/nfs/exports", json=body, headers=headers)


class TestNfsAuth:
    def test_status_forbidden_for_regular_user(self, client, user_headers):
        r = client.get(f"{settings.api_prefix}/nfs/status", headers=user_headers)
        assert r.status_code == 403

    def test_list_forbidden_for_regular_user(self, client, user_headers):
        r = client.get(f"{settings.api_prefix}/nfs/exports", headers=user_headers)
        assert r.status_code == 403

    def test_create_forbidden_for_regular_user(self, client, user_headers):
        r = _create(client, user_headers)
        assert r.status_code == 403


class TestNfsCrud:
    def test_status_ok_for_admin(self, client, admin_headers):
        r = client.get(f"{settings.api_prefix}/nfs/status", headers=admin_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["is_running"] is False
        assert isinstance(body["exports_count"], int)

    def test_create_list_update_delete(self, client, admin_headers):
        r = _create(client, admin_headers)
        assert r.status_code == 201, r.text
        created = r.json()
        export_id = created["id"]
        assert created["path"] == "Media"
        assert created["mount_target"].endswith("Media")

        r = client.get(f"{settings.api_prefix}/nfs/exports", headers=admin_headers)
        assert r.status_code == 200
        paths = {e["path"] for e in r.json()["exports"]}
        assert "Media" in paths

        r = client.put(
            f"{settings.api_prefix}/nfs/exports/{export_id}",
            json={"path": "Media", "clients": "192.168.1.0/24", "read_only": True,
                  "root_squash": True, "enabled": True, "comment": None},
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["read_only"] is True

        r = client.delete(f"{settings.api_prefix}/nfs/exports/{export_id}", headers=admin_headers)
        assert r.status_code == 204
        r = client.get(f"{settings.api_prefix}/nfs/exports", headers=admin_headers)
        assert export_id not in {e["id"] for e in r.json()["exports"]}

    def test_duplicate_path_conflict(self, client, admin_headers):
        assert _create(client, admin_headers, path="Dup").status_code == 201
        assert _create(client, admin_headers, path="Dup").status_code == 409

    def test_traversal_path_rejected(self, client, admin_headers):
        r = _create(client, admin_headers, path="../etc")
        assert r.status_code == 422

    def test_bad_clients_rejected(self, client, admin_headers):
        r = _create(client, admin_headers, path="Bad", clients="not a host!")
        assert r.status_code == 422
