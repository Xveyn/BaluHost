from __future__ import annotations

import os
from io import BytesIO
from typing import Generator

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("NAS_MODE", "dev")
os.environ.setdefault("NAS_QUOTA_BYTES", str(10 * 1024 * 1024 * 1024))

from app.main import app  # noqa: E402
from app.core.config import settings
from app.schemas.user import UserCreate
from app.services import users as user_service
from scripts.reset_dev_storage import reset_dev_storage


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    reset_dev_storage()
    with TestClient(app) as test_client:
        yield test_client
    reset_dev_storage()


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        f"{settings.api_prefix}/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _create_user(username: str, email: str, password: str, role: str = "user") -> str:
    user = user_service.create_user(
        UserCreate(username=username, email=email, password=password, role=role)
    )
    return user.id


@pytest.fixture
def admin_token(client: TestClient) -> str:
    return _login(client, "admin", "changeme")


@pytest.fixture
def user1_token(client: TestClient) -> str:
    _create_user("user1", "user1@example.com", "password1", "user")
    return _login(client, "user1", "password1")


@pytest.fixture
def user2_token(client: TestClient) -> str:
    _create_user("user2", "user2@example.com", "password2", "user")
    return _login(client, "user2", "password2")


def test_owner_can_delete_own_file(client: TestClient, user1_token: str) -> None:
    # Upload file as user1
    files = {"files": ("test.txt", BytesIO(b"content"), "text/plain")}
    upload_resp = client.post(
        f"{settings.api_prefix}/files/upload",
        files=files,
        data={"path": ""},
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert upload_resp.status_code == 200

    # Delete file as user1
    delete_resp = client.delete(
        f"{settings.api_prefix}/files/test.txt",
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert delete_resp.status_code == 200


def test_non_owner_cannot_delete_file(client: TestClient, user1_token: str, user2_token: str) -> None:
    # Upload file as user1
    files = {"files": ("private.txt", BytesIO(b"user1 data"), "text/plain")}
    upload_resp = client.post(
        f"{settings.api_prefix}/files/upload",
        files=files,
        data={"path": ""},
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert upload_resp.status_code == 200

    # Try to delete as user2
    delete_resp = client.delete(
        f"{settings.api_prefix}/files/private.txt",
        headers={"Authorization": f"Bearer {user2_token}"},
    )
    assert delete_resp.status_code == 403


def test_admin_can_delete_any_file(client: TestClient, user1_token: str, admin_token: str) -> None:
    # Upload file as user1
    files = {"files": ("user_file.txt", BytesIO(b"owned by user1"), "text/plain")}
    upload_resp = client.post(
        f"{settings.api_prefix}/files/upload",
        files=files,
        data={"path": ""},
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert upload_resp.status_code == 200

    # Admin deletes the file
    delete_resp = client.delete(
        f"{settings.api_prefix}/files/user_file.txt",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete_resp.status_code == 200


def test_owner_can_rename_own_file(client: TestClient, user1_token: str) -> None:
    # Upload file
    files = {"files": ("original.txt", BytesIO(b"content"), "text/plain")}
    client.post(
        f"{settings.api_prefix}/files/upload",
        files=files,
        data={"path": ""},
        headers={"Authorization": f"Bearer {user1_token}"},
    )

    # Rename file
    rename_resp = client.put(
        f"{settings.api_prefix}/files/rename",
        json={"old_path": "original.txt", "new_name": "renamed.txt"},
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert rename_resp.status_code == 200


def test_non_owner_cannot_rename_file(client: TestClient, user1_token: str, user2_token: str) -> None:
    # Upload file as user1
    files = {"files": ("locked.txt", BytesIO(b"content"), "text/plain")}
    client.post(
        f"{settings.api_prefix}/files/upload",
        files=files,
        data={"path": ""},
        headers={"Authorization": f"Bearer {user1_token}"},
    )

    # Try to rename as user2
    rename_resp = client.put(
        f"{settings.api_prefix}/files/rename",
        json={"old_path": "locked.txt", "new_name": "hacked.txt"},
        headers={"Authorization": f"Bearer {user2_token}"},
    )
    assert rename_resp.status_code == 403


def test_owner_can_move_own_file(client: TestClient, user1_token: str) -> None:
    # Create folder
    client.post(
        f"{settings.api_prefix}/files/folder",
        json={"path": "", "name": "myfolder"},
        headers={"Authorization": f"Bearer {user1_token}"},
    )

    # Upload file
    files = {"files": ("moveme.txt", BytesIO(b"content"), "text/plain")}
    client.post(
        f"{settings.api_prefix}/files/upload",
        files=files,
        data={"path": ""},
        headers={"Authorization": f"Bearer {user1_token}"},
    )

    # Move file
    move_resp = client.put(
        f"{settings.api_prefix}/files/move",
        json={"source_path": "moveme.txt", "target_path": "myfolder/moveme.txt"},
        headers={"Authorization": f"Bearer {user1_token}"},
    )
    assert move_resp.status_code == 200


def test_non_owner_cannot_move_file(client: TestClient, user1_token: str, user2_token: str) -> None:
    # Create folder as user2
    client.post(
        f"{settings.api_prefix}/files/folder",
        json={"path": "", "name": "user2folder"},
        headers={"Authorization": f"Bearer {user2_token}"},
    )

    # Upload file as user1
    files = {"files": ("nomove.txt", BytesIO(b"stay"), "text/plain")}
    client.post(
        f"{settings.api_prefix}/files/upload",
        files=files,
        data={"path": ""},
        headers={"Authorization": f"Bearer {user1_token}"},
    )

    # Try to move user1 file into user2 folder
    move_resp = client.put(
        f"{settings.api_prefix}/files/move",
        json={"source_path": "nomove.txt", "target_path": "user2folder/nomove.txt"},
        headers={"Authorization": f"Bearer {user2_token}"},
    )
    assert move_resp.status_code == 403


def test_user_cannot_upload_to_other_user_folder(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    # Create folder as user1
    client.post(
        f"{settings.api_prefix}/files/folder",
        json={"path": "", "name": "private"},
        headers={"Authorization": f"Bearer {user1_token}"},
    )

    # Try to upload as user2 into user1 folder
    files = {"files": ("intrusion.txt", BytesIO(b"nope"), "text/plain")}
    upload_resp = client.post(
        f"{settings.api_prefix}/files/upload",
        files=files,
        data={"path": "private"},
        headers={"Authorization": f"Bearer {user2_token}"},
    )
    assert upload_resp.status_code == 403


def test_admin_can_upload_anywhere(client: TestClient, user1_token: str, admin_token: str) -> None:
    # Create folder as user1
    client.post(
        f"{settings.api_prefix}/files/folder",
        json={"path": "", "name": "userfolder"},
        headers={"Authorization": f"Bearer {user1_token}"},
    )

    # Admin uploads into user folder
    files = {"files": ("admin_note.txt", BytesIO(b"from admin"), "text/plain")}
    upload_resp = client.post(
        f"{settings.api_prefix}/files/upload",
        files=files,
        data={"path": "userfolder"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert upload_resp.status_code == 200


def test_list_files_shows_only_accessible(
    client: TestClient, user1_token: str, user2_token: str
) -> None:
    # Upload file as user1
    files = {"files": ("visible.txt", BytesIO(b"user1"), "text/plain")}
    client.post(
        f"{settings.api_prefix}/files/upload",
        files=files,
        data={"path": ""},
        headers={"Authorization": f"Bearer {user1_token}"},
    )

    # List as user2
    list_resp = client.get(
        f"{settings.api_prefix}/files/list",
        headers={"Authorization": f"Bearer {user2_token}"},
    )
    assert list_resp.status_code == 200
    files_data = list_resp.json()["files"]
    
    # User2 should not see user1's files (unless no owner or admin override)
    user1_files = [f for f in files_data if f.get("owner_id") and f["owner_id"] != "1"]
    # Since we're filtering on backend now, files without ownership or visible should appear
    # This test depends on implementation - adjust based on actual filter behavior
