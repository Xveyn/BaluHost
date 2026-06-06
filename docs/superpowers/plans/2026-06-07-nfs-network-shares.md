# NFS Network Shares Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add NFS support (GitHub #183) parallel to Samba: admin-defined host-based exports managed from the System Control page, generating `/etc/exports.d/baluhost.exports` + reloading via `exportfs -ra`.

**Architecture:** A new `nfs_exports` DB table is the source of truth. An async `nfs_service` (dev-mode no-ops, like `samba_service`) regenerates the exports file from the DB and reloads it. Admin-only CRUD routes drive it; a `NfsManagementCard` lives next to `SambaManagementCard` in `SystemControlPage`.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic + Pytest (backend); React + TypeScript + axios + Vitest + i18next (frontend).

**Reference spec:** `docs/superpowers/specs/2026-06-07-nfs-network-shares-design.md`
**Templates to mirror:** `backend/app/services/samba_service.py`, `backend/app/api/routes/samba.py`, `backend/app/schemas/samba.py`, `backend/tests/services/test_samba_service.py`, `client/src/components/samba/SambaManagementCard.tsx`, `client/src/api/samba.ts`, `deploy/samba/`.

**Working dir for all tasks:** `D:\Programme (x86)\Baluhost\.claude\worktrees\feat+nfs-network-shares` (branch `feat/nfs-network-shares`). Backend cmds from its `backend/`, frontend from its `client/`. Shell `grep`/`glob` are hook-blocked — use Read.

---

## File Structure

Backend:
- `backend/app/models/nfs_export.py` — `NfsExport` ORM model (new).
- `backend/app/models/__init__.py` — register model (modify).
- `backend/alembic/versions/c7f2a1b4d8e9_add_nfs_exports_table.py` — migration (new).
- `backend/app/services/nfs_service.py` — validators, config generation, reload, status (new).
- `backend/app/schemas/nfs.py` — request/response models (new).
- `backend/app/api/routes/nfs.py` — admin-only CRUD + status (new).
- `backend/app/api/routes/__init__.py` — register router (modify).
- `backend/tests/services/test_nfs_service.py`, `backend/tests/api/test_nfs_routes.py` (new).

Deploy:
- `deploy/nfs/baluhost-nfs-sudoers`, `deploy/nfs/setup-nfs.sh` (new). NOTE: `deploy/` is CODEOWNERS-protected; the sudoers entry is intentionally scoped to `exportfs` with explicit args.

Frontend:
- `client/src/api/nfs.ts` (new).
- `client/src/components/nfs/NfsManagementCard.tsx` (new).
- `client/src/pages/SystemControlPage.tsx` — add NFS tab (modify).
- `client/src/i18n/locales/{de,en}/system.json` — `nfs.*` card keys (modify).
- `client/src/i18n/locales/{de,en}/common.json` — `systemControl.tabs.nfs` label (modify).
- `client/src/__tests__/components/nfs/NfsManagementCard.test.tsx` (new).

---

## Task 1: NfsExport model + migration

**Files:**
- Create: `backend/app/models/nfs_export.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/c7f2a1b4d8e9_add_nfs_exports_table.py`
- Test: `backend/tests/models/test_nfs_export.py`

- [ ] **Step 1: Write the failing model test**

Create `backend/tests/models/test_nfs_export.py`:

```python
"""Tests for the NfsExport model."""
from sqlalchemy.orm import Session

from app.models.nfs_export import NfsExport


def test_nfs_export_roundtrip(db_session: Session):
    exp = NfsExport(
        path="Media",
        clients="192.168.1.0/24",
        read_only=False,
        root_squash=True,
        enabled=True,
        comment="media share",
    )
    db_session.add(exp)
    db_session.commit()
    db_session.refresh(exp)

    assert exp.id is not None
    got = db_session.query(NfsExport).filter_by(path="Media").one()
    assert got.clients == "192.168.1.0/24"
    assert got.read_only is False
    assert got.root_squash is True
    assert got.enabled is True
    assert got.comment == "media share"


def test_nfs_export_defaults(db_session: Session):
    exp = NfsExport(path="Docs", clients="*")
    db_session.add(exp)
    db_session.commit()
    db_session.refresh(exp)
    assert exp.read_only is False
    assert exp.root_squash is True
    assert exp.enabled is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/models/test_nfs_export.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.nfs_export'`.

- [ ] **Step 3: Create the model**

Create `backend/app/models/nfs_export.py`:

```python
"""NFS export configuration model."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import Base


class NfsExport(Base):
    """A single admin-defined, host-based NFS export."""

    __tablename__ = "nfs_exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Path relative to the storage root; "" means the storage root itself.
    path: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
    # Single client spec: IPv4, IPv4/CIDR, hostname, or "*".
    clients: Mapped[str] = mapped_column(String(255), nullable=False)
    read_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    root_squash: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    def __repr__(self) -> str:
        return f"<NfsExport(id={self.id}, path='{self.path}', clients='{self.clients}')>"
```

- [ ] **Step 4: Register the model**

In `backend/app/models/__init__.py`:
- After the line `from app.models.file_activity import FileActivity`, add:
  ```python
  from app.models.nfs_export import NfsExport
  ```
- In the `__all__` list, after `"FileActivity",`, add:
  ```python
      "NfsExport",
  ```

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && python -m pytest tests/models/test_nfs_export.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Write the Alembic migration (hand-written, chained onto the real head `45292ba19a35`)**

Create `backend/alembic/versions/c7f2a1b4d8e9_add_nfs_exports_table.py`:

```python
"""add nfs_exports table

Revision ID: c7f2a1b4d8e9
Revises: 45292ba19a35
Create Date: 2026-06-07
"""
from alembic import op
import sqlalchemy as sa

revision = "c7f2a1b4d8e9"
down_revision = "45292ba19a35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nfs_exports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("clients", sa.String(length=255), nullable=False),
        sa.Column("read_only", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("root_squash", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("path", name="uq_nfs_exports_path"),
    )


def downgrade() -> None:
    op.drop_table("nfs_exports")
```

- [ ] **Step 7: Verify the migration chains cleanly to a single head**

Run: `cd backend && python -m alembic heads`
Expected: a single line `c7f2a1b4d8e9 (head)`. If it shows multiple heads, the `down_revision` is wrong — fix it to the previous single head reported by `git stash`-free `alembic history | head`.

Then apply it: `cd backend && python -m alembic upgrade head`
Expected: `Running upgrade 45292ba19a35 -> c7f2a1b4d8e9, add nfs_exports table`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/nfs_export.py backend/app/models/__init__.py backend/alembic/versions/c7f2a1b4d8e9_add_nfs_exports_table.py backend/tests/models/test_nfs_export.py
git commit -m "feat(nfs): NfsExport model + migration"
```

---

## Task 2: NFS service (validators, config generation, reload, status)

**Files:**
- Create: `backend/app/services/nfs_service.py`
- Test: `backend/tests/services/test_nfs_service.py`

- [ ] **Step 1: Write the failing service tests**

Create `backend/tests/services/test_nfs_service.py`:

```python
"""Tests for services/nfs_service.py."""
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models.nfs_export import NfsExport
from app.services import nfs_service


class TestValidateClients:
    def test_accepts_valid_specs(self):
        for spec in ["*", "192.168.1.5", "192.168.1.0/24", "host.local", "10.0.0.0/8"]:
            assert nfs_service.validate_clients(spec) == spec

    def test_rejects_bad_specs(self):
        for spec in ["", "300.1.1.1", "1.2.3.4/40", "bad spec!", "a b"]:
            with pytest.raises(ValueError):
                nfs_service.validate_clients(spec)


class TestValidateExportPath:
    def test_relative_path_within_root(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.services.nfs_service.settings.nas_storage_path", str(tmp_path))
        result = nfs_service.validate_export_path("Media")
        assert result.endswith("Media")

    def test_empty_path_is_root(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.services.nfs_service.settings.nas_storage_path", str(tmp_path))
        result = nfs_service.validate_export_path("")
        assert Path(result) == Path(str(tmp_path)).resolve()

    def test_traversal_rejected(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.services.nfs_service.settings.nas_storage_path", str(tmp_path))
        for bad in ["../etc", "Media/../../etc", "../../../etc/passwd"]:
            with pytest.raises(ValueError):
                nfs_service.validate_export_path(bad)


@pytest.mark.asyncio
class TestDevModeStubs:
    async def test_regenerate_returns_true(self):
        assert await nfs_service.regenerate_exports_config() is True

    async def test_apply_returns_true(self):
        assert await nfs_service.apply_exports() is True

    async def test_status_shape(self):
        status = await nfs_service.get_nfs_status()
        assert status["is_running"] is False
        assert status["version"] == "dev-mode"
        assert isinstance(status["exports_count"], int)


@pytest.mark.asyncio
class TestRegenerateExportsConfig:
    async def test_writes_correct_export_line(self, db_session: Session, tmp_path, monkeypatch):
        from sqlalchemy.orm import sessionmaker
        from app.core.config import settings

        # Point the service's SessionLocal at the test DB
        test_engine = db_session.get_bind()
        TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
        monkeypatch.setattr("app.services.nfs_service.SessionLocal", TestSessionLocal)

        # One enabled export
        exp = NfsExport(path="Media", clients="192.168.1.0/24", read_only=False, root_squash=True, enabled=True)
        db_session.add(exp)
        db_session.commit()
        db_session.refresh(exp)

        # Non-dev mode, storage root + conf path in tmp
        monkeypatch.setattr(settings, "is_dev_mode", False)
        monkeypatch.setattr(settings, "nas_storage_path", str(tmp_path))
        conf_path = str(tmp_path / "baluhost.exports")
        monkeypatch.setattr(nfs_service, "_get_exports_conf_path", lambda: conf_path)

        assert await nfs_service.regenerate_exports_config() is True

        content = Path(conf_path).read_text()
        assert "Media" in content
        assert f"192.168.1.0/24(rw,root_squash,sync,no_subtree_check,fsid={exp.id})" in content

    async def test_disabled_export_excluded(self, db_session: Session, tmp_path, monkeypatch):
        from sqlalchemy.orm import sessionmaker
        from app.core.config import settings

        test_engine = db_session.get_bind()
        TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
        monkeypatch.setattr("app.services.nfs_service.SessionLocal", TestSessionLocal)

        db_session.add(NfsExport(path="Off", clients="*", enabled=False))
        db_session.commit()

        monkeypatch.setattr(settings, "is_dev_mode", False)
        monkeypatch.setattr(settings, "nas_storage_path", str(tmp_path))
        conf_path = str(tmp_path / "baluhost.exports")
        monkeypatch.setattr(nfs_service, "_get_exports_conf_path", lambda: conf_path)

        assert await nfs_service.regenerate_exports_config() is True
        assert "Off" not in Path(conf_path).read_text()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_nfs_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.nfs_service'`.

- [ ] **Step 3: Implement the service**

Create `backend/app/services/nfs_service.py`:

```python
"""
NFS export management service for BaluHost.

Generates /etc/exports.d/baluhost.exports from admin-defined export records and
reloads it via `exportfs -ra`. In dev mode all system commands are no-ops.
"""
import asyncio
import ipaddress
import logging
import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Optional

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.nfs_export import NfsExport

logger = logging.getLogger(__name__)

NFS_EXPORTS_CONF = "/etc/exports.d/baluhost.exports"

# RFC-1123-ish hostname (also allows single-label names like "host").
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"([a-zA-Z0-9_](?:[a-zA-Z0-9_-]{0,61}[a-zA-Z0-9_])?)"
    r"(\.[a-zA-Z0-9_](?:[a-zA-Z0-9_-]{0,61}[a-zA-Z0-9_])?)*$"
)


def _get_exports_conf_path() -> str:
    """Return the path used for the generated exports file (overridable in tests)."""
    return getattr(settings, "nfs_exports_conf_path", NFS_EXPORTS_CONF)


def validate_clients(clients: str) -> str:
    """Validate a single NFS client spec.

    Accepts '*', an IPv4 address, an IPv4 CIDR, or a DNS hostname.
    Returns the trimmed spec. Raises ValueError otherwise.
    """
    spec = (clients or "").strip()
    if not spec:
        raise ValueError("clients must not be empty")
    if spec == "*":
        return spec
    if "/" in spec:
        try:
            ipaddress.ip_network(spec, strict=False)
            return spec
        except ValueError as exc:
            raise ValueError(f"Invalid CIDR for NFS clients: {spec!r}") from exc
    try:
        ipaddress.ip_address(spec)
        return spec
    except ValueError:
        pass
    if _HOSTNAME_RE.match(spec):
        return spec
    raise ValueError(f"Invalid NFS client spec: {spec!r}")


def validate_export_path(path: str) -> str:
    """Validate an export path (relative to the storage root); return absolute path.

    Empty string means the storage root itself. Rejects path traversal and any
    path that resolves outside the storage root.
    """
    storage_root = Path(settings.nas_storage_path).expanduser().resolve()
    rel = (path or "").strip().lstrip("/")
    if ".." in PurePosixPath(rel).parts:
        raise ValueError(f"Path traversal not allowed: {path!r}")
    abs_path = (storage_root / rel).resolve()
    if abs_path != storage_root and storage_root not in abs_path.parents:
        raise ValueError(f"Export path escapes storage root: {path!r}")
    return str(abs_path)


async def _run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    """Run a system command (no shell). Returns (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


async def regenerate_exports_config() -> bool:
    """Regenerate /etc/exports.d/baluhost.exports from enabled DB exports."""
    if settings.is_dev_mode:
        logger.info("[DEV] Mock regenerate_exports_config()")
        return True

    db = SessionLocal()
    try:
        exports = (
            db.query(NfsExport)
            .filter(NfsExport.enabled == True)  # noqa: E712
            .order_by(NfsExport.id)
            .all()
        )
    finally:
        db.close()

    lines = ["# Auto-generated by BaluHost — do not edit manually", ""]
    for exp in exports:
        abs_path = validate_export_path(exp.path)
        client_spec = validate_clients(exp.clients)
        mode = "ro" if exp.read_only else "rw"
        squash = "root_squash" if exp.root_squash else "no_root_squash"
        opts = f"{mode},{squash},sync,no_subtree_check,fsid={exp.id}"
        lines.append(f"{abs_path} {client_spec}({opts})")
    lines.append("")

    conf_path = _get_exports_conf_path()
    content = "\n".join(lines)
    try:
        dir_path = os.path.dirname(conf_path)
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, prefix=".baluhost-exports-", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.rename(tmp_path, conf_path)
        logger.info("Regenerated NFS exports config (%d exports)", len(exports))
        return True
    except OSError as exc:
        logger.error("Failed to write NFS exports config: %s", exc)
        return False


async def apply_exports() -> bool:
    """Reload all NFS exports via `exportfs -ra`."""
    if settings.is_dev_mode:
        logger.info("[DEV] Mock apply_exports()")
        return True
    rc, _, stderr = await _run_cmd(["sudo", "exportfs", "-ra"])
    if rc != 0:
        logger.error("exportfs -ra failed: %s", stderr)
        return False
    logger.info("NFS exports reloaded")
    return True


async def get_nfs_status() -> dict:
    """Return {is_running, version, exports_count}."""
    db = SessionLocal()
    try:
        count = db.query(NfsExport).filter(NfsExport.enabled == True).count()  # noqa: E712
    finally:
        db.close()

    if settings.is_dev_mode:
        return {"is_running": False, "version": "dev-mode", "exports_count": count}

    rc, _, _ = await _run_cmd(["systemctl", "is-active", "nfs-server"])
    is_running = rc == 0
    if not is_running:
        rc2, _, _ = await _run_cmd(["pgrep", "nfsd"])
        is_running = rc2 == 0

    version: Optional[str] = None
    return {"is_running": is_running, "version": version, "exports_count": count}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && python -m pytest tests/services/test_nfs_service.py -v`
Expected: PASS (all classes/cases).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/nfs_service.py backend/tests/services/test_nfs_service.py
git commit -m "feat(nfs): export config service (validators, regenerate, apply, status)"
```

---

## Task 3: NFS schemas

**Files:**
- Create: `backend/app/schemas/nfs.py`

- [ ] **Step 1: Create the schemas**

Create `backend/app/schemas/nfs.py`:

```python
"""Pydantic models for NFS export management."""
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.services.nfs_service import validate_clients, validate_export_path


class NfsExportBase(BaseModel):
    path: str = Field(default="", description="Path relative to storage root; empty = whole root")
    clients: str = Field(..., description="Allowed clients: IP, CIDR, hostname, or *")
    read_only: bool = False
    root_squash: bool = True
    enabled: bool = True
    comment: Optional[str] = None

    @field_validator("clients")
    @classmethod
    def _validate_clients(cls, v: str) -> str:
        return validate_clients(v)

    @field_validator("path")
    @classmethod
    def _validate_path(cls, v: str) -> str:
        validate_export_path(v)  # raises ValueError on traversal/escape
        return (v or "").strip().lstrip("/")


class NfsExportCreate(NfsExportBase):
    pass


class NfsExportUpdate(NfsExportBase):
    pass


class NfsExportResponse(BaseModel):
    id: int
    path: str
    clients: str
    read_only: bool
    root_squash: bool
    enabled: bool
    comment: Optional[str] = None
    mount_target: str

    model_config = {"from_attributes": True}


class NfsExportsResponse(BaseModel):
    exports: list[NfsExportResponse]


class NfsStatusResponse(BaseModel):
    is_running: bool
    version: Optional[str] = None
    exports_count: int = 0
```

- [ ] **Step 2: Smoke-check the import**

Run: `cd backend && python -c "from app.schemas.nfs import NfsExportCreate, NfsExportResponse, NfsStatusResponse; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/nfs.py
git commit -m "feat(nfs): request/response schemas with path/clients validation"
```

---

## Task 4: NFS routes (admin-only CRUD + status)

**Files:**
- Create: `backend/app/api/routes/nfs.py`
- Modify: `backend/app/api/routes/__init__.py`
- Test: `backend/tests/api/test_nfs_routes.py`

- [ ] **Step 1: Write the failing route tests**

Create `backend/tests/api/test_nfs_routes.py`:

```python
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
        # create
        r = _create(client, admin_headers)
        assert r.status_code == 201, r.text
        created = r.json()
        export_id = created["id"]
        assert created["path"] == "Media"
        assert created["mount_target"].endswith("Media")

        # list
        r = client.get(f"{settings.api_prefix}/nfs/exports", headers=admin_headers)
        assert r.status_code == 200
        paths = {e["path"] for e in r.json()["exports"]}
        assert "Media" in paths

        # update
        r = client.put(
            f"{settings.api_prefix}/nfs/exports/{export_id}",
            json={"path": "Media", "clients": "192.168.1.0/24", "read_only": True,
                  "root_squash": True, "enabled": True, "comment": None},
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["read_only"] is True

        # delete
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_nfs_routes.py -v`
Expected: FAIL — 404s (route not registered yet).

- [ ] **Step 3: Create the routes**

Create `backend/app/api/routes/nfs.py`:

```python
"""NFS export management API endpoints (admin only)."""
import logging
import socket

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api import deps
from app.core.database import get_db
from app.core.rate_limiter import user_limiter, get_limit
from app.models.nfs_export import NfsExport
from app.schemas.nfs import (
    NfsExportCreate,
    NfsExportUpdate,
    NfsExportResponse,
    NfsExportsResponse,
    NfsStatusResponse,
)
from app.services import nfs_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nfs", tags=["nfs"])


def _get_local_ip() -> str:
    """Detect the primary local IP address."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _to_response(exp: NfsExport, server_ip: str) -> NfsExportResponse:
    abs_path = nfs_service.validate_export_path(exp.path)
    return NfsExportResponse(
        id=exp.id,
        path=exp.path,
        clients=exp.clients,
        read_only=exp.read_only,
        root_squash=exp.root_squash,
        enabled=exp.enabled,
        comment=exp.comment,
        mount_target=f"{server_ip}:{abs_path}",
    )


@router.get("/status", response_model=NfsStatusResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_nfs_status(
    request: Request, response: Response,
    _admin=Depends(deps.get_current_admin),
):
    """Get NFS server status (admin only)."""
    raw = await nfs_service.get_nfs_status()
    return NfsStatusResponse(**raw)


@router.get("/exports", response_model=NfsExportsResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def list_nfs_exports(
    request: Request, response: Response,
    _admin=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """List all NFS exports (admin only)."""
    ip = _get_local_ip()
    exports = db.query(NfsExport).order_by(NfsExport.id).all()
    return NfsExportsResponse(exports=[_to_response(e, ip) for e in exports])


@router.post("/exports", response_model=NfsExportResponse, status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("admin_operations"))
async def create_nfs_export(
    request: Request, response: Response,
    payload: NfsExportCreate,
    _admin=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Create an NFS export (admin only)."""
    if db.query(NfsExport).filter(NfsExport.path == payload.path).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An export for this path already exists")
    exp = NfsExport(
        path=payload.path, clients=payload.clients, read_only=payload.read_only,
        root_squash=payload.root_squash, enabled=payload.enabled, comment=payload.comment,
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    await nfs_service.regenerate_exports_config()
    await nfs_service.apply_exports()
    return _to_response(exp, _get_local_ip())


@router.put("/exports/{export_id}", response_model=NfsExportResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_nfs_export(
    request: Request, response: Response,
    export_id: int,
    payload: NfsExportUpdate,
    _admin=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Update an NFS export (admin only)."""
    exp = db.query(NfsExport).filter(NfsExport.id == export_id).first()
    if not exp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    if payload.path != exp.path and db.query(NfsExport).filter(NfsExport.path == payload.path).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An export for this path already exists")
    exp.path = payload.path
    exp.clients = payload.clients
    exp.read_only = payload.read_only
    exp.root_squash = payload.root_squash
    exp.enabled = payload.enabled
    exp.comment = payload.comment
    db.commit()
    db.refresh(exp)
    await nfs_service.regenerate_exports_config()
    await nfs_service.apply_exports()
    return _to_response(exp, _get_local_ip())


@router.delete("/exports/{export_id}", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("admin_operations"))
async def delete_nfs_export(
    request: Request, response: Response,
    export_id: int,
    _admin=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Delete an NFS export (admin only)."""
    exp = db.query(NfsExport).filter(NfsExport.id == export_id).first()
    if not exp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    db.delete(exp)
    db.commit()
    await nfs_service.regenerate_exports_config()
    await nfs_service.apply_exports()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: Register the router**

In `backend/app/api/routes/__init__.py`:
- In the big `from app.api.routes import (...)` block, add `nfs,` on the line that currently reads `notifications, updates, chunked_upload, webdav, samba, cloud, cloud_export,` → change to include `nfs` e.g. append `, nfs` after `samba`:
  ```python
      notifications, updates, chunked_upload, webdav, samba, nfs, cloud, cloud_export,
  ```
- After the line `api_router.include_router(samba.router, tags=["samba"])`, add:
  ```python
  api_router.include_router(nfs.router, tags=["nfs"])
  ```

- [ ] **Step 5: Run to verify it passes**

Run: `cd backend && python -m pytest tests/api/test_nfs_routes.py -v`
Expected: PASS (all auth + CRUD + validation cases).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/nfs.py backend/app/api/routes/__init__.py backend/tests/api/test_nfs_routes.py
git commit -m "feat(nfs): admin-only CRUD + status routes"
```

---

## Task 5: Deploy (sudoers + setup script)

**Files:**
- Create: `deploy/nfs/baluhost-nfs-sudoers`
- Create: `deploy/nfs/setup-nfs.sh`

NOTE: `deploy/` is CODEOWNERS-protected. The sudoers entry is scoped to `exportfs` with explicit args (tighter than Samba's binary-only entries). No tests (shell scripts; reviewed by CODEOWNERS).

- [ ] **Step 1: Create the sudoers file**

Create `deploy/nfs/baluhost-nfs-sudoers`:

```
# BaluHost NFS sudoers rules
# Install: sudo cp baluhost-nfs-sudoers /etc/sudoers.d/baluhost-nfs
# Verify:  sudo visudo -c

sven ALL=(ALL) NOPASSWD: /usr/sbin/exportfs -ra
sven ALL=(ALL) NOPASSWD: /usr/sbin/exportfs -r
```

- [ ] **Step 2: Create the setup script**

Create `deploy/nfs/setup-nfs.sh`:

```bash
#!/bin/bash
# BaluHost NFS Setup Script
# Run once on the production server to install and configure the NFS server.
#
# Usage: sudo bash setup-nfs.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_USER="${SERVICE_USER:-sven}"
STORAGE_GROUP="${STORAGE_GROUP:-baluhost}"
EXPORTS_CONF="/etc/exports.d/baluhost.exports"

echo "=== BaluHost NFS Setup ==="

echo "[1/4] Installing NFS server..."
apt-get update -qq
apt-get install -y -qq nfs-kernel-server

echo "[2/4] Creating exports config..."
mkdir -p /etc/exports.d
touch "$EXPORTS_CONF"
chown "$SERVICE_USER:$STORAGE_GROUP" "$EXPORTS_CONF"
chmod 644 "$EXPORTS_CONF"

echo "[3/4] Installing sudoers rules..."
cp "$SCRIPT_DIR/baluhost-nfs-sudoers" /etc/sudoers.d/baluhost-nfs
chmod 440 /etc/sudoers.d/baluhost-nfs
visudo -c

echo "[4/4] Enabling nfs-server..."
systemctl enable --now nfs-server

echo ""
echo "=== NFS Setup Complete ==="
echo "nfs-server status: $(systemctl is-active nfs-server)"
echo ""
echo "Next steps:"
echo "  1. Create NFS exports in BaluHost UI (System Control -> NFS)"
echo "  2. Linux client: sudo mount -t nfs $(hostname -I | awk '{print $1}'):<path> /mnt/baluhost"
```

- [ ] **Step 3: Commit**

```bash
git add deploy/nfs/baluhost-nfs-sudoers deploy/nfs/setup-nfs.sh
git commit -m "deploy(nfs): exportfs sudoers + setup script"
```

---

## Task 6: Frontend API client

**Files:**
- Create: `client/src/api/nfs.ts`

- [ ] **Step 1: Create the client**

Create `client/src/api/nfs.ts`:

```typescript
import { apiClient } from '../lib/api';

export interface NfsExport {
  id: number;
  path: string;
  clients: string;
  read_only: boolean;
  root_squash: boolean;
  enabled: boolean;
  comment: string | null;
  mount_target: string;
}

export interface NfsStatus {
  is_running: boolean;
  version: string | null;
  exports_count: number;
}

export interface NfsExportInput {
  path: string;
  clients: string;
  read_only: boolean;
  root_squash: boolean;
  enabled: boolean;
  comment?: string | null;
}

export async function getNfsStatus(): Promise<NfsStatus> {
  const { data } = await apiClient.get<NfsStatus>('/api/nfs/status');
  return data;
}

export async function listNfsExports(): Promise<NfsExport[]> {
  const { data } = await apiClient.get<{ exports: NfsExport[] }>('/api/nfs/exports');
  return data.exports;
}

export async function createNfsExport(input: NfsExportInput): Promise<NfsExport> {
  const { data } = await apiClient.post<NfsExport>('/api/nfs/exports', input);
  return data;
}

export async function updateNfsExport(id: number, input: NfsExportInput): Promise<NfsExport> {
  const { data } = await apiClient.put<NfsExport>(`/api/nfs/exports/${id}`, input);
  return data;
}

export async function deleteNfsExport(id: number): Promise<void> {
  await apiClient.delete(`/api/nfs/exports/${id}`);
}
```

- [ ] **Step 2: Type-check**

Run: `cd client && npx tsc --noEmit`
Expected: no errors referencing `api/nfs.ts` (pre-existing unrelated errors, if any, are acceptable — report them).

- [ ] **Step 3: Commit**

```bash
git add client/src/api/nfs.ts
git commit -m "feat(nfs): typed api/nfs client"
```

---

## Task 7: NFS management card + i18n + Vitest test

**Files:**
- Create: `client/src/components/nfs/NfsManagementCard.tsx`
- Modify: `client/src/i18n/locales/de/system.json`, `client/src/i18n/locales/en/system.json`
- Test: `client/src/__tests__/components/nfs/NfsManagementCard.test.tsx`

- [ ] **Step 1: Add i18n keys (English)**

In `client/src/i18n/locales/en/system.json`, add a top-level `"nfs"` object (sibling of the existing `"samba"` object — keep JSON valid):

```json
  "nfs": {
    "title": "NFS Exports",
    "subtitle": "Share folders to Linux/Unix clients over NFS",
    "refresh": "Refresh",
    "running": "Running",
    "notRunning": "Not running",
    "notRunningHint": "The NFS server is not running. Run deploy/nfs/setup-nfs.sh on the server.",
    "exportsCount": "Exports",
    "lanWarning": "NFS has no per-user authentication. Only export to trusted hosts/subnets on your local network.",
    "addExport": "Add export",
    "noExports": "No NFS exports yet.",
    "path": "Path",
    "wholeRoot": "(whole storage root)",
    "clients": "Allowed clients",
    "mode": "Mode",
    "readOnly": "Read-only",
    "readWrite": "Read-write",
    "squash": "Root squash",
    "on": "on",
    "off": "off",
    "enabledLabel": "Enabled",
    "actions": "Actions",
    "edit": "Edit",
    "delete": "Delete",
    "deleteConfirm": "Delete this NFS export?",
    "mountExample": "Mount example",
    "copy": "Copy",
    "copied": "Copied",
    "save": "Save",
    "cancel": "Cancel",
    "create": "Create",
    "loading": "Loading NFS exports...",
    "pathPlaceholder": "Media (relative to storage root, empty = whole root)",
    "clientsPlaceholder": "192.168.1.0/24 or * or host.local",
    "comment": "Comment",
    "addTitle": "Add NFS export",
    "editTitle": "Edit NFS export",
    "createFailed": "Failed to create export",
    "updateFailed": "Failed to update export",
    "deleteFailed": "Failed to delete export",
    "created": "Export created",
    "updated": "Export updated",
    "deleted": "Export deleted"
  }
```

- [ ] **Step 2: Add i18n keys (German)**

In `client/src/i18n/locales/de/system.json`, add the sibling `"nfs"` object:

```json
  "nfs": {
    "title": "NFS-Exporte",
    "subtitle": "Ordner für Linux/Unix-Clients per NFS freigeben",
    "refresh": "Aktualisieren",
    "running": "Läuft",
    "notRunning": "Nicht aktiv",
    "notRunningHint": "Der NFS-Server läuft nicht. Führe deploy/nfs/setup-nfs.sh auf dem Server aus.",
    "exportsCount": "Exporte",
    "lanWarning": "NFS hat keine benutzerbezogene Authentifizierung. Exportiere nur an vertrauenswürdige Hosts/Subnetze im lokalen Netzwerk.",
    "addExport": "Export hinzufügen",
    "noExports": "Noch keine NFS-Exporte.",
    "path": "Pfad",
    "wholeRoot": "(gesamter Storage-Root)",
    "clients": "Erlaubte Clients",
    "mode": "Modus",
    "readOnly": "Nur Lesen",
    "readWrite": "Lesen & Schreiben",
    "squash": "Root-Squash",
    "on": "an",
    "off": "aus",
    "enabledLabel": "Aktiv",
    "actions": "Aktionen",
    "edit": "Bearbeiten",
    "delete": "Löschen",
    "deleteConfirm": "Diesen NFS-Export löschen?",
    "mountExample": "Mount-Beispiel",
    "copy": "Kopieren",
    "copied": "Kopiert",
    "save": "Speichern",
    "cancel": "Abbrechen",
    "create": "Erstellen",
    "loading": "NFS-Exporte werden geladen...",
    "pathPlaceholder": "Media (relativ zum Storage-Root, leer = gesamter Root)",
    "clientsPlaceholder": "192.168.1.0/24 oder * oder host.local",
    "comment": "Kommentar",
    "addTitle": "NFS-Export hinzufügen",
    "editTitle": "NFS-Export bearbeiten",
    "createFailed": "Export konnte nicht erstellt werden",
    "updateFailed": "Export konnte nicht aktualisiert werden",
    "deleteFailed": "Export konnte nicht gelöscht werden",
    "created": "Export erstellt",
    "updated": "Export aktualisiert",
    "deleted": "Export gelöscht"
  }
```

- [ ] **Step 3: Validate JSON**

Run: `cd client && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/de/system.json','utf8'));JSON.parse(require('fs').readFileSync('src/i18n/locales/en/system.json','utf8'));console.log('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Write the failing component test**

Create `client/src/__tests__/components/nfs/NfsManagementCard.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import NfsManagementCard from '../../../components/nfs/NfsManagementCard';
import type { NfsExport, NfsStatus } from '../../../api/nfs';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../../api/nfs', () => ({
  getNfsStatus: vi.fn(),
  listNfsExports: vi.fn(),
  createNfsExport: vi.fn(),
  updateNfsExport: vi.fn(),
  deleteNfsExport: vi.fn(),
}));

import { getNfsStatus, listNfsExports } from '../../../api/nfs';

const status: NfsStatus = { is_running: true, version: null, exports_count: 1 };
const exports: NfsExport[] = [
  {
    id: 1, path: 'Media', clients: '192.168.1.0/24', read_only: false,
    root_squash: true, enabled: true, comment: null,
    mount_target: '192.168.1.10:/srv/baluhost/Media',
  },
];

describe('NfsManagementCard', () => {
  beforeEach(() => {
    vi.mocked(getNfsStatus).mockResolvedValue(status);
    vi.mocked(listNfsExports).mockResolvedValue(exports);
  });
  afterEach(() => vi.restoreAllMocks());

  it('renders the export list from the API', async () => {
    render(<NfsManagementCard />);
    await waitFor(() => expect(screen.getByText('Media')).toBeInTheDocument());
    expect(screen.getByText('192.168.1.0/24')).toBeInTheDocument();
    expect(getNfsStatus).toHaveBeenCalled();
    expect(listNfsExports).toHaveBeenCalled();
  });
});
```

- [ ] **Step 5: Run to verify it fails**

Run: `cd client && npx vitest run src/__tests__/components/nfs/NfsManagementCard.test.tsx`
Expected: FAIL — component module does not exist yet.

- [ ] **Step 6: Create the component**

Create `client/src/components/nfs/NfsManagementCard.tsx`:

```tsx
import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Server, RefreshCw, AlertCircle, Loader2, Plus, Pencil, Trash2 } from 'lucide-react';
import toast from 'react-hot-toast';
import {
  getNfsStatus, listNfsExports, createNfsExport, updateNfsExport, deleteNfsExport,
  type NfsStatus, type NfsExport, type NfsExportInput,
} from '../../api/nfs';

const EMPTY_FORM: NfsExportInput = {
  path: '', clients: '', read_only: false, root_squash: true, enabled: true, comment: null,
};

export default function NfsManagementCard() {
  const { t } = useTranslation('system');
  const [status, setStatus] = useState<NfsStatus | null>(null);
  const [exports, setExports] = useState<NfsExport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<NfsExport | null>(null);
  const [form, setForm] = useState<NfsExportInput>(EMPTY_FORM);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [s, e] = await Promise.all([getNfsStatus(), listNfsExports()]);
      setStatus(s);
      setExports(e);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const openAdd = () => { setEditing(null); setForm(EMPTY_FORM); setShowForm(true); };
  const openEdit = (exp: NfsExport) => {
    setEditing(exp);
    setForm({
      path: exp.path, clients: exp.clients, read_only: exp.read_only,
      root_squash: exp.root_squash, enabled: exp.enabled, comment: exp.comment,
    });
    setShowForm(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (editing) {
        await updateNfsExport(editing.id, form);
        toast.success(t('nfs.updated'));
      } else {
        await createNfsExport(form);
        toast.success(t('nfs.created'));
      }
      setShowForm(false);
      await loadData();
    } catch {
      toast.error(t(editing ? 'nfs.updateFailed' : 'nfs.createFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (exp: NfsExport) => {
    if (!window.confirm(t('nfs.deleteConfirm'))) return;
    try {
      await deleteNfsExport(exp.id);
      toast.success(t('nfs.deleted'));
      await loadData();
    } catch {
      toast.error(t('nfs.deleteFailed'));
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-slate-400">
        <Loader2 className="h-5 w-5 animate-spin mr-2" />
        {t('nfs.loading')}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-red-500/10 border border-red-500/20 p-4 text-red-400">
        <AlertCircle className="h-5 w-5 shrink-0" />
        <span>{error}</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <Server className="h-6 w-6 text-blue-400" />
            {t('nfs.title')}
          </h2>
          <p className="mt-1 text-sm text-slate-400">{t('nfs.subtitle')}</p>
        </div>
        <button
          onClick={loadData}
          className="flex items-center gap-1.5 rounded-lg bg-slate-800/50 px-3 py-2 text-sm text-slate-400 hover:text-white hover:bg-slate-700/50 transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
          {t('nfs.refresh')}
        </button>
      </div>

      {/* Status */}
      {status && (
        <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 p-5 flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <div className={`h-2.5 w-2.5 rounded-full ${status.is_running ? 'bg-green-400' : 'bg-red-400'}`} />
            <span className={`text-sm font-medium ${status.is_running ? 'text-green-400' : 'text-red-400'}`}>
              {status.is_running ? t('nfs.running') : t('nfs.notRunning')}
            </span>
          </div>
          <div className="text-sm text-slate-400">{t('nfs.exportsCount')}: {status.exports_count}</div>
        </div>
      )}

      {status && !status.is_running && (
        <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-4 text-amber-300 text-sm">
          <AlertCircle className="h-4 w-4 inline mr-2" />
          {t('nfs.notRunningHint')}
        </div>
      )}

      {/* LAN-only warning */}
      <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-4 text-amber-300 text-sm">
        <AlertCircle className="h-4 w-4 inline mr-2" />
        {t('nfs.lanWarning')}
      </div>

      {/* Export list */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-medium text-white">{t('nfs.title')}</h3>
          <button
            onClick={openAdd}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 transition-colors"
          >
            <Plus className="h-4 w-4" />
            {t('nfs.addExport')}
          </button>
        </div>

        {exports.length === 0 ? (
          <p className="text-sm text-slate-500">{t('nfs.noExports')}</p>
        ) : (
          <div className="rounded-xl bg-slate-800/50 border border-slate-700/50 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-700/50 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">
                  <th className="px-4 py-3">{t('nfs.path')}</th>
                  <th className="px-4 py-3">{t('nfs.clients')}</th>
                  <th className="px-4 py-3">{t('nfs.mode')}</th>
                  <th className="px-4 py-3">{t('nfs.squash')}</th>
                  <th className="px-4 py-3">{t('nfs.enabledLabel')}</th>
                  <th className="px-4 py-3 text-right">{t('nfs.actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/30">
                {exports.map((exp) => (
                  <tr key={exp.id} className="hover:bg-slate-800/30 transition-colors text-sm">
                    <td className="px-4 py-3 text-white font-medium">
                      {exp.path || <span className="text-slate-500">{t('nfs.wholeRoot')}</span>}
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-300">{exp.clients}</td>
                    <td className="px-4 py-3 text-slate-300">
                      {exp.read_only ? t('nfs.readOnly') : t('nfs.readWrite')}
                    </td>
                    <td className="px-4 py-3 text-slate-300">{exp.root_squash ? t('nfs.on') : t('nfs.off')}</td>
                    <td className="px-4 py-3 text-slate-300">{exp.enabled ? t('nfs.on') : t('nfs.off')}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        <button onClick={() => openEdit(exp)} className="text-slate-400 hover:text-white" title={t('nfs.edit')}>
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button onClick={() => handleDelete(exp)} className="text-red-400 hover:text-red-300" title={t('nfs.delete')}>
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                      <code className="mt-1 block text-[11px] font-mono text-slate-500 break-all">{exp.mount_target}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add/Edit modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl bg-slate-900 border border-slate-700/50 p-6 shadow-2xl space-y-4">
            <h3 className="text-lg font-semibold text-white">
              {editing ? t('nfs.editTitle') : t('nfs.addTitle')}
            </h3>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">{t('nfs.path')}</label>
              <input
                type="text" value={form.path}
                onChange={(e) => setForm({ ...form, path: e.target.value })}
                placeholder={t('nfs.pathPlaceholder')}
                className="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-blue-500 outline-none"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">{t('nfs.clients')}</label>
              <input
                type="text" value={form.clients}
                onChange={(e) => setForm({ ...form, clients: e.target.value })}
                placeholder={t('nfs.clientsPlaceholder')}
                className="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-blue-500 outline-none"
              />
            </div>

            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" checked={form.read_only}
                  onChange={(e) => setForm({ ...form, read_only: e.target.checked })} />
                {t('nfs.readOnly')}
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" checked={form.root_squash}
                  onChange={(e) => setForm({ ...form, root_squash: e.target.checked })} />
                {t('nfs.squash')}
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" checked={form.enabled}
                  onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
                {t('nfs.enabledLabel')}
              </label>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => setShowForm(false)}
                className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:text-white hover:bg-slate-800 transition-colors">
                {t('nfs.cancel')}
              </button>
              <button onClick={handleSave} disabled={saving}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50 transition-colors">
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : (editing ? t('nfs.save') : t('nfs.create'))}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 7: Run to verify it passes**

Run: `cd client && npx vitest run src/__tests__/components/nfs/NfsManagementCard.test.tsx`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add client/src/components/nfs/NfsManagementCard.tsx client/src/i18n/locales/de/system.json client/src/i18n/locales/en/system.json client/src/__tests__/components/nfs/NfsManagementCard.test.tsx
git commit -m "feat(nfs): NFS management card + i18n (de/en)"
```

---

## Task 8: Wire the NFS tab into SystemControlPage

**Files:**
- Modify: `client/src/pages/SystemControlPage.tsx`
- Modify: `client/src/i18n/locales/de/common.json`, `client/src/i18n/locales/en/common.json`

- [ ] **Step 1: Add the tab-label i18n key**

In `client/src/i18n/locales/en/common.json`, locate `systemControl.tabs` (it contains `"samba": "SMB/CIFS"` or similar). Add a sibling key:
```json
        "nfs": "NFS",
```
Do the same in `client/src/i18n/locales/de/common.json` (value `"NFS"`).

Validate: `cd client && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/de/common.json','utf8'));JSON.parse(require('fs').readFileSync('src/i18n/locales/en/common.json','utf8'));console.log('ok')"` → `ok`.

- [ ] **Step 2: Add the tab to SystemControlPage**

In `client/src/pages/SystemControlPage.tsx`:

(a) Add the import after the existing `import SambaManagementCard from '../components/samba/SambaManagementCard';` line:
```tsx
import NfsManagementCard from '../components/nfs/NfsManagementCard';
```

(b) Extend the `TabType` union — add `'nfs'`. Change:
```tsx
type TabType = 'energy' | 'fan' | 'sleep' | 'raid' | 'backup' | 'ssdcache' | 'vpn' | 'webdav' | 'samba' | 'firebase' | 'services' | 'vcl' | 'smart' | 'ratelimits' | 'envconfig' | 'balupi' | 'statusbar' | 'apikeys';
```
to include `| 'nfs'` after `'samba'`:
```tsx
type TabType = 'energy' | 'fan' | 'sleep' | 'raid' | 'backup' | 'ssdcache' | 'vpn' | 'webdav' | 'samba' | 'nfs' | 'firebase' | 'services' | 'vcl' | 'smart' | 'ratelimits' | 'envconfig' | 'balupi' | 'statusbar' | 'apikeys';
```

(c) In the `network` category `tabs` array, add the NFS tab right after the `samba` entry (the `Server` icon is already imported at the top of the file):
```tsx
      { id: 'nfs', labelKey: 'systemControl.tabs.nfs', icon: <Server className="h-5 w-5" /> },
```

(d) In the Tab Content block, add the render line right after `{activeTab === 'samba' && <SambaManagementCard />}`:
```tsx
        {activeTab === 'nfs' && <NfsManagementCard />}
```

- [ ] **Step 3: Type-check**

Run: `cd client && npx tsc --noEmit`
Expected: clean (no errors referencing SystemControlPage or the new files).

- [ ] **Step 4: Commit**

```bash
git add client/src/pages/SystemControlPage.tsx client/src/i18n/locales/de/common.json client/src/i18n/locales/en/common.json
git commit -m "feat(nfs): add NFS tab to System Control page"
```

---

## Task 9: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Backend — touched tests**

Run: `cd backend && python -m pytest tests/models/test_nfs_export.py tests/services/test_nfs_service.py tests/api/test_nfs_routes.py -v`
Expected: all PASS.

- [ ] **Step 2: Backend — confirm Alembic single head**

Run: `cd backend && python -m alembic heads`
Expected: single head `c7f2a1b4d8e9 (head)`.

- [ ] **Step 3: Frontend — type-check + full unit suite**

Run: `cd client && npx tsc --noEmit && npx vitest run`
Expected: no TS errors; all Vitest tests pass (incl. the new NFS card test).

- [ ] **Step 4: Frontend — production build**

Run: `cd client && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Manual smoke (dev mode)**

Start `python start_dev.py`, log in as `admin/DevMode2024` → System Control → Network → **NFS** tab. The card shows status (dev: "Not running"), the LAN warning, an empty export list. Add an export (path `Media`, clients `192.168.1.0/24`) → it appears with a `mount_target` line. Edit it (toggle read-only) → persists. Delete it → list empties. Log in as a regular user → System Control is admin-only, so the tab is not reachable (backend also returns 403). (Covered by automated tests; smoke is optional.)

---

## Notes for the implementer

- Repo uses `core.autocrlf=true` on Windows — let Git handle line endings.
- Backend cmds from `backend/`, frontend from `client/`. Branch: `feat/nfs-network-shares`.
- The spec is the source of truth: `docs/superpowers/specs/2026-06-07-nfs-network-shares-design.md`.
- `deploy/` is CODEOWNERS-protected; Task 5 touches it — expect owner review on the PR.
- Dev mode: all NFS system commands are no-ops, so route tests exercise DB + validation without a real NFS server.
</content>
