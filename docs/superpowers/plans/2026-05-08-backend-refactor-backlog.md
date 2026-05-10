# Backend Refactor Backlog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Address every finding from the 2026-05-08 backend refactor audit (7 carry-overs from 2026-05-04 + 6 new findings) without changing observable behavior or breaking the 4-worker production deployment.

**Architecture:** Refactors are sequenced in 9 phases ordered by risk, with quick wins first, then unification refactors, service-layer extractions, and finally the two god-class splits. Each phase produces working, testable software and ends in a PR to `main`. Phases 8 and 9 (PowerManager split and SleepManager split) are scoped here as architecture decisions; detailed task breakdowns are deferred to two follow-up plans because each requires its own multi-day test design.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0+, pytest, pytest-asyncio, slowapi.

---

## Critical Multi-Worker Constraint

Production runs **4 Uvicorn workers**. Exactly one becomes "primary" via `fcntl.flock` on `/tmp/baluhost-primary.lock` (see `backend/app/core/lifespan.py:60-99`). Hardware-controlling singletons (`PowerManagerService`, `MonitoringOrchestrator`, `FanControlService`, GPU manager) only own hardware on the primary worker; followers run in read-only/proxy mode and route mutations through the DB-backed command queue (`app/services/power/command_queue.py` and friends) or read shared state from `/tmp/baluhost_shm/` JSON files.

**Anything in this plan that touches a singleton MUST preserve:**

1. The `start(primary: bool)` parameter on `PowerManagerService`, `MonitoringOrchestrator`, `FanControlService`, `GpuPowerManagerService`, and the `start_power_manager(primary: bool)` / `start_gpu_power_manager(primary: bool)` / `start_monitoring(...)` module-level entry points.
2. The `_primary` field semantics on each service.
3. The `command_queue` and `config_store` interfaces (DB schema, polling cadence).
4. The SHM file format under `/tmp/baluhost_shm/`.
5. The `IS_PRIMARY_WORKER` flag in `app/core/lifespan.py`.

Each task that modifies a singleton lists "**Multi-worker check**" with the exact verification command.

---

## File Structure (Net New / Modified)

| Path | Status | Phase | Responsibility |
|---|---|---|---|
| `backend/app/services/files/permissions.py` | **new** | 3 | FileShare CRUD service (extracted from routes/files.py) |
| `backend/app/services/files/mountpoints.py` | **new** | 3 | Mountpoint enumeration + breakdown (extracted from routes/files.py) |
| `backend/app/services/pihole/ad_discovery/patterns_service.py` | **new** | 5 | Pattern CRUD service |
| `backend/app/services/pihole/ad_discovery/suspects_service.py` | **new** | 5 | Suspect listing + filtering service |
| `backend/app/core/exceptions.py` | **new** | 6 | `ServiceError` hierarchy |
| `backend/app/core/exception_handlers.py` | **new** | 6 | App-level exception handlers (registered in `main.py`) |
| `backend/tests/services/files/test_permissions_service.py` | **new** | 3 | Tests for new permissions service |
| `backend/tests/services/files/test_mountpoints_service.py` | **new** | 3 | Tests for new mountpoints service |
| `backend/tests/services/files/test_metadata_db_bulk_ensure.py` | **new** | 4 | Tests for bulk ensure_metadata |
| `backend/tests/services/test_singleton_consistency.py` | **new** | 2 | Tests asserting one canonical accessor per service |
| `backend/tests/api/test_exception_handlers.py` | **new** | 6 | Tests for global exception handler |
| `backend/app/api/routes/power.py` | modify | 1 | Use `Depends(get_db)` (drop direct `SessionLocal()`); single `get_power_status()` call |
| `backend/app/api/routes/files.py` | modify | 1, 3, 4 | Async `list_files`; hoisted imports; thin route handlers |
| `backend/app/api/routes/ad_discovery.py` | modify | 5 | Delegate CRUD to services |
| `backend/app/api/routes/fans.py` | modify | 6 | Drop generic `Exception` handlers (replaced by app-level handler) |
| `backend/app/services/power/manager.py` | modify | 2 | Drop `__new__` + class `_instance`; keep module-level singleton |
| `backend/app/services/monitoring/orchestrator.py` | modify | 2 | Drop class `_instance` + `get_instance()`; keep module-level singleton |
| `backend/app/services/power/fan_control.py` | modify | 2 | Drop class `_instance`; expose module-level `get_fan_control_service()` |
| `backend/app/services/files/operations.py` | modify | 4, 7 | Bulk `ensure_metadata` in `list_directory`; remove dead re-exports |
| `backend/app/services/files/metadata_db.py` | modify | 4 | Add `ensure_metadata_bulk()` |
| `backend/app/main.py` | modify | 6 | Register exception handlers |

Phases 8 and 9 have their own file structures documented in their dedicated plans (referenced below).

---

## Phase 0 — Pre-flight

### Task 0.1: Capture baseline

**Files:** none

- [ ] **Step 1: Verify clean working tree on `main`**

```bash
cd "D:/Programme (x86)/Baluhost"
git status
git switch main
git pull --ff-only
```

Expected: `nothing to commit, working tree clean`. If not, stash or commit existing work first.

- [ ] **Step 2: Run full backend test suite for green baseline**

```bash
cd "D:/Programme (x86)/Baluhost/backend"
python -m pytest -x -q 2>&1 | tee ../.tmp_baseline.txt
```

Expected: all tests pass. If any fail on `main` already, note them in `.tmp_baseline.txt` so they can be ignored later (they are not regressions caused by this plan).

- [ ] **Step 3: Record line counts of files about to change**

```bash
wc -l "D:/Programme (x86)/Baluhost/backend/app/services/power/manager.py" \
      "D:/Programme (x86)/Baluhost/backend/app/services/power/sleep.py" \
      "D:/Programme (x86)/Baluhost/backend/app/services/monitoring/orchestrator.py" \
      "D:/Programme (x86)/Baluhost/backend/app/services/power/fan_control.py" \
      "D:/Programme (x86)/Baluhost/backend/app/api/routes/files.py" \
      "D:/Programme (x86)/Baluhost/backend/app/api/routes/ad_discovery.py" \
      "D:/Programme (x86)/Baluhost/backend/app/api/routes/fans.py" \
      > ../.tmp_baseline_lines.txt
```

These line counts are referenced in later tasks to verify that big refactors actually shrunk the source files.

---

## Phase 1 — Quick Wins

Four small, low-risk fixes. Each is its own commit, all on one feature branch with one PR at the end of the phase.

```bash
git switch -c refactor/quick-wins
```

### Task 1.1: Drop direct `SessionLocal()` from power route auth dependency (#6)

**Files:**
- Modify: `backend/app/api/routes/power.py:23-64`

- [ ] **Step 1: Write a failing test asserting the dependency uses `get_db`**

Create `backend/tests/api/test_power_auth_dependency.py`:

```python
"""Test that the power route auth dependency does not bypass get_db."""
import inspect

from app.api.routes import power as power_routes


def test_admin_or_service_token_uses_get_db_dependency():
    """The dependency must accept a Session via Depends(get_db), not open SessionLocal()."""
    sig = inspect.signature(power_routes._get_admin_or_service_token)
    params = sig.parameters

    # Must have a `db` parameter (the FastAPI Session injection)
    assert "db" in params, "Auth dependency should inject a Session via Depends(get_db)"

    # The dependency must not call SessionLocal() inside its body
    src = inspect.getsource(power_routes._get_admin_or_service_token)
    assert "SessionLocal" not in src, (
        "Auth dependency should not call SessionLocal() directly — use Depends(get_db) instead"
    )
```

- [ ] **Step 2: Run test, confirm it fails**

```bash
cd "D:/Programme (x86)/Baluhost/backend"
python -m pytest tests/api/test_power_auth_dependency.py -v
```

Expected: FAIL — current code uses `SessionLocal`.

- [ ] **Step 3: Rewrite the dependency to use `Depends(get_db)`**

Replace the existing `_get_admin_or_service_token` body in `backend/app/api/routes/power.py`:

```python
async def _get_admin_or_service_token(
    request: Request,
    token: Optional[str] = Depends(_oauth2_scheme),
    db: Session = Depends(deps.get_db),
) -> None:
    """Accept either a valid admin JWT or the scheduler service token."""
    service_token = request.headers.get("X-Service-Token")
    if service_token and service_token == settings.scheduler_service_token:
        return

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    from app.services import auth as auth_service, users as user_service
    try:
        payload = auth_service.decode_token(token)
    except auth_service.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    user = user_service.get_user(payload.sub, db=db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    user_pub = user_service.serialize_user(user)
    if user_pub.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
```

Add `from sqlalchemy.orm import Session` to the imports at the top of the file.

- [ ] **Step 4: Run the new test + the existing power-route tests**

```bash
python -m pytest tests/api/test_power_auth_dependency.py tests/api/ -k power -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/power.py backend/tests/api/test_power_auth_dependency.py
git commit -m "refactor(power): drop SessionLocal() from auth dependency, use Depends(get_db)"
```

### Task 1.2: Make `list_files` async (#11)

**Files:**
- Modify: `backend/app/api/routes/files.py:562-604`

- [ ] **Step 1: Note: existing tests cover this route**

`backend/tests/api/test_files_routes.py` exercises `/files/list`. We rely on those for regression coverage; no new test required for the async conversion (it is a structural change, not a behavior change).

- [ ] **Step 2: Convert handler signature and offload sync work**

In `backend/app/api/routes/files.py`, change `def list_files(...)` to `async def list_files(...)` and wrap the only blocking call (`file_service.list_directory(...)`) in `asyncio.to_thread`:

```python
@router.get("/list", response_model=FileListResponse)
@user_limiter.limit(get_limit("file_list"))
async def list_files(
    request: Request,
    response: Response,
    path: str = "",
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FileListResponse:
    audit_logger = get_audit_logger_db()
    original_path = path

    if not is_privileged(user) and not original_path.strip("/"):
        entries = list_user_root(user, db)
        entries = _enrich_with_sync_info(entries, user.id, False, db)
        return FileListResponse(files=entries)

    if not is_privileged(user) and original_path.strip("/") == SHARED_WITH_ME_DIR:
        entries = list_shared_with_me(user, db)
        entries = _enrich_with_sync_info(entries, user.id, False, db)
        return FileListResponse(files=entries)

    jailed_path = _jail_path(path, user, db)

    try:
        entries = await asyncio.to_thread(
            lambda: list(file_service.list_directory(jailed_path, user=user, db=db))
        )
    except PermissionDeniedError as exc:
        audit_logger.log_authorization_failure(
            user=user.username,
            action="list_directory",
            resource=jailed_path,
            required_permission="read",
            db=db,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except file_service.FileAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    entries = _enrich_with_sync_info(entries, user.id, is_privileged(user), db)
    return FileListResponse(files=entries)
```

Add `import asyncio` at the top of `files.py` if it is not already there.

- [ ] **Step 3: Run the existing files-route tests**

```bash
python -m pytest tests/api -k "files" -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes/files.py
git commit -m "refactor(files): make list_files async, offload list_directory to to_thread"
```

### Task 1.3: Eliminate the duplicate `get_power_status()` call in `set_power_profile` (#8)

**Files:**
- Modify: `backend/app/api/routes/power.py:131-166`

- [ ] **Step 1: Write a failing test that counts `get_power_status` invocations**

Create `backend/tests/api/test_power_set_profile_efficiency.py`:

```python
"""Regression: set_power_profile must not call get_power_status() twice."""
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_set_power_profile_calls_status_at_most_once(client, admin_headers):
    """Setting a profile should not need a full status fetch + a second one for diff."""
    from app.services.power.manager import get_power_manager

    manager = get_power_manager()

    call_count = {"n": 0}
    real_status = manager.get_power_status

    async def counting_status():
        call_count["n"] += 1
        return await real_status()

    with patch.object(manager, "get_power_status", side_effect=counting_status):
        response = client.post(
            "/api/power/profile",
            json={"profile": "balanced"},
            headers=admin_headers,
        )
        assert response.status_code in (200, 500)  # 500 is fine if backend can't apply
    assert call_count["n"] <= 1, (
        f"get_power_status() was called {call_count['n']} times — should be 0 or 1"
    )
```

- [ ] **Step 2: Run test, confirm it fails**

```bash
python -m pytest tests/api/test_power_set_profile_efficiency.py -v
```

Expected: FAIL — current code calls it twice.

- [ ] **Step 3: Read previous profile from `manager._current_profile` instead**

In `backend/app/api/routes/power.py`, replace `set_power_profile` body:

```python
@router.post("/profile", response_model=SetProfileResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def set_power_profile(
    request: Request, response: Response,
    body: SetProfileRequest,
    user: UserPublic = Depends(deps.get_current_admin)
) -> SetProfileResponse:
    """Manually set a power profile (admin only)."""
    manager = get_power_manager()
    previous_profile = manager._current_profile  # cached state, no extra DB/SHM hit

    reason = body.reason or f"Manual override by {user.username}"
    success, error_msg = await manager.apply_profile(
        profile=body.profile,
        reason=reason,
        duration_seconds=body.duration_seconds,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg or "Failed to apply power profile",
        )

    return SetProfileResponse(
        success=True,
        message=f"Profile changed to {body.profile.value}",
        previous_profile=previous_profile,
        new_profile=body.profile,
        applied_at=datetime.now(timezone.utc),
    )
```

- [ ] **Step 4: Multi-worker check**

On follower workers `_current_profile` is hydrated from `runtime_state` only when `get_power_status()` is called (see `manager.py:900-907`). For the `set_power_profile` route specifically, primary-worker semantics apply because `apply_profile` is a mutation. Verify followers still produce a sensible `previous_profile`:

```bash
grep -n "_hydrate_from_runtime_state" "D:/Programme (x86)/Baluhost/backend/app/services/power/manager.py"
```

Expected: `_hydrate_from_runtime_state` is called inside `apply_profile` for follower paths (or the mutation is rejected). If neither, add a single `if not self._primary: self._hydrate_from_runtime_state()` at the very top of `apply_profile`. (Inspect first; do not add if already present.)

- [ ] **Step 5: Run test, confirm it passes**

```bash
python -m pytest tests/api/test_power_set_profile_efficiency.py tests/api -k power -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/power.py backend/tests/api/test_power_set_profile_efficiency.py
git commit -m "refactor(power): read previous profile from cached state in set_power_profile"
```

### Task 1.4: Hoist local imports in `files.py` (#12)

**Files:**
- Modify: `backend/app/api/routes/files.py` — top of file + bodies at `~217-218, 254-255, 269-270, 300-301, 306-307, 345-346, 1019`

- [ ] **Step 1: Confirm the imports do not introduce circular imports**

The function-local imports likely existed to dodge cycles. Verify with a quick smoke check by adding the imports temporarily at the top and importing the routes module:

```bash
python -c "from app.api.routes import files; print('ok')"
```

If that fails with `ImportError: cannot import name … (most likely due to a circular import)`, document the cycle and use `TYPE_CHECKING` guards for type-only references; keep runtime imports local.

- [ ] **Step 2: Add the imports to module top**

In `backend/app/api/routes/files.py`, near the existing imports add:

```python
from app.services.files import metadata_db as file_metadata_db
from app.models.file_share import FileShare
from app.services.files import ownership as ownership_service
```

(Adjust the third line to match the current local-import string at line 1019 — read it first.)

- [ ] **Step 3: Remove the function-local imports**

Search for the local imports inside the bodies (around lines 217-218, 254-255, 269-270, 300-301, 306-307, 345-346, 1019) and delete them. Each deletion should be a one-line removal — the symbol they introduced is now imported at module scope.

- [ ] **Step 4: Run the route module's tests**

```bash
python -m pytest tests/api -k "files" -v
```

Expected: all pass. If a circular-import error appears, revert the offending import to function-local and add a `# circular: keep local` comment beside it.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/files.py
git commit -m "refactor(files): hoist function-local imports to module level"
```

### Task 1.5: Run full suite, push, open PR (Phase 1)

- [ ] **Step 1: Full suite**

```bash
cd "D:/Programme (x86)/Baluhost/backend"
python -m pytest -x -q
```

Expected: all green.

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin refactor/quick-wins
gh pr create --base main --title "refactor: backend audit quick wins (#6 #8 #11 #12)" --body "$(cat <<'EOF'
## Summary
- power route auth dependency uses Depends(get_db) (#6)
- list_files is async, sync work via asyncio.to_thread (#11)
- set_power_profile reads previous profile from cached state (#8)
- files.py local imports hoisted to module level (#12)

## Test plan
- [x] tests/api/test_power_auth_dependency.py
- [x] tests/api/test_power_set_profile_efficiency.py
- [x] tests/api/ -k files
- [x] full backend suite green

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Switch back to `main` after PR merge**

```bash
git switch main
git pull --ff-only
```

---

## Phase 2 — Singleton Unification (#5 + B1)

**Decision:** Adopt **module-level singleton** as the canonical pattern. Drop `__new__` and class `_instance` from `PowerManagerService`, drop class `_instance` + classmethod `get_instance()` from `MonitoringOrchestrator` and `FanControlService`. The accessor is the existing module-level function (`get_power_manager()`, `get_monitoring_orchestrator()`, `get_fan_control_service()`); FanControl needs that function created.

**Why module-level:**
- It already exists for two of the three services and is used by all production callers.
- Tests can reset by patching the module-level reference (one place per service).
- No `__new__` magic; classes become normal classes and easier to subclass in tests.
- Multi-worker semantics are unaffected: each Uvicorn worker has its own module instance, primary/follower routing happens via `start(primary=...)` and the DB command queue (unchanged).

```bash
git switch -c refactor/singleton-unification
```

### Task 2.1: Add cross-service consistency test

**Files:**
- Create: `backend/tests/services/test_singleton_consistency.py`

- [ ] **Step 1: Write the consistency test**

```python
"""Cross-service test: each hardware singleton must have exactly one canonical accessor.

Class-level _instance + get_instance() patterns coexisting with a module-level
global caused inconsistent state across tests. This test enforces the rule.
"""
import pytest


def test_power_manager_no_class_instance():
    from app.services.power import manager as m

    assert not hasattr(m.PowerManagerService, "_instance"), (
        "PowerManagerService._instance must be removed; use module-level _power_manager"
    )
    assert callable(m.get_power_manager)


def test_monitoring_orchestrator_no_class_instance():
    from app.services.monitoring import orchestrator as o

    assert not hasattr(o.MonitoringOrchestrator, "_instance"), (
        "MonitoringOrchestrator._instance must be removed; use module-level _orchestrator"
    )
    assert not hasattr(o.MonitoringOrchestrator, "get_instance"), (
        "MonitoringOrchestrator.get_instance must be removed; use get_monitoring_orchestrator()"
    )
    assert callable(o.get_monitoring_orchestrator)


def test_fan_control_service_module_level_accessor():
    from app.services.power import fan_control as f

    assert callable(getattr(f, "get_fan_control_service", None)), (
        "fan_control module must expose get_fan_control_service() at module level"
    )
    # The classmethod may stay as a thin wrapper for backward-compat, but the
    # canonical entry point is the module-level function.


def test_power_manager_returns_same_instance_repeatedly():
    from app.services.power.manager import get_power_manager

    a = get_power_manager()
    b = get_power_manager()
    assert a is b
```

- [ ] **Step 2: Run, confirm it fails**

```bash
python -m pytest tests/services/test_singleton_consistency.py -v
```

Expected: FAIL on at least the first three tests.

### Task 2.2: Migrate `PowerManagerService`

**Files:**
- Modify: `backend/app/services/power/manager.py:72-119`
- Modify: `backend/tests/services/test_power_manager.py` — all `reset_singleton` fixtures

- [ ] **Step 1: Replace `__new__` with a normal `__init__`**

In `backend/app/services/power/manager.py`, replace the class header and `__new__` block (around lines 72-119):

```python
class PowerManagerService:
    """Central service for managing CPU power profiles.

    Process-level singleton — use ``get_power_manager()`` to obtain.
    On a 4-worker deployment each Uvicorn process holds its own instance;
    only the primary worker (``self._primary == True``) owns hardware,
    followers route mutations through the DB-backed command queue.
    """

    def __init__(self):
        self._demands: Dict[str, PowerDemandInfo] = {}
        self._current_profile = PowerProfile.IDLE
        self._current_property: Optional[ServicePowerProperty] = ServicePowerProperty.IDLE
        self._last_profile_change: Optional[datetime] = None
        self._history: List[PowerHistoryEntry] = []
        self._max_history = 1000
        self._auto_scaling_config = AutoScalingConfig()  # type: ignore[call-arg]
        self._cooldown_until: Optional[datetime] = None
        self._manual_override_until: Optional[datetime] = None
        self._cpu_usage_callback: Optional[Callable[[], Optional[float]]] = None
        self._backend: Optional[CpuPowerBackend] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._command_poll_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._primary: bool = True  # set in start()
        self._profiles = DEFAULT_PROFILES.copy()
        self._state_lock = asyncio.Lock()
        self._dynamic_mode_enabled: bool = False
        self._dynamic_mode_config: Optional[DynamicModeConfig] = None
        logger.info("PowerManagerService initialized")
```

Remove the `_instance: Optional[...] = None`, the `_lock = Lock()` class attribute, the `__new__` method, and the `_initialized` guard. Drop the now-unused `from threading import Lock` import.

- [ ] **Step 2: Update test fixtures to reset the module global**

In `backend/tests/services/test_power_manager.py`, replace every occurrence of:

```python
@pytest.fixture(autouse=True)
def reset_singleton(self):
    """Reset singleton before each test."""
    PowerManagerService._instance = None
    yield
    PowerManagerService._instance = None
```

with:

```python
@pytest.fixture(autouse=True)
def reset_singleton(self):
    """Reset module-level singleton before/after each test."""
    from app.services.power import manager as _m
    _m._power_manager = None
    yield
    _m._power_manager = None
```

There are 5+ such fixtures in this file — update all of them.

- [ ] **Step 3: Multi-worker check**

```bash
grep -n "primary\|_primary\|start_power_manager" "D:/Programme (x86)/Baluhost/backend/app/services/power/manager.py" | head -20
```

Expected: `start_power_manager(primary=...)` and `self._primary` are still present and unchanged.

- [ ] **Step 4: Run test_power_manager.py + consistency test**

```bash
python -m pytest tests/services/test_power_manager.py tests/services/test_singleton_consistency.py::test_power_manager_no_class_instance tests/services/test_singleton_consistency.py::test_power_manager_returns_same_instance_repeatedly -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power/manager.py backend/tests/services/test_power_manager.py backend/tests/services/test_singleton_consistency.py
git commit -m "refactor(power): drop __new__ singleton, use module-level _power_manager"
```

### Task 2.3: Migrate `MonitoringOrchestrator`

**Files:**
- Modify: `backend/app/services/monitoring/orchestrator.py:43-115`
- Modify: callers of `MonitoringOrchestrator.get_instance()` if any

- [ ] **Step 1: Find all callers of the classmethod**

```bash
grep -rn "MonitoringOrchestrator.get_instance\|MonitoringOrchestrator\._instance" "D:/Programme (x86)/Baluhost/backend"
```

Expected: a small set, mostly in tests. Note each location.

- [ ] **Step 2: Drop class-level singleton bits**

In `backend/app/services/monitoring/orchestrator.py`:

- Remove the `_instance: Optional["MonitoringOrchestrator"] = None` class attribute (around line 54).
- Remove the `@classmethod def get_instance(cls)` method (around lines 110-115).

The module-level `_orchestrator` global and `get_monitoring_orchestrator()` function (around lines 600-611) stay as-is.

- [ ] **Step 3: Migrate every caller**

For each line found in Step 1 outside the orchestrator file itself, replace `MonitoringOrchestrator.get_instance()` with `get_monitoring_orchestrator()` and `MonitoringOrchestrator._instance = None` with `import app.services.monitoring.orchestrator as _o; _o._orchestrator = None`.

- [ ] **Step 4: Multi-worker check**

```bash
grep -n "primary\|MONITORING_WORKER" "D:/Programme (x86)/Baluhost/backend/app/services/monitoring/orchestrator.py" "D:/Programme (x86)/Baluhost/backend/app/core/service_registry.py"
```

Expected: `MONITORING_WORKER_SERVICES` and primary-only behavior are unchanged.

- [ ] **Step 5: Run monitoring tests**

```bash
python -m pytest tests/services -k monitoring tests/api -k monitoring tests/services/test_singleton_consistency.py::test_monitoring_orchestrator_no_class_instance -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/monitoring/orchestrator.py backend/tests
git commit -m "refactor(monitoring): drop classmethod get_instance, use module-level accessor"
```

### Task 2.4: Migrate `FanControlService`

**Files:**
- Modify: `backend/app/services/power/fan_control.py:120-160` (init + classmethod)
- Modify: `backend/app/api/routes/fans.py:51` (import) and the `get_fan_service` dependency
- Modify: `backend/app/core/lifespan.py` (startup call)

- [ ] **Step 1: Read the current `get_fan_control_service` (already exists?)**

```bash
grep -n "def get_fan_control_service\|FanControlService\.get_instance" "D:/Programme (x86)/Baluhost/backend/app/services/power/fan_control.py"
```

Note whether a module-level `get_fan_control_service()` already exists. (It is imported in `fans.py:51`, so it must exist somewhere — verify and reuse.)

- [ ] **Step 2: Define the canonical module-level accessor**

If `get_fan_control_service()` already exists, ensure its body is exactly:

```python
_fan_control_service: Optional[FanControlService] = None


def get_fan_control_service(
    config: Optional[Settings] = None,
    db_session_factory=None,
) -> FanControlService:
    """Get the module-level FanControlService singleton.

    On first call within a process, ``config`` and ``db_session_factory`` are
    required. Subsequent calls return the cached instance and ignore arguments.
    """
    global _fan_control_service
    if _fan_control_service is None:
        if config is None or db_session_factory is None:
            raise RuntimeError("FanControlService not initialized")
        _fan_control_service = FanControlService(config, db_session_factory)
    return _fan_control_service
```

If it does not exist, add it at the end of the file (after the class definition).

- [ ] **Step 3: Drop class-level singleton bits**

In `FanControlService` (around lines 120-160 of `fan_control.py`):

- Remove the `_instance: Optional[...] = None` and `_lock = asyncio.Lock()` class attributes.
- Remove the `FanControlService._instance = self` line at the end of `__init__` (currently `fan_control.py:140`).
- Remove the `@classmethod async def get_instance(cls, ...)` method.

- [ ] **Step 4: Migrate the lifespan call site**

In `backend/app/core/lifespan.py`, find the existing `FanControlService.get_instance(...)` call (search for it) and replace with:

```python
from app.services.power.fan_control import get_fan_control_service
fan_service = get_fan_control_service(config=settings, db_session_factory=SessionLocal)
await fan_service.start(monitoring=IS_PRIMARY_WORKER)
```

(Adjust the surrounding code to match the existing pattern; do not change `await fan_service.start(...)` semantics.)

- [ ] **Step 5: Multi-worker check**

```bash
grep -n "monitoring=" "D:/Programme (x86)/Baluhost/backend/app/services/power/fan_control.py" "D:/Programme (x86)/Baluhost/backend/app/core/lifespan.py"
```

Expected: `monitoring=` boolean still drives whether the fan control loop owns hardware. Confirm `IS_PRIMARY_WORKER` is still passed.

- [ ] **Step 6: Run fan tests + consistency test**

```bash
python -m pytest tests/services -k "fan" tests/api -k "fan" tests/services/test_singleton_consistency.py::test_fan_control_service_module_level_accessor -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/power/fan_control.py backend/app/api/routes/fans.py backend/app/core/lifespan.py
git commit -m "refactor(fans): drop classmethod get_instance, use module-level get_fan_control_service"
```

### Task 2.5: Phase 2 PR

- [ ] **Step 1: Run full backend suite**

```bash
python -m pytest -x -q
```

- [ ] **Step 2: Manual smoke (dev mode)**

```bash
cd "D:/Programme (x86)/Baluhost"
python start_dev.py
```

In another terminal:

```bash
curl -s http://localhost:3001/api/power/status -H "Authorization: Bearer <admin-token>"
curl -s http://localhost:3001/api/fans/status -H "Authorization: Bearer <admin-token>"
curl -s http://localhost:3001/api/monitoring/cpu -H "Authorization: Bearer <admin-token>"
```

Expected: all return 200. Stop with Ctrl+C.

- [ ] **Step 3: Push & PR**

```bash
git push -u origin refactor/singleton-unification
gh pr create --base main --title "refactor: unify singleton pattern across hardware services (#5 B1)" --body "$(cat <<'EOF'
## Summary
- PowerManagerService: drop __new__/class _instance, keep module-level _power_manager
- MonitoringOrchestrator: drop classmethod get_instance, keep module-level _orchestrator
- FanControlService: drop classmethod get_instance, expose module-level get_fan_control_service
- New cross-service consistency test guards against regression

## Multi-worker preserved
- start(primary=...) signatures unchanged on all three services
- Primary file lock and IS_PRIMARY_WORKER flag untouched
- DB command queue and SHM file format unchanged

## Test plan
- [x] tests/services/test_singleton_consistency.py
- [x] tests/services/test_power_manager.py
- [x] tests/services -k "monitoring" / "fan"
- [x] manual dev-mode smoke

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: Switch back to main after merge**

```bash
git switch main && git pull --ff-only
```

---

## Phase 3 — Service-Layer Extractions for `files.py` (#4)

```bash
git switch -c refactor/files-service-layer
```

### Task 3.1: Extract permissions service

**Files:**
- Create: `backend/app/services/files/permissions.py`
- Create: `backend/tests/services/files/test_permissions_service.py`
- Modify: `backend/app/api/routes/files.py:296-392`

- [ ] **Step 1: Write tests for the new service first**

Create `backend/tests/services/files/test_permissions_service.py`:

```python
"""Tests for the file permissions service (extracted from routes/files.py)."""
import pytest

from app.services.files import permissions as perms_service
from app.schemas.files import FilePermissionRule


def test_get_permissions_returns_owner_and_rules(db_session, sample_file_metadata):
    """get_file_permissions returns the owner and any FileShare rules."""
    result = perms_service.get_file_permissions(
        path=sample_file_metadata.path,
        requesting_user_id=sample_file_metadata.owner_id,
        db=db_session,
    )
    assert result is not None
    assert result.path == sample_file_metadata.path
    assert result.owner_id == sample_file_metadata.owner_id
    assert result.rules == []


def test_get_permissions_returns_none_for_unknown_path(db_session, regular_user):
    """Unknown paths return None (so the route can 404)."""
    result = perms_service.get_file_permissions(
        path="does/not/exist.txt",
        requesting_user_id=regular_user.id,
        db=db_session,
    )
    assert result is None


def test_set_permissions_replaces_rules(db_session, sample_file_metadata, another_user):
    """set_file_permissions atomically replaces all existing rules."""
    new_rules = [
        FilePermissionRule(user_id=another_user.id, can_view=True, can_edit=False, can_delete=False),
    ]
    result = perms_service.set_file_permissions(
        path=sample_file_metadata.path,
        rules=new_rules,
        requesting_user_id=sample_file_metadata.owner_id,
        db=db_session,
    )
    assert len(result.rules) == 1
    assert result.rules[0].user_id == another_user.id
    assert result.rules[0].can_view is True


def test_set_permissions_rejects_non_owner(db_session, sample_file_metadata, another_user):
    """Non-owners cannot change permissions (raises PermissionDeniedError)."""
    from app.services.permissions import PermissionDeniedError
    with pytest.raises(PermissionDeniedError):
        perms_service.set_file_permissions(
            path=sample_file_metadata.path,
            rules=[],
            requesting_user_id=another_user.id,
            db=db_session,
        )
```

- [ ] **Step 2: Run, confirm fail (module doesn't exist)**

```bash
python -m pytest tests/services/files/test_permissions_service.py -v
```

Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Create the service**

Create `backend/app/services/files/permissions.py`:

```python
"""File-permission (FileShare) service.

Extracted from routes/files.py to keep HTTP handlers thin per the
services/CLAUDE.md service-layer convention.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.file_share import FileShare
from app.schemas.files import FilePermissions, FilePermissionRule
from app.services.files import metadata_db as file_metadata_db
from app.services.permissions import ensure_owner_or_privileged
from app.schemas.user import UserPublic


def _serialize_rules(shares: list[FileShare]) -> list[FilePermissionRule]:
    return [
        FilePermissionRule(
            user_id=s.shared_with_user_id,
            can_view=s.can_read,
            can_edit=s.can_write,
            can_delete=s.can_delete,
        )
        for s in shares
    ]


def get_file_permissions(
    *,
    path: str,
    requesting_user_id: int,
    db: Session,
) -> Optional[FilePermissions]:
    """Return permissions for *path* or None if the path has no metadata."""
    metadata = file_metadata_db.ensure_metadata(
        path, requesting_user_id=requesting_user_id, db=db
    )
    if not metadata:
        return None
    shares = db.query(FileShare).filter(FileShare.file_id == metadata.id).all()
    return FilePermissions(
        path=metadata.path,
        owner_id=metadata.owner_id,
        rules=_serialize_rules(shares),
    )


def set_file_permissions(
    *,
    path: str,
    rules: list[FilePermissionRule],
    requesting_user: UserPublic | None = None,
    requesting_user_id: int,
    db: Session,
) -> FilePermissions:
    """Replace all FileShare rules for *path*.

    *requesting_user* is preferred when available (gives privileged-role bypass);
    *requesting_user_id* is the integer fallback used by tests/non-HTTP callers.

    Raises:
        FileNotFoundError: path has no metadata
        PermissionDeniedError: requester is not owner/privileged
    """
    metadata = file_metadata_db.ensure_metadata(
        path, requesting_user_id=requesting_user_id, db=db
    )
    if not metadata:
        raise FileNotFoundError(f"File not found: {path}")

    if requesting_user is not None:
        ensure_owner_or_privileged(requesting_user, str(metadata.owner_id))
    else:
        from app.services.permissions import PermissionDeniedError
        if int(metadata.owner_id) != int(requesting_user_id):
            raise PermissionDeniedError("Only the owner can change permissions")

    db.query(FileShare).filter(FileShare.file_id == metadata.id).delete()
    for rule in rules:
        db.add(FileShare(
            file_id=metadata.id,
            owner_id=metadata.owner_id,
            shared_with_user_id=rule.user_id,
            can_read=rule.can_view,
            can_write=rule.can_edit,
            can_delete=rule.can_delete,
            can_share=False,
        ))
    db.commit()

    shares = db.query(FileShare).filter(FileShare.file_id == metadata.id).all()
    return FilePermissions(
        path=metadata.path,
        owner_id=metadata.owner_id,
        rules=_serialize_rules(shares),
    )
```

- [ ] **Step 4: Run service tests, confirm pass**

```bash
python -m pytest tests/services/files/test_permissions_service.py -v
```

Expected: all pass.

- [ ] **Step 5: Migrate the routes to delegate**

In `backend/app/api/routes/files.py` replace `get_permissions` and `set_permissions` (around lines 296-392) with thin wrappers:

```python
from app.services.files import permissions as perms_service


@router.get("/permissions", response_model=FilePermissions)
@user_limiter.limit(get_limit("file_list"))
async def get_permissions(
    request: Request,
    response: Response,
    path: str,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FilePermissions:
    path = _jail_path(path, user, db)
    result = perms_service.get_file_permissions(
        path=path, requesting_user_id=user.id, db=db
    )
    if result is None:
        raise HTTPException(status_code=404, detail="File not found")
    return result


@router.put("/permissions", response_model=FilePermissions)
@user_limiter.limit(get_limit("file_delete"))
async def set_permissions(
    request: Request,
    response: Response,
    payload: FilePermissionsRequest,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
) -> FilePermissions:
    payload.path = _jail_path(payload.path, user, db)
    try:
        result = perms_service.set_file_permissions(
            path=payload.path,
            rules=payload.rules,
            requesting_user=user,
            requesting_user_id=user.id,
            db=db,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    track_activity(user.id, "file.permission", payload.path)
    return result
```

Remove the now-unused `from app.models.file_share import FileShare` import inside these functions (Phase 1 may already have hoisted it; if so, leave the module-level import — it is used by other code in the file).

- [ ] **Step 6: Run route tests**

```bash
python -m pytest tests/api -k "permissions" tests/services/files -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/files/permissions.py backend/app/api/routes/files.py backend/tests/services/files/test_permissions_service.py
git commit -m "refactor(files): extract permissions service from routes (#4 part 1)"
```

### Task 3.2: Extract mountpoints service

**Files:**
- Create: `backend/app/services/files/mountpoints.py`
- Create: `backend/tests/services/files/test_mountpoints_service.py`
- Modify: `backend/app/api/routes/files.py:395-542`

- [ ] **Step 1: Write the test**

Create `backend/tests/services/files/test_mountpoints_service.py`:

```python
"""Tests for the mountpoints service."""
from app.services.files import mountpoints as mp_service


def test_dev_mode_returns_dev_storage_and_mock_arrays(db_session, monkeypatch):
    """In dev mode the service returns dev-storage + mock RAID arrays."""
    monkeypatch.setattr("app.core.config.settings.is_dev_mode", True)
    response = mp_service.get_mountpoints(db=db_session)

    assert response.default_mountpoint == "dev-storage"
    ids = [m.id for m in response.mountpoints]
    assert "dev-storage" in ids


def test_response_has_default_mountpoint(db_session, monkeypatch):
    """The default_mountpoint must point to one of the listed mountpoints."""
    monkeypatch.setattr("app.core.config.settings.is_dev_mode", True)
    response = mp_service.get_mountpoints(db=db_session)
    ids = [m.id for m in response.mountpoints]
    assert response.default_mountpoint in ids
```

- [ ] **Step 2: Confirm fail**

```bash
python -m pytest tests/services/files/test_mountpoints_service.py -v
```

Expected: FAIL — ModuleNotFoundError.

- [ ] **Step 3: Create the service**

Create `backend/app/services/files/mountpoints.py`. Move the entire body of the `get_mountpoints` route (the ~130-line block currently at `routes/files.py:395-542`) into a function:

```python
"""Mountpoint enumeration service.

Extracted from routes/files.py — pure business logic, no FastAPI dependencies.
"""
from __future__ import annotations

import logging
import shutil

import psutil
from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.storage import MountpointsResponse, StorageMountpoint
from app.services.files import operations as file_service
from app.services.files.operations import ROOT_DIR
from app.services.hardware import raid as raid_service
from app.services.hardware.raid import find_raid_mountpoint
from app.services.storage_breakdown import compute_storage_breakdown

logger = logging.getLogger(__name__)


def _dev_mode_mountpoints(db: Session) -> list[StorageMountpoint]:
    raid_status = raid_service.get_status()
    used_bytes = file_service.calculate_used_bytes()
    quota_bytes = settings.nas_quota_bytes or 0
    available_bytes = file_service.calculate_available_bytes()

    from pathlib import Path
    dev_mp_path = str(Path(settings.nas_storage_path).resolve())
    breakdown = compute_storage_breakdown(dev_mp_path, used_bytes, db)

    out: list[StorageMountpoint] = [StorageMountpoint(
        id="dev-storage",
        name="Dev Storage",
        type="dev-storage",
        path="",
        size_bytes=quota_bytes,
        used_bytes=used_bytes,
        available_bytes=available_bytes,
        status="optimal",
        is_default=True,
        breakdown=breakdown,
    )]
    for array in raid_status.arrays:
        out.append(StorageMountpoint(
            id=array.name,
            name=f"{array.level.upper()} Setup - {array.name}",
            type="raid",
            path=f"/{array.name}",
            size_bytes=array.size_bytes,
            used_bytes=0,
            available_bytes=array.size_bytes,
            raid_level=array.level,
            status=array.status,
            is_default=False,
        ))
    return out


def _prod_mode_mountpoints(db: Session) -> list[StorageMountpoint]:
    raid_status = raid_service.get_status()
    raid_arrays = raid_status.arrays

    if raid_arrays:
        primary = raid_arrays[0]
        raid_mountpoint = find_raid_mountpoint(primary.name)
        if raid_mountpoint:
            usage = psutil.disk_usage(raid_mountpoint)
            size_bytes, used_bytes, available_bytes = usage.total, usage.used, usage.free
        else:
            logger.warning("RAID %s not mounted. Showing ROOT_DIR values.", primary.name)
            try:
                fallback = shutil.disk_usage(ROOT_DIR)
                size_bytes, used_bytes, available_bytes = fallback.total, fallback.used, fallback.free
            except Exception:
                size_bytes = used_bytes = available_bytes = 0

        worst_status = "optimal"
        for a in raid_arrays:
            if a.status == "degraded":
                worst_status = "degraded"
                break
            if a.status == "rebuilding" and worst_status != "degraded":
                worst_status = "rebuilding"

        breakdown = compute_storage_breakdown(
            raid_mountpoint or str(ROOT_DIR), used_bytes, db,
        )
        return [StorageMountpoint(
            id=primary.name,
            name=f"{primary.level.upper()} Storage - {primary.name}",
            type="raid",
            path="",
            size_bytes=size_bytes,
            used_bytes=used_bytes,
            available_bytes=available_bytes,
            raid_level=primary.level,
            status=worst_status,
            is_default=True,
            breakdown=breakdown,
        )]

    try:
        disk_usage = shutil.disk_usage(ROOT_DIR)
        size_bytes, used_bytes, available_bytes = disk_usage.total, disk_usage.used, disk_usage.free
    except Exception:
        size_bytes = used_bytes = available_bytes = 0

    breakdown = compute_storage_breakdown(str(ROOT_DIR), used_bytes, db)
    return [StorageMountpoint(
        id="storage",
        name="Storage",
        type="storage",
        path="",
        size_bytes=size_bytes,
        used_bytes=used_bytes,
        available_bytes=available_bytes,
        raid_level=None,
        status="optimal",
        is_default=True,
        breakdown=breakdown,
    )]


def get_mountpoints(*, db: Session) -> MountpointsResponse:
    """Return the list of storage mountpoints for the dashboard."""
    if settings.is_dev_mode:
        mountpoints = _dev_mode_mountpoints(db)
    else:
        mountpoints = _prod_mode_mountpoints(db)

    default_id = next(
        (m.id for m in mountpoints if m.is_default),
        mountpoints[0].id if mountpoints else "dev-storage",
    )
    return MountpointsResponse(
        mountpoints=mountpoints,
        default_mountpoint=default_id,
    )
```

- [ ] **Step 4: Confirm tests pass**

```bash
python -m pytest tests/services/files/test_mountpoints_service.py -v
```

Expected: pass.

- [ ] **Step 5: Replace the route with a thin wrapper**

In `backend/app/api/routes/files.py` replace `get_mountpoints` (currently lines 395-542) with:

```python
from app.services.files import mountpoints as mountpoints_service


@router.get("/mountpoints")
@user_limiter.limit(get_limit("file_list"))
async def get_mountpoints(
    request: Request,
    response: Response,
    user: UserPublic = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    """Get list of available storage mountpoints (RAID arrays, disks, etc.)."""
    return mountpoints_service.get_mountpoints(db=db)
```

Drop the now-unused imports inside the route body.

- [ ] **Step 6: Run route + service tests**

```bash
python -m pytest tests/api -k "mountpoints" tests/services/files -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/files/mountpoints.py backend/app/api/routes/files.py backend/tests/services/files/test_mountpoints_service.py
git commit -m "refactor(files): extract mountpoints service from routes (#4 part 2)"
```

### Task 3.3: Phase 3 PR

- [ ] **Step 1: Full suite**

```bash
python -m pytest -x -q
```

- [ ] **Step 2: Push & PR**

```bash
git push -u origin refactor/files-service-layer
gh pr create --base main --title "refactor: extract permissions + mountpoints services from files routes (#4)" --body "$(cat <<'EOF'
## Summary
- New services/files/permissions.py — FileShare CRUD
- New services/files/mountpoints.py — mountpoint enumeration
- routes/files.py: permission + mountpoint handlers reduced to thin wrappers (~10 lines each, was 230+ combined)

## Test plan
- [x] tests/services/files/test_permissions_service.py
- [x] tests/services/files/test_mountpoints_service.py
- [x] tests/api -k "files" / "permissions" / "mountpoints"

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
git switch main && git pull --ff-only
```

---

## Phase 4 — N+1 Fix in `list_directory` (#7)

```bash
git switch -c refactor/list-directory-bulk-ensure
```

### Task 4.1: Add `ensure_metadata_bulk()`

**Files:**
- Modify: `backend/app/services/files/metadata_db.py:421-477`
- Create: `backend/tests/services/files/test_metadata_db_bulk_ensure.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/services/files/test_metadata_db_bulk_ensure.py`:

```python
"""Tests for ensure_metadata_bulk."""
from pathlib import Path

from app.services.files import metadata_db


def test_bulk_ensure_creates_missing_directories(db_session, regular_user, tmp_path, monkeypatch):
    """ensure_metadata_bulk creates a metadata row for each on-disk dir lacking one."""
    monkeypatch.setattr("app.services.files.path_utils._resolve_path", lambda p: tmp_path / p)
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / "gamma").mkdir()

    result = metadata_db.ensure_metadata_bulk(
        ["alpha", "beta", "gamma"],
        requesting_user_id=regular_user.id,
        db=db_session,
    )
    assert set(result.keys()) == {"alpha", "beta", "gamma"}
    for path, meta in result.items():
        assert meta is not None
        assert meta.path == path
        assert meta.is_directory is True


def test_bulk_ensure_skips_paths_not_on_disk(db_session, regular_user, tmp_path, monkeypatch):
    """Paths that do not exist on disk are absent from the result mapping."""
    monkeypatch.setattr("app.services.files.path_utils._resolve_path", lambda p: tmp_path / p)
    (tmp_path / "real").mkdir()

    result = metadata_db.ensure_metadata_bulk(
        ["real", "ghost"],
        requesting_user_id=regular_user.id,
        db=db_session,
    )
    assert "real" in result
    assert "ghost" not in result


def test_bulk_ensure_uses_single_query_for_existing(db_session, regular_user, sample_directory_metadata):
    """Existing metadata is returned without a fresh insert (verified by stable id)."""
    result = metadata_db.ensure_metadata_bulk(
        [sample_directory_metadata.path],
        requesting_user_id=regular_user.id,
        db=db_session,
    )
    assert result[sample_directory_metadata.path].id == sample_directory_metadata.id
```

- [ ] **Step 2: Confirm fail**

```bash
python -m pytest tests/services/files/test_metadata_db_bulk_ensure.py -v
```

Expected: FAIL — `ensure_metadata_bulk` does not exist.

- [ ] **Step 3: Implement the function**

Append to `backend/app/services/files/metadata_db.py`:

```python
def ensure_metadata_bulk(
    relative_paths: list[str],
    *,
    requesting_user_id: int,
    db: Optional[Session] = None,
) -> dict[str, FileMetadata]:
    """Bulk-ensure metadata rows for *relative_paths*.

    For each path:
    - Already in DB → returned as-is.
    - Not in DB but exists on disk → row created (single batched commit).
    - Not in DB and not on disk → omitted from the result.

    Performance: 1 SELECT for the existence check, 1 commit for all inserts —
    instead of 1 SELECT + 1 INSERT per path (the prior list_directory hot path).
    """
    if not relative_paths:
        return {}

    should_close = db is None
    if db is None:
        db = SessionLocal()

    try:
        existing = get_metadata_bulk(relative_paths, db=db)
        missing = [p for p in relative_paths if _normalize_path(p) not in existing]

        from app.services.files.path_utils import _resolve_path
        new_rows: list[FileMetadata] = []
        for path in missing:
            try:
                resolved = _resolve_path(path)
            except Exception:
                continue
            if not resolved.exists():
                continue
            normalized = _normalize_path(path)
            owner_id = _infer_owner_id(normalized, requesting_user_id, db)
            is_dir = resolved.is_dir()
            size = 0 if is_dir else resolved.stat().st_size
            new_rows.append(FileMetadata(
                path=normalized,
                name=resolved.name,
                owner_id=owner_id,
                size_bytes=size,
                is_directory=is_dir,
                parent_path=_get_parent_path(normalized),
            ))

        if new_rows:
            try:
                db.add_all(new_rows)
                db.commit()
                for row in new_rows:
                    db.refresh(row)
            except IntegrityError:
                db.rollback()
                # Race: re-read everything for the missing paths
                refreshed = get_metadata_bulk(missing, db=db)
                existing.update(refreshed)
            else:
                for row in new_rows:
                    existing[row.path] = row

        return existing
    finally:
        if should_close:
            db.close()
```

- [ ] **Step 4: Confirm tests pass**

```bash
python -m pytest tests/services/files/test_metadata_db_bulk_ensure.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/files/metadata_db.py backend/tests/services/files/test_metadata_db_bulk_ensure.py
git commit -m "feat(files): add ensure_metadata_bulk to metadata_db"
```

### Task 4.2: Wire bulk into `list_directory`

**Files:**
- Modify: `backend/app/services/files/operations.py:226-237`

- [ ] **Step 1: Replace the for-loop with the bulk call**

In `backend/app/services/files/operations.py`, replace lines 226-237 (the `dir_paths_needing_ensure` block):

```python
    if db:
        dir_paths_needing_ensure = [
            rel for _, rel, is_dir in entries if is_dir and rel not in metadata_map
        ]
        if dir_paths_needing_ensure:
            new_meta = file_metadata_db.ensure_metadata_bulk(
                dir_paths_needing_ensure,
                requesting_user_id=user.id,
                db=db,
            )
            for rel, meta in new_meta.items():
                metadata_map[rel] = meta
                owner_map[rel] = str(meta.owner_id)
```

- [ ] **Step 2: Run list_directory tests**

```bash
python -m pytest tests/services/files tests/api -k files -v
```

Expected: all pass.

- [ ] **Step 3: Optional perf sanity check (manual)**

In dev mode, create 50 fresh directories and list the parent. The first listing should not produce 50 individual `INSERT` statements. Watch with `EXPLAIN`-style logging if SQLAlchemy `echo=True` is on.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/files/operations.py
git commit -m "perf(files): bulk-ensure metadata for new directories in list_directory"
```

### Task 4.3: Phase 4 PR

```bash
python -m pytest -x -q
git push -u origin refactor/list-directory-bulk-ensure
gh pr create --base main --title "perf(files): batch ensure_metadata for new directories (#7)" --body "Replaces N inserts with 1 SELECT + 1 batched commit."
git switch main && git pull --ff-only
```

---

## Phase 5 — Service Layer for `ad_discovery.py` (B2)

```bash
git switch -c refactor/ad-discovery-service-layer
```

### Task 5.1: Pattern CRUD service

**Files:**
- Create: `backend/app/services/pihole/ad_discovery/patterns_service.py`
- Modify: `backend/app/api/routes/ad_discovery.py:226-330`

- [ ] **Step 1: Read existing analyzer/scorer to discover the AdDiscoveryPattern model surface**

```bash
cat "D:/Programme (x86)/Baluhost/backend/app/models/ad_discovery.py" | head -60
```

Note the field names of `AdDiscoveryPattern` so the service typings match.

- [ ] **Step 2: Write tests first**

Create `backend/tests/services/pihole/test_patterns_service.py`:

```python
"""Tests for the ad-discovery patterns service."""
import pytest

from app.services.pihole.ad_discovery import patterns_service


def test_list_patterns_returns_all(db_session, sample_ad_pattern):
    out = patterns_service.list_patterns(db=db_session)
    assert any(p.id == sample_ad_pattern.id for p in out)


def test_create_pattern_persists_row(db_session):
    p = patterns_service.create_pattern(
        db=db_session,
        pattern="ads.example.com",
        is_regex=False,
        weight=5,
        category="generic",
    )
    assert p.id is not None
    assert p.pattern == "ads.example.com"


def test_create_pattern_rejects_invalid_regex(db_session):
    with pytest.raises(ValueError):
        patterns_service.create_pattern(
            db=db_session,
            pattern="(unclosed",
            is_regex=True,
            weight=5,
            category="generic",
        )


def test_update_pattern_returns_updated(db_session, sample_ad_pattern):
    updated = patterns_service.update_pattern(
        db=db_session,
        pattern_id=sample_ad_pattern.id,
        weight=99,
    )
    assert updated.weight == 99


def test_update_pattern_returns_none_for_unknown(db_session):
    result = patterns_service.update_pattern(db=db_session, pattern_id=999_999, weight=1)
    assert result is None
```

You will need a `sample_ad_pattern` fixture; add it to `backend/tests/conftest.py` or a local `conftest.py` under `tests/services/pihole/`:

```python
@pytest.fixture
def sample_ad_pattern(db_session):
    from app.models.ad_discovery import AdDiscoveryPattern
    p = AdDiscoveryPattern(
        pattern="example-ad.com",
        is_regex=False,
        weight=5,
        category="generic",
        is_default=False,
        enabled=True,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p
```

- [ ] **Step 3: Confirm fail**

```bash
python -m pytest tests/services/pihole/test_patterns_service.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 4: Implement the service**

Create `backend/app/services/pihole/ad_discovery/patterns_service.py`:

```python
"""Pattern CRUD service for ad-discovery.

Extracted from routes/ad_discovery.py — all pattern DB access happens here.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.ad_discovery import AdDiscoveryPattern


def list_patterns(*, db: Session) -> list[AdDiscoveryPattern]:
    return db.query(AdDiscoveryPattern).all()


def create_pattern(
    *,
    db: Session,
    pattern: str,
    is_regex: bool,
    weight: int,
    category: str,
) -> AdDiscoveryPattern:
    if is_regex:
        try:
            compiled = re.compile(pattern)
            compiled.search("safe-test-domain.example.com")
        except re.error as exc:
            raise ValueError(f"Invalid regex pattern: {exc}") from exc

    row = AdDiscoveryPattern(
        pattern=pattern,
        is_regex=is_regex,
        weight=weight,
        category=category,
        is_default=False,
        enabled=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_pattern(
    *,
    db: Session,
    pattern_id: int,
    weight: Optional[int] = None,
    enabled: Optional[bool] = None,
    category: Optional[str] = None,
) -> Optional[AdDiscoveryPattern]:
    row = db.query(AdDiscoveryPattern).filter(AdDiscoveryPattern.id == pattern_id).first()
    if row is None:
        return None
    if weight is not None:
        row.weight = weight
    if enabled is not None:
        row.enabled = enabled
    if category is not None:
        row.category = category
    db.commit()
    db.refresh(row)
    return row


def delete_pattern(*, db: Session, pattern_id: int) -> bool:
    row = db.query(AdDiscoveryPattern).filter(AdDiscoveryPattern.id == pattern_id).first()
    if row is None:
        return False
    if row.is_default:
        raise ValueError("Default patterns cannot be deleted, only disabled")
    db.delete(row)
    db.commit()
    return True
```

- [ ] **Step 5: Confirm tests pass**

```bash
python -m pytest tests/services/pihole/test_patterns_service.py -v
```

Expected: all pass.

- [ ] **Step 6: Migrate the routes**

In `backend/app/api/routes/ad_discovery.py` replace the `list_patterns`, `create_pattern`, `update_pattern`, and `delete_pattern` handlers (lines ~226-330) with thin wrappers that delegate to `patterns_service`. Remove the in-handler `from app.models.ad_discovery import AdDiscoveryPattern` imports — they are no longer used in the route file.

```python
from app.services.pihole.ad_discovery import patterns_service


@router.get("/patterns", response_model=PatternListResponse)
@user_limiter.limit(get_limit("ad_discovery"))
async def list_patterns(
    request: Request, response: Response,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    rows = patterns_service.list_patterns(db=db)
    return PatternListResponse(patterns=[PatternEntry.model_validate(p) for p in rows])


@router.post("/patterns", response_model=PatternEntry, status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("ad_discovery"))
async def create_pattern(
    request: Request, response: Response,
    body: PatternCreateRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    try:
        row = patterns_service.create_pattern(
            db=db,
            pattern=body.pattern,
            is_regex=body.is_regex,
            weight=body.weight,
            category=body.category,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    get_audit_logger_db().log_event(
        event_type="AD_DISCOVERY", user=current_user.username,
        action="ad_discovery_pattern_created",
        details={"pattern": body.pattern, "category": body.category},
    )
    return PatternEntry.model_validate(row)


@router.patch("/patterns/{pattern_id}", response_model=PatternEntry)
@user_limiter.limit(get_limit("ad_discovery"))
async def update_pattern(
    request: Request, response: Response,
    pattern_id: int,
    body: PatternUpdateRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    row = patterns_service.update_pattern(
        db=db,
        pattern_id=pattern_id,
        weight=body.weight,
        enabled=body.enabled,
        category=body.category,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pattern not found")
    return PatternEntry.model_validate(row)


@router.delete("/patterns/{pattern_id}", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("ad_discovery"))
async def delete_pattern(
    request: Request, response: Response,
    pattern_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    try:
        ok = patterns_service.delete_pattern(db=db, pattern_id=pattern_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pattern not found")
```

- [ ] **Step 7: Run all ad-discovery tests**

```bash
python -m pytest tests/api -k "ad_discovery" tests/services/pihole -v
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/pihole/ad_discovery/patterns_service.py backend/app/api/routes/ad_discovery.py backend/tests
git commit -m "refactor(ad_discovery): extract pattern CRUD service from routes (B2 part 1)"
```

### Task 5.2: Suspect listing service

**Files:**
- Create: `backend/app/services/pihole/ad_discovery/suspects_service.py`
- Modify: `backend/app/api/routes/ad_discovery.py:77-117`

- [ ] **Step 1: Write tests**

Create `backend/tests/services/pihole/test_suspects_service.py`:

```python
"""Tests for the ad-discovery suspects service."""
from app.services.pihole.ad_discovery import suspects_service


def test_list_suspects_paginates(db_session):
    """list_suspects returns (rows, total) honoring page_size."""
    rows, total = suspects_service.list_suspects(
        db=db_session, status_filter=None, source=None,
        sort_by="heuristic_score", order="desc", page=1, page_size=10,
    )
    assert isinstance(rows, list)
    assert isinstance(total, int)


def test_list_suspects_filters_by_status(db_session, monkeypatch):
    """When status_filter is set, only matching rows are returned."""
    rows, _ = suspects_service.list_suspects(
        db=db_session, status_filter="confirmed", source=None,
        sort_by="heuristic_score", order="desc", page=1, page_size=50,
    )
    for r in rows:
        assert r.status == "confirmed"
```

- [ ] **Step 2: Confirm fail, then implement**

```bash
python -m pytest tests/services/pihole/test_suspects_service.py -v
```

Create `backend/app/services/pihole/ad_discovery/suspects_service.py`:

```python
"""Suspect query service for ad-discovery."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.ad_discovery import AdDiscoverySuspect


def list_suspects(
    *,
    db: Session,
    status_filter: Optional[str],
    source: Optional[str],
    sort_by: str,
    order: str,
    page: int,
    page_size: int,
) -> tuple[list[AdDiscoverySuspect], int]:
    q = db.query(AdDiscoverySuspect)
    if status_filter:
        q = q.filter(AdDiscoverySuspect.status == status_filter)
    if source:
        q = q.filter(AdDiscoverySuspect.source == source)

    total = q.count()

    col = getattr(AdDiscoverySuspect, sort_by, None)
    if col is not None:
        q = q.order_by(col.desc() if order == "desc" else col.asc())
    else:
        q = q.order_by(AdDiscoverySuspect.heuristic_score.desc())

    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    return rows, total
```

- [ ] **Step 3: Migrate the route**

In `backend/app/api/routes/ad_discovery.py` replace the body of `list_suspects` (around lines 77-116):

```python
from app.services.pihole.ad_discovery import suspects_service


@router.get("/suspects", response_model=SuspectListResponse)
@user_limiter.limit(get_limit("ad_discovery"))
async def list_suspects(
    request: Request, response: Response,
    suspect_status: Optional[str] = Query(None, alias="status"),
    source: Optional[str] = Query(None),
    sort_by: str = Query("heuristic_score"),
    order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    rows, total = suspects_service.list_suspects(
        db=db,
        status_filter=suspect_status,
        source=source,
        sort_by=sort_by,
        order=order,
        page=page,
        page_size=page_size,
    )
    return SuspectListResponse(
        suspects=[SuspectEntry.model_validate(s) for s in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
```

- [ ] **Step 4: Run, commit**

```bash
python -m pytest tests/api -k "ad_discovery" tests/services/pihole -v
git add backend/app/services/pihole/ad_discovery/suspects_service.py backend/app/api/routes/ad_discovery.py backend/tests
git commit -m "refactor(ad_discovery): extract suspect listing service (B2 part 2)"
```

### Task 5.3: Phase 5 PR

```bash
python -m pytest -x -q
git push -u origin refactor/ad-discovery-service-layer
gh pr create --base main --title "refactor: ad-discovery service layer (B2)" --body "Pattern CRUD and suspect listing extracted from routes into services."
git switch main && git pull --ff-only
```

---

## Phase 6 — Centralized Exception Handling (B3)

```bash
git switch -c refactor/exception-handlers
```

### Task 6.1: `ServiceError` hierarchy

**Files:**
- Create: `backend/app/core/exceptions.py`

- [ ] **Step 1: Write the module**

```python
"""Domain exception hierarchy for service-layer errors.

Routes catch these and convert to HTTPException via the central
exception handler in ``core/exception_handlers.py``.
"""


class ServiceError(Exception):
    """Base class for all service-layer errors."""

    http_status: int = 500
    public_message: str = "Internal server error"

    def __init__(self, message: str = "", *, public_message: str | None = None):
        super().__init__(message or self.public_message)
        if public_message is not None:
            self.public_message = public_message


class NotFoundError(ServiceError):
    http_status = 404
    public_message = "Resource not found"


class PermissionError_(ServiceError):
    """Authorization failure inside the service layer."""
    http_status = 403
    public_message = "Forbidden"


class ValidationError_(ServiceError):
    http_status = 422
    public_message = "Invalid request"


class ConflictError(ServiceError):
    http_status = 409
    public_message = "Conflict with current state"
```

(Underscored names avoid shadowing built-ins where used.)

- [ ] **Step 2: Commit (handlers come next)**

```bash
git add backend/app/core/exceptions.py
git commit -m "feat(core): add ServiceError exception hierarchy"
```

### Task 6.2: App-level exception handler

**Files:**
- Create: `backend/app/core/exception_handlers.py`
- Create: `backend/tests/api/test_exception_handlers.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write the test first**

```python
"""Tests for the global exception handler."""
import pytest
from fastapi import APIRouter

from app.core.exceptions import ServiceError, NotFoundError


@pytest.fixture
def _register_test_routes(client):
    """Register fault-injection routes on the test app."""
    from app.main import app
    test_router = APIRouter()

    @test_router.get("/__test__/raises-service-error")
    def _raises_service():
        raise NotFoundError("widget 42")

    @test_router.get("/__test__/raises-bare-exception")
    def _raises_bare():
        raise RuntimeError("internal detail with secret=hunter2")

    app.include_router(test_router)
    yield


def test_service_error_returns_mapped_status_and_public_message(client, _register_test_routes):
    r = client.get("/__test__/raises-service-error")
    assert r.status_code == 404
    body = r.json()
    assert body["detail"] == "Resource not found"


def test_bare_exception_returns_500_without_leaking_message(client, _register_test_routes):
    r = client.get("/__test__/raises-bare-exception")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "Internal server error"
    assert "secret" not in body["detail"]
    assert "hunter2" not in body["detail"]
```

- [ ] **Step 2: Confirm fail**

```bash
python -m pytest tests/api/test_exception_handlers.py -v
```

Expected: at least the second test fails because today's behavior may leak `str(e)`.

- [ ] **Step 3: Create the handler module**

```python
"""Global exception handlers for the FastAPI app.

- ServiceError → mapped HTTP status + public_message
- Exception (catch-all) → 500 with generic message; full trace logged

Goal: never leak internal exception strings to API clients (Sensitive
Data Exposure under OWASP). Spec source: security-agent.md.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import ServiceError

logger = logging.getLogger(__name__)


async def _service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    logger.warning(
        "ServiceError on %s %s: %s",
        request.method, request.url.path, exc,
    )
    return JSONResponse(
        status_code=exc.http_status,
        content={"detail": exc.public_message},
    )


async def _bare_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled exception on %s %s: %s",
        request.method, request.url.path, exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceError, _service_error_handler)
    # Catch-all — only for unhandled exceptions; FastAPI's HTTPException is
    # processed by the framework's default handler before reaching this.
    app.add_exception_handler(Exception, _bare_exception_handler)
```

- [ ] **Step 4: Wire it up in `main.py`**

In `backend/app/main.py`, after `app = FastAPI(...)` is created, add:

```python
from app.core.exception_handlers import register_exception_handlers
register_exception_handlers(app)
```

- [ ] **Step 5: Confirm tests pass**

```bash
python -m pytest tests/api/test_exception_handlers.py -v
```

Expected: both tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/exception_handlers.py backend/app/main.py backend/tests/api/test_exception_handlers.py
git commit -m "feat(core): global exception handler hides internal errors from clients (B3 part 1)"
```

### Task 6.3: Migrate `fans.py` to drop generic `except Exception`

**Files:**
- Modify: `backend/app/api/routes/fans.py` — every `try: ... except Exception as e: raise HTTPException(500, f"...{str(e)}")` block

- [ ] **Step 1: Migrate one handler at a time**

Pick `get_fan_status` first. Replace:

```python
try:
    status = await service.get_status()
    fans = [FanInfo(**fan_data) for fan_data in status["fans"]]
    return FanStatusResponse(...)
except Exception as e:
    logger.error(f"Failed to get fan status: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail=f"Failed to get fan status: {str(e)}")
```

with:

```python
status = await service.get_status()
fans = [FanInfo(**fan_data) for fan_data in status["fans"]]
return FanStatusResponse(...)
```

(Drop the surrounding `try/except Exception` entirely. Keep targeted exception handling for known business cases — e.g. `HTTPException` for 404s should stay.)

- [ ] **Step 2: Repeat for every handler in `fans.py`**

Apply the same pattern to: `set_fan_mode`, `set_fan_pwm`, `update_fan_curve`, `get_fan_history`, `switch_backend`, `apply_preset`, `update_fan_config`, `list_temp_sensors`, schedule + curve-profile endpoints. Keep `try/except` blocks only when they catch a **specific** exception type and convert it to a meaningful HTTP code (e.g. `except FanNotFoundError: raise HTTPException(404, ...)`).

- [ ] **Step 3: Run fan tests**

```bash
python -m pytest tests/api -k "fan" tests/services -k "fan" -v
```

Expected: all pass. The error-path tests now expect `{"detail": "Internal server error"}` (or 500) rather than the raw exception text — update assertions if any were locked to the old format.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes/fans.py backend/tests
git commit -m "refactor(fans): drop generic Exception handlers, rely on global handler (B3 part 2)"
```

### Task 6.4: Phase 6 PR

```bash
python -m pytest -x -q
git push -u origin refactor/exception-handlers
gh pr create --base main --title "refactor: global exception handler + ServiceError hierarchy (B3)" --body "$(cat <<'EOF'
## Summary
- New core/exceptions.py — ServiceError hierarchy (NotFound, Permission, Validation, Conflict)
- New core/exception_handlers.py — registered in main.py
- fans.py: dropped 10+ generic Exception handlers that leaked str(e) to clients
- Closes B3 from the audit

## Security note
Aligns with security-agent.md "Sensitive Data Exposure" — internal exception
messages no longer reach API clients; full traces remain in logs.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
git switch main && git pull --ff-only
```

---

## Phase 7 — Re-export Cleanup (B6)

```bash
git switch -c refactor/operations-reexports
```

### Task 7.1: Audit + remove dead re-exports from `operations.py`

**Files:**
- Modify: `backend/app/services/files/operations.py:39-78`

- [ ] **Step 1: Find every external caller of the re-exported symbols**

For each symbol re-exported from `operations.py` (lines 39-78 — `path_utils`, `access`, `storage` re-exports), grep:

```bash
for sym in ROOT_DIR SHARED_DIR_NAME SHARED_WITH_ME_DIR SYSTEM_DIR_NAME is_path_shared_with_user get_share_permissions; do
  echo "=== $sym ==="
  grep -rn "from app.services.files.operations import.*$sym\|from app.services.files.operations import .*$sym" "D:/Programme (x86)/Baluhost/backend"
done
```

- [ ] **Step 2: Migrate callers to import from canonical module**

For each caller, change `from app.services.files.operations import X` to `from app.services.files.path_utils import X` (or `access`, or `storage` — whichever is the actual home, indicated by the comment block in `operations.py`).

- [ ] **Step 3: Drop the re-export blocks**

Once every caller is migrated, delete the `# Re-exports from path_utils (backward compatibility)` block in `operations.py`. Keep only re-exports that still have at least one caller. (After migration, ideally none — delete all.)

- [ ] **Step 4: Run full suite**

```bash
python -m pytest -x -q
```

Expected: all pass — if any module fails with `ImportError`, you missed a caller in Step 2.

- [ ] **Step 5: Commit + PR**

```bash
git add backend/app/services/files/operations.py backend/app
git commit -m "refactor(files): remove dead operations.py re-exports, callers import from canonical modules (B6)"
git push -u origin refactor/operations-reexports
gh pr create --base main --title "refactor(files): remove operations.py re-export shims (B6)" --body "Migration of imports complete; shims no longer needed."
git switch main && git pull --ff-only
```

---

## Phase 8 — `PowerManagerService` Decomposition (B4) — DEFER TO DEDICATED PLAN

**Why deferred:** `PowerManagerService` is 1013 lines and mixes six independent responsibilities (demand registry, profile applier, dynamic-mode controller, status aggregation, history, primary/follower routing). A safe split needs its own test-design pass and a behavior contract per extracted class. Including detailed bite-sized tasks here would triple the size of this plan and dilute review focus.

**Decomposition target (locked in here, executed in the follow-up plan):**

| Extracted unit | New file | Responsibility |
|---|---|---|
| `DemandRegistry` | `services/power/demand_registry.py` | Register/unregister demands, load from DB, recalculate winning profile |
| `DynamicModeController` | `services/power/dynamic_mode.py` | Enable/disable dynamic mode, governor scaling |
| `ProfileApplier` | `services/power/profile_applier.py` | Apply profile to backend, persist to DB, update SHM |
| `PowerHistoryStore` | `services/power/history.py` | History buffer + cooldown + manual override timing |
| `PowerManagerService` (slim) | `services/power/manager.py` | Composes the above; remains the public façade |

**Multi-worker constraints carried over:**
- `start(primary=True)` stays on `PowerManagerService`.
- Followers continue routing via `command_queue` and reading `runtime_state` via `_hydrate_from_runtime_state`.
- Both `DemandRegistry` and `ProfileApplier` need to know `_primary` to gate writes.

**Action item (this plan):**
- [ ] **Step 1: Create the follow-up plan**

```bash
echo "TBD: separate plan file" # placeholder — actual creation happens in the dedicated plan task
```

(Replaced by writing `docs/superpowers/plans/2026-05-09-power-manager-split.md` using the writing-plans skill, after Phase 7 merges and the audit's quick wins are settled.)

---

## Phase 9 — `SleepManagerService` Decomposition (B5) — DEFER TO DEDICATED PLAN

**Why deferred:** Same reasoning as Phase 8 — `services/power/sleep.py` is 1142 lines (largest backend file), and the recent always-awake feature (commit `89062a54`) added more state to an already overloaded class without splitting.

**Decomposition target (locked in here):**

| Extracted unit | New file | Responsibility |
|---|---|---|
| `SleepStateMachine` | `services/power/sleep_state_machine.py` | AWAKE → SOFT_SLEEP → TRUE_SUSPEND transitions |
| `IdleDetector` | `services/power/sleep_idle.py` | Activity metrics + idle-loop |
| `SleepScheduler` | `services/power/sleep_scheduler.py` | Schedule mode + always-awake override |
| `SleepHistoryService` | `services/power/sleep_history.py` | History persistence |
| `SleepManagerService` (slim) | `services/power/sleep.py` | Composes the above; public façade |

(Backend abstraction `SleepBackend`, `DevSleepBackend`, `LinuxSleepBackend` already extracted — leave as-is.)

**Action item:** Create `docs/superpowers/plans/2026-05-10-sleep-manager-split.md` after Phase 8 completes.

---

## Self-Review Notes

**Spec coverage:**
- #4 → Phase 3 (Tasks 3.1, 3.2)
- #5 → Phase 2 (Tasks 2.1–2.5)
- #6 → Phase 1 (Task 1.1)
- #7 → Phase 4 (Tasks 4.1, 4.2)
- #8 → Phase 1 (Task 1.3)
- #11 → Phase 1 (Task 1.2)
- #12 → Phase 1 (Task 1.4)
- B1 → Phase 2 (Task 2.4)
- B2 → Phase 5 (Tasks 5.1, 5.2)
- B3 → Phase 6 (Tasks 6.1–6.4)
- B4 → Phase 8 (deferred to dedicated plan)
- B5 → Phase 9 (deferred to dedicated plan)
- B6 → Phase 7 (Task 7.1)

**Multi-worker preservation checks** are listed in every singleton-touching task (Tasks 2.2, 2.3, 2.4) — the `start(primary=...)` signature, file-lock election in `lifespan.py`, and DB command queue all stay untouched.

**Convention adherence:**
- Tests precede implementation everywhere a behavior change is involved.
- Each phase ends with a single PR to `main` (per `feedback_release_workflow`).
- Full pytest run before each PR (per `feedback_run_tests_before_pr`).
- Service-layer pattern from `services/CLAUDE.md` is reinforced, not invented.
