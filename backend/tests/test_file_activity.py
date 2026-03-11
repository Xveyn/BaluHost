"""Tests for file activity tracking."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.file_activity import FileActivity
from app.schemas.file_activity import VALID_ACTION_TYPES
from app.services.file_activity import FileActivityService


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------

class TestFileActivityService:
    """Unit tests for FileActivityService."""

    def _make_service(self, db: Session) -> FileActivityService:
        return FileActivityService(db)

    def test_record_creates_entry(self, db_session: Session):
        svc = self._make_service(db_session)
        result = svc.record(
            user_id=1,
            action_type="file.upload",
            file_path="admin/test.txt",
            file_name="test.txt",
        )
        db_session.commit()

        assert result is not None
        assert result.action_type == "file.upload"
        assert result.file_name == "test.txt"
        assert result.source == "server"

    def test_record_deduplicates_within_window(self, db_session: Session):
        svc = self._make_service(db_session)
        now = datetime.now(timezone.utc)

        r1 = svc.record(
            user_id=1,
            action_type="file.download",
            file_path="admin/doc.pdf",
            file_name="doc.pdf",
            occurred_at=now,
        )
        assert r1 is not None

        # Same user, path, action within 5 minutes → deduplicated
        r2 = svc.record(
            user_id=1,
            action_type="file.download",
            file_path="admin/doc.pdf",
            file_name="doc.pdf",
            occurred_at=now + timedelta(seconds=60),
        )
        db_session.commit()

        assert r2 is None  # deduplicated
        count = db_session.query(FileActivity).count()
        assert count == 1

    def test_record_no_dedup_different_action(self, db_session: Session):
        svc = self._make_service(db_session)

        svc.record(1, "file.download", "a/b.txt", "b.txt")
        svc.record(1, "file.upload", "a/b.txt", "b.txt")
        db_session.commit()

        assert db_session.query(FileActivity).count() == 2

    def test_record_no_dedup_outside_window(self, db_session: Session):
        svc = self._make_service(db_session)
        now = datetime.now(timezone.utc)

        svc.record(1, "file.open", "a/b.txt", "b.txt", occurred_at=now - timedelta(minutes=10))
        svc.record(1, "file.open", "a/b.txt", "b.txt", occurred_at=now)
        db_session.commit()

        assert db_session.query(FileActivity).count() == 2

    def test_get_recent_activities(self, db_session: Session):
        svc = self._make_service(db_session)
        now = datetime.now(timezone.utc)

        for i in range(5):
            svc.record(
                user_id=1,
                action_type="file.upload",
                file_path=f"admin/file{i}.txt",
                file_name=f"file{i}.txt",
                occurred_at=now + timedelta(minutes=i),
            )
        db_session.commit()

        items, total = svc.get_recent_activities(user_id=1, limit=3)
        assert total == 5
        assert len(items) == 3
        # Most recent first
        assert items[0].file_name == "file4.txt"

    def test_get_recent_activities_filter_action_type(self, db_session: Session):
        svc = self._make_service(db_session)

        svc.record(1, "file.upload", "a/1.txt", "1.txt")
        svc.record(1, "file.download", "a/2.txt", "2.txt")
        db_session.commit()

        items, total = svc.get_recent_activities(
            user_id=1, action_types=["file.upload"]
        )
        assert total == 1
        assert items[0].action_type == "file.upload"

    def test_get_recent_activities_filter_path_prefix(self, db_session: Session):
        svc = self._make_service(db_session)

        svc.record(1, "file.upload", "admin/docs/a.txt", "a.txt")
        svc.record(1, "file.upload", "admin/photos/b.jpg", "b.jpg")
        db_session.commit()

        items, total = svc.get_recent_activities(
            user_id=1, path_prefix="admin/docs"
        )
        assert total == 1
        assert items[0].file_path == "admin/docs/a.txt"

    def test_get_recent_activities_user_isolation(self, db_session: Session):
        svc = self._make_service(db_session)

        svc.record(1, "file.upload", "admin/a.txt", "a.txt")
        svc.record(2, "file.upload", "user2/b.txt", "b.txt")
        db_session.commit()

        items, total = svc.get_recent_activities(user_id=1)
        assert total == 1
        assert items[0].file_path == "admin/a.txt"

    def test_get_recent_files(self, db_session: Session):
        svc = self._make_service(db_session)
        now = datetime.now(timezone.utc)

        # Two actions on same file, one on another
        svc.record(1, "file.download", "a/doc.pdf", "doc.pdf",
                    occurred_at=now - timedelta(minutes=10))
        svc.record(1, "file.open", "a/doc.pdf", "doc.pdf",
                    occurred_at=now)
        svc.record(1, "file.upload", "a/img.png", "img.png",
                    occurred_at=now - timedelta(minutes=5))
        db_session.commit()

        files = svc.get_recent_files(
            user_id=1,
            actions=["file.download", "file.open", "file.upload"],
        )
        assert len(files) == 2
        # Most recently used first
        assert files[0].file_path == "a/doc.pdf"
        assert files[0].action_count >= 1

    def test_cleanup_default_retention(self, db_session: Session):
        svc = self._make_service(db_session)
        old = datetime.now(timezone.utc) - timedelta(days=100)

        svc.record(1, "file.upload", "a/old.txt", "old.txt", occurred_at=old)
        svc.record(1, "file.upload", "a/new.txt", "new.txt")
        db_session.commit()

        deleted = svc.cleanup()
        assert deleted >= 1
        assert db_session.query(FileActivity).count() == 1

    def test_record_with_metadata(self, db_session: Session):
        svc = self._make_service(db_session)
        svc.record(
            user_id=1,
            action_type="file.move",
            file_path="admin/new/file.txt",
            file_name="file.txt",
            metadata={"from": "admin/old/file.txt", "to": "admin/new/file.txt"},
        )
        db_session.commit()

        items, _ = svc.get_recent_activities(user_id=1)
        assert items[0].metadata is not None
        assert items[0].metadata["from"] == "admin/old/file.txt"

    def test_record_client_source(self, db_session: Session):
        svc = self._make_service(db_session)
        svc.record(
            user_id=1,
            action_type="file.open",
            file_path="admin/readme.md",
            file_name="readme.md",
            source="client",
            device_id="pixel-7-abc",
        )
        db_session.commit()

        items, _ = svc.get_recent_activities(user_id=1)
        assert items[0].source == "client"
        assert items[0].device_id == "pixel-7-abc"


# ---------------------------------------------------------------------------
# API-level tests
# ---------------------------------------------------------------------------

class TestActivityEndpoints:
    """Integration tests for /api/activity/* endpoints."""

    def test_get_recent_requires_auth(self, client):
        res = client.get("/api/activity/recent")
        assert res.status_code == 401

    def test_get_recent_empty(self, client, admin_headers):
        res = client.get("/api/activity/recent", headers=admin_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["activities"] == []
        assert data["total"] == 0
        assert data["has_more"] is False

    def test_get_recent_files_requires_auth(self, client):
        res = client.get("/api/activity/recent-files")
        assert res.status_code == 401

    def test_get_recent_files_empty(self, client, admin_headers):
        res = client.get("/api/activity/recent-files", headers=admin_headers)
        assert res.status_code == 200
        assert res.json()["files"] == []

    def test_report_requires_auth(self, client):
        res = client.post("/api/activity/report", json={"activities": []})
        assert res.status_code == 401

    def test_report_activities(self, client, admin_headers):
        res = client.post(
            "/api/activity/report",
            headers=admin_headers,
            json={
                "activities": [
                    {
                        "action_type": "file.open",
                        "file_path": "admin/test.txt",
                        "file_name": "test.txt",
                        "is_directory": False,
                    }
                ]
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["accepted"] == 1
        assert data["rejected"] == 0

    def test_report_rejects_invalid_action(self, client, admin_headers):
        res = client.post(
            "/api/activity/report",
            headers=admin_headers,
            json={
                "activities": [
                    {
                        "action_type": "invalid.action",
                        "file_path": "admin/test.txt",
                        "file_name": "test.txt",
                        "is_directory": False,
                    }
                ]
            },
        )
        assert res.status_code == 200
        assert res.json()["rejected"] == 1
        assert res.json()["accepted"] == 0

    def test_report_rejects_path_traversal(self, client, admin_headers):
        res = client.post(
            "/api/activity/report",
            headers=admin_headers,
            json={
                "activities": [
                    {
                        "action_type": "file.open",
                        "file_path": "../../etc/passwd",
                        "file_name": "passwd",
                        "is_directory": False,
                    }
                ]
            },
        )
        assert res.status_code == 200
        assert res.json()["rejected"] == 1

    def test_report_deduplication(self, client, admin_headers):
        activity = {
            "action_type": "file.open",
            "file_path": "admin/dedup.txt",
            "file_name": "dedup.txt",
            "is_directory": False,
        }
        # First report
        res1 = client.post(
            "/api/activity/report",
            headers=admin_headers,
            json={"activities": [activity]},
        )
        assert res1.json()["accepted"] == 1

        # Same report again → deduplicated
        res2 = client.post(
            "/api/activity/report",
            headers=admin_headers,
            json={"activities": [activity]},
        )
        assert res2.json()["deduplicated"] == 1
        assert res2.json()["accepted"] == 0

    def test_get_recent_with_filters(self, client, admin_headers):
        # Report some activities first
        client.post(
            "/api/activity/report",
            headers=admin_headers,
            json={
                "activities": [
                    {
                        "action_type": "file.upload",
                        "file_path": "admin/a.txt",
                        "file_name": "a.txt",
                        "is_directory": False,
                    },
                    {
                        "action_type": "file.download",
                        "file_path": "admin/b.txt",
                        "file_name": "b.txt",
                        "is_directory": False,
                    },
                ]
            },
        )

        # Filter by action_type
        res = client.get(
            "/api/activity/recent?action_types=file.upload",
            headers=admin_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert all(a["action_type"] == "file.upload" for a in data["activities"])

    def test_get_recent_pagination(self, client, admin_headers):
        # Report multiple activities
        activities = [
            {
                "action_type": "file.upload",
                "file_path": f"admin/file{i}.txt",
                "file_name": f"file{i}.txt",
                "is_directory": False,
            }
            for i in range(5)
        ]
        client.post(
            "/api/activity/report",
            headers=admin_headers,
            json={"activities": activities},
        )

        res = client.get(
            "/api/activity/recent?limit=2&offset=0",
            headers=admin_headers,
        )
        data = res.json()
        assert len(data["activities"]) == 2
        assert data["total"] == 5
        assert data["has_more"] is True

    def test_report_batch_validation(self, client, admin_headers):
        """Empty batch should fail validation."""
        res = client.post(
            "/api/activity/report",
            headers=admin_headers,
            json={"activities": []},
        )
        assert res.status_code == 422  # Pydantic validation: min_length=1
