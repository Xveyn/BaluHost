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
    response = client.post(
        f"{settings.api_prefix}/files/folder",
        json={"name": "TestFolder", "path": ""},
        headers=user_headers,
    )
    
    assert response.status_code == 200
    assert response.json()["message"] == "Folder created"
    
    # Verify metadata exists in database
    metadata = file_metadata_db.get_metadata("TestFolder", db=db_session)
    assert metadata is not None
    assert metadata.name == "TestFolder"
    assert metadata.is_directory is True


def test_upload_file_creates_metadata(client: TestClient, user_headers: dict, db_session: Session, tmp_path):
    """Test that uploading a file stores metadata in database."""
    # Create a temporary test file
    test_content = b"Hello, World!"
    
    response = client.post(
        f"{settings.api_prefix}/files/upload",
        data={"path": ""},
        files={"files": ("test.txt", test_content, "text/plain")},
        headers=user_headers,
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["uploaded"] == 1
    
    # Verify metadata exists in database
    metadata = file_metadata_db.get_metadata("test.txt", db=db_session)
    assert metadata is not None
    assert metadata.name == "test.txt"
    assert metadata.is_directory is False
    assert metadata.size_bytes == len(test_content)


def test_delete_file_removes_metadata(client: TestClient, user_headers: dict, db_session: Session, regular_user):
    """Test that deleting a file removes metadata from database."""
    # First create a file with metadata
    file_metadata_db.create_metadata(
        relative_path="to_delete.txt",
        name="to_delete.txt",
        owner_id=regular_user.id,
        size_bytes=100,
        is_directory=False,
        db=db_session
    )
    
    # Create the actual file
    from app.services.files import ROOT_DIR
    test_file = ROOT_DIR / "to_delete.txt"
    test_file.write_text("test content")
    
    # Delete via API
    response = client.delete(
        f"{settings.api_prefix}/files/to_delete.txt",
        headers=user_headers,
    )
    
    assert response.status_code == 200
    
    # Verify metadata is gone
    metadata = file_metadata_db.get_metadata("to_delete.txt", db=db_session)
    assert metadata is None


def test_rename_file_updates_metadata(client: TestClient, user_headers: dict, db_session: Session, regular_user):
    """Test that renaming a file updates metadata in database."""
    # Create file with metadata
    file_metadata_db.create_metadata(
        relative_path="old_name.txt",
        name="old_name.txt",
        owner_id=regular_user.id,
        size_bytes=50,
        is_directory=False,
        db=db_session
    )
    
    # Create actual file
    from app.services.files import ROOT_DIR
    test_file = ROOT_DIR / "old_name.txt"
    test_file.write_text("content")
    
    # Rename via API
    response = client.put(
        f"{settings.api_prefix}/files/rename",
        json={"old_path": "old_name.txt", "new_name": "new_name.txt"},
        headers=user_headers,
    )
    
    assert response.status_code == 200
    
    # Verify old metadata is gone
    old_meta = file_metadata_db.get_metadata("old_name.txt", db=db_session)
    assert old_meta is None
    
    # Verify new metadata exists
    new_meta = file_metadata_db.get_metadata("new_name.txt", db=db_session)
    assert new_meta is not None
    assert new_meta.name == "new_name.txt"


def test_move_file_updates_metadata(client: TestClient, user_headers: dict, db_session: Session, regular_user):
    """Test that moving a file updates metadata in database."""
    # Create source file with metadata
    file_metadata_db.create_metadata(
        relative_path="source.txt",
        name="source.txt",
        owner_id=regular_user.id,
        size_bytes=50,
        is_directory=False,
        db=db_session
    )
    
    # Create destination folder
    file_metadata_db.create_metadata(
        relative_path="destination",
        name="destination",
        owner_id=regular_user.id,
        size_bytes=0,
        is_directory=True,
        db=db_session
    )
    
    # Create actual file and folder
    from app.services.files import ROOT_DIR
    test_file = ROOT_DIR / "source.txt"
    test_file.write_text("content")
    dest_folder = ROOT_DIR / "destination"
    dest_folder.mkdir(exist_ok=True)
    
    # Move via API
    response = client.put(
        f"{settings.api_prefix}/files/move",
        json={"source_path": "source.txt", "target_path": "destination"},
        headers=user_headers,
    )
    
    assert response.status_code == 200
    
    # Verify old metadata is gone
    old_meta = file_metadata_db.get_metadata("source.txt", db=db_session)
    assert old_meta is None
    
    # Verify new metadata exists at new path
    new_meta = file_metadata_db.get_metadata("destination/source.txt", db=db_session)
    assert new_meta is not None
    assert new_meta.name == "source.txt"
    assert new_meta.parent_path == "destination"


def test_list_files_shows_owned_files_only(client: TestClient, user_headers: dict, another_user_headers: dict, db_session: Session, regular_user, another_user):
    """Test that users only see their own files in listings."""
    # Create files for different users
    file_metadata_db.create_metadata(
        relative_path="user1_file.txt",
        name="user1_file.txt",
        owner_id=regular_user.id,
        size_bytes=100,
        is_directory=False,
        db=db_session
    )
    
    file_metadata_db.create_metadata(
        relative_path="user2_file.txt",
        name="user2_file.txt",
        owner_id=another_user.id,
        size_bytes=100,
        is_directory=False,
        db=db_session
    )
    
    # Create actual files
    from app.services.files import ROOT_DIR
    (ROOT_DIR / "user1_file.txt").write_text("content1")
    (ROOT_DIR / "user2_file.txt").write_text("content2")
    
    # User 1 lists files - should only see their own
    response1 = client.get(
        f"{settings.api_prefix}/files/list",
        headers=user_headers,
    )
    
    assert response1.status_code == 200
    files1 = response1.json()["files"]
    file_names1 = {f["name"] for f in files1}
    assert "user1_file.txt" in file_names1
    assert "user2_file.txt" not in file_names1
    
    # User 2 lists files - should only see their own
    response2 = client.get(
        f"{settings.api_prefix}/files/list",
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
