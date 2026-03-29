# Cloud Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to upload NAS files/folders to Google Drive or OneDrive and generate sharing links, integrated into the existing Share modal and Shares page.

**Architecture:** New `CloudExportJob` model + `CloudExportService` handle background upload via rclone and link creation. The existing `RcloneAdapter` gets upload/link methods. Frontend: unified Share modal with Intern/Cloud tabs, new "Cloud Shares" tab on SharesPage.

**Tech Stack:** Python/FastAPI, SQLAlchemy, rclone CLI, React/TypeScript, Tailwind CSS, i18n (react-i18next)

**Spec:** `docs/superpowers/specs/2026-03-29-cloud-export-design.md`

---

## File Map

### New Files (Backend)
| File | Responsibility |
|------|---------------|
| `backend/app/models/cloud_export.py` | `CloudExportJob` ORM model |
| `backend/app/schemas/cloud_export.py` | Pydantic request/response schemas |
| `backend/app/services/cloud/export_service.py` | Export business logic (start, execute, revoke, retry, stats) |
| `backend/app/api/routes/cloud_export.py` | API endpoints under `/api/cloud-export/` |
| `backend/alembic/versions/xxxx_add_cloud_export_jobs.py` | DB migration |
| `backend/tests/services/test_cloud_export_service.py` | Service unit tests |
| `backend/tests/api/test_cloud_export_routes.py` | API integration tests |

### Modified Files (Backend)
| File | Change |
|------|--------|
| `backend/app/services/cloud/adapters/base.py` | Add `UploadResult`, `upload_file`, `upload_folder`, `create_share_link` to ABC |
| `backend/app/services/cloud/adapters/rclone.py` | Implement upload + link methods |
| `backend/app/services/cloud/adapters/dev.py` | Mock upload + link methods |
| `backend/app/services/cloud/service.py` | Add `check_connection_scope`, extend `get_oauth_url` with scopes param, extend `handle_oauth_callback` for upgrade |
| `backend/app/api/routes/__init__.py` | Register `cloud_export` router |
| `backend/app/services/audit/admin_db.py` | Add `cloud_export_jobs` to table whitelist |

### New Files (Frontend)
| File | Responsibility |
|------|---------------|
| `client/src/api/cloud-export.ts` | API client functions |
| `client/src/components/ShareFileModal.tsx` | Unified share modal (replaces CreateFileShareModal usage in FileManager) |

### Modified Files (Frontend)
| File | Change |
|------|--------|
| `client/src/pages/FileManager.tsx` | Use new `ShareFileModal` instead of `CreateFileShareModal` |
| `client/src/pages/SharesPage.tsx` | Add "Cloud Shares" tab with stats + table |
| `client/src/i18n/locales/en/shares.json` | Add cloud export i18n keys |
| `client/src/i18n/locales/de/shares.json` | Add cloud export i18n keys (German) |

---

## Task 1: CloudExportJob Model + Migration

**Files:**
- Create: `backend/app/models/cloud_export.py`
- Modify: `backend/app/services/audit/admin_db.py:18-20`
- Test: `backend/tests/services/test_cloud_export_service.py`

- [ ] **Step 1: Write the model test**

Create `backend/tests/services/test_cloud_export_service.py`:

```python
"""Tests for CloudExportJob model and CloudExportService."""

from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.cloud import CloudConnection
from app.models.cloud_export import CloudExportJob


def _create_connection(db: Session, user_id: int = 1) -> CloudConnection:
    """Helper to create a cloud connection."""
    conn = CloudConnection(
        user_id=user_id,
        provider="google_drive",
        display_name="Test Drive",
        encrypted_config="encrypted-data",
        is_active=True,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


class TestCloudExportJobModel:
    def test_create_export_job(self, db_session: Session):
        conn = _create_connection(db_session)
        job = CloudExportJob(
            user_id=1,
            connection_id=conn.id,
            source_path="Documents/report.pdf",
            is_directory=False,
            file_name="report.pdf",
            file_size_bytes=2_500_000,
            cloud_folder="BaluHost Shares/",
            link_type="view",
            status="pending",
            progress_bytes=0,
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        assert job.id is not None
        assert job.status == "pending"
        assert job.share_link is None
        assert job.cloud_path is None

    def test_is_expired_with_no_expiry(self, db_session: Session):
        conn = _create_connection(db_session)
        job = CloudExportJob(
            user_id=1,
            connection_id=conn.id,
            source_path="test.txt",
            is_directory=False,
            file_name="test.txt",
            cloud_folder="BaluHost Shares/",
            link_type="view",
            status="ready",
            progress_bytes=0,
        )
        db_session.add(job)
        db_session.commit()
        assert job.is_expired() is False

    def test_is_expired_with_future_expiry(self, db_session: Session):
        conn = _create_connection(db_session)
        job = CloudExportJob(
            user_id=1,
            connection_id=conn.id,
            source_path="test.txt",
            is_directory=False,
            file_name="test.txt",
            cloud_folder="BaluHost Shares/",
            link_type="view",
            status="ready",
            progress_bytes=0,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db_session.add(job)
        db_session.commit()
        assert job.is_expired() is False

    def test_is_expired_with_past_expiry(self, db_session: Session):
        conn = _create_connection(db_session)
        job = CloudExportJob(
            user_id=1,
            connection_id=conn.id,
            source_path="test.txt",
            is_directory=False,
            file_name="test.txt",
            cloud_folder="BaluHost Shares/",
            link_type="view",
            status="ready",
            progress_bytes=0,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(job)
        db_session.commit()
        assert job.is_expired() is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_cloud_export_service.py::TestCloudExportJobModel -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.cloud_export'`

- [ ] **Step 3: Create the model**

Create `backend/app/models/cloud_export.py`:

```python
"""Database model for cloud export jobs."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class CloudExportJob(Base):
    """Cloud export job — uploads a NAS file/folder to a cloud provider and creates a sharing link."""

    __tablename__ = "cloud_export_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cloud_connections.id", ondelete="CASCADE"), nullable=False
    )

    # Source (NAS)
    source_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_directory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Destination (Cloud)
    cloud_folder: Mapped[str] = mapped_column(
        String(500), nullable=False, default="BaluHost Shares/"
    )
    cloud_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Sharing
    share_link: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    link_type: Mapped[str] = mapped_column(String(20), nullable=False, default="view")
    link_password: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | uploading | creating_link | ready | failed | revoked
    progress_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<CloudExportJob(id={self.id}, status='{self.status}', file='{self.file_name}')>"

    def is_expired(self) -> bool:
        """Check if the export link has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_cloud_export_service.py::TestCloudExportJobModel -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Add to admin_db whitelist and REDACT_PATTERN coverage**

In `backend/app/services/audit/admin_db.py`, add `"cloud_export_jobs"` to the `"Cloud"` category in `_TABLE_CATEGORIES`. The existing `REDACT_PATTERN` already covers `password|secret|token|private_key|api_key` which will redact `link_password`.

- [ ] **Step 6: Create Alembic migration**

Run: `cd backend && alembic revision --autogenerate -m "add cloud_export_jobs table"`
Then: `cd backend && alembic upgrade head`

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/cloud_export.py backend/tests/services/test_cloud_export_service.py backend/app/services/audit/admin_db.py backend/alembic/versions/
git commit -m "feat(cloud-export): add CloudExportJob model and migration"
```

---

## Task 2: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/cloud_export.py`
- Test: `backend/tests/services/test_cloud_export_service.py` (append)

- [ ] **Step 1: Write schema validation tests**

Append to `backend/tests/services/test_cloud_export_service.py`:

```python
from app.schemas.cloud_export import CloudExportRequest, CloudExportJobResponse, CloudExportStatistics


class TestCloudExportSchemas:
    def test_export_request_defaults(self):
        req = CloudExportRequest(connection_id=1, source_path="docs/report.pdf")
        assert req.cloud_folder == "BaluHost Shares/"
        assert req.link_type == "view"
        assert req.expires_at is None

    def test_export_request_custom_values(self):
        req = CloudExportRequest(
            connection_id=1,
            source_path="docs/report.pdf",
            cloud_folder="My Exports/",
            link_type="edit",
        )
        assert req.cloud_folder == "My Exports/"
        assert req.link_type == "edit"

    def test_export_request_rejects_invalid_link_type(self):
        with pytest.raises(Exception):
            CloudExportRequest(
                connection_id=1,
                source_path="test.txt",
                link_type="delete",
            )

    def test_job_response_from_model(self, db_session: Session):
        conn = _create_connection(db_session)
        job = CloudExportJob(
            user_id=1,
            connection_id=conn.id,
            source_path="test.txt",
            is_directory=False,
            file_name="test.txt",
            cloud_folder="BaluHost Shares/",
            link_type="view",
            status="ready",
            progress_bytes=1024,
            share_link="https://drive.google.com/file/d/abc123/view",
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)

        resp = CloudExportJobResponse.model_validate(job, from_attributes=True)
        assert resp.id == job.id
        assert resp.status == "ready"
        assert resp.share_link == "https://drive.google.com/file/d/abc123/view"

    def test_statistics_schema(self):
        stats = CloudExportStatistics(
            total_exports=10,
            active_exports=5,
            failed_exports=2,
            total_upload_bytes=1_000_000,
        )
        assert stats.active_exports == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_cloud_export_service.py::TestCloudExportSchemas -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas.cloud_export'`

- [ ] **Step 3: Create the schemas**

Create `backend/app/schemas/cloud_export.py`:

```python
"""Pydantic schemas for cloud export API."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CloudExportRequest(BaseModel):
    """Request to start a cloud export job."""

    connection_id: int
    source_path: str = Field(min_length=1, description="Relative path on the NAS")
    cloud_folder: str = Field(
        default="BaluHost Shares/", description="Target folder in cloud drive"
    )
    link_type: Literal["view", "edit"] = Field(
        default="view", description="Sharing link permission type"
    )
    expires_at: Optional[datetime] = Field(
        default=None, description="Optional link expiration"
    )


class CloudExportJobResponse(BaseModel):
    """Response schema for an export job."""

    id: int
    user_id: int
    connection_id: int
    source_path: str
    file_name: str
    is_directory: bool
    file_size_bytes: Optional[int] = None
    cloud_folder: str
    cloud_path: Optional[str] = None
    share_link: Optional[str] = None
    link_type: str
    status: str
    progress_bytes: int
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CloudExportStatistics(BaseModel):
    """Statistics for the Cloud Shares tab on SharesPage."""

    total_exports: int
    active_exports: int
    failed_exports: int
    total_upload_bytes: int


class CheckScopeRequest(BaseModel):
    """Request to check if a connection has export-capable scope."""

    connection_id: int


class CheckScopeResponse(BaseModel):
    """Response indicating export scope availability."""

    has_export_scope: bool
    provider: str
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_cloud_export_service.py::TestCloudExportSchemas -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/cloud_export.py backend/tests/services/test_cloud_export_service.py
git commit -m "feat(cloud-export): add Pydantic schemas for export API"
```

---

## Task 3: RcloneAdapter Upload + Link Methods

**Files:**
- Modify: `backend/app/services/cloud/adapters/base.py`
- Modify: `backend/app/services/cloud/adapters/rclone.py`
- Modify: `backend/app/services/cloud/adapters/dev.py`
- Test: `backend/tests/services/test_cloud_export_service.py` (append)

- [ ] **Step 1: Write tests for DevCloudAdapter upload + link**

Append to `backend/tests/services/test_cloud_export_service.py`:

```python
import asyncio
from pathlib import Path
import tempfile

from app.services.cloud.adapters.dev import DevCloudAdapter


class TestDevCloudAdapterUpload:
    def test_upload_file(self, tmp_path: Path):
        adapter = DevCloudAdapter(provider="google_drive")
        local_file = tmp_path / "test.txt"
        local_file.write_text("hello world")

        progress_values = []
        asyncio.get_event_loop().run_until_complete(
            adapter.upload_file(local_file, "/BaluHost Shares/test.txt", lambda b: progress_values.append(b))
        )
        assert len(progress_values) > 0
        assert progress_values[-1] > 0

    def test_upload_folder(self, tmp_path: Path):
        adapter = DevCloudAdapter(provider="google_drive")
        folder = tmp_path / "docs"
        folder.mkdir()
        (folder / "a.txt").write_text("aaa")
        (folder / "b.txt").write_text("bbb")

        result = asyncio.get_event_loop().run_until_complete(
            adapter.upload_folder(folder, "/BaluHost Shares/docs")
        )
        assert result.files_transferred == 2
        assert result.bytes_transferred > 0
        assert len(result.errors) == 0

    def test_create_share_link(self):
        adapter = DevCloudAdapter(provider="google_drive")
        link = asyncio.get_event_loop().run_until_complete(
            adapter.create_share_link("/BaluHost Shares/test.txt", link_type="view")
        )
        assert link.startswith("https://")
        assert "mock" in link.lower() or "baluhost" in link.lower() or "example" in link.lower()

    def test_create_share_link_onedrive(self):
        adapter = DevCloudAdapter(provider="onedrive")
        link = asyncio.get_event_loop().run_until_complete(
            adapter.create_share_link("/BaluHost Shares/test.txt", link_type="edit")
        )
        assert link.startswith("https://")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_cloud_export_service.py::TestDevCloudAdapterUpload -v`
Expected: FAIL — `AttributeError: 'DevCloudAdapter' object has no attribute 'upload_file'`

- [ ] **Step 3: Add abstract methods to CloudAdapter base**

In `backend/app/services/cloud/adapters/base.py`, add after the existing `DownloadResult` dataclass:

```python
@dataclass
class UploadResult:
    """Result of a folder upload operation."""
    files_transferred: int = 0
    bytes_transferred: int = 0
    errors: list[str] = field(default_factory=list)
```

And add these methods to the `CloudAdapter` ABC (as default implementations that raise, so existing adapters don't break):

```python
    async def upload_file(
        self,
        local_path: Path,
        remote_path: str,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> None:
        """Upload a single file to the cloud."""
        raise NotImplementedError("Upload not supported by this adapter")

    async def upload_folder(
        self,
        local_path: Path,
        remote_path: str,
        progress_callback: Optional[Callable[[int, Optional[str]], None]] = None,
    ) -> "UploadResult":
        """Upload an entire folder recursively."""
        raise NotImplementedError("Upload not supported by this adapter")

    async def create_share_link(
        self, remote_path: str, link_type: str = "view"
    ) -> str:
        """Create a sharing link for a file/folder. Returns the URL."""
        raise NotImplementedError("Share links not supported by this adapter")
```

- [ ] **Step 4: Implement in DevCloudAdapter**

Append to `backend/app/services/cloud/adapters/dev.py` inside the `DevCloudAdapter` class (after `_calc_size`):

```python
    async def upload_file(
        self,
        local_path: Path,
        remote_path: str,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> None:
        """Simulate uploading a file."""
        size = local_path.stat().st_size if local_path.exists() else 1024
        uploaded = 0
        chunk = max(size // 5, 256)
        while uploaded < size:
            await asyncio.sleep(0.05)
            uploaded = min(uploaded + chunk, size)
            if progress_callback:
                progress_callback(uploaded)

    async def upload_folder(
        self,
        local_path: Path,
        remote_path: str,
        progress_callback: Optional[Callable[[int, Optional[str]], None]] = None,
    ) -> "UploadResult":
        """Simulate uploading a folder."""
        from app.services.cloud.adapters.base import UploadResult

        result = UploadResult()
        if not local_path.is_dir():
            result.errors.append(f"Not a directory: {local_path}")
            return result

        for f in local_path.rglob("*"):
            if f.is_file():
                if progress_callback:
                    progress_callback(result.bytes_transferred, f.name)
                await self.upload_file(f, f"{remote_path}/{f.relative_to(local_path)}")
                result.files_transferred += 1
                result.bytes_transferred += f.stat().st_size
        return result

    async def create_share_link(
        self, remote_path: str, link_type: str = "view"
    ) -> str:
        """Return a mock sharing link."""
        await asyncio.sleep(0.2)
        import hashlib
        file_hash = hashlib.md5(remote_path.encode()).hexdigest()[:12]
        if self.provider == "onedrive":
            return f"https://1drv.ms/example/{file_hash}?e={link_type}"
        return f"https://drive.google.com/file/d/mock-{file_hash}/view?usp=sharing"
```

Also add the import at the top of `dev.py` if not already present: `from app.services.cloud.adapters.base import UploadResult` (add to the existing import line).

- [ ] **Step 5: Implement in RcloneAdapter**

Append to `backend/app/services/cloud/adapters/rclone.py` inside the `RcloneAdapter` class (before `generate_config`):

```python
    async def upload_file(
        self,
        local_path: Path,
        remote_path: str,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> None:
        """Upload a single file using rclone copyto."""
        remote = f"{self.remote_name}:{remote_path.lstrip('/')}"

        if not progress_callback:
            await self._run_rclone("copyto", str(local_path), remote, timeout=3600)
            return

        config_path = self._get_config_path()
        cmd = [
            "rclone", "--config", config_path,
            "copyto", str(local_path), remote,
            "--stats", "1s", "--stats-one-line", "-v",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        if proc.stderr:
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                text = line.decode().strip()
                if "Transferred:" in text and "/" in text:
                    try:
                        parts = text.split("Transferred:")[1].strip()
                        transferred_part = parts.split("/")[0].strip()
                        bytes_done = self._parse_size(transferred_part)
                        if bytes_done is not None:
                            progress_callback(bytes_done)
                    except (IndexError, ValueError):
                        pass

        await proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"rclone copyto upload failed (exit {proc.returncode})")

        if local_path.exists():
            progress_callback(local_path.stat().st_size)

    async def upload_folder(
        self,
        local_path: Path,
        remote_path: str,
        progress_callback: Optional[Callable[[int, Optional[str]], None]] = None,
    ) -> "UploadResult":
        """Upload a folder using rclone copy."""
        from app.services.cloud.adapters.base import UploadResult

        remote = f"{self.remote_name}:{remote_path.lstrip('/')}"

        config_path = self._get_config_path()
        cmd = [
            "rclone", "--config", config_path,
            "copy", str(local_path), remote,
            "--stats", "2s", "--stats-one-line", "-v",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        result = UploadResult()
        _current_file: Optional[str] = None

        if proc.stderr:
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                text = line.decode().strip()

                if text.startswith("* ") and ":" in text:
                    fname = text[2:].split(":")[0].strip()
                    if fname:
                        _current_file = fname

                if "Transferred:" in text and "/" in text:
                    try:
                        parts = text.split("Transferred:")[1].strip()
                        transferred_part = parts.split("/")[0].strip()
                        bytes_done = self._parse_size(transferred_part)
                        if progress_callback and bytes_done is not None:
                            progress_callback(bytes_done, _current_file)
                    except (IndexError, ValueError):
                        pass

        await proc.wait()

        if proc.returncode != 0:
            stderr_text = ""
            if proc.stderr:
                remaining = await proc.stderr.read()
                stderr_text = remaining.decode().strip()
            result.errors.append(f"rclone exit code {proc.returncode}: {stderr_text}")

        for f in local_path.rglob("*"):
            if f.is_file():
                result.files_transferred += 1
                result.bytes_transferred += f.stat().st_size

        return result

    async def create_share_link(
        self, remote_path: str, link_type: str = "view"
    ) -> str:
        """Create a sharing link using rclone link."""
        remote = f"{self.remote_name}:{remote_path.lstrip('/')}"
        output = await self._run_rclone("link", remote, timeout=60)
        # rclone link outputs the URL on the last non-empty line
        lines = [l.strip() for l in output.strip().splitlines() if l.strip()]
        if not lines:
            raise RuntimeError("rclone link returned no output")
        return lines[-1]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_cloud_export_service.py::TestDevCloudAdapterUpload -v`
Expected: All 4 tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/cloud/adapters/base.py backend/app/services/cloud/adapters/rclone.py backend/app/services/cloud/adapters/dev.py backend/tests/services/test_cloud_export_service.py
git commit -m "feat(cloud-export): add upload and share-link methods to cloud adapters"
```

---

## Task 4: CloudExportService

**Files:**
- Create: `backend/app/services/cloud/export_service.py`
- Test: `backend/tests/services/test_cloud_export_service.py` (append)

- [ ] **Step 1: Write service tests**

Append to `backend/tests/services/test_cloud_export_service.py`:

```python
from unittest.mock import patch, AsyncMock, MagicMock

from app.services.cloud.export_service import CloudExportService


class TestCloudExportServiceStartExport:
    def test_start_export_creates_job(self, db_session: Session):
        conn = _create_connection(db_session)
        service = CloudExportService(db_session)

        job = service.start_export(
            connection_id=conn.id,
            user_id=1,
            source_path="Documents/report.pdf",
            cloud_folder="BaluHost Shares/",
            link_type="view",
            expires_at=None,
        )

        assert job.id is not None
        assert job.status == "pending"
        assert job.file_name == "report.pdf"
        assert job.is_directory is False
        assert job.cloud_folder == "BaluHost Shares/"

    def test_start_export_directory(self, db_session: Session):
        conn = _create_connection(db_session)
        service = CloudExportService(db_session)

        job = service.start_export(
            connection_id=conn.id,
            user_id=1,
            source_path="Photos/Vacation/",
            cloud_folder="BaluHost Shares/",
            link_type="view",
            expires_at=None,
        )

        assert job.file_name == "Vacation"
        assert job.is_directory is True

    def test_start_export_rejects_path_traversal(self, db_session: Session):
        conn = _create_connection(db_session)
        service = CloudExportService(db_session)

        with pytest.raises(ValueError, match="path traversal"):
            service.start_export(
                connection_id=conn.id,
                user_id=1,
                source_path="../etc/passwd",
                cloud_folder="BaluHost Shares/",
                link_type="view",
                expires_at=None,
            )

    def test_start_export_invalid_connection(self, db_session: Session):
        service = CloudExportService(db_session)

        with pytest.raises(ValueError, match="not found"):
            service.start_export(
                connection_id=999,
                user_id=1,
                source_path="test.txt",
                cloud_folder="BaluHost Shares/",
                link_type="view",
                expires_at=None,
            )


class TestCloudExportServiceQueries:
    def _create_job(self, db: Session, conn_id: int, user_id: int = 1, status: str = "ready") -> CloudExportJob:
        job = CloudExportJob(
            user_id=user_id,
            connection_id=conn_id,
            source_path="test.txt",
            is_directory=False,
            file_name="test.txt",
            cloud_folder="BaluHost Shares/",
            link_type="view",
            status=status,
            progress_bytes=1024,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def test_get_user_exports(self, db_session: Session):
        conn = _create_connection(db_session)
        self._create_job(db_session, conn.id)
        self._create_job(db_session, conn.id)

        service = CloudExportService(db_session)
        jobs = service.get_user_exports(user_id=1)
        assert len(jobs) == 2

    def test_get_user_exports_filters_by_user(self, db_session: Session):
        conn = _create_connection(db_session)
        self._create_job(db_session, conn.id, user_id=1)
        self._create_job(db_session, conn.id, user_id=2)

        service = CloudExportService(db_session)
        jobs = service.get_user_exports(user_id=1)
        assert len(jobs) == 1

    def test_get_export_status(self, db_session: Session):
        conn = _create_connection(db_session)
        job = self._create_job(db_session, conn.id)

        service = CloudExportService(db_session)
        result = service.get_export_status(job.id, user_id=1)
        assert result is not None
        assert result.id == job.id

    def test_get_export_status_wrong_user(self, db_session: Session):
        conn = _create_connection(db_session)
        job = self._create_job(db_session, conn.id, user_id=1)

        service = CloudExportService(db_session)
        result = service.get_export_status(job.id, user_id=999)
        assert result is None

    def test_get_export_statistics(self, db_session: Session):
        conn = _create_connection(db_session)
        self._create_job(db_session, conn.id, status="ready")
        self._create_job(db_session, conn.id, status="failed")
        self._create_job(db_session, conn.id, status="revoked")

        service = CloudExportService(db_session)
        stats = service.get_export_statistics(user_id=1)
        assert stats.total_exports == 3
        assert stats.active_exports == 1
        assert stats.failed_exports == 1

    def test_revoke_export(self, db_session: Session):
        conn = _create_connection(db_session)
        job = self._create_job(db_session, conn.id, status="ready")

        service = CloudExportService(db_session)
        with patch.object(service, '_delete_cloud_file', new_callable=AsyncMock):
            result = service.revoke_export(job.id, user_id=1)

        assert result is True
        db_session.refresh(job)
        assert job.status == "revoked"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_cloud_export_service.py::TestCloudExportServiceStartExport -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.cloud.export_service'`

- [ ] **Step 3: Create the service**

Create `backend/app/services/cloud/export_service.py`:

```python
"""Cloud export service — upload NAS files to cloud and create sharing links."""
import logging
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.cloud import CloudConnection
from app.models.cloud_export import CloudExportJob
from app.schemas.cloud_export import CloudExportStatistics
from app.services.cloud.service import CloudService

logger = logging.getLogger(__name__)


class CloudExportService:
    """Manages cloud export jobs — upload + share link creation."""

    def __init__(self, db: Session):
        self.db = db

    # ─── Start Export ─────────────────────────────────────────────

    def start_export(
        self,
        connection_id: int,
        user_id: int,
        source_path: str,
        cloud_folder: str,
        link_type: str,
        expires_at: Optional[datetime],
    ) -> CloudExportJob:
        """Create a new export job. Validates inputs."""
        # Reject path traversal
        if ".." in source_path:
            raise ValueError("Invalid source_path: path traversal not allowed")

        # Validate connection ownership
        cloud_service = CloudService(self.db)
        cloud_service.get_connection(connection_id, user_id)

        # Derive file name and detect directory
        clean_path = source_path.strip("/")
        parts = PurePosixPath(clean_path)
        file_name = parts.name or clean_path
        is_directory = clean_path.endswith("/") or not PurePosixPath(file_name).suffix

        # Try to get file size from filesystem
        file_size_bytes: Optional[int] = None
        try:
            storage_root = Path(settings.nas_storage_path).resolve()
            full_path = storage_root / clean_path
            if full_path.exists():
                if full_path.is_file():
                    file_size_bytes = full_path.stat().st_size
                    is_directory = False
                elif full_path.is_dir():
                    is_directory = True
                    file_size_bytes = sum(
                        f.stat().st_size for f in full_path.rglob("*") if f.is_file()
                    )
        except Exception:
            pass  # Size is optional, continue without it

        job = CloudExportJob(
            user_id=user_id,
            connection_id=connection_id,
            source_path=clean_path,
            is_directory=is_directory,
            file_name=file_name,
            file_size_bytes=file_size_bytes,
            cloud_folder=cloud_folder.strip("/") + "/" if cloud_folder else "BaluHost Shares/",
            link_type=link_type,
            status="pending",
            progress_bytes=0,
            expires_at=expires_at,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        logger.info(
            "Created cloud export job %d: %s -> %s (user %d)",
            job.id, source_path, cloud_folder, user_id,
        )
        return job

    # ─── Execute Export ───────────────────────────────────────────

    async def execute_export(self, job_id: int) -> None:
        """Background task: upload file/folder, then create share link."""
        job = self.db.query(CloudExportJob).get(job_id)
        if not job:
            logger.error("Export job %d not found", job_id)
            return

        connection = self.db.query(CloudConnection).get(job.connection_id)
        if not connection:
            job.status = "failed"
            job.error_message = "Cloud connection not found"
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            return

        cloud_service = CloudService(self.db)
        adapter = cloud_service.get_adapter_for_connection(connection)

        try:
            # Phase 1: Upload
            job.status = "uploading"
            self.db.commit()

            storage_root = Path(settings.nas_storage_path).resolve()
            local_path = storage_root / job.source_path

            if not local_path.exists():
                raise FileNotFoundError(f"Source path does not exist: {job.source_path}")

            cloud_dest = f"{job.cloud_folder}{job.file_name}"

            def progress_callback(bytes_done: int, *_args) -> None:
                job.progress_bytes = bytes_done
                self.db.commit()

            if job.is_directory:
                result = await adapter.upload_folder(
                    local_path, cloud_dest, progress_callback=progress_callback
                )
                job.progress_bytes = result.bytes_transferred
                if result.errors:
                    job.error_message = "; ".join(result.errors[:5])
            else:
                await adapter.upload_file(
                    local_path, cloud_dest, progress_callback=lambda b: progress_callback(b)
                )
                if local_path.exists():
                    job.progress_bytes = local_path.stat().st_size

            job.cloud_path = cloud_dest
            self.db.commit()

            # Phase 2: Create share link
            job.status = "creating_link"
            self.db.commit()

            share_link = await adapter.create_share_link(cloud_dest, job.link_type)
            job.share_link = share_link
            job.status = "ready"
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()

            # Update connection last_used_at
            connection.last_used_at = datetime.now(timezone.utc)
            self.db.commit()

            logger.info(
                "Export job %d completed: %s -> %s",
                job_id, job.source_path, share_link,
            )

        except Exception as e:
            logger.exception("Export job %d failed", job_id)
            job.status = "failed"
            job.error_message = str(e)[:500]
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()

        finally:
            await adapter.close()

    # ─── Revoke ───────────────────────────────────────────────────

    def revoke_export(self, job_id: int, user_id: int) -> bool:
        """Revoke an export — sets status to revoked. Cloud deletion is best-effort."""
        job = self.get_export_status(job_id, user_id)
        if not job or job.status not in ("ready", "creating_link"):
            return False

        job.status = "revoked"
        job.completed_at = datetime.now(timezone.utc)
        self.db.commit()

        # Best-effort cloud deletion in background
        # (actual rclone delete would be async — handled by caller if needed)
        logger.info("Revoked export job %d", job_id)
        return True

    async def _delete_cloud_file(self, job: CloudExportJob) -> None:
        """Best-effort deletion of uploaded cloud file."""
        if not job.cloud_path:
            return
        try:
            connection = self.db.query(CloudConnection).get(job.connection_id)
            if not connection:
                return
            cloud_service = CloudService(self.db)
            adapter = cloud_service.get_adapter_for_connection(connection)
            try:
                remote = f"{adapter.remote_name}:{job.cloud_path.lstrip('/')}"
                await adapter._run_rclone("delete", remote, timeout=60)
            finally:
                await adapter.close()
        except Exception:
            logger.warning("Failed to delete cloud file for job %d", job.id)

    # ─── Retry ────────────────────────────────────────────────────

    def retry_export(self, job_id: int, user_id: int) -> Optional[CloudExportJob]:
        """Retry a failed export by resetting it to pending."""
        job = self.get_export_status(job_id, user_id)
        if not job or job.status != "failed":
            return None

        job.status = "pending"
        job.progress_bytes = 0
        job.error_message = None
        job.share_link = None
        job.cloud_path = None
        job.completed_at = None
        self.db.commit()
        self.db.refresh(job)
        return job

    # ─── Queries ──────────────────────────────────────────────────

    def get_user_exports(self, user_id: int, limit: int = 50) -> list[CloudExportJob]:
        """Get all export jobs for a user, newest first."""
        return (
            self.db.query(CloudExportJob)
            .filter(CloudExportJob.user_id == user_id)
            .order_by(CloudExportJob.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_export_status(self, job_id: int, user_id: int) -> Optional[CloudExportJob]:
        """Get a single job, ensuring ownership."""
        return (
            self.db.query(CloudExportJob)
            .filter(
                CloudExportJob.id == job_id,
                CloudExportJob.user_id == user_id,
            )
            .first()
        )

    def get_export_statistics(self, user_id: int) -> CloudExportStatistics:
        """Get export statistics for the SharesPage."""
        now = datetime.now(timezone.utc)

        total = self.db.query(func.count(CloudExportJob.id)).filter(
            CloudExportJob.user_id == user_id
        ).scalar() or 0

        active = self.db.query(func.count(CloudExportJob.id)).filter(
            CloudExportJob.user_id == user_id,
            CloudExportJob.status == "ready",
            or_(
                CloudExportJob.expires_at.is_(None),
                CloudExportJob.expires_at > now,
            ),
        ).scalar() or 0

        failed = self.db.query(func.count(CloudExportJob.id)).filter(
            CloudExportJob.user_id == user_id,
            CloudExportJob.status == "failed",
        ).scalar() or 0

        total_bytes = self.db.query(func.coalesce(func.sum(CloudExportJob.progress_bytes), 0)).filter(
            CloudExportJob.user_id == user_id,
            CloudExportJob.status == "ready",
        ).scalar() or 0

        return CloudExportStatistics(
            total_exports=total,
            active_exports=active,
            failed_exports=failed,
            total_upload_bytes=total_bytes,
        )
```

- [ ] **Step 4: Run all service tests**

Run: `cd backend && python -m pytest tests/services/test_cloud_export_service.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/cloud/export_service.py backend/tests/services/test_cloud_export_service.py
git commit -m "feat(cloud-export): add CloudExportService with start, execute, revoke, retry, stats"
```

---

## Task 5: OAuth Scope Upgrade in CloudService

**Files:**
- Modify: `backend/app/services/cloud/service.py`
- Test: `backend/tests/services/test_cloud_export_service.py` (append)

- [ ] **Step 1: Write scope-check tests**

Append to `backend/tests/services/test_cloud_export_service.py`:

```python
from app.services.cloud.service import CloudService


class TestCloudServiceScopeCheck:
    def test_check_scope_readonly_google(self, db_session: Session):
        conn = CloudConnection(
            user_id=1,
            provider="google_drive",
            display_name="GDrive",
            encrypted_config="fake",
            rclone_remote_name="gdrive_test",
            is_active=True,
        )
        db_session.add(conn)
        db_session.commit()
        db_session.refresh(conn)

        service = CloudService(db_session)
        result = service.check_connection_scope(conn.id, 1)
        assert result["provider"] == "google_drive"
        # With fake config, default assumption is no export scope
        assert result["has_export_scope"] is False

    def test_check_scope_invalid_connection(self, db_session: Session):
        service = CloudService(db_session)
        with pytest.raises(ValueError):
            service.check_connection_scope(999, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_cloud_export_service.py::TestCloudServiceScopeCheck -v`
Expected: FAIL — `AttributeError: 'CloudService' object has no attribute 'check_connection_scope'`

- [ ] **Step 3: Add check_connection_scope and extend get_oauth_url**

In `backend/app/services/cloud/service.py`, add these methods to the `CloudService` class:

```python
    # ─── Scope Check & Upgrade ───────────────────────────────────

    EXPORT_SCOPES = {
        "google_drive": "https://www.googleapis.com/auth/drive.file",
        "onedrive": "Files.ReadWrite offline_access",
    }

    READONLY_SCOPES = {
        "google_drive": "drive.readonly",
        "onedrive": "Files.Read",
    }

    def check_connection_scope(self, connection_id: int, user_id: int) -> dict:
        """Check if a connection has export-capable (ReadWrite) scope."""
        conn = self.get_connection(connection_id, user_id)

        has_export_scope = False
        if conn.provider in ("google_drive", "onedrive") and conn.encrypted_config:
            try:
                config = decrypt_credentials(conn.encrypted_config)
                if conn.provider == "google_drive":
                    has_export_scope = "drive.file" in config or "drive " in config.lower() and "readonly" not in config.lower()
                elif conn.provider == "onedrive":
                    has_export_scope = "ReadWrite" in config or "readwrite" in config.lower()
            except Exception:
                pass

        return {"has_export_scope": has_export_scope, "provider": conn.provider}

    def get_export_oauth_url(self, provider: str, user_id: int, connection_id: int) -> str:
        """Generate OAuth URL with export scopes, including upgrade_connection_id in state."""
        if provider not in ("google_drive", "onedrive"):
            raise ValueError(f"Export not supported for provider: {provider}")

        from app.services.cloud.oauth_config import CloudOAuthConfigService
        creds = CloudOAuthConfigService(self.db).get_credentials(provider, user_id)
        if not creds:
            raise ValueError(f"OAuth not configured for {provider}")
        client_id, _client_secret = creds

        state = json.dumps({
            "provider": provider,
            "user_id": user_id,
            "upgrade_connection_id": connection_id,
        })

        if provider == "google_drive":
            params = {
                "client_id": client_id,
                "redirect_uri": self._get_redirect_uri(),
                "response_type": "code",
                "scope": self.EXPORT_SCOPES["google_drive"],
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
            }
            return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

        elif provider == "onedrive":
            params = {
                "client_id": client_id,
                "redirect_uri": self._get_redirect_uri(),
                "response_type": "code",
                "scope": self.EXPORT_SCOPES["onedrive"],
                "state": state,
            }
            return f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{urlencode(params)}"

        raise ValueError(f"Unknown provider: {provider}")
```

Then modify `handle_oauth_callback` to handle upgrades. After `token_json = json.dumps(token_data)` (line ~137), add logic to check for `upgrade_connection_id` in `state_data`:

At the point where the connection is created (around line 140-161 of `service.py`), wrap it in:

```python
        # Check if this is a scope upgrade for an existing connection
        upgrade_connection_id = None
        # (The caller passes state_data — add upgrade_connection_id check)
```

Actually, the cleaner approach: modify `handle_oauth_callback` to accept `state_data` and check for upgrade. The state parsing happens in the route, so extend `handle_oauth_callback` signature to accept an optional `upgrade_connection_id`:

In `handle_oauth_callback`, after `token_json = json.dumps(token_data)` and before creating a new `CloudConnection`, add:

```python
        # Handle scope upgrade — update existing connection instead of creating new
        if upgrade_connection_id is not None:
            existing = self.get_connection(upgrade_connection_id, user_id)
            from app.services.cloud.adapters.rclone import RcloneAdapter
            _remote_name, config_content = RcloneAdapter.generate_config(provider, token_json)
            existing.encrypted_config = encrypt_credentials(config_content)
            existing.rclone_remote_name = _remote_name
            self.db.commit()
            self.db.refresh(existing)
            logger.info("Upgraded scope for connection %d (user %d)", upgrade_connection_id, user_id)
            return existing
```

Add `upgrade_connection_id: int | None = None` to the `handle_oauth_callback` method signature.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_cloud_export_service.py::TestCloudServiceScopeCheck -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/cloud/service.py backend/tests/services/test_cloud_export_service.py
git commit -m "feat(cloud-export): add scope check and OAuth upgrade support to CloudService"
```

---

## Task 6: API Routes

**Files:**
- Create: `backend/app/api/routes/cloud_export.py`
- Modify: `backend/app/api/routes/__init__.py`
- Modify: `backend/app/api/routes/cloud.py` (OAuth callback upgrade handling)
- Create: `backend/tests/api/test_cloud_export_routes.py`

- [ ] **Step 1: Write route tests**

Create `backend/tests/api/test_cloud_export_routes.py`:

```python
"""Tests for cloud export API routes."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.cloud import CloudConnection
from app.models.cloud_export import CloudExportJob


def _create_connection(db: Session, user_id: int = 1) -> CloudConnection:
    conn = CloudConnection(
        user_id=user_id,
        provider="google_drive",
        display_name="Test Drive",
        encrypted_config="encrypted-data",
        is_active=True,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


def _create_export_job(
    db: Session, conn_id: int, user_id: int = 1, status: str = "ready"
) -> CloudExportJob:
    job = CloudExportJob(
        user_id=user_id,
        connection_id=conn_id,
        source_path="test.txt",
        is_directory=False,
        file_name="test.txt",
        cloud_folder="BaluHost Shares/",
        link_type="view",
        status=status,
        progress_bytes=1024,
        share_link="https://drive.google.com/mock" if status == "ready" else None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


class TestCloudExportRoutes:
    def test_list_exports_empty(self, client: TestClient, admin_token: str):
        resp = client.get(
            "/api/cloud-export/jobs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_exports_with_jobs(
        self, client: TestClient, admin_token: str, db_session: Session
    ):
        conn = _create_connection(db_session, user_id=1)
        _create_export_job(db_session, conn.id, user_id=1)

        resp = client.get(
            "/api/cloud-export/jobs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["file_name"] == "test.txt"

    def test_get_export_status(
        self, client: TestClient, admin_token: str, db_session: Session
    ):
        conn = _create_connection(db_session, user_id=1)
        job = _create_export_job(db_session, conn.id)

        resp = client.get(
            f"/api/cloud-export/jobs/{job.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

    def test_get_export_status_not_found(self, client: TestClient, admin_token: str):
        resp = client.get(
            "/api/cloud-export/jobs/999",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    def test_get_statistics(self, client: TestClient, admin_token: str, db_session: Session):
        conn = _create_connection(db_session, user_id=1)
        _create_export_job(db_session, conn.id, status="ready")
        _create_export_job(db_session, conn.id, status="failed")

        resp = client.get(
            "/api/cloud-export/statistics",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["total_exports"] == 2
        assert stats["active_exports"] == 1
        assert stats["failed_exports"] == 1

    def test_revoke_export(self, client: TestClient, admin_token: str, db_session: Session):
        conn = _create_connection(db_session, user_id=1)
        job = _create_export_job(db_session, conn.id, status="ready")

        resp = client.post(
            f"/api/cloud-export/jobs/{job.id}/revoke",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_retry_export(self, client: TestClient, admin_token: str, db_session: Session):
        conn = _create_connection(db_session, user_id=1)
        job = _create_export_job(db_session, conn.id, status="failed")

        resp = client.post(
            f"/api/cloud-export/jobs/{job.id}/retry",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_unauthenticated_returns_401(self, client: TestClient):
        resp = client.get("/api/cloud-export/jobs")
        assert resp.status_code in (401, 403)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/api/test_cloud_export_routes.py -v`
Expected: FAIL — routes don't exist yet

- [ ] **Step 3: Create the routes**

Create `backend/app/api/routes/cloud_export.py`:

```python
"""Cloud export API endpoints."""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.models.user import User
from app.schemas.cloud_export import (
    CheckScopeRequest,
    CheckScopeResponse,
    CloudExportJobResponse,
    CloudExportRequest,
    CloudExportStatistics,
)
from app.schemas.user import UserPublic
from app.services.audit.logger_db import AuditLoggerDB
from app.services.cloud.export_service import CloudExportService
from app.services.cloud.service import CloudService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=CloudExportJobResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def start_export(
    request: Request,
    response: Response,
    body: CloudExportRequest,
    background_tasks: BackgroundTasks,
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start a cloud export job (upload + share link)."""
    service = CloudExportService(db)
    try:
        job = service.start_export(
            connection_id=body.connection_id,
            user_id=current_user.id,
            source_path=body.source_path,
            cloud_folder=body.cloud_folder,
            link_type=body.link_type,
            expires_at=body.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Execute in background
    background_tasks.add_task(_run_export_async, job.id, db)

    audit = AuditLoggerDB()
    audit.log_event(
        event_type="FILE_OPERATION",
        action="cloud_export_started",
        user=current_user.username,
        resource=body.source_path,
        db=db,
    )

    return CloudExportJobResponse.model_validate(job)


@router.get("/jobs", response_model=list[CloudExportJobResponse])
@user_limiter.limit(get_limit("admin_operations"))
async def list_exports(
    request: Request,
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all export jobs for the current user."""
    service = CloudExportService(db)
    jobs = service.get_user_exports(current_user.id, limit=limit)
    return [CloudExportJobResponse.model_validate(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=CloudExportJobResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_export_status(
    request: Request,
    response: Response,
    job_id: int,
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get status of a specific export job."""
    service = CloudExportService(db)
    job = service.get_export_status(job_id, current_user.id)
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")
    return CloudExportJobResponse.model_validate(job)


@router.post("/jobs/{job_id}/revoke")
@user_limiter.limit(get_limit("admin_operations"))
async def revoke_export(
    request: Request,
    response: Response,
    job_id: int,
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revoke a cloud export (delete cloud file + invalidate link)."""
    service = CloudExportService(db)
    success = service.revoke_export(job_id, current_user.id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot revoke this export")

    audit = AuditLoggerDB()
    audit.log_event(
        event_type="FILE_OPERATION",
        action="cloud_export_revoked",
        user=current_user.username,
        resource=f"job:{job_id}",
        db=db,
    )

    return {"success": True, "message": "Export revoked"}


@router.post("/jobs/{job_id}/retry", response_model=CloudExportJobResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def retry_export(
    request: Request,
    response: Response,
    job_id: int,
    background_tasks: BackgroundTasks,
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retry a failed export job."""
    service = CloudExportService(db)
    job = service.retry_export(job_id, current_user.id)
    if not job:
        raise HTTPException(status_code=400, detail="Cannot retry this export (not failed)")

    background_tasks.add_task(_run_export_async, job.id, db)
    return CloudExportJobResponse.model_validate(job)


@router.get("/statistics", response_model=CloudExportStatistics)
@user_limiter.limit(get_limit("admin_operations"))
async def get_statistics(
    request: Request,
    response: Response,
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get cloud export statistics for the Shares page."""
    service = CloudExportService(db)
    return service.get_export_statistics(current_user.id)


@router.post("/check-scope", response_model=CheckScopeResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def check_scope(
    request: Request,
    response: Response,
    body: CheckScopeRequest,
    current_user: UserPublic = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check if a cloud connection has export-capable scope."""
    service = CloudService(db)
    try:
        result = service.check_connection_scope(body.connection_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return CheckScopeResponse(**result)


# ─── Background task helper ──────────────────────────────────

async def _run_export_async(job_id: int, db: Session) -> None:
    """Execute export job in background."""
    try:
        service = CloudExportService(db)
        await service.execute_export(job_id)
    except Exception as e:
        logger.exception("Background export failed for job %d: %s", job_id, e)
```

- [ ] **Step 4: Register the router**

In `backend/app/api/routes/__init__.py`:

Add `cloud_export` to the import line (after `cloud`):

```python
    cloud, cloud_export, sleep,
```

Add the router registration (after the `cloud` line):

```python
api_router.include_router(cloud_export.router, prefix="/cloud-export", tags=["cloud-export"])
```

- [ ] **Step 5: Update OAuth callback for scope upgrade**

In `backend/app/api/routes/cloud.py`, modify the `oauth_callback_redirect` function to pass `upgrade_connection_id` from state to `handle_oauth_callback`:

After `user_id = state_data["user_id"]` (around line 203), add:

```python
        upgrade_connection_id = state_data.get("upgrade_connection_id")
```

And change the `service.handle_oauth_callback` call to:

```python
        service.handle_oauth_callback(provider, code, user_id, upgrade_connection_id=upgrade_connection_id)
```

Do the same in the POST `oauth_callback` endpoint (around line 224-231).

- [ ] **Step 6: Run route tests**

Run: `cd backend && python -m pytest tests/api/test_cloud_export_routes.py -v`
Expected: All tests PASS

- [ ] **Step 7: Run full test suite to check for regressions**

Run: `cd backend && python -m pytest --timeout=60 -x -q`
Expected: No failures

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/routes/cloud_export.py backend/app/api/routes/__init__.py backend/app/api/routes/cloud.py backend/tests/api/test_cloud_export_routes.py
git commit -m "feat(cloud-export): add API routes and register cloud-export router"
```

---

## Task 7: Frontend API Client

**Files:**
- Create: `client/src/api/cloud-export.ts`

- [ ] **Step 1: Create the API client**

Create `client/src/api/cloud-export.ts`:

```typescript
import { apiClient } from '../lib/api';

// ─── Types ──────────────────────────────────────────────────

export interface CloudExportRequest {
  connection_id: number;
  source_path: string;
  cloud_folder?: string;
  link_type?: 'view' | 'edit';
  expires_at?: string | null;
}

export interface CloudExportJob {
  id: number;
  user_id: number;
  connection_id: number;
  source_path: string;
  file_name: string;
  is_directory: boolean;
  file_size_bytes: number | null;
  cloud_folder: string;
  cloud_path: string | null;
  share_link: string | null;
  link_type: string;
  status: 'pending' | 'uploading' | 'creating_link' | 'ready' | 'failed' | 'revoked';
  progress_bytes: number;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
  expires_at: string | null;
}

export interface CloudExportStatistics {
  total_exports: number;
  active_exports: number;
  failed_exports: number;
  total_upload_bytes: number;
}

export interface CheckScopeResponse {
  has_export_scope: boolean;
  provider: string;
}

// ─── API Functions ──────────────────────────────────────────

export async function startCloudExport(data: CloudExportRequest): Promise<CloudExportJob> {
  const resp = await apiClient.post('/api/cloud-export/', data);
  return resp.data;
}

export async function listCloudExports(limit = 50): Promise<CloudExportJob[]> {
  const resp = await apiClient.get('/api/cloud-export/jobs', { params: { limit } });
  return resp.data;
}

export async function getCloudExportStatus(jobId: number): Promise<CloudExportJob> {
  const resp = await apiClient.get(`/api/cloud-export/jobs/${jobId}`);
  return resp.data;
}

export async function revokeCloudExport(jobId: number): Promise<void> {
  await apiClient.post(`/api/cloud-export/jobs/${jobId}/revoke`);
}

export async function retryCloudExport(jobId: number): Promise<CloudExportJob> {
  const resp = await apiClient.post(`/api/cloud-export/jobs/${jobId}/retry`);
  return resp.data;
}

export async function getCloudExportStatistics(): Promise<CloudExportStatistics> {
  const resp = await apiClient.get('/api/cloud-export/statistics');
  return resp.data;
}

export async function checkConnectionScope(connectionId: number): Promise<CheckScopeResponse> {
  const resp = await apiClient.post('/api/cloud-export/check-scope', {
    connection_id: connectionId,
  });
  return resp.data;
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/api/cloud-export.ts
git commit -m "feat(cloud-export): add frontend API client"
```

---

## Task 8: i18n Keys

**Files:**
- Modify: `client/src/i18n/locales/en/shares.json`
- Modify: `client/src/i18n/locales/de/shares.json`

- [ ] **Step 1: Add English i18n keys**

Add a `"cloudExport"` section to `client/src/i18n/locales/en/shares.json`:

```json
"cloudExport": {
  "tab": "Cloud Shares",
  "tabShort": "Cloud",
  "provider": "Provider",
  "targetFolder": "Target Folder",
  "targetFolderHint": "Folder in your cloud drive",
  "linkType": "Link Type",
  "linkTypeView": "View only",
  "linkTypeEdit": "Can edit",
  "noConnections": "No cloud accounts connected",
  "connectHint": "Connect a Google Drive or OneDrive account in Cloud Import first.",
  "goToCloudImport": "Go to Cloud Import",
  "upgradeScope": "Grant write access",
  "upgradeScopeHint": "Your cloud connection needs write permission for exports.",
  "startExport": "Share via Cloud",
  "exporting": "Starting export...",
  "exportStarted": "Cloud export started — upload is running in the background",
  "status": {
    "pending": "Pending",
    "uploading": "Uploading",
    "creating_link": "Creating link",
    "ready": "Ready",
    "failed": "Failed",
    "revoked": "Revoked"
  },
  "copyLink": "Copy link",
  "linkCopied": "Link copied to clipboard",
  "revoke": "Revoke",
  "revokeConfirm": "This will delete the file from your cloud drive and invalidate the sharing link. This cannot be undone.",
  "revoked": "Export revoked",
  "revokeFailed": "Failed to revoke export",
  "retry": "Retry",
  "retryStarted": "Retrying export...",
  "retryFailed": "Failed to retry export",
  "cancel": "Cancel",
  "stats": {
    "activeExports": "Active Cloud Shares",
    "uploadVolume": "Upload Volume"
  },
  "empty": {
    "noExports": "No cloud exports yet",
    "noExportsDesc": "Share files externally by using the Cloud Export tab in the Share dialog."
  }
}
```

Also add to the `"tabs"` section:

```json
"cloudExports": "Cloud Shares",
"cloudExportsShort": "Cloud"
```

- [ ] **Step 2: Add German i18n keys**

Add the corresponding `"cloudExport"` section to `client/src/i18n/locales/de/shares.json` with German translations:

```json
"cloudExport": {
  "tab": "Cloud-Freigaben",
  "tabShort": "Cloud",
  "provider": "Anbieter",
  "targetFolder": "Zielordner",
  "targetFolderHint": "Ordner in deinem Cloud-Laufwerk",
  "linkType": "Link-Typ",
  "linkTypeView": "Nur ansehen",
  "linkTypeEdit": "Bearbeiten erlaubt",
  "noConnections": "Kein Cloud-Konto verbunden",
  "connectHint": "Verbinde zuerst ein Google Drive oder OneDrive Konto unter Cloud-Import.",
  "goToCloudImport": "Zum Cloud-Import",
  "upgradeScope": "Schreibzugriff gewähren",
  "upgradeScopeHint": "Deine Cloud-Verbindung benötigt Schreibberechtigung für Exports.",
  "startExport": "Per Cloud teilen",
  "exporting": "Export wird gestartet...",
  "exportStarted": "Cloud-Export gestartet — Upload läuft im Hintergrund",
  "status": {
    "pending": "Wartend",
    "uploading": "Wird hochgeladen",
    "creating_link": "Link wird erstellt",
    "ready": "Bereit",
    "failed": "Fehlgeschlagen",
    "revoked": "Widerrufen"
  },
  "copyLink": "Link kopieren",
  "linkCopied": "Link in Zwischenablage kopiert",
  "revoke": "Widerrufen",
  "revokeConfirm": "Dies löscht die Datei aus deinem Cloud-Laufwerk und macht den Freigabelink ungültig. Dies kann nicht rückgängig gemacht werden.",
  "revoked": "Export widerrufen",
  "revokeFailed": "Export konnte nicht widerrufen werden",
  "retry": "Wiederholen",
  "retryStarted": "Export wird wiederholt...",
  "retryFailed": "Export konnte nicht wiederholt werden",
  "cancel": "Abbrechen",
  "stats": {
    "activeExports": "Aktive Cloud-Freigaben",
    "uploadVolume": "Upload-Volumen"
  },
  "empty": {
    "noExports": "Noch keine Cloud-Exports",
    "noExportsDesc": "Teile Dateien extern über den Cloud-Export-Tab im Teilen-Dialog."
  }
}
```

Also add to `"tabs"`:

```json
"cloudExports": "Cloud-Freigaben",
"cloudExportsShort": "Cloud"
```

- [ ] **Step 3: Commit**

```bash
git add client/src/i18n/locales/en/shares.json client/src/i18n/locales/de/shares.json
git commit -m "feat(cloud-export): add i18n keys for cloud export (en + de)"
```

---

## Task 9: ShareFileModal (Unified Share Modal)

**Files:**
- Create: `client/src/components/ShareFileModal.tsx`
- Modify: `client/src/pages/FileManager.tsx`

- [ ] **Step 1: Create the unified ShareFileModal**

Create `client/src/components/ShareFileModal.tsx`. This component has two tabs — "Intern" reuses the logic from `CreateFileShareModal` (user select, permissions, expiry), "Cloud Export" shows provider dropdown, target folder, link type, expiry.

The component receives `fileId`, `fileName`, `users` (for internal tab), `onClose`, `onSuccess` as props.

Key implementation points:
- Tab state: `'internal' | 'cloud'`
- Internal tab: same form as `CreateFileShareModal` (copy the form body, not the file explorer — `fileId` is always provided)
- Cloud tab: fetches connections via `GET /api/cloud/connections`, shows provider dropdown, target folder input with "BaluHost Shares/" default, link type radio, optional expiry date, scope-check on connection selection
- Submit internal: calls `createFileShare()` from existing `api/shares.ts`
- Submit cloud: calls `startCloudExport()` from new `api/cloud-export.ts`

The full implementation should follow the existing modal patterns (backdrop, slate-900 card, X close button, form sections, Tailwind classes matching `CreateFileShareModal` and `EditFileShareModal`).

- [ ] **Step 2: Update FileManager to use ShareFileModal**

In `client/src/pages/FileManager.tsx`:

Replace the import:
```typescript
// Before:
import CreateFileShareModal from '../components/CreateFileShareModal';
// After:
import ShareFileModal from '../components/ShareFileModal';
```

Replace the modal rendering (around line 887-898):
```typescript
{/* Share File Modal */}
{sharingFile && sharingFile.file_id && (
  <ShareFileModal
    fileId={sharingFile.file_id}
    fileName={sharingFile.name}
    users={allUsers}
    onClose={() => setSharingFile(null)}
    onSuccess={() => {
      setSharingFile(null);
      toast.success(t('fileManager:messages.shared', 'Shared successfully'));
    }}
  />
)}
```

- [ ] **Step 3: Test manually in dev mode**

Run: `python start_dev.py`
- Navigate to File Manager
- Right-click a file → Share
- Verify the modal shows two tabs: "Intern" and "Cloud Export"
- Internal tab should work exactly as before
- Cloud tab should show "No cloud accounts connected" hint (or provider list if dev connections exist)

- [ ] **Step 4: Commit**

```bash
git add client/src/components/ShareFileModal.tsx client/src/pages/FileManager.tsx
git commit -m "feat(cloud-export): add unified ShareFileModal with internal + cloud tabs"
```

---

## Task 10: SharesPage — Cloud Shares Tab

**Files:**
- Modify: `client/src/pages/SharesPage.tsx`

- [ ] **Step 1: Add the Cloud Shares tab**

In `client/src/pages/SharesPage.tsx`:

Add imports:
```typescript
import { Cloud, Copy, RefreshCw } from 'lucide-react';
import {
  listCloudExports,
  getCloudExportStatistics,
  revokeCloudExport,
  retryCloudExport,
  type CloudExportJob,
  type CloudExportStatistics as CloudExportStats,
} from '../api/cloud-export';
import { formatBytes } from '../lib/formatters';
```

Extend the tab type and state:
```typescript
const [activeTab, setActiveTab] = useState<'shares' | 'shared-with-me' | 'cloud-exports'>('shares');
const [cloudExports, setCloudExports] = useState<CloudExportJob[]>([]);
const [cloudStats, setCloudStats] = useState<CloudExportStats | null>(null);
```

Add `cloud-exports` to the `tabs` array:
```typescript
{ key: 'cloud-exports' as const, label: t('tabs.cloudExports'), shortLabel: t('tabs.cloudExportsShort'), icon: Cloud },
```

Load cloud export data in `loadData`:
```typescript
const [stats, shares, shared, cExports, cStats] = await Promise.all([
  getShareStatistics(),
  listFileShares(),
  listFilesSharedWithMe(),
  listCloudExports().catch(() => []),
  getCloudExportStatistics().catch(() => null),
]);
// ... existing sets ...
setCloudExports(cExports);
setCloudStats(cStats);
```

Add the cloud-exports tab content after the shared-with-me tab content. It includes:
- StatCards for Active Cloud Shares and Upload Volume (shown when `cloudStats` is available)
- Desktop table with columns: Provider, File, Link (copy button), Status, Created, Expires, Actions
- Mobile card view
- Empty state
- Revoke handler with confirm dialog
- Retry handler
- Copy-to-clipboard for share links

The status column should show a colored badge:
- `ready` → green
- `uploading` / `creating_link` → blue with spinner
- `pending` → slate
- `failed` → red
- `revoked` → slate/muted

For `uploading` status, if `file_size_bytes` is available, show a progress percentage: `Math.round((job.progress_bytes / job.file_size_bytes) * 100)%`

- [ ] **Step 2: Test manually in dev mode**

Run: `python start_dev.py`
- Navigate to Shares page
- Verify three tabs visible: "My Shares", "Shared with Me", "Cloud Shares"
- Cloud Shares tab shows empty state
- Stats cards show zeros

- [ ] **Step 3: Commit**

```bash
git add client/src/pages/SharesPage.tsx
git commit -m "feat(cloud-export): add Cloud Shares tab to SharesPage with stats and job list"
```

---

## Task 11: Integration Test — Full Export Flow (Dev Mode)

**Files:**
- Test: `backend/tests/services/test_cloud_export_service.py` (append)

- [ ] **Step 1: Write end-to-end export flow test**

Append to `backend/tests/services/test_cloud_export_service.py`:

```python
class TestCloudExportExecuteFlow:
    """Integration test for the full export flow using DevCloudAdapter."""

    @pytest.mark.asyncio
    async def test_execute_export_file(self, db_session: Session, tmp_path: Path):
        """Test full export: upload file + create link in dev mode."""
        # Setup: create connection and a local file
        conn = _create_connection(db_session)

        from app.core.config import settings
        original_storage = settings.nas_storage_path

        try:
            settings.nas_storage_path = str(tmp_path)
            test_file = tmp_path / "report.pdf"
            test_file.write_bytes(b"x" * 5000)

            service = CloudExportService(db_session)
            job = service.start_export(
                connection_id=conn.id,
                user_id=1,
                source_path="report.pdf",
                cloud_folder="BaluHost Shares/",
                link_type="view",
                expires_at=None,
            )

            assert job.status == "pending"

            # Execute (uses DevCloudAdapter in dev mode)
            await service.execute_export(job.id)

            db_session.refresh(job)
            assert job.status == "ready"
            assert job.share_link is not None
            assert job.share_link.startswith("https://")
            assert job.cloud_path == "BaluHost Shares/report.pdf"
            assert job.completed_at is not None

        finally:
            settings.nas_storage_path = original_storage

    @pytest.mark.asyncio
    async def test_execute_export_missing_file(self, db_session: Session, tmp_path: Path):
        """Test export fails gracefully when source file doesn't exist."""
        conn = _create_connection(db_session)

        from app.core.config import settings
        original_storage = settings.nas_storage_path

        try:
            settings.nas_storage_path = str(tmp_path)
            # Don't create the file

            service = CloudExportService(db_session)
            job = service.start_export(
                connection_id=conn.id,
                user_id=1,
                source_path="nonexistent.txt",
                cloud_folder="BaluHost Shares/",
                link_type="view",
                expires_at=None,
            )

            await service.execute_export(job.id)

            db_session.refresh(job)
            assert job.status == "failed"
            assert "does not exist" in (job.error_message or "")

        finally:
            settings.nas_storage_path = original_storage
```

- [ ] **Step 2: Run the integration tests**

Run: `cd backend && python -m pytest tests/services/test_cloud_export_service.py::TestCloudExportExecuteFlow -v`
Expected: All 2 tests PASS

- [ ] **Step 3: Run entire test suite**

Run: `cd backend && python -m pytest --timeout=60 -x -q`
Expected: No failures

- [ ] **Step 4: Commit**

```bash
git add backend/tests/services/test_cloud_export_service.py
git commit -m "test(cloud-export): add integration tests for full export flow"
```

---

## Summary

| Task | Component | Tests |
|------|-----------|-------|
| 1 | CloudExportJob model + migration | 4 model tests |
| 2 | Pydantic schemas | 5 schema tests |
| 3 | Adapter upload + link methods | 4 dev adapter tests |
| 4 | CloudExportService | 9 service tests |
| 5 | OAuth scope upgrade | 2 scope tests |
| 6 | API routes + registration | 8 route tests |
| 7 | Frontend API client | — |
| 8 | i18n keys (en + de) | — |
| 9 | ShareFileModal (unified) | Manual dev-mode test |
| 10 | SharesPage Cloud tab | Manual dev-mode test |
| 11 | Integration test (full flow) | 2 integration tests |

Total: 11 tasks, ~34 automated tests, 2 manual verification points.
