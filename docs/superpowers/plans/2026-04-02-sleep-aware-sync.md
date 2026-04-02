# Sleep-Aware Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make sync clients respect admin-set sleep schedules — automatic syncs are blocked during sleep, manual syncs still auto-wake, and schedule creation is validated against sleep windows.

**Architecture:** A shared `is_time_in_sleep_window()` helper (backend) and `isTimeInSleepWindow()` (frontend) provide the overlap check. A new FastAPI dependency `require_sync_allowed` guards sync data endpoints. The sleep auto-wake middleware learns to respect `X-Sync-Trigger` headers. A new `GET /api/sync/preflight` endpoint provides sleep schedule info to clients.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript (frontend), pytest (tests)

**Spec:** `docs/superpowers/specs/2026-04-02-sleep-aware-sync-design.md`

---

### Task 1: Sleep Window Helper + Tests

**Files:**
- Create: `backend/app/services/sync/sleep_check.py`
- Create: `backend/tests/test_sync_sleep_check.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_sync_sleep_check.py
"""Tests for sleep window overlap check."""
import pytest
from app.services.sync.sleep_check import is_time_in_sleep_window


class TestIsTimeInSleepWindow:
    """Test the time-in-sleep-window helper."""

    def test_normal_window_inside(self):
        """14:00-16:00 window, sync at 15:00 -> conflict."""
        assert is_time_in_sleep_window("15:00", "14:00", "16:00") is True

    def test_normal_window_outside_before(self):
        """14:00-16:00 window, sync at 13:00 -> no conflict."""
        assert is_time_in_sleep_window("13:00", "14:00", "16:00") is False

    def test_normal_window_outside_after(self):
        """14:00-16:00 window, sync at 17:00 -> no conflict."""
        assert is_time_in_sleep_window("17:00", "14:00", "16:00") is False

    def test_overnight_window_inside_before_midnight(self):
        """23:00-06:00 window, sync at 23:30 -> conflict."""
        assert is_time_in_sleep_window("23:30", "23:00", "06:00") is True

    def test_overnight_window_inside_after_midnight(self):
        """23:00-06:00 window, sync at 02:00 -> conflict."""
        assert is_time_in_sleep_window("02:00", "23:00", "06:00") is True

    def test_overnight_window_outside(self):
        """23:00-06:00 window, sync at 12:00 -> no conflict."""
        assert is_time_in_sleep_window("12:00", "23:00", "06:00") is False

    def test_boundary_sleep_time_equals_sync(self):
        """Sync at exact sleep_time -> conflict (inclusive start)."""
        assert is_time_in_sleep_window("23:00", "23:00", "06:00") is True

    def test_boundary_wake_time_equals_sync(self):
        """Sync at exact wake_time -> no conflict (exclusive end)."""
        assert is_time_in_sleep_window("06:00", "23:00", "06:00") is False

    def test_same_time_window(self):
        """sleep_time == wake_time -> no valid window -> no conflict."""
        assert is_time_in_sleep_window("12:00", "06:00", "06:00") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_sync_sleep_check.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.sync.sleep_check'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/services/sync/sleep_check.py
"""Sleep window overlap check for sync scheduling."""


def is_time_in_sleep_window(sync_time: str, sleep_time: str, wake_time: str) -> bool:
    """Check if sync_time (HH:MM) falls within the sleep window [sleep_time, wake_time).

    Handles overnight windows (e.g. 23:00-06:00).
    Returns False if sleep_time == wake_time (no valid window).
    """
    if sleep_time == wake_time:
        return False

    sync_minutes = _to_minutes(sync_time)
    sleep_minutes = _to_minutes(sleep_time)
    wake_minutes = _to_minutes(wake_time)

    if sleep_minutes < wake_minutes:
        # Normal window: e.g. 14:00-16:00
        return sleep_minutes <= sync_minutes < wake_minutes
    else:
        # Overnight window: e.g. 23:00-06:00
        return sync_minutes >= sleep_minutes or sync_minutes < wake_minutes


def _to_minutes(time_str: str) -> int:
    """Convert HH:MM string to minutes since midnight."""
    h, m = map(int, time_str.split(":"))
    return h * 60 + m
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_sync_sleep_check.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sync/sleep_check.py backend/tests/test_sync_sleep_check.py
git commit -m "feat(sync): add sleep window overlap check helper"
```

---

### Task 2: Preflight Schema + Endpoint

**Files:**
- Modify: `backend/app/schemas/sync.py` — add `SyncPreflightResponse`
- Modify: `backend/app/api/routes/sync.py` — add `GET /preflight` endpoint
- Create: `backend/tests/test_sync_preflight.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_sync_preflight.py
"""Tests for the sync preflight endpoint."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.sleep import SleepState


@pytest.fixture
def client(db_session, admin_token):
    """TestClient with auth."""
    from app.core.database import get_db
    app.dependency_overrides[get_db] = lambda: db_session
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {admin_token}"
    yield c
    app.dependency_overrides.clear()


class TestSyncPreflight:
    """Test GET /api/sync/preflight."""

    def test_preflight_awake_no_schedule(self, client):
        """When awake with no sleep schedule, sync is allowed."""
        mock_manager = MagicMock()
        mock_manager._current_state = SleepState.AWAKE
        mock_manager._load_config.return_value = None

        with patch("app.api.routes.sync.get_sleep_manager", return_value=mock_manager):
            resp = client.get("/api/sync/preflight")

        assert resp.status_code == 200
        data = resp.json()
        assert data["sync_allowed"] is True
        assert data["current_sleep_state"] == "awake"
        assert data["sleep_schedule"] is None
        assert data["block_reason"] is None

    def test_preflight_soft_sleep(self, client):
        """When in soft sleep, sync is not allowed."""
        mock_manager = MagicMock()
        mock_manager._current_state = SleepState.SOFT_SLEEP
        mock_manager._load_config.return_value = None

        with patch("app.api.routes.sync.get_sleep_manager", return_value=mock_manager):
            resp = client.get("/api/sync/preflight")

        assert resp.status_code == 200
        data = resp.json()
        assert data["sync_allowed"] is False
        assert data["block_reason"] == "sleep_active"

    def test_preflight_with_schedule(self, client):
        """When schedule is enabled, response includes schedule info."""
        mock_config = MagicMock()
        mock_config.schedule_enabled = True
        mock_config.schedule_sleep_time = "23:00"
        mock_config.schedule_wake_time = "06:00"
        mock_config.schedule_mode = "suspend"

        mock_manager = MagicMock()
        mock_manager._current_state = SleepState.AWAKE
        mock_manager._load_config.return_value = mock_config

        with patch("app.api.routes.sync.get_sleep_manager", return_value=mock_manager):
            resp = client.get("/api/sync/preflight")

        assert resp.status_code == 200
        data = resp.json()
        assert data["sync_allowed"] is True
        assert data["sleep_schedule"] is not None
        assert data["sleep_schedule"]["sleep_time"] == "23:00"
        assert data["sleep_schedule"]["wake_time"] == "06:00"

    def test_preflight_no_sleep_manager(self, client):
        """When sleep manager not running, sync is allowed (graceful degradation)."""
        with patch("app.api.routes.sync.get_sleep_manager", return_value=None):
            resp = client.get("/api/sync/preflight")

        assert resp.status_code == 200
        data = resp.json()
        assert data["sync_allowed"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_sync_preflight.py -v`
Expected: FAIL — `ImportError` (schema not yet defined)

- [ ] **Step 3: Add the Pydantic schemas to `backend/app/schemas/sync.py`**

Append at end of file:

```python
# ============================================================================
# SYNC PREFLIGHT (SLEEP-AWARE SYNC)
# ============================================================================

class SleepScheduleInfo(BaseModel):
    """Sleep schedule info for sync clients."""
    enabled: bool = Field(..., description="Whether sleep schedule is active")
    sleep_time: str = Field(..., description="Sleep start time (HH:MM)")
    wake_time: str = Field(..., description="Wake time (HH:MM)")
    mode: str = Field(..., description="Sleep mode: soft or suspend")


class SyncPreflightResponse(BaseModel):
    """Response for sync preflight check."""
    sync_allowed: bool = Field(..., description="Whether automatic sync is currently allowed")
    current_sleep_state: str = Field(..., description="Current NAS sleep state")
    sleep_schedule: Optional[SleepScheduleInfo] = Field(default=None, description="Sleep schedule if active")
    next_sleep_at: Optional[str] = Field(default=None, description="Next scheduled sleep time (ISO 8601)")
    next_wake_at: Optional[str] = Field(default=None, description="Next scheduled wake time (ISO 8601)")
    block_reason: Optional[str] = Field(default=None, description="Why sync is blocked: sleep_active or null")
```

- [ ] **Step 4: Add the preflight endpoint to `backend/app/api/routes/sync.py`**

Add import at top:

```python
from app.services.power.sleep import get_sleep_manager
from app.schemas.sync import SyncPreflightResponse, SleepScheduleInfo
```

Add endpoint after the existing imports/router setup (before the first `@router` endpoint):

```python
@router.get("/preflight", response_model=SyncPreflightResponse)
@user_limiter.limit(get_limit("sync_operations"))
async def sync_preflight(
    request: Request,
    response: Response,
    current_user: User = Depends(deps.get_current_user),
) -> SyncPreflightResponse:
    """Check if automatic sync is currently allowed and return sleep schedule.

    Lightweight endpoint for sync clients to call before starting automatic sync.
    Does NOT wake the NAS from sleep (whitelisted in auto-wake middleware).
    """
    manager = get_sleep_manager()

    if manager is None:
        # Sleep manager not running — allow sync (graceful degradation)
        return SyncPreflightResponse(
            sync_allowed=True,
            current_sleep_state="awake",
        )

    from app.schemas.sleep import SleepState
    current_state = manager._current_state
    is_awake = current_state == SleepState.AWAKE

    # Build schedule info
    schedule_info = None
    next_sleep_at = None
    next_wake_at = None
    config = manager._load_config()

    if config and config.schedule_enabled:
        schedule_info = SleepScheduleInfo(
            enabled=True,
            sleep_time=config.schedule_sleep_time,
            wake_time=config.schedule_wake_time,
            mode=config.schedule_mode,
        )
        # Compute next occurrence
        from datetime import datetime, timedelta
        now = datetime.now()
        for time_str, attr in [
            (config.schedule_sleep_time, "next_sleep_at"),
            (config.schedule_wake_time, "next_wake_at"),
        ]:
            h, m = map(int, time_str.split(":"))
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            if attr == "next_sleep_at":
                next_sleep_at = target.isoformat()
            else:
                next_wake_at = target.isoformat()

    return SyncPreflightResponse(
        sync_allowed=is_awake,
        current_sleep_state=current_state.value,
        sleep_schedule=schedule_info,
        next_sleep_at=next_sleep_at,
        next_wake_at=next_wake_at,
        block_reason="sleep_active" if not is_awake else None,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_sync_preflight.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/sync.py backend/app/api/routes/sync.py backend/tests/test_sync_preflight.py
git commit -m "feat(sync): add preflight endpoint for sleep-aware sync"
```

---

### Task 3: Server-Side Guard Dependency

**Files:**
- Modify: `backend/app/api/deps.py` — add `require_sync_allowed` dependency
- Create: `backend/tests/test_sync_guard.py`
- Modify: `backend/app/api/routes/sync.py` — apply guard to data endpoints
- Modify: `backend/app/api/routes/sync_advanced.py` — apply guard to upload endpoints

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_sync_guard.py
"""Tests for the sync sleep guard dependency."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI, Depends, Request
from fastapi.testclient import TestClient

from app.schemas.sleep import SleepState


def _make_app():
    """Create a minimal FastAPI app with the guard dependency."""
    from app.api.deps import require_sync_allowed

    test_app = FastAPI()

    @test_app.get("/test-guarded")
    async def guarded_endpoint(request: Request, _=Depends(require_sync_allowed)):
        return {"ok": True}

    return test_app


class TestRequireSyncAllowed:
    """Test the require_sync_allowed dependency."""

    def test_awake_allows_auto_sync(self):
        """Auto sync is allowed when NAS is awake."""
        app = _make_app()
        mock_manager = MagicMock()
        mock_manager._current_state = SleepState.AWAKE

        with patch("app.api.deps.get_sleep_manager", return_value=mock_manager):
            client = TestClient(app)
            resp = client.get("/test-guarded", headers={"X-Sync-Trigger": "auto"})
        assert resp.status_code == 200

    def test_soft_sleep_blocks_auto_sync(self):
        """Auto sync is blocked (503) when NAS is in soft sleep."""
        app = _make_app()
        mock_manager = MagicMock()
        mock_manager._current_state = SleepState.SOFT_SLEEP
        mock_config = MagicMock()
        mock_config.schedule_enabled = True
        mock_config.schedule_wake_time = "06:00"
        mock_manager._load_config.return_value = mock_config

        with patch("app.api.deps.get_sleep_manager", return_value=mock_manager):
            client = TestClient(app)
            resp = client.get("/test-guarded", headers={"X-Sync-Trigger": "auto"})
        assert resp.status_code == 503
        assert "sleep" in resp.json()["detail"].lower()

    def test_soft_sleep_allows_manual_sync(self):
        """Manual sync is allowed even during soft sleep (auto-wake handles it)."""
        app = _make_app()
        mock_manager = MagicMock()
        mock_manager._current_state = SleepState.SOFT_SLEEP

        with patch("app.api.deps.get_sleep_manager", return_value=mock_manager):
            client = TestClient(app)
            resp = client.get("/test-guarded", headers={"X-Sync-Trigger": "manual"})
        assert resp.status_code == 200

    def test_no_header_treated_as_manual(self):
        """Missing X-Sync-Trigger header is treated as manual (backwards compat)."""
        app = _make_app()
        mock_manager = MagicMock()
        mock_manager._current_state = SleepState.SOFT_SLEEP

        with patch("app.api.deps.get_sleep_manager", return_value=mock_manager):
            client = TestClient(app)
            resp = client.get("/test-guarded")
        assert resp.status_code == 200

    def test_scheduled_trigger_blocked(self):
        """Scheduled sync is blocked like auto sync."""
        app = _make_app()
        mock_manager = MagicMock()
        mock_manager._current_state = SleepState.SOFT_SLEEP
        mock_manager._load_config.return_value = None

        with patch("app.api.deps.get_sleep_manager", return_value=mock_manager):
            client = TestClient(app)
            resp = client.get("/test-guarded", headers={"X-Sync-Trigger": "scheduled"})
        assert resp.status_code == 503

    def test_no_sleep_manager_allows_all(self):
        """When sleep manager is not running, all syncs are allowed."""
        app = _make_app()

        with patch("app.api.deps.get_sleep_manager", return_value=None):
            client = TestClient(app)
            resp = client.get("/test-guarded", headers={"X-Sync-Trigger": "auto"})
        assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_sync_guard.py -v`
Expected: FAIL — `ImportError: cannot import name 'require_sync_allowed' from 'app.api.deps'`

- [ ] **Step 3: Implement `require_sync_allowed` in `backend/app/api/deps.py`**

Add at the end of `backend/app/api/deps.py`:

```python
async def require_sync_allowed(request: Request) -> None:
    """Dependency that blocks automatic sync requests during sleep mode.

    Reads X-Sync-Trigger header:
    - "auto" / "scheduled" -> blocked during sleep (503)
    - "manual" / missing   -> allowed (auto-wake middleware handles waking)
    """
    from app.services.power.sleep import get_sleep_manager
    from app.schemas.sleep import SleepState

    trigger = (request.headers.get("X-Sync-Trigger") or "manual").lower()
    if trigger not in ("auto", "scheduled"):
        return  # manual or unknown -> allow

    manager = get_sleep_manager()
    if manager is None:
        return  # sleep manager not running -> allow

    state = manager._current_state
    if state == SleepState.AWAKE:
        return  # system is awake -> allow

    # Compute next_wake_at and retry_after from config
    config = manager._load_config()
    next_wake_at = None
    retry_after = None
    if config and config.schedule_enabled:
        from datetime import datetime, timedelta
        now = datetime.now()
        h, m = map(int, config.schedule_wake_time.split(":"))
        wake_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if wake_dt <= now:
            wake_dt += timedelta(days=1)
        next_wake_at = wake_dt.isoformat()
        retry_after = int((wake_dt - now).total_seconds())

    raise HTTPException(
        status_code=503,
        detail="Sync blocked: NAS is in sleep mode",
        headers={"Retry-After": str(retry_after)} if retry_after else {},
    )
```

- [ ] **Step 4: Run guard tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_sync_guard.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Apply guard to sync data endpoints in `backend/app/api/routes/sync.py`**

Add import:

```python
from app.api.deps import require_sync_allowed
```

Add `Depends(require_sync_allowed)` to these endpoint signatures:
- `detect_changes` (line ~153): add `_guard=Depends(require_sync_allowed)` parameter
- `get_sync_state` (line ~240): add `_guard=Depends(require_sync_allowed)` parameter
- `report_sync_folders` (line ~298): add `_guard=Depends(require_sync_allowed)` parameter

- [ ] **Step 6: Apply guard to sync_advanced data endpoints in `backend/app/api/routes/sync_advanced.py`**

Add import:

```python
from app.api.deps import require_sync_allowed
```

Add `_guard=Depends(require_sync_allowed)` to:
- `start_chunked_upload` (line ~46)
- `upload_chunk` (line ~67)
- `resume_upload` (line ~113)

- [ ] **Step 7: Run full test suite to verify no regressions**

Run: `cd backend && python -m pytest tests/test_sync_guard.py tests/test_sync_preflight.py tests/test_sync_sleep_check.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/deps.py backend/app/api/routes/sync.py backend/app/api/routes/sync_advanced.py backend/tests/test_sync_guard.py
git commit -m "feat(sync): add server-side guard blocking auto-sync during sleep"
```

---

### Task 4: Sleep Auto-Wake Middleware Update

**Files:**
- Modify: `backend/app/middleware/sleep_auto_wake.py`
- Modify: `backend/tests/test_sleep.py` — add middleware tests for new behavior

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_sleep.py` (in a new class at the end):

```python
class TestSleepAutoWakeMiddlewareSyncTrigger:
    """Test that auto-wake middleware respects X-Sync-Trigger header."""

    @pytest.mark.asyncio
    async def test_auto_sync_does_not_wake(self):
        """Sync requests with X-Sync-Trigger: auto should NOT auto-wake."""
        from app.middleware.sleep_auto_wake import SleepAutoWakeMiddleware
        from starlette.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.responses import JSONResponse

        wake_called = False

        async def mock_endpoint(request):
            return JSONResponse({"ok": True})

        test_app = Starlette(routes=[Route("/api/sync/changes", mock_endpoint, methods=["POST"])])
        test_app.add_middleware(SleepAutoWakeMiddleware)

        mock_manager = MagicMock()
        mock_manager._current_state = SleepState.SOFT_SLEEP
        mock_manager.exit_soft_sleep = AsyncMock()

        with patch("app.middleware.sleep_auto_wake.get_sleep_manager", return_value=mock_manager):
            with patch("app.middleware.sleep_auto_wake.SleepState", SleepState):
                client = TestClient(test_app)
                client.post("/api/sync/changes", headers={"X-Sync-Trigger": "auto"})

        mock_manager.exit_soft_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_manual_sync_does_wake(self):
        """Sync requests with X-Sync-Trigger: manual should auto-wake as before."""
        from app.middleware.sleep_auto_wake import SleepAutoWakeMiddleware
        from starlette.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.responses import JSONResponse

        async def mock_endpoint(request):
            return JSONResponse({"ok": True})

        test_app = Starlette(routes=[Route("/api/sync/changes", mock_endpoint, methods=["POST"])])
        test_app.add_middleware(SleepAutoWakeMiddleware)

        mock_manager = MagicMock()
        mock_manager._current_state = SleepState.SOFT_SLEEP
        mock_manager.exit_soft_sleep = AsyncMock(return_value=True)

        with patch("app.middleware.sleep_auto_wake.get_sleep_manager", return_value=mock_manager):
            with patch("app.middleware.sleep_auto_wake.SleepState", SleepState):
                client = TestClient(test_app)
                client.post("/api/sync/changes", headers={"X-Sync-Trigger": "manual"})

        mock_manager.exit_soft_sleep.assert_called_once()

    @pytest.mark.asyncio
    async def test_preflight_whitelisted(self):
        """GET /api/sync/preflight should not trigger auto-wake."""
        from app.middleware.sleep_auto_wake import _WAKE_WHITELIST_PREFIXES
        assert any("/api/sync/preflight" .startswith(p) or p == "/api/sync/preflight"
                    for p in _WAKE_WHITELIST_PREFIXES)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_sleep.py::TestSleepAutoWakeMiddlewareSyncTrigger -v`
Expected: FAIL — whitelist check fails and import issues

- [ ] **Step 3: Update the middleware**

Edit `backend/app/middleware/sleep_auto_wake.py`:

1. Add `/api/sync/preflight` to `_WAKE_WHITELIST_PREFIXES`:

```python
_WAKE_WHITELIST_PREFIXES = (
    "/api/system/sleep/status",
    "/api/system/sleep/config",
    "/api/system/sleep/history",
    "/api/system/sleep/capabilities",
    "/api/power/status",
    "/api/system/info",
    "/api/monitoring/",
    "/api/admin/services",
    "/api/sync/preflight",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
)
```

2. In the `dispatch` method, after the whitelist check and before calling `exit_soft_sleep`, add the `X-Sync-Trigger` check:

Replace the block starting at `if not is_whitelisted:` (lines 55-68) with:

```python
        if not is_whitelisted:
            try:
                from app.services.power.sleep import get_sleep_manager
                from app.schemas.sleep import SleepState

                manager = get_sleep_manager()
                if manager and manager._current_state == SleepState.SOFT_SLEEP:
                    # Check X-Sync-Trigger header for sync paths
                    sync_trigger = request.headers.get("X-Sync-Trigger", "").lower()
                    if sync_trigger in ("auto", "scheduled"):
                        # Automatic sync during sleep — do NOT wake, let guard return 503
                        logger.debug(
                            "Skipping auto-wake for automatic sync: %s %s (trigger=%s)",
                            method, path, sync_trigger,
                        )
                    else:
                        # Non-whitelisted request while in soft sleep -> auto-wake
                        logger.info(
                            "Auto-wake triggered by %s %s",
                            method, path,
                        )
                        await manager.exit_soft_sleep(f"auto_wake: {method} {path}")
            except Exception as e:
                logger.debug("Auto-wake check failed: %s", e)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_sleep.py::TestSleepAutoWakeMiddlewareSyncTrigger -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/middleware/sleep_auto_wake.py backend/tests/test_sleep.py
git commit -m "feat(sync): update auto-wake middleware to respect X-Sync-Trigger header"
```

---

### Task 5: Sync Schedule Validation Against Sleep Window

**Files:**
- Modify: `backend/app/services/sync/scheduler.py` — add validation in `create_schedule` and `update_schedule`
- Create: `backend/tests/test_sync_schedule_validation.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_sync_schedule_validation.py
"""Tests for sync schedule validation against sleep windows."""
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session

from app.services.sync.scheduler import SyncSchedulerService


class TestSyncScheduleSleepValidation:
    """Test that sync schedule creation/update rejects times in sleep windows."""

    def _make_service(self, db: Session) -> SyncSchedulerService:
        return SyncSchedulerService(db)

    def _mock_sleep_config(self, enabled=True, sleep_time="23:00", wake_time="06:00"):
        config = MagicMock()
        config.schedule_enabled = enabled
        config.schedule_sleep_time = sleep_time
        config.schedule_wake_time = wake_time
        return config

    def test_create_schedule_in_sleep_window_rejected(self, db_session):
        """Creating a schedule at 02:00 with sleep window 23:00-06:00 should raise ValueError."""
        service = self._make_service(db_session)
        config = self._mock_sleep_config()

        with patch("app.services.sync.scheduler.SyncSchedulerService._get_sleep_config", return_value=config):
            with pytest.raises(ValueError, match="sleep window"):
                service.create_schedule(
                    user_id=1,
                    device_id="test-device",
                    schedule_type="daily",
                    time_of_day="02:00",
                )

    def test_create_schedule_outside_sleep_window_allowed(self, db_session):
        """Creating a schedule at 12:00 with sleep window 23:00-06:00 should work."""
        service = self._make_service(db_session)
        config = self._mock_sleep_config()

        with patch("app.services.sync.scheduler.SyncSchedulerService._get_sleep_config", return_value=config):
            result = service.create_schedule(
                user_id=1,
                device_id="test-device",
                schedule_type="daily",
                time_of_day="12:00",
            )
        assert result is not None

    def test_create_schedule_no_sleep_config_allowed(self, db_session):
        """When no sleep config exists, any time is allowed."""
        service = self._make_service(db_session)

        with patch("app.services.sync.scheduler.SyncSchedulerService._get_sleep_config", return_value=None):
            result = service.create_schedule(
                user_id=1,
                device_id="test-device",
                schedule_type="daily",
                time_of_day="02:00",
            )
        assert result is not None

    def test_create_schedule_sleep_disabled_allowed(self, db_session):
        """When sleep schedule is disabled, any time is allowed."""
        service = self._make_service(db_session)
        config = self._mock_sleep_config(enabled=False)

        with patch("app.services.sync.scheduler.SyncSchedulerService._get_sleep_config", return_value=config):
            result = service.create_schedule(
                user_id=1,
                device_id="test-device",
                schedule_type="daily",
                time_of_day="02:00",
            )
        assert result is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_sync_schedule_validation.py -v`
Expected: FAIL — `_get_sleep_config` method does not exist

- [ ] **Step 3: Add sleep config lookup and validation to `backend/app/services/sync/scheduler.py`**

Add import at top:

```python
from app.services.sync.sleep_check import is_time_in_sleep_window
```

Add method to `SyncSchedulerService` class:

```python
    def _get_sleep_config(self):
        """Load sleep config from DB for validation."""
        from sqlalchemy import select
        from app.models.sleep import SleepConfig as SleepConfigModel
        try:
            return self.db.execute(
                select(SleepConfigModel).where(SleepConfigModel.id == 1)
            ).scalar_one_or_none()
        except Exception:
            return None

    def _validate_time_against_sleep(self, time_of_day: str) -> None:
        """Raise ValueError if time_of_day falls within the sleep window."""
        config = self._get_sleep_config()
        if not config or not config.schedule_enabled:
            return
        if is_time_in_sleep_window(time_of_day, config.schedule_sleep_time, config.schedule_wake_time):
            raise ValueError(
                f"Sync schedule conflicts with sleep window "
                f"({config.schedule_sleep_time}-{config.schedule_wake_time}). "
                f"Choose a time outside the sleep window."
            )
```

Add call in `create_schedule` — insert after the method signature, before creating the `SyncSchedule` object:

```python
        self._validate_time_against_sleep(time_of_day or "02:00")
```

Add call in `update_schedule` — insert after `for key, value in kwargs.items():` block, before `self._calculate_next_run`:

```python
        # Validate updated time against sleep window
        new_time = kwargs.get("time_of_day") or schedule.time_of_day
        if new_time:
            self._validate_time_against_sleep(new_time)
```

- [ ] **Step 4: Update the route handlers to return 409 on ValueError**

In `backend/app/api/routes/sync_advanced.py`, update `create_sync_schedule` (line ~196):

Wrap the `scheduler.create_schedule(...)` call:

```python
    try:
        result = scheduler.create_schedule(
            user_id=current_user.id,
            device_id=payload.device_id,
            schedule_type=payload.schedule_type,
            time_of_day=payload.time_of_day,
            day_of_week=payload.day_of_week,
            day_of_month=payload.day_of_month,
            sync_deletions=payload.sync_deletions,
            resolve_conflicts=payload.resolve_conflicts,
            auto_vpn=payload.auto_vpn
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
```

Same for `update_sync_schedule` (line ~287):

Wrap `scheduler.update_schedule(...)`:

```python
    try:
        result = scheduler.update_schedule(...)
        ...
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_sync_schedule_validation.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/sync/scheduler.py backend/app/api/routes/sync_advanced.py backend/tests/test_sync_schedule_validation.py
git commit -m "feat(sync): validate sync schedules against sleep window"
```

---

### Task 6: Frontend — API Client + Sleep Window Utility

**Files:**
- Modify: `client/src/api/sync.ts` — add `getSyncPreflight` function and types
- Create: `client/src/lib/sleep-utils.ts` — `isTimeInSleepWindow()` helper

- [ ] **Step 1: Add types and API function to `client/src/api/sync.ts`**

Add types after the existing interfaces:

```typescript
export interface SleepScheduleInfo {
  enabled: boolean;
  sleep_time: string;
  wake_time: string;
  mode: string;
}

export interface SyncPreflightResponse {
  sync_allowed: boolean;
  current_sleep_state: string;
  sleep_schedule: SleepScheduleInfo | null;
  next_sleep_at: string | null;
  next_wake_at: string | null;
  block_reason: string | null;
}
```

Add API function after the existing schedule functions:

```typescript
// ---------------------------------------------------------------------------
// Preflight (Sleep-Aware Sync)
// ---------------------------------------------------------------------------

export async function getSyncPreflight(): Promise<SyncPreflightResponse> {
  const res = await apiClient.get('/api/sync/preflight');
  return res.data;
}
```

- [ ] **Step 2: Create the frontend sleep window utility**

```typescript
// client/src/lib/sleep-utils.ts
/**
 * Check if a time (HH:MM) falls within a sleep window.
 * Handles overnight windows (e.g. 23:00-06:00).
 */
export function isTimeInSleepWindow(
  syncTime: string,
  sleepTime: string,
  wakeTime: string,
): boolean {
  if (sleepTime === wakeTime) return false;

  const toMinutes = (t: string) => {
    const [h, m] = t.split(':').map(Number);
    return h * 60 + m;
  };

  const sync = toMinutes(syncTime);
  const sleep = toMinutes(sleepTime);
  const wake = toMinutes(wakeTime);

  if (sleep < wake) {
    // Normal window: e.g. 14:00-16:00
    return sync >= sleep && sync < wake;
  }
  // Overnight window: e.g. 23:00-06:00
  return sync >= sleep || sync < wake;
}
```

- [ ] **Step 3: Commit**

```bash
git add client/src/api/sync.ts client/src/lib/sleep-utils.ts
git commit -m "feat(sync): add frontend preflight API client and sleep window utility"
```

---

### Task 7: Frontend — Schedule Form Sleep Warning

**Files:**
- Modify: `client/src/components/sync-settings/ScheduleFormFields.tsx` — add sleep window warning
- Modify: `client/src/hooks/useSyncSettings.ts` — fetch preflight data

- [ ] **Step 1: Add preflight data to `useSyncSettings` hook**

In `client/src/hooks/useSyncSettings.ts`, add import:

```typescript
import { getSyncPreflight, type SyncPreflightResponse } from '../api/sync';
```

Add a new `useAsyncData` call inside `useSyncSettings()`:

```typescript
  const {
    data: preflight,
  } = useAsyncData<SyncPreflightResponse>(getSyncPreflight);
```

Add `sleepSchedule` to the return object:

```typescript
  return {
    // ... existing fields ...
    sleepSchedule: preflight?.sleep_schedule ?? null,
  };
```

- [ ] **Step 2: Update `ScheduleFormFields` to accept and show sleep warning**

Replace the entire content of `client/src/components/sync-settings/ScheduleFormFields.tsx`:

```tsx
import { useTranslation } from 'react-i18next';
import { AlertTriangle } from 'lucide-react';
import { isTimeInSleepWindow } from '../../lib/sleep-utils';

const WEEKDAYS = [
  { value: 0, label: 'Mo' },
  { value: 1, label: 'Di' },
  { value: 2, label: 'Mi' },
  { value: 3, label: 'Do' },
  { value: 4, label: 'Fr' },
  { value: 5, label: 'Sa' },
  { value: 6, label: 'So' },
];

interface SleepScheduleInfo {
  enabled: boolean;
  sleep_time: string;
  wake_time: string;
  mode: string;
}

interface ScheduleFormFieldsProps {
  scheduleType: string;
  scheduleTime: string;
  dayOfWeek: number;
  dayOfMonth: number;
  onChangeType: (type: string) => void;
  onChangeTime: (time: string) => void;
  onChangeDayOfWeek: (day: number) => void;
  onChangeDayOfMonth: (day: number) => void;
  sleepSchedule?: SleepScheduleInfo | null;
}

export function ScheduleFormFields({
  scheduleType,
  scheduleTime,
  dayOfWeek,
  dayOfMonth,
  onChangeType,
  onChangeTime,
  onChangeDayOfWeek,
  onChangeDayOfMonth,
  sleepSchedule,
}: ScheduleFormFieldsProps) {
  const { t } = useTranslation('settings');

  const inSleepWindow = sleepSchedule?.enabled
    ? isTimeInSleepWindow(scheduleTime, sleepSchedule.sleep_time, sleepSchedule.wake_time)
    : false;

  return (
    <>
      {/* Schedule Type */}
      <div>
        <label className="block text-sm text-slate-400 mb-1">{t('sync.scheduleType')}</label>
        <select
          value={scheduleType}
          onChange={(e) => onChangeType(e.target.value)}
          className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
        >
          <option value="daily">{t('sync.daily')}</option>
          <option value="weekly">{t('sync.weekly')}</option>
          <option value="monthly">{t('sync.monthly')}</option>
        </select>
      </div>

      {/* Time */}
      <div>
        <label className="block text-sm text-slate-400 mb-1">{t('sync.time')}</label>
        <input
          type="time"
          value={scheduleTime}
          onChange={(e) => onChangeTime(e.target.value)}
          className={`w-full px-3 py-2 bg-slate-800 border rounded-lg text-slate-100 ${
            inSleepWindow ? 'border-amber-500' : 'border-slate-700'
          }`}
        />
        {inSleepWindow && (
          <div className="mt-2 flex items-start gap-2 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
            <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
            <span className="text-sm text-amber-300">
              {t('sync.sleepWindowWarning', {
                sleepTime: sleepSchedule!.sleep_time,
                wakeTime: sleepSchedule!.wake_time,
              })}
            </span>
          </div>
        )}
      </div>

      {/* Day of Week (for weekly) */}
      {scheduleType === 'weekly' && (
        <div>
          <label className="block text-sm text-slate-400 mb-1">{t('sync.dayOfWeek')}</label>
          <div className="flex gap-1">
            {WEEKDAYS.map((day) => (
              <button
                key={day.value}
                type="button"
                onClick={() => onChangeDayOfWeek(day.value)}
                className={`flex-1 px-2 py-2 rounded-lg text-sm font-medium transition-colors ${
                  dayOfWeek === day.value
                    ? 'bg-sky-500 text-white'
                    : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                }`}
              >
                {day.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Day of Month (for monthly) */}
      {scheduleType === 'monthly' && (
        <div>
          <label className="block text-sm text-slate-400 mb-1">{t('sync.dayOfMonth')}</label>
          <select
            value={dayOfMonth}
            onChange={(e) => onChangeDayOfMonth(parseInt(e.target.value))}
            className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-100"
          >
            {Array.from({ length: 31 }, (_, i) => i + 1).map((day) => (
              <option key={day} value={day}>{day}.</option>
            ))}
          </select>
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 3: Wire the sleep schedule through `SyncSettings.tsx`**

In `client/src/components/SyncSettings.tsx`, update the destructuring from `useSyncSettings`:

```typescript
  const {
    // ... existing fields ...
    sleepSchedule,
  } = useSyncSettings();
```

Pass `sleepSchedule` to `ScheduleFormFields`:

```tsx
              <ScheduleFormFields
                scheduleType={scheduleType}
                scheduleTime={scheduleTime}
                dayOfWeek={dayOfWeek}
                dayOfMonth={dayOfMonth}
                onChangeType={setScheduleType}
                onChangeTime={setScheduleTime}
                onChangeDayOfWeek={setDayOfWeek}
                onChangeDayOfMonth={setDayOfMonth}
                sleepSchedule={sleepSchedule}
              />
```

Disable the create button when time is in sleep window. Import `isTimeInSleepWindow`:

```typescript
import { isTimeInSleepWindow } from '../lib/sleep-utils';
```

Update the button:

```tsx
            <button
              onClick={onCreate}
              disabled={
                !selectedDevice ||
                (sleepSchedule?.enabled
                  ? isTimeInSleepWindow(scheduleTime, sleepSchedule.sleep_time, sleepSchedule.wake_time)
                  : false)
              }
              className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
            >
              {t('sync.createScheduleBtn')}
            </button>
```

- [ ] **Step 4: Add i18n key for the warning**

Find and edit the settings translation file. Add:

```json
"sleepWindowWarning": "Dieser Zeitpunkt liegt im Sleep-Fenster ({{sleepTime}}\u2013{{wakeTime}}). Der Sync wird nicht ausgefuehrt."
```

- [ ] **Step 5: Commit**

```bash
git add client/src/hooks/useSyncSettings.ts client/src/components/sync-settings/ScheduleFormFields.tsx client/src/components/SyncSettings.tsx
git commit -m "feat(sync): add sleep window warning to schedule form"
```

---

### Task 8: Frontend — Schedule List Sleep Conflict Icons

**Files:**
- Modify: `client/src/components/sync-settings/ScheduleList.tsx` — add warning icons

- [ ] **Step 1: Update `ScheduleList` to accept sleep schedule and show warnings**

In `client/src/components/sync-settings/ScheduleList.tsx`:

Add imports:

```typescript
import { AlertTriangle } from 'lucide-react';
import { isTimeInSleepWindow } from '../../lib/sleep-utils';
```

Update the `ScheduleListProps` interface:

```typescript
interface SleepScheduleInfo {
  enabled: boolean;
  sleep_time: string;
  wake_time: string;
  mode: string;
}

interface ScheduleListProps {
  schedules: SyncSchedule[];
  devices: SyncDevice[];
  onUpdate: (id: number, form: ScheduleFormData) => Promise<boolean>;
  onDisable: (id: number) => Promise<void>;
  sleepSchedule?: SleepScheduleInfo | null;
}
```

Update the function signature:

```typescript
export function ScheduleList({ schedules, devices, onUpdate, onDisable, sleepSchedule }: ScheduleListProps) {
```

Inside the schedule `.map()`, after the `<span>` showing `getScheduleDescription(schedule)`, add:

```tsx
                    {sleepSchedule?.enabled &&
                      isTimeInSleepWindow(schedule.time_of_day, sleepSchedule.sleep_time, sleepSchedule.wake_time) && (
                        <span
                          className="inline-flex items-center gap-1 px-2 py-1 bg-amber-500/20 text-amber-400 text-xs rounded-full border border-amber-500/30"
                          title={`Wird blockiert durch Sleep-Schedule (${sleepSchedule.sleep_time}–${sleepSchedule.wake_time})`}
                        >
                          <AlertTriangle className="w-3 h-3" />
                          Sleep
                        </span>
                      )}
```

Also pass `sleepSchedule` to `ScheduleFormFields` inside the edit modal:

```tsx
              <ScheduleFormFields
                scheduleType={editType}
                scheduleTime={editTime}
                dayOfWeek={editDayOfWeek}
                dayOfMonth={editDayOfMonth}
                onChangeType={setEditType}
                onChangeTime={setEditTime}
                onChangeDayOfWeek={setEditDayOfWeek}
                onChangeDayOfMonth={setEditDayOfMonth}
                sleepSchedule={sleepSchedule}
              />
```

- [ ] **Step 2: Wire sleep schedule in `SyncSettings.tsx`**

Pass `sleepSchedule` to `ScheduleList`:

```tsx
        <ScheduleList
          schedules={schedules}
          devices={devices}
          onUpdate={handleUpdateSchedule}
          onDisable={handleDisableSchedule}
          sleepSchedule={sleepSchedule}
        />
```

- [ ] **Step 3: Commit**

```bash
git add client/src/components/sync-settings/ScheduleList.tsx client/src/components/SyncSettings.tsx
git commit -m "feat(sync): show sleep conflict warnings on existing schedules"
```

---

### Task 9: Final Integration Test + i18n

**Files:**
- Verify i18n keys exist
- Run full backend test suite
- Manual smoke test

- [ ] **Step 1: Find and update the settings i18n file**

Locate the German locale file for the `settings` namespace and add the `sleepWindowWarning` key (see Task 7 Step 4). If using English fallback, add to both.

- [ ] **Step 2: Run full backend test suite**

Run: `cd backend && python -m pytest tests/test_sync_sleep_check.py tests/test_sync_preflight.py tests/test_sync_guard.py tests/test_sync_schedule_validation.py tests/test_sleep.py -v`
Expected: All tests PASS

- [ ] **Step 3: Build frontend to verify no TypeScript errors**

Run: `cd client && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 4: Commit any remaining i18n changes**

```bash
git add -A
git commit -m "feat(sync): add sleep-aware sync i18n keys"
```
