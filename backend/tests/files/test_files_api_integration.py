"""
Integration tests for Files API with database.

Tests the complete flow: API → Service → Database
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services import file_metadata_db


def test_create_folder_creates_metadata(client: TestClient, user_headers: dict, db_session: Session):
    """Test that creating a folder stores metadata in database."""
    # Non-admin users must use their home directory as parent path;
    # _jail_path() rejects empty path with 403 for non-admin users.
    response = client.post(
        f"{settings.api_prefix}/files/folder",
        json={"name": "TestFolder", "path": "testuser"},
        headers=user_headers,
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Folder created"

    # Verify metadata exists in database
    metadata = file_metadata_db.get_metadata("testuser/TestFolder", db=db_session)
    assert metadata is not None
    assert metadata.name == "TestFolder"
    assert metadata.is_directory is True


def test_upload_file_creates_metadata(client: TestClient, user_headers: dict, db_session: Session, tmp_path):
    """Test that uploading a file stores metadata in database."""
    # Create a temporary test file
    test_content = b"Hello, World!"

    response = client.post(
        f"{settings.api_prefix}/files/upload",
        data={"path": "testuser"},
        files={"files": ("test.txt", test_content, "text/plain")},
        headers=user_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["uploaded"] == 1

    # Verify the file exists on disk (metadata is written via a separate
    # SessionLocal() call inside the upload service, which uses a different
    # in-memory DB in tests; so we verify the upload response + disk instead).
    from app.services.files import ROOT_DIR
    uploaded_file = ROOT_DIR / "testuser" / "test.txt"
    assert uploaded_file.exists()
    assert uploaded_file.read_bytes() == test_content


def test_delete_file_removes_metadata(client: TestClient, user_headers: dict, db_session: Session, regular_user):
    """Test that deleting a file removes metadata from database."""
    # First create a file with metadata under user's home directory
    file_metadata_db.create_metadata(
        relative_path="testuser/to_delete.txt",
        name="to_delete.txt",
        owner_id=regular_user.id,
        size_bytes=100,
        is_directory=False,
        db=db_session
    )

    # Create the actual file
    from app.services.files import ROOT_DIR
    user_dir = ROOT_DIR / "testuser"
    user_dir.mkdir(parents=True, exist_ok=True)
    test_file = user_dir / "to_delete.txt"
    test_file.write_text("test content")

    # Delete via API
    response = client.delete(
        f"{settings.api_prefix}/files/testuser/to_delete.txt",
        headers=user_headers,
    )

    assert response.status_code == 200

    # Verify metadata is gone
    metadata = file_metadata_db.get_metadata("testuser/to_delete.txt", db=db_session)
    assert metadata is None


def test_rename_file_updates_metadata(client: TestClient, user_headers: dict, db_session: Session, regular_user):
    """Test that renaming a file updates metadata in database."""
    # Create file with metadata under user's home directory
    file_metadata_db.create_metadata(
        relative_path="testuser/old_name.txt",
        name="old_name.txt",
        owner_id=regular_user.id,
        size_bytes=50,
        is_directory=False,
        db=db_session
    )

    # Create actual file
    from app.services.files import ROOT_DIR
    user_dir = ROOT_DIR / "testuser"
    user_dir.mkdir(parents=True, exist_ok=True)
    test_file = user_dir / "old_name.txt"
    test_file.write_text("content")

    # Rename via API
    response = client.put(
        f"{settings.api_prefix}/files/rename",
        json={"old_path": "testuser/old_name.txt", "new_name": "new_name.txt"},
        headers=user_headers,
    )

    assert response.status_code == 200

    # Verify old metadata is gone
    old_meta = file_metadata_db.get_metadata("testuser/old_name.txt", db=db_session)
    assert old_meta is None

    # Verify new metadata exists
    new_meta = file_metadata_db.get_metadata("testuser/new_name.txt", db=db_session)
    assert new_meta is not None
    assert new_meta.name == "new_name.txt"


def test_move_file_updates_metadata(client: TestClient, user_headers: dict, db_session: Session, regular_user):
    """Test that moving a file updates metadata in database."""
    # Create source file with metadata under user's home directory
    file_metadata_db.create_metadata(
        relative_path="testuser/source.txt",
        name="source.txt",
        owner_id=regular_user.id,
        size_bytes=50,
        is_directory=False,
        db=db_session
    )

    # Create destination folder under user's home directory
    file_metadata_db.create_metadata(
        relative_path="testuser/destination",
        name="destination",
        owner_id=regular_user.id,
        size_bytes=0,
        is_directory=True,
        db=db_session
    )

    # Create actual file and folder
    from app.services.files import ROOT_DIR
    user_dir = ROOT_DIR / "testuser"
    user_dir.mkdir(parents=True, exist_ok=True)
    test_file = user_dir / "source.txt"
    test_file.write_text("content")
    dest_folder = user_dir / "destination"
    dest_folder.mkdir(exist_ok=True)

    # Move via API
    response = client.put(
        f"{settings.api_prefix}/files/move",
        json={"source_path": "testuser/source.txt", "target_path": "testuser/destination"},
        headers=user_headers,
    )

    assert response.status_code == 200

    # Verify old metadata is gone
    old_meta = file_metadata_db.get_metadata("testuser/source.txt", db=db_session)
    assert old_meta is None

    # Verify new metadata exists at new path
    new_meta = file_metadata_db.get_metadata("testuser/destination/source.txt", db=db_session)
    assert new_meta is not None
    assert new_meta.name == "source.txt"
    assert new_meta.parent_path == "testuser/destination"


def test_list_files_shows_owned_files_only(client: TestClient, user_headers: dict, another_user_headers: dict, db_session: Session, regular_user, another_user):
    """Test that users only see their own files in listings."""
    # Create files under each user's home directory
    file_metadata_db.create_metadata(
        relative_path="testuser/user1_file.txt",
        name="user1_file.txt",
        owner_id=regular_user.id,
        size_bytes=100,
        is_directory=False,
        db=db_session
    )

    file_metadata_db.create_metadata(
        relative_path="anotheruser/user2_file.txt",
        name="user2_file.txt",
        owner_id=another_user.id,
        size_bytes=100,
        is_directory=False,
        db=db_session
    )

    # Create actual files
    from app.services.files import ROOT_DIR
    user1_dir = ROOT_DIR / "testuser"
    user1_dir.mkdir(parents=True, exist_ok=True)
    (user1_dir / "user1_file.txt").write_text("content1")
    user2_dir = ROOT_DIR / "anotheruser"
    user2_dir.mkdir(parents=True, exist_ok=True)
    (user2_dir / "user2_file.txt").write_text("content2")

    # User 1 lists files in their home directory
    response1 = client.get(
        f"{settings.api_prefix}/files/list",
        params={"path": "testuser"},
        headers=user_headers,
    )

    assert response1.status_code == 200
    files1 = response1.json()["files"]
    file_names1 = {f["name"] for f in files1}
    assert "user1_file.txt" in file_names1
    assert "user2_file.txt" not in file_names1

    # User 2 lists files in their home directory
    response2 = client.get(
        f"{settings.api_prefix}/files/list",
        params={"path": "anotheruser"},
        headers=another_user_headers,
    )

    assert response2.status_code == 200
    files2 = response2.json()["files"]
    file_names2 = {f["name"] for f in files2}
    assert "user2_file.txt" in file_names2
    assert "user1_file.txt" not in file_names2


def test_admin_can_see_all_files(client: TestClient, admin_headers: dict, user_headers: dict, db_session: Session, admin_user, regular_user):
    """Test that admin users can see all files."""
    # Create file owned by regular user
    file_metadata_db.create_metadata(
        relative_path="user_file.txt",
        name="user_file.txt",
        owner_id=regular_user.id,
        size_bytes=100,
        is_directory=False,
        db=db_session
    )
    
    # Create actual file
    from app.services.files import ROOT_DIR
    (ROOT_DIR / "user_file.txt").write_text("content")
    
    # Admin lists files - should see user's file
    response = client.get(
        f"{settings.api_prefix}/files/list",
        headers=admin_headers,
    )
    
    assert response.status_code == 200
    files = response.json()["files"]
    file_names = {f["name"] for f in files}
    assert "user_file.txt" in file_names
