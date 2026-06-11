# Presence-Aware Suspend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Block automatic true suspend (auto-escalation, scheduled suspend, OS-driven suspend) while a user is actively present in the web app, via a heartbeat-based presence tracker (issue #214).

**Architecture:** A new `presence_sessions` DB table receives heartbeats from any Uvicorn worker (`POST /api/system/sleep/presence`); the primary worker's sleep loops query it as a third suppressor next to always-awake and core-uptime, and the logind block-sleep inhibitor is held while presence is active. The web client sends heartbeats from a `usePresenceHeartbeat` hook — only while the tab is visible (`active` mode, default) or always while open (`session` mode).

**Tech Stack:** Python/FastAPI + SQLAlchemy + Alembic (backend), React/TypeScript + Vitest (frontend), pytest (tests)

**Spec:** `docs/superpowers/specs/2026-06-11-sleep-presence-suspend-design.md`
**Branch:** `feat/sleep-presence-suspend-214` (from `origin/main` eee18852)
**Alembic head at plan time:** `c7f2a1b4d8e9` (verify with `cd backend && python -m alembic heads` before Task 1!)

**Verified integration facts (do not re-derive):**
- Sleep routes are mounted at `/api/system/sleep/*`; route file `backend/app/api/routes/sleep.py` has no prefix itself.
- `record_http_request()` is called by `SleepAutoWakeMiddleware.dispatch` for **all** requests (`backend/app/middleware/sleep_auto_wake.py:44`) — the heartbeat needs an explicit exclusion there, plus an entry in `_WAKE_WHITELIST_PREFIXES`.
- `update_config` (`backend/app/services/power/sleep.py:1209`) applies partial updates via a generic `setattr` loop — new config fields work automatically once they exist in `SleepConfigUpdate` + the model. Only `get_config()` needs explicit new fields.
- `sudo systemctl suspend` / `sudo rtcwake -m mem` run as root and bypass logind block-inhibitors — holding the inhibitor for presence does NOT break manual suspend (same as today's core-uptime hold).
- `enter_true_suspend` already blocks non-MANUAL triggers when `inhibitor_held` (`sleep.py:996-1003`) — the explicit presence guard added in Task 6 matters for dev mode (no systemd-inhibit) and defense in depth.
- Test fixtures: `client: TestClient`, `admin_user`, `regular_user` + `get_auth_headers` from `tests/conftest.py` (see `backend/tests/api/test_os_auto_suspend_route.py` for the pattern).
- Repo uses CRLF on Windows (`core.autocrlf=true`) — LF→CRLF warnings from git are normal.

---

### Task 1: Data model + Alembic migration

**Files:**
- Modify: `backend/app/models/sleep.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/sleep_presence_2026_06_11.py`
- Test: `backend/tests/services/power/test_presence_service.py` (model smoke test only; service tests come in Task 2)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/services/power/test_presence_service.py`:

```python
"""Tests for the presence tracker (issue #214)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.database import SessionLocal
from app.models.sleep import PresenceSession


@pytest.fixture(autouse=True)
def _clean_presence_rows():
    """Each test starts and ends with an empty presence_sessions table."""
    db = SessionLocal()
    try:
        db.query(PresenceSession).delete()
        db.commit()
    finally:
        db.close()
    yield
    db = SessionLocal()
    try:
        db.query(PresenceSession).delete()
        db.commit()
    finally:
        db.close()


def test_presence_session_model_roundtrip():
    db = SessionLocal()
    try:
        row = PresenceSession(
            client_id="tab-abc-123",
            user_id=1,
            client_type="web",
            last_heartbeat_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        loaded = db.get(PresenceSession, "tab-abc-123")
        assert loaded is not None
        assert loaded.user_id == 1
        assert loaded.client_type == "web"
    finally:
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/power/test_presence_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'PresenceSession'`

- [ ] **Step 3: Add the model + config columns**

In `backend/app/models/sleep.py`, add to the imports (line 7) `ForeignKey`:

```python
from sqlalchemy import Integer, String, Float, Boolean, DateTime, Text, ForeignKey
```

Add three columns to `SleepConfig`, directly below the always-awake block (after line 56):

```python
    # Presence-aware suspend (issue #214)
    presence_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    presence_mode: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # "active" | "session"
    presence_timeout_minutes: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
```

Append a new model at the end of the file:

```python
class PresenceSession(Base):
    """A client (browser tab / mobile app) that recently sent a presence heartbeat.

    Written by any Uvicorn worker on POST /api/system/sleep/presence; read by
    the primary worker's sleep loops (same any-worker-writes / primary-reads
    pattern as power_demands).
    """
    __tablename__ = "presence_sessions"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_type: Mapped[str] = mapped_column(String(20), nullable=False, default="web")
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<PresenceSession({self.client_id}, user={self.user_id}, last={self.last_heartbeat_at})>"
```

In `backend/app/models/__init__.py`: extend the existing `from app.models.sleep import ...` line with `PresenceSession` and add `"PresenceSession"` to `__all__`.

- [ ] **Step 4: Create the Alembic migration**

First verify the head: `cd backend && python -m alembic heads` — expected `c7f2a1b4d8e9 (head)`. If it differs, use the actual head as `down_revision` (multi-head pitfall, PR #123).

Create `backend/alembic/versions/sleep_presence_2026_06_11.py`:

```python
"""add presence_sessions table + presence config to sleep_config (issue #214)

Revision ID: sleep_presence_2026_06_11
Revises: c7f2a1b4d8e9
Create Date: 2026-06-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'sleep_presence_2026_06_11'
down_revision: Union[str, Sequence[str], None] = 'c7f2a1b4d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'presence_sessions',
        sa.Column('client_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('client_type', sa.String(length=20), nullable=False, server_default='web'),
        sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('client_id'),
    )
    op.create_index('ix_presence_sessions_user_id', 'presence_sessions', ['user_id'])
    op.create_index('ix_presence_sessions_last_heartbeat_at', 'presence_sessions', ['last_heartbeat_at'])

    op.add_column('sleep_config', sa.Column('presence_enabled', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('sleep_config', sa.Column('presence_mode', sa.String(length=20), nullable=False, server_default='active'))
    op.add_column('sleep_config', sa.Column('presence_timeout_minutes', sa.Integer(), nullable=False, server_default='3'))


def downgrade() -> None:
    op.drop_column('sleep_config', 'presence_timeout_minutes')
    op.drop_column('sleep_config', 'presence_mode')
    op.drop_column('sleep_config', 'presence_enabled')
    op.drop_index('ix_presence_sessions_last_heartbeat_at', table_name='presence_sessions')
    op.drop_index('ix_presence_sessions_user_id', table_name='presence_sessions')
    op.drop_table('presence_sessions')
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/services/power/test_presence_service.py -v`
Expected: PASS (test DB uses `init_db()` create_all, so the new model is picked up without running the migration)

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/sleep.py backend/app/models/__init__.py backend/alembic/versions/sleep_presence_2026_06_11.py backend/tests/services/power/test_presence_service.py
git commit -m "feat(sleep): presence_sessions model + sleep_config presence columns (#214)"
```

---

### Task 2: Presence tracker service

**Files:**
- Create: `backend/app/services/power/presence.py`
- Test: `backend/tests/services/power/test_presence_service.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/services/power/test_presence_service.py`:

```python
from app.services.power import presence


def _insert_session(client_id: str, age_minutes: float, user_id: int = 1) -> None:
    db = SessionLocal()
    try:
        db.add(PresenceSession(
            client_id=client_id,
            user_id=user_id,
            client_type="web",
            last_heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=age_minutes),
        ))
        db.commit()
    finally:
        db.close()


class TestRecordHeartbeat:
    def test_creates_row(self):
        presence.record_heartbeat(user_id=1, client_id="tab-1", client_type="web")
        db = SessionLocal()
        try:
            row = db.get(PresenceSession, "tab-1")
            assert row is not None
            assert row.user_id == 1
        finally:
            db.close()

    def test_upserts_existing_row(self):
        presence.record_heartbeat(user_id=1, client_id="tab-1", client_type="web")
        presence.record_heartbeat(user_id=2, client_id="tab-1", client_type="mobile")
        db = SessionLocal()
        try:
            rows = db.query(PresenceSession).all()
            assert len(rows) == 1
            assert rows[0].user_id == 2
            assert rows[0].client_type == "mobile"
        finally:
            db.close()


class TestIsAnyonePresent:
    def test_false_when_no_rows(self):
        assert presence.is_anyone_present(timeout_minutes=3) is False

    def test_true_for_fresh_heartbeat(self):
        _insert_session("tab-fresh", age_minutes=1)
        assert presence.is_anyone_present(timeout_minutes=3) is True

    def test_false_for_expired_heartbeat(self):
        _insert_session("tab-old", age_minutes=10)
        assert presence.is_anyone_present(timeout_minutes=3) is False

    def test_any_single_fresh_session_suffices(self):
        _insert_session("tab-old", age_minutes=10)
        _insert_session("tab-fresh", age_minutes=1, user_id=2)
        assert presence.is_anyone_present(timeout_minutes=3) is True


class TestGetPresentSessions:
    def test_returns_only_fresh_sessions(self):
        _insert_session("tab-old", age_minutes=10)
        _insert_session("tab-fresh", age_minutes=1)
        sessions = presence.get_present_sessions(timeout_minutes=3)
        assert [s.client_id for s in sessions] == ["tab-fresh"]


class TestCleanupExpired:
    def test_deletes_only_stale_rows(self):
        _insert_session("tab-ancient", age_minutes=60 * 25)  # > 24h
        _insert_session("tab-recent", age_minutes=5)
        deleted = presence.cleanup_expired()
        assert deleted == 1
        db = SessionLocal()
        try:
            remaining = [r.client_id for r in db.query(PresenceSession).all()]
        finally:
            db.close()
        assert remaining == ["tab-recent"]


class TestGetPresenceSettings:
    def test_returns_config_values(self):
        from app.models.sleep import SleepConfig
        db = SessionLocal()
        try:
            cfg = db.get(SleepConfig, 1)
            if cfg is None:
                cfg = SleepConfig(id=1)
                db.add(cfg)
            cfg.presence_enabled = True
            cfg.presence_mode = "session"
            cfg.presence_timeout_minutes = 7
            db.commit()
        finally:
            db.close()
        enabled, mode, timeout = presence.get_presence_settings()
        assert enabled is True
        assert mode == "session"
        assert timeout == 7
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/power/test_presence_service.py -v`
Expected: FAIL — `ImportError: cannot import name 'presence'` (module does not exist)

- [ ] **Step 3: Implement the tracker**

Create `backend/app/services/power/presence.py`:

```python
"""
Presence tracking for sleep mode (issue #214).

Heartbeats arrive on any Uvicorn worker via POST /api/system/sleep/presence
and are upserted into the presence_sessions table; the primary worker's
sleep loops read it (same any-worker-writes / primary-reads pattern as
power_demands). Each function opens its own short-lived session.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.models.sleep import PresenceSession, SleepConfig

logger = logging.getLogger(__name__)

# Served to clients in the heartbeat response; clients self-configure.
HEARTBEAT_INTERVAL_SECONDS = 45

# Rows older than this are garbage-collected by cleanup_expired().
_CLEANUP_MAX_AGE = timedelta(hours=24)


def record_heartbeat(user_id: int, client_id: str, client_type: str) -> None:
    """Upsert the heartbeat row for *client_id*."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        row = db.get(PresenceSession, client_id)
        if row is None:
            row = PresenceSession(
                client_id=client_id,
                user_id=user_id,
                client_type=client_type,
                last_heartbeat_at=now,
            )
            db.add(row)
        else:
            row.user_id = user_id
            row.client_type = client_type
            row.last_heartbeat_at = now
        db.commit()
    finally:
        db.close()


def is_anyone_present(timeout_minutes: int) -> bool:
    """True if any session sent a heartbeat within the timeout window."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
    db = SessionLocal()
    try:
        row = db.execute(
            select(PresenceSession.client_id)
            .where(PresenceSession.last_heartbeat_at > cutoff)
            .limit(1)
        ).first()
        return row is not None
    finally:
        db.close()


def get_present_sessions(timeout_minutes: int) -> list[PresenceSession]:
    """All sessions with a heartbeat within the timeout window (for status)."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
    db = SessionLocal()
    try:
        rows = db.execute(
            select(PresenceSession).where(PresenceSession.last_heartbeat_at > cutoff)
        ).scalars().all()
        db.expunge_all()
        return list(rows)
    finally:
        db.close()


def cleanup_expired() -> int:
    """Delete sessions whose last heartbeat is older than 24h. Returns count."""
    cutoff = datetime.now(timezone.utc) - _CLEANUP_MAX_AGE
    db = SessionLocal()
    try:
        result = db.execute(
            delete(PresenceSession).where(PresenceSession.last_heartbeat_at < cutoff)
        )
        db.commit()
        return int(result.rowcount or 0)
    finally:
        db.close()


def get_presence_settings() -> tuple[bool, str, int]:
    """Return (presence_enabled, presence_mode, presence_timeout_minutes).

    Falls back to model defaults when no config row exists yet.
    """
    db = SessionLocal()
    try:
        cfg = db.get(SleepConfig, 1)
        if cfg is None:
            return True, "active", 3
        return (
            bool(cfg.presence_enabled),
            str(cfg.presence_mode),
            int(cfg.presence_timeout_minutes),
        )
    finally:
        db.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/power/test_presence_service.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/presence.py backend/tests/services/power/test_presence_service.py
git commit -m "feat(sleep): presence tracker service (#214)"
```

---

### Task 3: Schemas + rate limit key

**Files:**
- Modify: `backend/app/schemas/sleep.py`
- Modify: `backend/app/core/rate_limiter.py:146` (RATE_LIMITS dict)

- [ ] **Step 1: Add schemas**

In `backend/app/schemas/sleep.py`, add after the `ScheduleMode` enum (line 51):

```python
class PresenceMode(str, Enum):
    """How clients signal presence (issue #214)."""
    ACTIVE = "active"    # heartbeats only while tab/app is visible
    SESSION = "session"  # heartbeats while tab/app is open, regardless of focus
```

Add after `AlwaysAwakeStatus` (line 86):

```python
class PresenceStatus(BaseModel):
    """Snapshot of user-presence state (issue #214)."""
    enabled: bool = Field(default=False, description="Presence feature toggle")
    mode: PresenceMode = Field(default=PresenceMode.ACTIVE)
    anyone_present: bool = Field(default=False, description="Any session with a fresh heartbeat")
    active_session_count: int = Field(default=0)
    suppressing_suspend: bool = Field(default=False, description="True when presence currently blocks true suspend")
```

Add to `SleepStatusResponse` (after the `always_awake` field, line 125):

```python
    presence: PresenceStatus = Field(default_factory=PresenceStatus)
```

Add to `SleepConfigResponse` (after the always-awake fields, line 190):

```python
    # Presence-aware suspend (issue #214)
    presence_enabled: bool = Field(default=True, description="Block auto-suspend while a user is present")
    presence_mode: PresenceMode = Field(default=PresenceMode.ACTIVE)
    presence_timeout_minutes: int = Field(default=3, description="Minutes without heartbeat until presence expires")
```

Add to `SleepConfigUpdate` (after `always_awake_until`, line 216):

```python
    presence_enabled: Optional[bool] = None
    presence_mode: Optional[PresenceMode] = None
    presence_timeout_minutes: Optional[int] = Field(default=None, ge=1, le=60)
```

Add at the end of the file:

```python
# ---------------------------------------------------------------------------
# Presence heartbeat (issue #214)
# ---------------------------------------------------------------------------

class PresenceHeartbeatRequest(BaseModel):
    """Heartbeat sent by web/mobile/desktop clients while present."""
    client_id: str = Field(
        ..., min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$",
        description="Client-generated stable ID per tab/device (e.g. UUID)",
    )
    client_type: Literal["web", "mobile", "desktop"] = Field(default="web")


class PresenceHeartbeatResponse(BaseModel):
    """Heartbeat ack; clients self-configure from mode + interval."""
    present: bool = Field(default=True)
    enabled: bool = Field(..., description="Presence feature toggle (admin config)")
    mode: PresenceMode = Field(...)
    heartbeat_interval_seconds: int = Field(default=45)
    timeout_minutes: int = Field(...)
```

- [ ] **Step 2: Add the rate limit key**

In `backend/app/core/rate_limiter.py`, add to the `RATE_LIMITS` dict (after `"smart_device_import_history"`, line 146):

```python
    # Presence heartbeat — 1 request / 45s per client, with headroom for
    # visibility-change immediate beats and multiple tabs per user
    "presence_heartbeat": "10/minute",
```

- [ ] **Step 3: Smoke-check imports**

Run: `cd backend && python -c "from app.schemas.sleep import PresenceMode, PresenceStatus, PresenceHeartbeatRequest, PresenceHeartbeatResponse; from app.core.rate_limiter import get_limit; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/sleep.py backend/app/core/rate_limiter.py
git commit -m "feat(sleep): presence schemas + heartbeat rate-limit key (#214)"
```

---

### Task 4: Heartbeat endpoint

**Files:**
- Modify: `backend/app/api/routes/sleep.py`
- Test: `backend/tests/api/test_presence_route.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/api/test_presence_route.py`:

```python
"""Integration tests for POST /api/system/sleep/presence (issue #214)."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import get_auth_headers
from app.core.config import settings

PRESENCE_URL = f"{settings.api_prefix}/system/sleep/presence"


@pytest.fixture
def user_headers(client: TestClient, regular_user) -> dict[str, str]:
    return get_auth_headers(client, "testuser", "Testpass123!")


class TestPresenceHeartbeat:
    def test_requires_auth(self, client: TestClient):
        r = client.post(PRESENCE_URL, json={"client_id": "tab-12345678", "client_type": "web"})
        assert r.status_code in (401, 403)

    def test_regular_user_can_heartbeat(self, client: TestClient, user_headers):
        with patch("app.api.routes.sleep.presence_service.record_heartbeat") as mock_record, \
             patch("app.api.routes.sleep.presence_service.get_presence_settings",
                   return_value=(True, "active", 3)):
            r = client.post(
                PRESENCE_URL, headers=user_headers,
                json={"client_id": "tab-12345678", "client_type": "web"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["present"] is True
        assert body["enabled"] is True
        assert body["mode"] == "active"
        assert body["heartbeat_interval_seconds"] == 45
        assert body["timeout_minutes"] == 3
        mock_record.assert_called_once()
        _, kwargs = mock_record.call_args
        assert kwargs["client_id"] == "tab-12345678"
        assert kwargs["client_type"] == "web"

    def test_rejects_short_client_id(self, client: TestClient, user_headers):
        r = client.post(PRESENCE_URL, headers=user_headers,
                        json={"client_id": "x", "client_type": "web"})
        assert r.status_code == 422

    def test_rejects_invalid_chars_in_client_id(self, client: TestClient, user_headers):
        r = client.post(PRESENCE_URL, headers=user_headers,
                        json={"client_id": "tab/../../etc", "client_type": "web"})
        assert r.status_code == 422

    def test_rejects_unknown_client_type(self, client: TestClient, user_headers):
        r = client.post(PRESENCE_URL, headers=user_headers,
                        json={"client_id": "tab-12345678", "client_type": "toaster"})
        assert r.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/api/test_presence_route.py -v`
Expected: FAIL — 404 (route does not exist) / AttributeError on `presence_service`

- [ ] **Step 3: Add the route**

In `backend/app/api/routes/sleep.py`:

Extend the schema import block (line 22-35) with:

```python
    PresenceHeartbeatRequest,
    PresenceHeartbeatResponse,
```

Add below the existing service imports (line 39):

```python
from app.services.power import presence as presence_service
```

Add the route (place it after the `/wol` route, before the config routes):

```python
@router.post("/presence", response_model=PresenceHeartbeatResponse)
@user_limiter.limit(get_limit("presence_heartbeat"))
async def presence_heartbeat(
    request: Request, response: Response,
    body: PresenceHeartbeatRequest,
    current_user: User = Depends(get_current_user),
) -> PresenceHeartbeatResponse:
    """Record a user-presence heartbeat (issue #214).

    Any authenticated user. Excluded from auto-wake and from the HTTP-RPM
    idle metric (see SleepAutoWakeMiddleware) so presence never blocks soft
    sleep — it only blocks automatic true suspend.
    """
    presence_service.record_heartbeat(
        user_id=current_user.id,
        client_id=body.client_id,
        client_type=body.client_type,
    )
    enabled, mode, timeout = presence_service.get_presence_settings()
    return PresenceHeartbeatResponse(
        present=True,
        enabled=enabled,
        mode=mode,
        heartbeat_interval_seconds=presence_service.HEARTBEAT_INTERVAL_SECONDS,
        timeout_minutes=timeout,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/api/test_presence_route.py -v`
Expected: PASS (5)

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/sleep.py backend/tests/api/test_presence_route.py
git commit -m "feat(sleep): POST /api/system/sleep/presence heartbeat endpoint (#214)"
```

---

### Task 5: Middleware exclusions (no auto-wake, no HTTP-RPM count)

**Files:**
- Modify: `backend/app/middleware/sleep_auto_wake.py`
- Test: `backend/tests/test_sleep_auto_wake_presence.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_sleep_auto_wake_presence.py`:

```python
"""SleepAutoWakeMiddleware: presence heartbeats must not wake nor count (issue #214)."""
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.sleep_auto_wake import SleepAutoWakeMiddleware
from app.schemas.sleep import SleepState


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SleepAutoWakeMiddleware)

    @app.post("/api/system/sleep/presence")
    async def presence_stub():
        return {"ok": True}

    @app.post("/api/files/upload")
    async def other_stub():
        return {"ok": True}

    return app


def _sleeping_manager() -> MagicMock:
    manager = MagicMock()
    manager._current_state = SleepState.SOFT_SLEEP
    manager.exit_soft_sleep = AsyncMock()
    return manager


def test_presence_heartbeat_does_not_count_toward_http_rpm():
    app = _make_app()
    with patch("app.services.power.sleep.record_http_request") as mock_record, \
         patch("app.services.power.sleep.get_sleep_manager", return_value=None):
        TestClient(app).post("/api/system/sleep/presence")
    mock_record.assert_not_called()


def test_other_requests_still_count_toward_http_rpm():
    app = _make_app()
    with patch("app.services.power.sleep.record_http_request") as mock_record, \
         patch("app.services.power.sleep.get_sleep_manager", return_value=None):
        TestClient(app).post("/api/files/upload")
    mock_record.assert_called_once()


def test_presence_heartbeat_does_not_auto_wake_from_soft_sleep():
    app = _make_app()
    manager = _sleeping_manager()
    with patch("app.services.power.sleep.record_http_request"), \
         patch("app.services.power.sleep.get_sleep_manager", return_value=manager):
        TestClient(app).post("/api/system/sleep/presence")
    manager.exit_soft_sleep.assert_not_called()


def test_other_request_still_auto_wakes_from_soft_sleep():
    app = _make_app()
    manager = _sleeping_manager()
    with patch("app.services.power.sleep.record_http_request"), \
         patch("app.services.power.sleep.get_sleep_manager", return_value=manager):
        TestClient(app).post("/api/files/upload")
    manager.exit_soft_sleep.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_sleep_auto_wake_presence.py -v`
Expected: `test_presence_heartbeat_does_not_count_toward_http_rpm` and `test_presence_heartbeat_does_not_auto_wake_from_soft_sleep` FAIL; the two "other request" tests PASS

- [ ] **Step 3: Modify the middleware**

In `backend/app/middleware/sleep_auto_wake.py`:

Add `"/api/system/sleep/presence",` to `_WAKE_WHITELIST_PREFIXES` (after the `/api/system/sleep/capabilities` entry, line 22).

Add below the tuple:

```python
# The presence heartbeat must not count toward the HTTP-RPM idle metric —
# otherwise an open tab would indirectly block soft sleep, which stays
# allowed by design (issue #214: presence only blocks true suspend).
_RPM_EXCLUDED_PATHS = ("/api/system/sleep/presence",)
```

Change the start of `dispatch` (lines 41-47) to:

```python
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Count the request for idle detection (except excluded paths)
        if path not in _RPM_EXCLUDED_PATHS:
            try:
                from app.services.power.sleep import record_http_request
                record_http_request()
            except Exception:
                pass

        # Check if we need to auto-wake
        method = request.method
```

(and delete the now-duplicate `path = request.url.path` / `method = request.method` lines below.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_sleep_auto_wake_presence.py -v`
Expected: PASS (4)

- [ ] **Step 5: Commit**

```bash
git add backend/app/middleware/sleep_auto_wake.py backend/tests/test_sleep_auto_wake_presence.py
git commit -m "feat(sleep): exclude presence heartbeat from auto-wake + HTTP-RPM (#214)"
```

---

### Task 6: Sleep manager integration (guards, inhibitor, status, cleanup)

**Files:**
- Modify: `backend/app/services/power/sleep.py`
- Test: `backend/tests/services/test_sleep_presence_integration.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/test_sleep_presence_integration.py`:

```python
"""Integration tests: SleepManagerService respects user presence (issue #214)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.sleep import SleepConfig
from app.services.power.sleep import SleepManagerService
from app.services.power.sleep_backend_dev import DevSleepBackend
from app.schemas.sleep import SleepState, SleepTrigger


def _build_service():
    SleepManagerService._instance = None  # reset singleton
    return SleepManagerService(DevSleepBackend())


def _config(
    presence_enabled: bool = True,
    presence_timeout_minutes: int = 3,
    auto_escalation_enabled: bool = True,
    schedule_enabled: bool = False,
    schedule_mode: str = "suspend",
):
    return SleepConfig(
        id=1,
        auto_idle_enabled=False,
        idle_timeout_minutes=15,
        idle_cpu_threshold=99.0,
        idle_disk_io_threshold=99.0,
        idle_http_threshold=999.0,
        auto_escalation_enabled=auto_escalation_enabled,
        escalation_after_minutes=1,
        schedule_enabled=schedule_enabled,
        schedule_sleep_time="23:00",
        schedule_wake_time="06:00",
        schedule_mode=schedule_mode,
        wol_mac_address=None,
        wol_broadcast_address=None,
        pause_monitoring=False,
        pause_disk_io=False,
        reduced_telemetry_interval=30.0,
        disk_spindown_enabled=False,
        core_uptime_enabled=False,
        always_awake_enabled=False,
        always_awake_until=None,
        presence_enabled=presence_enabled,
        presence_mode="active",
        presence_timeout_minutes=presence_timeout_minutes,
    )


class TestIsUserPresent:
    def test_false_when_config_none(self):
        svc = _build_service()
        assert svc._is_user_present(None) is False

    def test_false_when_disabled_even_if_sessions_exist(self):
        svc = _build_service()
        with patch("app.services.power.presence.is_anyone_present", return_value=True):
            assert svc._is_user_present(_config(presence_enabled=False)) is False

    def test_true_when_enabled_and_session_fresh(self):
        svc = _build_service()
        with patch("app.services.power.presence.is_anyone_present", return_value=True) as m:
            assert svc._is_user_present(_config()) is True
        m.assert_called_once_with(3)

    def test_false_on_db_error(self):
        """Fail toward energy saving: a DB outage must not block suspend forever."""
        svc = _build_service()
        with patch("app.services.power.presence.is_anyone_present", side_effect=RuntimeError("db down")):
            assert svc._is_user_present(_config()) is False


@pytest.mark.asyncio
async def test_escalation_skipped_while_user_present():
    svc = _build_service()
    cfg = _config(auto_escalation_enabled=True)
    svc._current_state = SleepState.SOFT_SLEEP
    svc._is_running = True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "enter_true_suspend", new=AsyncMock()) as mock_suspend, \
         patch("app.services.power.presence.is_anyone_present", return_value=True), \
         patch("app.services.power.sleep.asyncio.sleep", new=AsyncMock()):
        await svc._escalation_monitor()

    mock_suspend.assert_not_called()


@pytest.mark.asyncio
async def test_escalation_proceeds_when_nobody_present():
    svc = _build_service()
    cfg = _config(auto_escalation_enabled=True)
    svc._current_state = SleepState.SOFT_SLEEP
    svc._is_running = True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "enter_true_suspend", new=AsyncMock()) as mock_suspend, \
         patch("app.services.power.presence.is_anyone_present", return_value=False), \
         patch("app.services.power.sleep.asyncio.sleep", new=AsyncMock()):
        await svc._escalation_monitor()

    mock_suspend.assert_called_once()


@pytest.mark.asyncio
async def test_schedule_suspend_suppressed_while_user_present():
    svc = _build_service()
    cfg = _config(schedule_enabled=True, schedule_mode="suspend")
    svc._current_state = SleepState.AWAKE
    svc._is_running = True

    call_count = 0

    async def fake_sleep(*_a, **_k):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            svc._is_running = False

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_reconcile_sleep_inhibitor"), \
         patch.object(svc, "_time_matches", return_value=True), \
         patch.object(svc, "enter_true_suspend", new=AsyncMock()) as mock_suspend, \
         patch("app.services.power.presence.is_anyone_present", return_value=True), \
         patch("app.services.power.sleep.asyncio.sleep", side_effect=fake_sleep):
        await svc._schedule_check_loop()

    mock_suspend.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_soft_sleep_proceeds_while_user_present():
    """Presence blocks true suspend ONLY — scheduled soft sleep must still fire."""
    svc = _build_service()
    cfg = _config(schedule_enabled=True, schedule_mode="soft")
    svc._current_state = SleepState.AWAKE
    svc._is_running = True

    call_count = 0

    async def fake_sleep(*_a, **_k):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            svc._is_running = False

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_reconcile_sleep_inhibitor"), \
         patch.object(svc, "_time_matches", return_value=True), \
         patch.object(svc, "enter_soft_sleep", new=AsyncMock()) as mock_soft, \
         patch("app.services.power.presence.is_anyone_present", return_value=True), \
         patch("app.services.power.sleep.asyncio.sleep", side_effect=fake_sleep):
        await svc._schedule_check_loop()

    mock_soft.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", [
    SleepTrigger.SCHEDULE,
    SleepTrigger.AUTO_IDLE,
    SleepTrigger.AUTO_ESCALATION,
])
async def test_enter_true_suspend_blocks_non_manual_while_present(trigger):
    svc = _build_service()
    cfg = _config()
    svc._current_state = SleepState.SOFT_SLEEP

    suspend_called: list = []

    async def fake_suspend_system(wake_at=None):
        suspend_called.append(wake_at)
        return True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc._backend, "suspend_system", side_effect=fake_suspend_system), \
         patch("app.services.power.presence.is_anyone_present", return_value=True), \
         patch("app.services.power.sleep.SessionLocal"):
        ok = await svc.enter_true_suspend("auto", trigger)

    assert ok is False
    assert suspend_called == []


@pytest.mark.asyncio
async def test_enter_true_suspend_manual_proceeds_while_present():
    svc = _build_service()
    cfg = _config()
    svc._current_state = SleepState.SOFT_SLEEP

    suspend_called: list = []

    async def fake_suspend_system(wake_at=None):
        suspend_called.append(wake_at)
        return True

    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc._backend, "suspend_system", side_effect=fake_suspend_system), \
         patch("app.services.power.presence.is_anyone_present", return_value=True), \
         patch("app.services.power.sleep.SessionLocal"), \
         patch("app.services.notifications.events.emit_system_suspend", new=AsyncMock()), \
         patch("app.services.notifications.events.emit_system_resume", new=AsyncMock()):
        ok = await svc.enter_true_suspend("manual by admin", SleepTrigger.MANUAL)

    assert ok is True
    assert len(suspend_called) == 1


class TestInhibitorReconcile:
    def test_presence_holds_inhibitor(self):
        svc = _build_service()
        cfg = _config()
        with patch("app.services.power.presence.is_anyone_present", return_value=True), \
             patch.object(svc._core_uptime_inhibitor, "is_held", return_value=False), \
             patch.object(svc._core_uptime_inhibitor, "acquire") as mock_acquire:
            svc._reconcile_sleep_inhibitor(cfg, in_core=False)
        mock_acquire.assert_called_once_with("user_present_active")

    def test_presence_expiry_releases_inhibitor(self):
        svc = _build_service()
        cfg = _config()
        with patch("app.services.power.presence.is_anyone_present", return_value=False), \
             patch.object(svc._core_uptime_inhibitor, "is_held", return_value=True), \
             patch.object(svc._core_uptime_inhibitor, "release") as mock_release:
            svc._reconcile_sleep_inhibitor(cfg, in_core=False)
        mock_release.assert_called_once()

    def test_existing_core_uptime_reason_unchanged(self):
        """Reason strings for pre-existing conditions must stay stable."""
        svc = _build_service()
        cfg = _config(presence_enabled=False)
        with patch.object(svc._core_uptime_inhibitor, "is_held", return_value=False), \
             patch.object(svc._core_uptime_inhibitor, "acquire") as mock_acquire:
            svc._reconcile_sleep_inhibitor(cfg, in_core=True)
        mock_acquire.assert_called_once_with("core_uptime_active")


def test_get_status_includes_presence_block():
    svc = _build_service()
    cfg = _config()
    fake_session = MagicMock(client_id="tab-1")
    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch("app.services.power.presence.get_present_sessions", return_value=[fake_session]):
        status = svc.get_status()
    assert status.presence.enabled is True
    assert status.presence.anyone_present is True
    assert status.presence.active_session_count == 1
    assert status.presence.suppressing_suspend is True


def test_get_status_presence_disabled():
    svc = _build_service()
    cfg = _config(presence_enabled=False)
    with patch.object(svc, "_load_config", return_value=cfg), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])):
        status = svc.get_status()
    assert status.presence.enabled is False
    assert status.presence.suppressing_suspend is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_sleep_presence_integration.py -v`
Expected: FAIL — `AttributeError: 'SleepManagerService' object has no attribute '_is_user_present'` and assertion failures

- [ ] **Step 3: Implement the integration in `backend/app/services/power/sleep.py`**

**(a)** Add the helper method, directly after `_is_system_idle` (line 450):

```python
    def _is_user_present(self, config) -> bool:
        """True if presence is enabled and any session has a fresh heartbeat.

        Issue #214: presence is the third suspend suppressor next to
        always-awake and core-uptime. On DB errors this fails toward
        energy saving (returns False) — a DB outage must not block
        suspend forever; the inhibitor re-converges on the next tick.
        """
        if not config or not getattr(config, "presence_enabled", False):
            return False
        try:
            from app.services.power import presence
            return presence.is_anyone_present(int(config.presence_timeout_minutes))
        except Exception as e:
            logger.warning("Presence check failed (failing open toward suspend): %s", e)
            return False
```

**(b)** `_escalation_monitor` (line 599): after the core-uptime skip block (line 623), add:

```python
            # Skip escalation while a user is present (issue #214)
            if self._is_user_present(config):
                logger.info("Auto-escalation skipped: user presence active")
                return
```

**(c)** `_schedule_check_loop` (line 510): two changes.

Presence housekeeping — directly after `config = self._load_config()` (line 519):

```python
                # Presence housekeeping: GC sessions stale for > 24h (issue #214)
                try:
                    from app.services.power import presence as presence_service
                    presence_service.cleanup_expired()
                except Exception:
                    pass
```

Suspend-path guard — inside `if mode == "suspend":` (line 578), before computing `wake_dt`:

```python
                        if mode == "suspend":
                            if self._is_user_present(config):
                                logger.info(
                                    "Schedule suspend trigger suppressed by user presence",
                                )
                                continue
                            wake_dt = self._next_occurrence(config.schedule_wake_time)
```

(The `soft` branch stays untouched — presence never blocks soft sleep.)

**(d)** `enter_true_suspend` (line 941): after the existing core-uptime/inhibitor guard (the `return False` ending at line 1003), add:

```python
        # Presence guard (issue #214): never auto-suspend while a user is
        # actively present in the web/mobile app. Manual suspend always wins.
        if trigger != SleepTrigger.MANUAL and self._is_user_present(config_check):
            logger.info(
                "enter_true_suspend blocked: user presence active (trigger=%s, reason=%s)",
                trigger.value, reason,
            )
            return False
```

**(e)** `_reconcile_sleep_inhibitor` (line 327): replace the body so presence is a third hold condition while keeping the existing reason strings stable:

```python
    def _reconcile_sleep_inhibitor(self, config, in_core: bool) -> None:
        """Converge the logind block-sleep inhibitor to the desired state.

        The inhibitor is held while ANY of these is in effect: an active
        core-uptime window, an active Always-Awake override, or an active
        user presence (issue #214). All three block third-party suspend
        (logind idle, desktop daemons, manual systemctl suspend) at the
        logind layer. Soft sleep is unaffected — the block lock only
        prevents kernel suspend. Releasing/acquiring is idempotent.

        Args:
            config: SleepConfig row (or None — treated as nothing active).
            in_core: Whether we are currently inside a core-uptime window.
                     Caller passes the already-computed value to avoid
                     re-querying the DB on every tick.
        """
        core_active = bool(in_core)
        aa_active = self._is_always_awake(config)
        presence_active = self._is_user_present(config)
        should_hold = core_active or aa_active or presence_active

        if should_hold and not self._core_uptime_inhibitor.is_held():
            parts = []
            if core_active:
                parts.append("core_uptime")
            if aa_active:
                parts.append("always_awake")
            if presence_active:
                parts.append("user_present")
            reason = "_and_".join(parts) + "_active"
            self._core_uptime_inhibitor.acquire(reason)
        elif not should_hold and self._core_uptime_inhibitor.is_held():
            self._core_uptime_inhibitor.release()
```

(Single-condition reasons stay `core_uptime_active` / `always_awake_active`; the existing two-condition combo stays `core_uptime_and_always_awake_active`.)

**(f)** `get_status` (line 1130): after the always-awake block (line 1163), add:

```python
        # Presence status (issue #214)
        from app.schemas.sleep import PresenceStatus
        presence_status = PresenceStatus()
        if config is not None:
            presence_status.enabled = bool(config.presence_enabled)
            presence_status.mode = config.presence_mode
            if config.presence_enabled:
                try:
                    from app.services.power import presence as presence_service
                    sessions = presence_service.get_present_sessions(
                        int(config.presence_timeout_minutes)
                    )
                    presence_status.active_session_count = len(sessions)
                    presence_status.anyone_present = len(sessions) > 0
                    presence_status.suppressing_suspend = presence_status.anyone_present
                except Exception as e:
                    logger.warning("Presence status read failed: %s", e)
```

and add `presence=presence_status,` to the `SleepStatusResponse(...)` constructor (after `always_awake=always_awake_status,`, line 1177).

**(g)** `get_config` (line 1180): add to the `SleepConfigResponse(...)` constructor:

```python
            presence_enabled=config.presence_enabled,
            presence_mode=config.presence_mode,
            presence_timeout_minutes=config.presence_timeout_minutes,
```

(`update_config` needs no change — the generic `setattr` loop handles the new fields.)

- [ ] **Step 4: Run the new tests**

Run: `cd backend && python -m pytest tests/services/test_sleep_presence_integration.py -v`
Expected: PASS (all)

- [ ] **Step 5: Run the existing sleep suites to verify no regression**

Run: `cd backend && python -m pytest tests/test_sleep.py tests/services/test_sleep_core_uptime_integration.py tests/services/power/test_presence_service.py tests/api/test_presence_route.py -v`
Expected: all PASS. (Note: `_reconcile_sleep_inhibitor` now also queries presence — if an existing core-uptime test fails on an unexpected DB call, patch `app.services.power.presence.is_anyone_present` to `False` in that test.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/power/sleep.py backend/tests/services/test_sleep_presence_integration.py
git commit -m "feat(sleep): presence guards for escalation/schedule/suspend + inhibitor + status (#214)"
```

---

### Task 7: Frontend API client

**Files:**
- Modify: `client/src/api/sleep.ts`

- [ ] **Step 1: Add types + function**

In `client/src/api/sleep.ts`:

Add after `AlwaysAwakeStatus` (line 54):

```typescript
export type PresenceMode = 'active' | 'session';

export interface PresenceStatus {
  enabled: boolean;
  mode: PresenceMode;
  anyone_present: boolean;
  active_session_count: number;
  suppressing_suspend: boolean;
}

export interface PresenceHeartbeatResponse {
  present: boolean;
  enabled: boolean;
  mode: PresenceMode;
  heartbeat_interval_seconds: number;
  timeout_minutes: number;
}
```

Add to `SleepStatusResponse` (line 75):

```typescript
  presence?: PresenceStatus;
```

Add to `SleepConfigResponse` (line 90):

```typescript
  presence_enabled: boolean;
  presence_mode: PresenceMode;
  presence_timeout_minutes: number;
```

Add to `SleepConfigUpdate` (line 113):

```typescript
  presence_enabled?: boolean;
  presence_mode?: PresenceMode;
  presence_timeout_minutes?: number;
```

Add the API function (after `sendWol`):

```typescript
export async function sendPresenceHeartbeat(body: {
  client_id: string;
  client_type: 'web' | 'mobile' | 'desktop';
}): Promise<PresenceHeartbeatResponse> {
  const response = await apiClient.post<PresenceHeartbeatResponse>(
    '/api/system/sleep/presence',
    body,
  );
  return response.data;
}
```

- [ ] **Step 2: Type-check**

Run: `cd client && npx tsc --noEmit`
Expected: no new errors

- [ ] **Step 3: Commit**

```bash
git add client/src/api/sleep.ts
git commit -m "feat(client): presence types + heartbeat API function (#214)"
```

---

### Task 8: `usePresenceHeartbeat` hook + Layout mount

**Files:**
- Create: `client/src/hooks/usePresenceHeartbeat.ts`
- Modify: `client/src/components/Layout.tsx` (mount near the `useAuth()` call, line 121)
- Test: `client/src/__tests__/hooks/usePresenceHeartbeat.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `client/src/__tests__/hooks/usePresenceHeartbeat.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePresenceHeartbeat } from '../../hooks/usePresenceHeartbeat';
import { sendPresenceHeartbeat } from '../../api/sleep';

vi.mock('../../api/sleep', () => ({
  sendPresenceHeartbeat: vi.fn().mockResolvedValue({
    present: true,
    enabled: true,
    mode: 'active',
    heartbeat_interval_seconds: 45,
    timeout_minutes: 3,
  }),
}));

const mockedSend = vi.mocked(sendPresenceHeartbeat);

function setVisibility(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', {
    value: state,
    configurable: true,
  });
}

async function flushAsync() {
  // let pending promise callbacks run
  await act(async () => { await Promise.resolve(); });
}

describe('usePresenceHeartbeat', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    sessionStorage.clear();
    setVisibility('visible');
    mockedSend.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('sends an immediate heartbeat on mount when visible', async () => {
    renderHook(() => usePresenceHeartbeat());
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(1);
    const arg = mockedSend.mock.calls[0][0];
    expect(arg.client_type).toBe('web');
    expect(arg.client_id.length).toBeGreaterThanOrEqual(8);
  });

  it('sends heartbeats on the interval while visible', async () => {
    renderHook(() => usePresenceHeartbeat());
    await flushAsync();
    await act(async () => { vi.advanceTimersByTime(45_000); });
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(2);
  });

  it('skips heartbeats while hidden in active mode', async () => {
    renderHook(() => usePresenceHeartbeat());
    await flushAsync();
    setVisibility('hidden');
    await act(async () => { vi.advanceTimersByTime(3 * 45_000); });
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(1); // only the initial beat
  });

  it('keeps sending while hidden in session mode', async () => {
    mockedSend.mockResolvedValue({
      present: true,
      enabled: true,
      mode: 'session',
      heartbeat_interval_seconds: 45,
      timeout_minutes: 3,
    });
    renderHook(() => usePresenceHeartbeat());
    await flushAsync(); // initial beat -> learns mode 'session'
    setVisibility('hidden');
    await act(async () => { vi.advanceTimersByTime(45_000); });
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(2);
  });

  it('sends immediately when the tab becomes visible again', async () => {
    renderHook(() => usePresenceHeartbeat());
    await flushAsync();
    setVisibility('hidden');
    await act(async () => { vi.advanceTimersByTime(45_000); });
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(1);

    setVisibility('visible');
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(2);
  });

  it('stops on unmount', async () => {
    const { unmount } = renderHook(() => usePresenceHeartbeat());
    await flushAsync();
    unmount();
    await act(async () => { vi.advanceTimersByTime(10 * 45_000); });
    expect(mockedSend).toHaveBeenCalledTimes(1);
  });

  it('swallows API errors silently', async () => {
    mockedSend.mockRejectedValueOnce(new Error('network down'));
    renderHook(() => usePresenceHeartbeat());
    await flushAsync();
    // no throw; next interval still fires
    await act(async () => { vi.advanceTimersByTime(45_000); });
    await flushAsync();
    expect(mockedSend).toHaveBeenCalledTimes(2);
  });

  it('reuses the same client_id across beats (sessionStorage)', async () => {
    renderHook(() => usePresenceHeartbeat());
    await flushAsync();
    await act(async () => { vi.advanceTimersByTime(45_000); });
    await flushAsync();
    const ids = mockedSend.mock.calls.map((c) => c[0].client_id);
    expect(new Set(ids).size).toBe(1);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd client && npx vitest run src/__tests__/hooks/usePresenceHeartbeat.test.ts`
Expected: FAIL — cannot resolve `../../hooks/usePresenceHeartbeat`

- [ ] **Step 3: Implement the hook**

Create `client/src/hooks/usePresenceHeartbeat.ts`:

```typescript
/**
 * Presence heartbeat (issue #214).
 *
 * Sends POST /api/system/sleep/presence on an interval so the backend knows
 * a user is actively present and will not auto-escalate to true suspend.
 *
 * Mode is learned from the heartbeat response:
 * - 'active'  (default): beats only while the tab is visible — a forgotten
 *   background tab does not keep the server awake.
 * - 'session': beats while the tab is open, regardless of visibility.
 *
 * Best-effort by design: all errors are swallowed; the hook must never
 * disturb the UI. Mount it once in the authenticated layout — unmounting
 * (logout) stops the heartbeat.
 */
import { useEffect } from 'react';
import { sendPresenceHeartbeat, type PresenceMode } from '../api/sleep';

const DEFAULT_INTERVAL_MS = 45_000;
const CLIENT_ID_KEY = 'baluhost_presence_client_id';

function getClientId(): string {
  let id = sessionStorage.getItem(CLIENT_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(CLIENT_ID_KEY, id);
  }
  return id;
}

export function usePresenceHeartbeat(): void {
  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;
    let intervalMs = DEFAULT_INTERVAL_MS;
    let mode: PresenceMode = 'active';
    const clientId = getClientId();

    const beat = async () => {
      if (mode === 'active' && document.visibilityState !== 'visible') return;
      try {
        const res = await sendPresenceHeartbeat({ client_id: clientId, client_type: 'web' });
        mode = res.mode;
        const nextMs = Math.max(15, res.heartbeat_interval_seconds) * 1000;
        if (nextMs !== intervalMs) {
          intervalMs = nextMs;
          schedule();
        }
      } catch {
        // best-effort: never disturb the UI
      }
    };

    const schedule = () => {
      if (timer) clearInterval(timer);
      timer = setInterval(() => { void beat(); }, intervalMs);
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') void beat();
    };

    void beat();
    schedule();
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      if (timer) clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, []);
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd client && npx vitest run src/__tests__/hooks/usePresenceHeartbeat.test.ts`
Expected: PASS (8)

- [ ] **Step 5: Mount in the authenticated layout**

In `client/src/components/Layout.tsx`: add the import

```typescript
import { usePresenceHeartbeat } from '../hooks/usePresenceHeartbeat';
```

and call it inside the `Layout` component body, directly after the `useAuth()` destructuring (line 121):

```typescript
  usePresenceHeartbeat();
```

(`Layout` only renders for authenticated users; unmount on logout stops the heartbeat.)

- [ ] **Step 6: Type-check + commit**

Run: `cd client && npx tsc --noEmit`
Expected: no new errors

```bash
git add client/src/hooks/usePresenceHeartbeat.ts client/src/components/Layout.tsx client/src/__tests__/hooks/usePresenceHeartbeat.test.ts
git commit -m "feat(client): presence heartbeat hook mounted in Layout (#214)"
```

---

### Task 9: Sleep page config card + i18n

**Files:**
- Modify: `client/src/components/power/SleepConfigPanel.tsx`
- Modify: `client/src/i18n/locales/de/system.json`
- Modify: `client/src/i18n/locales/en/system.json`

- [ ] **Step 1: Add i18n keys**

In both `client/src/i18n/locales/de/system.json` and `.../en/system.json`, add a `presence` object inside the existing `"sleep"` object.

German (`de/system.json`):

```json
"presence": {
  "title": "Anwesenheitserkennung",
  "description": "Verhindert automatischen True Suspend, solange ein Benutzer die Web-App aktiv nutzt. Soft Sleep bleibt erlaubt.",
  "modeLabel": "Modus",
  "modeActive": "Aktive Nutzung — Heartbeat nur bei sichtbarem Tab",
  "modeSession": "Offene Sitzung — jeder offene Tab zählt",
  "modeHint": "„Aktive Nutzung\" spart Energie: Ein vergessener Hintergrund-Tab hält den Server nicht wach.",
  "timeoutLabel": "Timeout (Minuten)",
  "suppressing": "True Suspend blockiert: {{count}} aktive Sitzung(en)"
}
```

English (`en/system.json`):

```json
"presence": {
  "title": "Presence detection",
  "description": "Prevents automatic true suspend while a user is actively using the web app. Soft sleep stays allowed.",
  "modeLabel": "Mode",
  "modeActive": "Active interaction — heartbeat only while the tab is visible",
  "modeSession": "Open session — any open tab counts",
  "modeHint": "\"Active interaction\" saves energy: a forgotten background tab does not keep the server awake.",
  "timeoutLabel": "Timeout (minutes)",
  "suppressing": "True suspend blocked: {{count}} active session(s)"
}
```

- [ ] **Step 2: Extend `SleepConfigPanel.tsx`**

Imports: add `Eye` to the lucide-react import (line 11); add `type PresenceMode` and `type PresenceStatus` to the `../../api/sleep` import (line 12-20).

Form state — add after the `diskSpindown` state (line 54):

```typescript
  const [presenceEnabled, setPresenceEnabled] = useState(true);
  const [presenceMode, setPresenceMode] = useState<PresenceMode>('active');
  const [presenceTimeout, setPresenceTimeout] = useState(3);
  const [presenceStatus, setPresenceStatus] = useState<PresenceStatus | null>(null);
```

`loadData` — in the existing `getSleepStatus()` try-block (line 92-98), add:

```typescript
        setPresenceStatus(st.presence ?? null);
```

`syncFormState` (line 106) — add:

```typescript
    setPresenceEnabled(c.presence_enabled);
    setPresenceMode(c.presence_mode);
    setPresenceTimeout(c.presence_timeout_minutes);
```

`handleSave` `updateSleepConfig({...})` call (line 130) — add:

```typescript
        presence_enabled: presenceEnabled,
        presence_mode: presenceMode,
        presence_timeout_minutes: presenceTimeout,
```

JSX — insert a new card between the Auto-Escalation card (ends line 255) and the Schedule card:

```tsx
      {/* Presence Detection (issue #214) */}
      <div className="card border-slate-700/50 p-4 sm:p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-medium text-white flex items-center gap-2">
            <Eye className="h-4 w-4 text-emerald-400" />
            {t('sleep.presence.title')}
          </h4>
          <Toggle checked={presenceEnabled} onChange={setPresenceEnabled} />
        </div>
        <p className="text-xs text-slate-400">{t('sleep.presence.description')}</p>

        {presenceEnabled && (
          <div className="space-y-3 pl-1">
            <div>
              <label className="block text-xs text-slate-400 mb-1">{t('sleep.presence.modeLabel')}</label>
              <select
                value={presenceMode}
                onChange={(e) => setPresenceMode(e.target.value as PresenceMode)}
                className="w-full rounded bg-slate-900 border border-slate-600 px-3 py-2 text-sm text-white focus:border-teal-400 focus:outline-none"
              >
                <option value="active">{t('sleep.presence.modeActive')}</option>
                <option value="session">{t('sleep.presence.modeSession')}</option>
              </select>
              <p className="mt-1 text-xs text-slate-500">{t('sleep.presence.modeHint')}</p>
            </div>
            <NumberInput
              label={t('sleep.presence.timeoutLabel')}
              value={presenceTimeout}
              onChange={setPresenceTimeout}
              min={1}
              max={60}
            />
            {presenceStatus?.suppressing_suspend && (
              <div className="rounded border border-emerald-500/20 bg-emerald-500/10 p-2 text-xs text-emerald-300">
                {t('sleep.presence.suppressing', { count: presenceStatus.active_session_count })}
              </div>
            )}
          </div>
        )}
      </div>
```

- [ ] **Step 3: Type-check + full frontend test run**

Run: `cd client && npx tsc --noEmit && npx vitest run`
Expected: type-check clean, all Vitest suites PASS

- [ ] **Step 4: Commit**

```bash
git add client/src/components/power/SleepConfigPanel.tsx client/src/i18n/locales/de/system.json client/src/i18n/locales/en/system.json
git commit -m "feat(client): presence detection card on sleep page + i18n (#214)"
```

---

### Task 10: CHANGELOG + version bump

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `backend/pyproject.toml`
- Modify: `client/package.json`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Bump version to 1.37.0**

- `backend/pyproject.toml`: `version = "1.37.0"`
- `client/package.json`: `"version": "1.37.0"`
- `CLAUDE.md`: `**Version**: 1.37.0 (as of June 2026)`

(Check the actual current version strings first — bump from whatever is on `main` now.)

- [ ] **Step 2: Add CHANGELOG entry**

Insert directly under the top header of `CHANGELOG.md`:

```markdown
## [1.37.0] - 2026-06-11

### Added
- **Presence-aware suspend** (#214): the sleep system no longer auto-suspends
  while a user is actively present in the web app. Web clients send a
  lightweight heartbeat (`POST /api/system/sleep/presence`) while the tab is
  visible; presence blocks auto-escalation and scheduled true suspend, and
  holds the logind block-sleep inhibitor so OS-driven suspends (KDE
  PowerDevil, logind IdleAction) are blocked too. Soft sleep stays allowed.
  Two modes: active interaction (default, heartbeat only while the tab is
  visible) and open session (any open tab counts). Configurable on the
  Sleep page (toggle, mode, timeout); the status block shows when presence
  is currently blocking suspend.
```

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md backend/pyproject.toml client/package.json CLAUDE.md
git commit -m "docs: CHANGELOG entry for v1.37.0 + version bump"
```

---

### Task 11: Final verification + PR

- [ ] **Step 1: Backend — run all touched/related suites**

```bash
cd backend && python -m pytest tests/services/power/test_presence_service.py tests/api/test_presence_route.py tests/test_sleep_auto_wake_presence.py tests/services/test_sleep_presence_integration.py tests/test_sleep.py tests/services/test_sleep_core_uptime_integration.py tests/api/test_os_auto_suspend_route.py -v
```
Expected: all PASS. (Full backend suite runs in CI; two known Windows-only flaky auth/permission delete tests are unrelated.)

- [ ] **Step 2: Frontend — full Vitest + typecheck + build**

```bash
cd client && npx tsc --noEmit && npx vitest run && npm run build
```
Expected: all PASS, build succeeds.

- [ ] **Step 3: Update services CLAUDE.md**

Add a line for the new module in `backend/app/services/CLAUDE.md` under the `power/` subdirectory listing:

```markdown
- `presence.py` — user-presence tracker (heartbeats → presence_sessions table; blocks auto true-suspend, issue #214)
```

Commit:

```bash
git add backend/app/services/CLAUDE.md
git commit -m "docs: register presence service in services CLAUDE.md"
```

- [ ] **Step 4: Push + PR**

```bash
git push -u origin feat/sleep-presence-suspend-214
```

Create the PR against `main` (write the body with the Write tool to a temp file, then `gh pr create --body-file` — here-strings break in both shells). Reference issue #214 with `Closes #214`.

- [ ] **Step 5: Follow-up issue (after merge)**

Create a follow-up issue in the `Xveyn/BaluApp` repo: foreground presence heartbeat against `POST /api/system/sleep/presence` (`client_type: "mobile"`), referencing BaluHost#214 and this plan. Ask the user before creating it.

---

## Notes for the implementer

- **Do not run the Alembic migration against the dev DB during implementation** — the test suite uses `init_db()` create_all. The migration is exercised on prod deploy. Verify `python -m alembic heads` shows exactly one head after Task 1.
- **Soft sleep must never be blocked by presence.** If you find yourself adding a presence check to `_idle_detection_loop` or `enter_soft_sleep`, stop — that contradicts the spec.
- **Existing reason strings** for the inhibitor (`core_uptime_active`, `always_awake_active`, `core_uptime_and_always_awake_active`) are asserted by existing tests; the rewrite in Task 6e keeps them byte-identical.
- **vi.mock factories must be complete** — if a test fails with "X is not a function" on the sleep API mock, add the missing export to the factory instead of partially mocking.
- CRLF: git will warn `LF will be replaced by CRLF` — that's expected on this repo.
