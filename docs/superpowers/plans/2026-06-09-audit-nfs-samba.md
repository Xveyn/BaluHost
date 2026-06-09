# NFS/Samba Share-Mutation Audit Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jede NFS-Export- und SMB-User-Mutation (Erfolg und Fehler) schreibt einen Audit-Log-Eintrag via `get_audit_logger_db().log_event(...)`.

**Architecture:** Direkte `log_event(event_type="SYSTEM_CONFIG", ...)`-Aufrufe in den vier Route-Handlern; kein neuer Code im Logger. Validierungs-Ablehnungen (404/409) loggen `success=False` vor dem `raise`; Service-Calls werden in `try/except Exception` gekapselt und loggen bei Exception `success=False` + re-raise; nach erfolgreicher Mutation `success=True`.

**Tech Stack:** FastAPI, SQLAlchemy, Pytest (TestClient + in-memory SQLite). Audit-Logger: `app.services.audit.logger_db.AuditLoggerDB`.

**Spec:** `docs/superpowers/specs/2026-06-09-audit-nfs-samba-design.md`

---

## File Structure

- **Modify** `backend/app/api/routes/nfs.py` — Import `get_audit_logger_db`; Audit-Aufrufe in `create_nfs_export`, `update_nfs_export`, `delete_nfs_export`; Parameter `_admin` → `current_admin`.
- **Modify** `backend/app/api/routes/samba.py` — Import `get_audit_logger_db`; Audit-Aufrufe in `toggle_smb_user`; Parameter `_admin` → `current_admin`.
- **Modify** `backend/tests/api/test_nfs_routes.py` — Neue Audit-Assertion-Tests.
- **Create** `backend/tests/api/test_samba_routes.py` — Toggle-Audit-Tests (Samba-Service gemockt).

**Hinweis zum Parameter:** Der bestehende Stil im Repo erlaubt `current_admin=Depends(deps.get_current_admin)` **ohne** Typ-Annotation (siehe `samba.py:119` `current_user=Depends(...)`). Wir nutzen diese Form — dadurch ist **kein** zusätzlicher `UserPublic`-Import nötig.

---

## Task 1: NFS-Export Audit-Logging

**Files:**
- Modify: `backend/app/api/routes/nfs.py`
- Test: `backend/tests/api/test_nfs_routes.py`

- [ ] **Step 1: Audit-Assertion-Tests schreiben (failing)**

In `backend/tests/api/test_nfs_routes.py` oben den Import ergänzen (unter die bestehende `from app.core.config import settings`-Zeile):

```python
import pytest
from app.models.audit_log import AuditLog
```

Am Dateiende anhängen:

```python
@pytest.fixture
def audit_enabled():
    """Ensure the global audit logger is enabled (a prior test may have disabled it)."""
    from app.services.audit.logger_db import get_audit_logger_db
    get_audit_logger_db().enable()


class TestNfsAudit:
    def test_create_writes_audit(self, client, admin_headers, db_session, audit_enabled):
        r = _create(client, admin_headers, path="AuditMedia")
        assert r.status_code == 201, r.text
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "nfs_export_created", AuditLog.success == True)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.event_type == "SYSTEM_CONFIG"
        assert row.resource == "AuditMedia"
        assert row.user == settings.admin_username

    def test_update_writes_audit(self, client, admin_headers, db_session, audit_enabled):
        export_id = _create(client, admin_headers, path="AuditUpd").json()["id"]
        r = client.put(
            f"{settings.api_prefix}/nfs/exports/{export_id}",
            json={"path": "AuditUpd", "clients": "192.168.1.0/24", "read_only": True,
                  "root_squash": True, "enabled": True, "comment": None},
            headers=admin_headers,
        )
        assert r.status_code == 200
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "nfs_export_updated", AuditLog.success == True)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.resource == "AuditUpd"

    def test_delete_writes_audit(self, client, admin_headers, db_session, audit_enabled):
        export_id = _create(client, admin_headers, path="AuditDel").json()["id"]
        r = client.delete(f"{settings.api_prefix}/nfs/exports/{export_id}", headers=admin_headers)
        assert r.status_code == 204
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "nfs_export_deleted", AuditLog.success == True)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.resource == "AuditDel"

    def test_delete_missing_writes_failure(self, client, admin_headers, db_session, audit_enabled):
        r = client.delete(f"{settings.api_prefix}/nfs/exports/888888", headers=admin_headers)
        assert r.status_code == 404
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "nfs_export_deleted", AuditLog.success == False)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.resource == "888888"
        assert row.error_message == "Export not found"

    def test_duplicate_create_writes_failure(self, client, admin_headers, db_session, audit_enabled):
        assert _create(client, admin_headers, path="AuditDup").status_code == 201
        assert _create(client, admin_headers, path="AuditDup").status_code == 409
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "nfs_export_created", AuditLog.success == False)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.resource == "AuditDup"
```

- [ ] **Step 2: Tests laufen lassen → fail**

Run: `cd backend && python -m pytest tests/api/test_nfs_routes.py::TestNfsAudit -v`
Expected: 5× FAIL (kein AuditLog-Row gefunden → `assert row is not None` schlägt fehl).

- [ ] **Step 3: `nfs.py` implementieren**

Import-Block ergänzen (nach `from app.services import nfs_service`, Zeile ~19):

```python
from app.services.audit.logger_db import get_audit_logger_db
```

`create_nfs_export` (ab `async def create_nfs_export`) vollständig ersetzen durch:

```python
async def create_nfs_export(
    request: Request, response: Response,
    payload: NfsExportCreate,
    current_admin=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Create an NFS export (admin only)."""
    audit = get_audit_logger_db()
    if db.query(NfsExport).filter(NfsExport.path == payload.path).first():
        audit.log_event(
            event_type="SYSTEM_CONFIG", user=current_admin.username,
            action="nfs_export_created", resource=payload.path,
            success=False, error_message="An export for this path already exists", db=db,
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An export for this path already exists")
    exp = NfsExport(
        path=payload.path, clients=payload.clients, read_only=payload.read_only,
        root_squash=payload.root_squash, enabled=payload.enabled, comment=payload.comment,
    )
    details = {
        "clients": payload.clients, "read_only": payload.read_only,
        "root_squash": payload.root_squash, "enabled": payload.enabled,
    }
    try:
        db.add(exp)
        db.commit()
        db.refresh(exp)
        await nfs_service.regenerate_exports_config()
        await nfs_service.apply_exports()
    except Exception as e:
        audit.log_event(
            event_type="SYSTEM_CONFIG", user=current_admin.username,
            action="nfs_export_created", resource=payload.path,
            success=False, error_message=str(e), db=db,
        )
        raise
    audit.log_event(
        event_type="SYSTEM_CONFIG", user=current_admin.username,
        action="nfs_export_created", resource=exp.path,
        success=True, details=details, db=db,
    )
    return _to_response(exp, _get_local_ip())
```

`update_nfs_export` vollständig ersetzen durch:

```python
async def update_nfs_export(
    request: Request, response: Response,
    export_id: int,
    payload: NfsExportUpdate,
    current_admin=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Update an NFS export (admin only)."""
    audit = get_audit_logger_db()
    exp = db.query(NfsExport).filter(NfsExport.id == export_id).first()
    if not exp:
        audit.log_event(
            event_type="SYSTEM_CONFIG", user=current_admin.username,
            action="nfs_export_updated", resource=str(export_id),
            success=False, error_message="Export not found", db=db,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    if payload.path != exp.path and db.query(NfsExport).filter(NfsExport.path == payload.path).first():
        audit.log_event(
            event_type="SYSTEM_CONFIG", user=current_admin.username,
            action="nfs_export_updated", resource=payload.path,
            success=False, error_message="An export for this path already exists", db=db,
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An export for this path already exists")
    exp.path = payload.path
    exp.clients = payload.clients
    exp.read_only = payload.read_only
    exp.root_squash = payload.root_squash
    exp.enabled = payload.enabled
    exp.comment = payload.comment
    details = {
        "clients": payload.clients, "read_only": payload.read_only,
        "root_squash": payload.root_squash, "enabled": payload.enabled,
    }
    try:
        db.commit()
        db.refresh(exp)
        await nfs_service.regenerate_exports_config()
        await nfs_service.apply_exports()
    except Exception as e:
        audit.log_event(
            event_type="SYSTEM_CONFIG", user=current_admin.username,
            action="nfs_export_updated", resource=payload.path,
            success=False, error_message=str(e), db=db,
        )
        raise
    audit.log_event(
        event_type="SYSTEM_CONFIG", user=current_admin.username,
        action="nfs_export_updated", resource=exp.path,
        success=True, details=details, db=db,
    )
    return _to_response(exp, _get_local_ip())
```

`delete_nfs_export` vollständig ersetzen durch:

```python
async def delete_nfs_export(
    request: Request, response: Response,
    export_id: int,
    current_admin=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Delete an NFS export (admin only)."""
    audit = get_audit_logger_db()
    exp = db.query(NfsExport).filter(NfsExport.id == export_id).first()
    if not exp:
        audit.log_event(
            event_type="SYSTEM_CONFIG", user=current_admin.username,
            action="nfs_export_deleted", resource=str(export_id),
            success=False, error_message="Export not found", db=db,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    path = exp.path
    try:
        db.delete(exp)
        db.commit()
        await nfs_service.regenerate_exports_config()
        await nfs_service.apply_exports()
    except Exception as e:
        audit.log_event(
            event_type="SYSTEM_CONFIG", user=current_admin.username,
            action="nfs_export_deleted", resource=path,
            success=False, error_message=str(e), db=db,
        )
        raise
    audit.log_event(
        event_type="SYSTEM_CONFIG", user=current_admin.username,
        action="nfs_export_deleted", resource=path,
        success=True, details={"export_id": export_id}, db=db,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: Tests laufen lassen → pass**

Run: `cd backend && python -m pytest tests/api/test_nfs_routes.py -v`
Expected: PASS (alle alten + 5 neue `TestNfsAudit`-Tests grün).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/nfs.py backend/tests/api/test_nfs_routes.py
git commit -m "feat(audit): log NFS export mutations via audit logger (#195)"
```

---

## Task 2: Samba SMB-Toggle Audit-Logging

**Files:**
- Modify: `backend/app/api/routes/samba.py`
- Create: `backend/tests/api/test_samba_routes.py`

- [ ] **Step 1: Test-Datei schreiben (failing)**

Neue Datei `backend/tests/api/test_samba_routes.py`:

```python
"""Route tests for /api/samba (admin-only SMB user management)."""
import pytest

from app.core.config import settings
from app.models.audit_log import AuditLog


@pytest.fixture
def audit_enabled():
    """Ensure the global audit logger is enabled (a prior test may have disabled it)."""
    from app.services.audit.logger_db import get_audit_logger_db
    get_audit_logger_db().enable()


@pytest.fixture
def mock_samba(monkeypatch):
    """Stub the system-touching Samba service calls so no real smbpasswd runs."""
    async def _noop(*args, **kwargs):
        return None

    from app.services import samba_service
    for fn in (
        "enable_smb_user", "disable_smb_user", "sync_smb_password",
        "regenerate_shares_config", "reload_samba",
    ):
        monkeypatch.setattr(samba_service, fn, _noop)


def _toggle(client, headers, user_id, enabled, password=None):
    body = {"enabled": enabled}
    if password is not None:
        body["password"] = password
    return client.post(
        f"{settings.api_prefix}/samba/users/{user_id}/toggle", json=body, headers=headers
    )


class TestSambaAuth:
    def test_toggle_forbidden_for_regular_user(self, client, user_headers, regular_user):
        r = _toggle(client, user_headers, regular_user.id, True)
        assert r.status_code == 403


class TestSambaToggleAudit:
    def test_enable_writes_audit(self, client, admin_headers, regular_user, db_session, audit_enabled, mock_samba):
        r = _toggle(client, admin_headers, regular_user.id, True)
        assert r.status_code == 200, r.text
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "smb_access_enabled", AuditLog.success == True)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.event_type == "SYSTEM_CONFIG"
        assert row.resource == regular_user.username
        assert row.user == settings.admin_username

    def test_disable_writes_audit(self, client, admin_headers, regular_user, db_session, audit_enabled, mock_samba):
        r = _toggle(client, admin_headers, regular_user.id, False)
        assert r.status_code == 200, r.text
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "smb_access_disabled", AuditLog.success == True)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.resource == regular_user.username

    def test_toggle_missing_user_writes_failure(self, client, admin_headers, db_session, audit_enabled, mock_samba):
        r = _toggle(client, admin_headers, 999999, True)
        assert r.status_code == 404
        row = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "smb_access_enabled", AuditLog.success == False)  # noqa: E712
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert row is not None
        assert row.resource == "999999"
        assert row.error_message == "User not found"
```

- [ ] **Step 2: Tests laufen lassen → fail**

Run: `cd backend && python -m pytest tests/api/test_samba_routes.py -v`
Expected: `TestSambaToggleAudit` 3× FAIL (kein AuditLog-Row). `TestSambaAuth::test_toggle_forbidden_for_regular_user` darf bereits PASS sein (Auth existiert schon).

- [ ] **Step 3: `samba.py` implementieren**

Import-Block ergänzen (nach `from app.services import samba_service, users as user_service`, Zeile ~22):

```python
from app.services.audit.logger_db import get_audit_logger_db
```

`toggle_smb_user` (ab `async def toggle_smb_user`) vollständig ersetzen durch:

```python
async def toggle_smb_user(
    request: Request, response: Response,
    user_id: int,
    payload: SambaUserToggleRequest,
    current_admin=Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
):
    """Toggle SMB access for a user (admin only).

    When enabling, an optional password can be provided for immediate sync.
    Without a password the user must change their password for SMB to work.
    """
    audit = get_audit_logger_db()
    action = "smb_access_enabled" if payload.enabled else "smb_access_disabled"

    user = user_service.set_smb_enabled(user_id, payload.enabled, db=db)
    if not user:
        audit.log_event(
            event_type="SYSTEM_CONFIG", user=current_admin.username,
            action=action, resource=str(user_id),
            success=False, error_message="User not found", db=db,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    password_synced = False
    try:
        if payload.enabled:
            # Sync password if provided
            if payload.password:
                await samba_service.sync_smb_password(user.username, payload.password)
                password_synced = True
            await samba_service.enable_smb_user(user.username)
        else:
            await samba_service.disable_smb_user(user.username)

        # Regenerate shares config and reload
        await samba_service.regenerate_shares_config()
        await samba_service.reload_samba()
    except Exception as e:
        audit.log_event(
            event_type="SYSTEM_CONFIG", user=current_admin.username,
            action=action, resource=user.username,
            success=False, error_message=str(e), db=db,
        )
        raise

    audit.log_event(
        event_type="SYSTEM_CONFIG", user=current_admin.username,
        action=action, resource=user.username,
        success=True, details={"enabled": payload.enabled, "password_synced": password_synced}, db=db,
    )

    return {
        "user_id": user.id,
        "username": user.username,
        "smb_enabled": user.smb_enabled,
    }
```

**Sicherheitshinweis:** Das Passwort selbst landet **nie** im `details`-Dict — nur der boolean `password_synced`.

- [ ] **Step 4: Tests laufen lassen → pass**

Run: `cd backend && python -m pytest tests/api/test_samba_routes.py -v`
Expected: PASS (4 Tests grün).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/samba.py backend/tests/api/test_samba_routes.py
git commit -m "feat(audit): log SMB user toggle via audit logger (#195)"
```

---

## Task 3: Gesamt-Verifikation

**Files:** (keine Änderung — nur Verifikation)

- [ ] **Step 1: Beide Test-Dateien zusammen laufen lassen**

Run: `cd backend && python -m pytest tests/api/test_nfs_routes.py tests/api/test_samba_routes.py -v`
Expected: PASS (alle Tests grün, inkl. der bereits bestehenden NFS-CRUD/Auth-Tests — bestätigt, dass die Signatur-/Verhaltensänderung nichts gebrochen hat).

- [ ] **Step 2: Audit-Logger-Regression prüfen**

Run: `cd backend && python -m pytest tests/logging -v`
Expected: PASS (keine Regression im Audit-System).

- [ ] **Step 3: Security-Self-Check (manuell)**

Sicherstellen: In `nfs.py` und `samba.py` enthält **kein** `details`-Dict ein Passwort/Secret. Bei Samba nur `{"enabled": ..., "password_synced": <bool>}`. `event_type` ist überall `"SYSTEM_CONFIG"` (admin-only Sichtbarkeit). Kein neuer Endpoint ohne Auth/Rate-Limit (es wurden keine Endpoints hinzugefügt).

- [ ] **Step 4: Kein Commit nötig** (reine Verifikation; Code-Commits erfolgten in Task 1 & 2).

---

## Notes

- **Branch:** `fix/195-audit-nfs-samba` (bereits von `origin/main` erstellt, Spec-Commit `04098baa` liegt vor).
- **PR-Ziel:** `main` (siehe `.claude/rules/production.md` — Feature/Fix-Branches PRen direkt nach `main`).
- **Windows/CRLF:** Repo läuft mit `core.autocrlf=true`; die `git commit`-Warnung „LF will be replaced by CRLF" ist erwartbar und unkritisch.
