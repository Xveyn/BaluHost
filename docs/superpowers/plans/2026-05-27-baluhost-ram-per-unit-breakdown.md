# BaluHost RAM Per-Unit Breakdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix BaluHost RAM tracking so the System Monitor counts all five systemd units (backend, backend-local, scheduler, webdav, monitoring) and breaks the total down per-unit in the UI.

**Architecture:** cmdline-pattern matching extended to all systemd `ExecStart` strings, first-match-wins to keep backend-local separate from backend. `MemorySampleSchema` gains `baluhost_memory_breakdown: dict[str, int]` (live-only, no DB migration — per-unit history already lives in `process_samples`). The `MemoryTab` StatCard becomes a small breakdown panel.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, psutil, SQLAlchemy 2.0, React 18, TypeScript, Tailwind, i18next.

**Spec:** [`docs/superpowers/specs/2026-05-27-baluhost-ram-per-unit-breakdown-design.md`](../specs/2026-05-27-baluhost-ram-per-unit-breakdown-design.md)

---

## Pre-flight

- [ ] **Step 1: Verify base branch**

Spec is committed on `fix/tauri-icon-rgba`. Move work to a clean feature branch off `main`.

Run from repo root:
```powershell
git fetch origin
git checkout -b feat/memory-per-unit-breakdown origin/main
git cherry-pick fix/tauri-icon-rgba -- docs/superpowers/specs/2026-05-27-baluhost-ram-per-unit-breakdown-design.md
```

Expected: a new branch with the spec file present and clean tree otherwise.

- [ ] **Step 2: Confirm test infrastructure**

Run:
```powershell
cd backend
python -m pytest tests/monitoring/test_collectors.py -q --collect-only
```

Expected: tests are collected without import errors. If `tests/monitoring/test_process_tracker.py` does not exist, that's fine — Task 1 creates it.

---

## Task 1: Add new BaluHost process patterns + all-of matching

**Files:**
- Modify: `backend/app/services/monitoring/process_tracker.py:25-29` (the `BALUHOST_PROCESS_PATTERNS` list)
- Modify: `backend/app/services/monitoring/process_tracker.py:122-158` (`_find_processes` matching)
- Create: `backend/tests/monitoring/test_process_tracker.py`

The current matching uses `any(p in cmdline ...)`. We need `all(...)` so a multi-token pattern like `["uvicorn app.main", "--fd 3"]` requires both tokens. The semantic for single-element patterns is unchanged.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/monitoring/test_process_tracker.py`:

```python
"""Tests for ProcessTracker pattern matching and BALUHOST_PROCESS_PATTERNS."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.monitoring import process_tracker
from app.services.monitoring.process_tracker import (
    BALUHOST_PROCESS_PATTERNS,
    ProcessTracker,
)


def _fake_proc(pid: int, name: str, cmdline_str: str, rss_bytes: int = 1024 * 1024):
    """Build a MagicMock that behaves like a psutil.Process .info dict source."""
    proc = MagicMock()
    proc.info = {
        "pid": pid,
        "name": name,
        "cmdline": cmdline_str.split(),
        "cpu_percent": 0.0,
        "memory_info": MagicMock(rss=rss_bytes),
        "status": "running",
    }
    return proc


def test_patterns_include_all_five_systemd_units():
    """All five prod systemd units have a process_name entry."""
    names = {entry["name"] for entry in BALUHOST_PROCESS_PATTERNS}
    assert "baluhost-backend" in names
    assert "baluhost-backend-local" in names
    assert "baluhost-scheduler" in names
    assert "baluhost-webdav" in names
    assert "baluhost-monitoring" in names


def test_patterns_order_puts_backend_local_before_backend():
    """First-match-wins requires backend-local to precede backend in the list."""
    order = [entry["name"] for entry in BALUHOST_PROCESS_PATTERNS]
    assert order.index("baluhost-backend-local") < order.index("baluhost-backend")


def test_find_processes_requires_all_patterns_to_match():
    """Multi-token pattern: all tokens must be in cmdline."""
    tracker = ProcessTracker()
    procs = [
        # Has only first token → should NOT match a two-token pattern
        _fake_proc(101, "python", "python -m uvicorn app.main --port 8000"),
        # Has both tokens → should match
        _fake_proc(102, "python", "python -m uvicorn app.main --fd 3 --workers 2"),
    ]
    with patch.object(process_tracker.psutil, "process_iter", return_value=procs):
        matched = tracker._find_processes(["uvicorn app.main", "--fd 3"])
    pids = [m["pid"] for m in matched]
    assert pids == [102]


def test_find_processes_single_pattern_still_matches():
    """Single-token pattern behaves like before (no regression)."""
    tracker = ProcessTracker()
    procs = [
        _fake_proc(201, "python", "python scripts/scheduler_worker.py"),
        _fake_proc(202, "python", "python scripts/webdav_worker.py"),
    ]
    with patch.object(process_tracker.psutil, "process_iter", return_value=procs):
        matched = tracker._find_processes(["scheduler_worker.py"])
    pids = [m["pid"] for m in matched]
    assert pids == [201]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:
```powershell
cd backend
python -m pytest tests/monitoring/test_process_tracker.py -v
```

Expected: `test_patterns_include_all_five_systemd_units` FAILS (scheduler/webdav/monitoring/backend-local keys missing). `test_find_processes_requires_all_patterns_to_match` FAILS (current code uses `any(...)`).

- [ ] **Step 3: Update `BALUHOST_PROCESS_PATTERNS`**

In `backend/app/services/monitoring/process_tracker.py`, replace lines 25-29 with:

```python
# Process patterns to track.
#
# Order matters: more-specific patterns first so first-match-wins routes
# baluhost-backend-local before baluhost-backend (both match "uvicorn app.main").
# `_find_processes` uses all-of matching — every token must appear in name or cmdline.
BALUHOST_PROCESS_PATTERNS = [
    {"name": "baluhost-backend-local",  "patterns": ["uvicorn app.main", "--fd 3"]},
    {"name": "baluhost-backend",        "patterns": ["uvicorn app.main"]},
    {"name": "baluhost-scheduler",      "patterns": ["scheduler_worker.py"]},
    {"name": "baluhost-webdav",         "patterns": ["webdav_worker.py"]},
    {"name": "baluhost-monitoring",     "patterns": ["monitoring_worker.py"]},
    {"name": "baluhost-tui",            "patterns": ["baluhost_tui"]},
    {"name": "baluhost-frontend-dev",   "patterns": ["vite"]},
]
```

- [ ] **Step 4: Switch `_find_processes` matching to all-of**

In `backend/app/services/monitoring/process_tracker.py`, in `_find_processes` (around line 142), replace:

```python
                    # Check if any pattern matches
                    if any(p.lower() in name or p.lower() in cmdline for p in patterns):
```

With:

```python
                    # All patterns must match (in name or cmdline)
                    if all(p.lower() in name or p.lower() in cmdline for p in patterns):
```

- [ ] **Step 5: Run tests and verify they pass**

Run:
```powershell
cd backend
python -m pytest tests/monitoring/test_process_tracker.py -v
```

Expected: all four tests PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/services/monitoring/process_tracker.py backend/tests/monitoring/test_process_tracker.py
git commit -m "feat(monitoring): expand BaluHost process patterns to all systemd units"
```

---

## Task 2: First-match-wins routing in `collect_samples`

**Files:**
- Modify: `backend/app/services/monitoring/process_tracker.py:55-120` (`collect_samples`)
- Modify: `backend/tests/monitoring/test_process_tracker.py` (extend)

A backend-local uvicorn process matches both `baluhost-backend-local` and `baluhost-backend` token sets. With the current per-pattern loop it would be sampled under both names. We need first-match-wins per PID.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/monitoring/test_process_tracker.py`:

```python
def test_collect_samples_routes_backend_local_to_its_own_bucket():
    """A uvicorn process with --fd 3 is sampled as baluhost-backend-local, NOT baluhost-backend."""
    tracker = ProcessTracker()
    procs = [
        # Backend (HTTP): uvicorn app.main without --fd
        _fake_proc(301, "python", "python -m uvicorn app.main --port 8000", rss_bytes=200 * 1024 * 1024),
        # Backend (Local): uvicorn app.main with --fd 3
        _fake_proc(302, "python", "python -m uvicorn app.main --fd 3 --workers 2", rss_bytes=100 * 1024 * 1024),
    ]
    with patch.object(process_tracker.psutil, "process_iter", return_value=procs):
        samples = tracker.collect_samples()

    by_pid = {s.pid: s for s in samples}
    assert by_pid[301].process_name == "baluhost-backend"
    assert by_pid[302].process_name == "baluhost-backend-local"
    # The same PID is NOT duplicated under two names
    assert sum(1 for s in samples if s.pid == 302) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
cd backend
python -m pytest tests/monitoring/test_process_tracker.py::test_collect_samples_routes_backend_local_to_its_own_bucket -v
```

Expected: FAIL. PID 302 appears under both names because `collect_samples` iterates patterns and `_find_processes` matches independently.

- [ ] **Step 3: Refactor `collect_samples` to iterate processes once, classify by first-matching pattern**

In `backend/app/services/monitoring/process_tracker.py`, replace the body of `collect_samples` (lines 55-120) with:

```python
    def collect_samples(self) -> List[ProcessSampleSchema]:
        """
        Collect samples for all BaluHost processes.

        Iterates processes once and classifies each PID under the first pattern
        whose tokens all match. This prevents double-counting when a process
        matches multiple patterns (e.g. backend-local also matches backend).
        """
        samples: List[ProcessSampleSchema] = []
        timestamp = datetime.now(timezone.utc)
        seen_names: set[str] = set()

        try:
            for proc in psutil.process_iter(
                ["pid", "name", "cmdline", "cpu_percent", "memory_info", "status"]
            ):
                try:
                    info = proc.info
                    name = (info.get("name") or "").lower()
                    cmdline = " ".join(info.get("cmdline") or []).lower()

                    matched_name: Optional[str] = None
                    for entry in BALUHOST_PROCESS_PATTERNS:
                        patterns = entry["patterns"]
                        if all(p.lower() in name or p.lower() in cmdline for p in patterns):
                            matched_name = entry["name"]
                            break

                    if matched_name is None:
                        continue

                    memory_mb = 0.0
                    if info.get("memory_info"):
                        memory_mb = info["memory_info"].rss / (1024 * 1024)

                    sample = ProcessSampleSchema(
                        timestamp=timestamp,
                        process_name=matched_name,
                        pid=info["pid"],
                        cpu_percent=round(info.get("cpu_percent", 0.0) or 0.0, 2),
                        memory_mb=round(memory_mb, 2),
                        status=info.get("status", "unknown"),
                        is_alive=True,
                    )
                    samples.append(sample)
                    seen_names.add(matched_name)

                    with self._lock:
                        self._process_buffers.setdefault(matched_name, []).append(sample)
                        if len(self._process_buffers[matched_name]) > self.buffer_size:
                            self._process_buffers[matched_name].pop(0)
                        self._known_pids[matched_name] = info["pid"]
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.error(f"Error iterating processes: {e}")

        # Emit synthetic "stopped" samples for previously seen names that are now gone
        with self._lock:
            gone = set(self._known_pids.keys()) - seen_names
            for matched_name in gone:
                last_pid = self._known_pids[matched_name]
                sample = ProcessSampleSchema(
                    timestamp=timestamp,
                    process_name=matched_name,
                    pid=last_pid,
                    cpu_percent=0.0,
                    memory_mb=0.0,
                    status="stopped",
                    is_alive=False,
                )
                samples.append(sample)
                self._process_buffers.setdefault(matched_name, []).append(sample)
                if len(self._process_buffers[matched_name]) > self.buffer_size:
                    self._process_buffers[matched_name].pop(0)
                logger.warning(
                    f"Process '{matched_name}' (PID {last_pid}) stopped or crashed"
                )
                del self._known_pids[matched_name]

        return samples
```

Also add to the imports at the top of the file (if not already present):

```python
from typing import Dict, List, Optional, Set, Type
```

(`Optional` may already be imported — keep one declaration.)

- [ ] **Step 4: Run all process tracker tests**

Run:
```powershell
cd backend
python -m pytest tests/monitoring/test_process_tracker.py -v
```

Expected: all five tests PASS.

- [ ] **Step 5: Run the broader monitoring suite for regressions**

Run:
```powershell
cd backend
python -m pytest tests/monitoring/ -v
```

Expected: no new failures.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/services/monitoring/process_tracker.py backend/tests/monitoring/test_process_tracker.py
git commit -m "feat(monitoring): first-match-wins routing in process_tracker.collect_samples"
```

---

## Task 3: `get_baluhost_memory_breakdown` (replace flat total)

**Files:**
- Modify: `backend/app/services/monitoring/memory_collector.py:23-50` (replace `get_baluhost_memory_bytes`)
- Modify: `backend/app/services/monitoring/memory_collector.py:75-96` (`collect_sample`)
- Modify: `backend/tests/monitoring/test_collectors.py` (extend) OR create `backend/tests/monitoring/test_memory_collector.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/monitoring/test_memory_collector.py`:

```python
"""Tests for memory_collector breakdown logic."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.monitoring import memory_collector
from app.services.monitoring.memory_collector import (
    MemoryMetricCollector,
    get_baluhost_memory_breakdown,
)
from app.services.monitoring.process_tracker import BALUHOST_PROCESS_PATTERNS


def _fake_proc(pid: int, cmdline_str: str, rss_bytes: int):
    proc = MagicMock()
    proc.info = {
        "pid": pid,
        "name": "python",
        "cmdline": cmdline_str.split(),
        "memory_info": MagicMock(rss=rss_bytes),
    }
    return proc


def test_breakdown_contains_all_defined_units():
    """All names from BALUHOST_PROCESS_PATTERNS appear as keys (zero-filled)."""
    with patch.object(memory_collector.psutil, "process_iter", return_value=[]):
        result = get_baluhost_memory_breakdown()
    for entry in BALUHOST_PROCESS_PATTERNS:
        assert entry["name"] in result
        assert result[entry["name"]] == 0


def test_breakdown_routes_processes_to_their_unit():
    """Each matched process contributes RSS to its unit bucket."""
    procs = [
        _fake_proc(401, "python -m uvicorn app.main --port 8000", rss_bytes=200_000_000),
        _fake_proc(402, "python -m uvicorn app.main --port 8000", rss_bytes=150_000_000),  # worker 2
        _fake_proc(403, "python -m uvicorn app.main --fd 3 --workers 2", rss_bytes=100_000_000),
        _fake_proc(404, "python scripts/scheduler_worker.py", rss_bytes=50_000_000),
        _fake_proc(405, "python scripts/webdav_worker.py", rss_bytes=40_000_000),
        _fake_proc(406, "python scripts/monitoring_worker.py", rss_bytes=30_000_000),
    ]
    with patch.object(memory_collector.psutil, "process_iter", return_value=procs):
        result = get_baluhost_memory_breakdown()

    assert result["baluhost-backend"] == 350_000_000
    assert result["baluhost-backend-local"] == 100_000_000
    assert result["baluhost-scheduler"] == 50_000_000
    assert result["baluhost-webdav"] == 40_000_000
    assert result["baluhost-monitoring"] == 30_000_000


def test_collect_sample_populates_breakdown_and_total():
    """MemoryMetricCollector.collect_sample fills both breakdown and total."""
    procs = [
        _fake_proc(501, "python -m uvicorn app.main --port 8000", rss_bytes=200_000_000),
        _fake_proc(502, "python scripts/scheduler_worker.py", rss_bytes=50_000_000),
    ]
    fake_vmem = MagicMock(
        total=16 * 1024**3,
        available=8 * 1024**3,
        percent=50.0,
    )
    with patch.object(memory_collector.psutil, "process_iter", return_value=procs), \
         patch.object(memory_collector.psutil, "virtual_memory", return_value=fake_vmem):
        collector = MemoryMetricCollector()
        sample = collector.collect_sample()

    assert sample is not None
    assert sample.baluhost_memory_bytes == 250_000_000  # total backward-compat
    assert sample.baluhost_memory_breakdown is not None
    assert sample.baluhost_memory_breakdown["baluhost-backend"] == 200_000_000
    assert sample.baluhost_memory_breakdown["baluhost-scheduler"] == 50_000_000
```

- [ ] **Step 2: Run tests and verify they fail**

Run:
```powershell
cd backend
python -m pytest tests/monitoring/test_memory_collector.py -v
```

Expected: ImportError or AttributeError — `get_baluhost_memory_breakdown` and `baluhost_memory_breakdown` don't exist yet.

- [ ] **Step 3: Replace `get_baluhost_memory_bytes` with `get_baluhost_memory_breakdown`**

In `backend/app/services/monitoring/memory_collector.py`, replace lines 23-50 with:

```python
def get_baluhost_memory_breakdown() -> dict[str, int]:
    """
    Get RSS memory per BaluHost systemd unit.

    Returns a dict keyed by ``process_name`` from ``BALUHOST_PROCESS_PATTERNS``.
    All defined unit names appear as keys; missing units have value 0 so the
    UI can distinguish "unit not defined" (key absent) from "unit not running"
    (key present, value 0).

    Routing is first-match-wins (same order as BALUHOST_PROCESS_PATTERNS) so
    a process matching multiple patterns is counted under the first.
    """
    breakdown: dict[str, int] = {entry["name"]: 0 for entry in BALUHOST_PROCESS_PATTERNS}

    try:
        for proc in psutil.process_iter(["pid", "name", "cmdline", "memory_info"]):
            try:
                info = proc.info
                name = (info.get("name") or "").lower()
                cmdline = " ".join(info.get("cmdline") or []).lower()

                for entry in BALUHOST_PROCESS_PATTERNS:
                    if all(p.lower() in name or p.lower() in cmdline for p in entry["patterns"]):
                        if info.get("memory_info"):
                            breakdown[entry["name"]] += info["memory_info"].rss
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        logger.debug(f"Error getting BaluHost memory breakdown: {e}")

    return breakdown


def get_baluhost_memory_bytes() -> int:
    """Backward-compat: total memory across all BaluHost processes."""
    return sum(get_baluhost_memory_breakdown().values())
```

- [ ] **Step 4: Update `collect_sample` to emit both fields**

In `backend/app/services/monitoring/memory_collector.py`, replace the `collect_sample` body (lines 75-96) with:

```python
    def collect_sample(self) -> Optional[MemorySampleSchema]:
        """Collect memory metrics sample."""
        try:
            timestamp = datetime.now(timezone.utc)

            mem = psutil.virtual_memory()
            breakdown = get_baluhost_memory_breakdown()
            total_baluhost = sum(breakdown.values())

            return MemorySampleSchema(
                timestamp=timestamp,
                used_bytes=mem.total - mem.available,
                total_bytes=mem.total,
                percent=round(mem.percent, 2),
                available_bytes=mem.available,
                baluhost_memory_bytes=total_baluhost,
                baluhost_memory_breakdown=breakdown,
            )
        except Exception as e:
            logger.error(f"Failed to collect memory sample: {e}")
            return None
```

- [ ] **Step 5: Run the tests — they will still fail until Task 4 lands**

Run:
```powershell
cd backend
python -m pytest tests/monitoring/test_memory_collector.py::test_breakdown_contains_all_defined_units tests/monitoring/test_memory_collector.py::test_breakdown_routes_processes_to_their_unit -v
```

Expected: these two PASS. `test_collect_sample_populates_breakdown_and_total` still FAILS because `MemorySampleSchema` doesn't have the field yet (Task 4 adds it). Continue.

- [ ] **Step 6: Commit (intermediate — schema still missing)**

```powershell
git add backend/app/services/monitoring/memory_collector.py backend/tests/monitoring/test_memory_collector.py
git commit -m "feat(monitoring): get_baluhost_memory_breakdown() per-unit RSS map"
```

---

## Task 4: Extend `MemorySampleSchema` + API response

**Files:**
- Modify: `backend/app/schemas/monitoring.py` (`MemorySampleSchema`, `CurrentMemoryResponse`)
- Modify: `backend/app/api/routes/monitoring.py:198-220` (`get_memory_current` response constructor)

- [ ] **Step 1: Find the schemas**

The schemas live in `backend/app/schemas/monitoring.py`. Locate `class MemorySampleSchema` and `class CurrentMemoryResponse`.

- [ ] **Step 2: Add the new field to both schemas**

In `backend/app/schemas/monitoring.py`, in `MemorySampleSchema`, add after `available_bytes`:

```python
    baluhost_memory_bytes: int = 0
    baluhost_memory_breakdown: Optional[Dict[str, int]] = None
```

(If `baluhost_memory_bytes` is already present, just add `baluhost_memory_breakdown`.)

In `CurrentMemoryResponse`, add the matching field — if the response mirrors `MemorySampleSchema` field-for-field, add `baluhost_memory_breakdown: Optional[Dict[str, int]] = None` there too.

Check that `Dict` and `Optional` are imported at the top of the file:
```python
from typing import Dict, List, Optional
```

- [ ] **Step 3: Update the route handler**

In `backend/app/api/routes/monitoring.py`, in `get_memory_current` (around line 198-220), update the response construction:

```python
    return CurrentMemoryResponse(
        timestamp=sample.timestamp,
        used_bytes=sample.used_bytes,
        total_bytes=sample.total_bytes,
        percent=sample.percent,
        available_bytes=sample.available_bytes,
        baluhost_memory_bytes=sample.baluhost_memory_bytes,
        baluhost_memory_breakdown=sample.baluhost_memory_breakdown,
    )
```

- [ ] **Step 4: Run the Task-3 test that was still failing**

Run:
```powershell
cd backend
python -m pytest tests/monitoring/test_memory_collector.py -v
```

Expected: all three tests PASS.

- [ ] **Step 5: Add an integration test for the route**

Append to `backend/tests/api/test_monitoring_routes.py` (inside the class that already has `test_memory_current_returns_data_or_503`):

```python
    def test_memory_current_includes_breakdown_field(self, client: TestClient, user_headers: dict):
        """Memory current response carries baluhost_memory_breakdown (may be null on cold start)."""
        response = client.get("/api/monitoring/memory/current", headers=user_headers)
        assert response.status_code in [200, 503]
        if response.status_code == 200:
            data = response.json()
            assert "baluhost_memory_breakdown" in data
            # Either None (no sample yet on this worker) or a dict
            breakdown = data["baluhost_memory_breakdown"]
            assert breakdown is None or isinstance(breakdown, dict)
            if isinstance(breakdown, dict):
                # All defined units should be keys
                for name in [
                    "baluhost-backend",
                    "baluhost-backend-local",
                    "baluhost-scheduler",
                    "baluhost-webdav",
                    "baluhost-monitoring",
                ]:
                    assert name in breakdown
```

- [ ] **Step 6: Run the integration test**

Run:
```powershell
cd backend
python -m pytest tests/api/test_monitoring_routes.py::TestMemoryEndpoints::test_memory_current_includes_breakdown_field -v
```

(Adjust class name if the test class is named differently — find it with `python -m pytest tests/api/test_monitoring_routes.py --collect-only`.)

Expected: PASS.

- [ ] **Step 7: Run the broader monitoring test suite**

Run:
```powershell
cd backend
python -m pytest tests/monitoring/ tests/api/test_monitoring_routes.py -v
```

Expected: no regressions.

- [ ] **Step 8: Commit**

```powershell
git add backend/app/schemas/monitoring.py backend/app/api/routes/monitoring.py backend/tests/api/test_monitoring_routes.py
git commit -m "feat(api): expose baluhost_memory_breakdown in /monitoring/memory/current"
```

---

## Task 5: Verify SHM payload carries the new field

**Files:**
- Read only: `backend/app/services/monitoring/worker_service.py` (no edits expected)
- Modify: `backend/tests/monitoring/test_orchestrator.py` (new test)

`worker_service._write_orchestrator_data_snapshot` serializes the memory sample via `model_dump(mode="json")`, so the new field flows through automatically. This task adds a regression test to lock that behavior in.

- [ ] **Step 1: Confirm by reading**

Run:
```powershell
type "backend\app\services\monitoring\worker_service.py" | findstr /n "memory_current"
```

Verify line that does `mem_cur.model_dump(mode="json")` — that's what carries `baluhost_memory_breakdown` through SHM.

- [ ] **Step 2: Add a regression test**

Append to `backend/tests/monitoring/test_orchestrator.py`:

```python
def test_memory_sample_model_dump_includes_breakdown():
    """SHM serialization (model_dump) must include the new breakdown field."""
    from datetime import datetime, timezone
    from app.schemas.monitoring import MemorySampleSchema

    sample = MemorySampleSchema(
        timestamp=datetime.now(timezone.utc),
        used_bytes=8_000_000_000,
        total_bytes=16_000_000_000,
        percent=50.0,
        available_bytes=8_000_000_000,
        baluhost_memory_bytes=300_000_000,
        baluhost_memory_breakdown={
            "baluhost-backend": 200_000_000,
            "baluhost-scheduler": 100_000_000,
        },
    )
    dumped = sample.model_dump(mode="json")
    assert "baluhost_memory_breakdown" in dumped
    assert dumped["baluhost_memory_breakdown"]["baluhost-backend"] == 200_000_000
```

- [ ] **Step 3: Run it**

Run:
```powershell
cd backend
python -m pytest tests/monitoring/test_orchestrator.py::test_memory_sample_model_dump_includes_breakdown -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add backend/tests/monitoring/test_orchestrator.py
git commit -m "test(monitoring): SHM payload regression test for memory breakdown"
```

---

## Task 6: Frontend — extend `MemorySample` type

**Files:**
- Modify: `client/src/api/monitoring.ts:60-67`

- [ ] **Step 1: Add the field**

In `client/src/api/monitoring.ts`, replace the `MemorySample` interface (lines 60-67):

```ts
export interface MemorySample {
  timestamp: string;
  used_bytes: number;
  total_bytes: number;
  percent: number;
  available_bytes?: number;
  baluhost_memory_bytes?: number;  // Total memory used by BaluHost processes
  baluhost_memory_breakdown?: Record<string, number>;  // RSS bytes per systemd unit
}
```

- [ ] **Step 2: Run the frontend type check**

Run:
```powershell
cd client
npx tsc --noEmit
```

Expected: no new errors. If there are pre-existing errors unrelated to this change, ignore.

- [ ] **Step 3: Commit**

```powershell
git add client/src/api/monitoring.ts
git commit -m "feat(client): MemorySample.baluhost_memory_breakdown type"
```

---

## Task 7: Frontend — BaluHost breakdown card in MemoryTab

**Files:**
- Modify: `client/src/components/system-monitor/MemoryTab.tsx`

Replace the single "BaluHost" `StatCard` with a panel that lists per-unit RSS underneath the total. Layout: takes the same 5th-card slot in the grid; on `width < sm` it is collapsible.

- [ ] **Step 1: Write the new component logic**

Replace the entire content of `client/src/components/system-monitor/MemoryTab.tsx` with:

```tsx
/**
 * MemoryTab -- RAM monitoring tab with usage chart and BaluHost per-unit breakdown.
 */

import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { MetricChart } from '../monitoring';
import type { TimeRange } from '../../api/monitoring';
import { useMemoryMonitoring } from '../../hooks/useMonitoring';
import { formatBytes, formatNumber } from '../../lib/formatters';
import { StatCard } from '../ui/StatCard';

// Display order of units in the breakdown (matches BALUHOST_PROCESS_PATTERNS in backend).
const UNIT_DISPLAY_ORDER = [
  'baluhost-backend',
  'baluhost-backend-local',
  'baluhost-scheduler',
  'baluhost-webdav',
  'baluhost-monitoring',
  'baluhost-tui',
  'baluhost-frontend-dev',
] as const;

// i18n key per unit (under `system:monitor.units.*`).
const UNIT_LABEL_KEY: Record<string, string> = {
  'baluhost-backend':       'monitor.units.backend',
  'baluhost-backend-local': 'monitor.units.backendLocal',
  'baluhost-scheduler':     'monitor.units.scheduler',
  'baluhost-webdav':        'monitor.units.webdav',
  'baluhost-monitoring':    'monitor.units.monitoring',
  'baluhost-tui':           'monitor.units.tui',
  'baluhost-frontend-dev':  'monitor.units.frontendDev',
};

export function MemoryTab({ timeRange }: { timeRange: TimeRange }) {
  const { t } = useTranslation(['system', 'common']);
  const { current, history, loading, error } = useMemoryMonitoring({ historyDuration: timeRange });
  const [breakdownOpen, setBreakdownOpen] = useState(false);

  const totalGb = current ? current.total_bytes / (1024 * 1024 * 1024) : 16;

  const chartData = useMemo(() => {
    return history
      .filter((s) => s.used_bytes > 0 && s.total_bytes > 0)
      .map((s) => ({
        time: s.timestamp,
        usedGb: s.used_bytes / (1024 * 1024 * 1024),
        baluhostGb: s.baluhost_memory_bytes && s.baluhost_memory_bytes > 0
          ? s.baluhost_memory_bytes / (1024 * 1024 * 1024)
          : null,
      }));
  }, [history]);

  const hasBaluhostData = chartData.some((d) => d.baluhostGb !== null);

  // Visible units = units with > 0 bytes, in canonical order.
  const visibleUnits = useMemo(() => {
    const breakdown = current?.baluhost_memory_breakdown;
    if (!breakdown) return [];
    return UNIT_DISPLAY_ORDER
      .filter((name) => (breakdown[name] ?? 0) > 0)
      .map((name) => ({ name, bytes: breakdown[name] }));
  }, [current]);

  if (error) {
    return <div className="text-red-400 text-center py-8">{error}</div>;
  }

  return (
    <div className="space-y-4 sm:space-y-6 min-w-0">
      <div className="grid grid-cols-1 min-[400px]:grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-5">
        <StatCard
          label={t('monitor.used')}
          value={current ? formatBytes(current.used_bytes) : '-'}
          color="purple"
          icon={<span className="text-purple-400 text-base sm:text-xl">📊</span>}
        />
        <StatCard
          label={t('monitor.total')}
          value={current ? formatBytes(current.total_bytes) : '-'}
          color="blue"
          icon={<span className="text-blue-400 text-base sm:text-xl">Σ</span>}
        />
        <StatCard
          label={t('monitor.available')}
          value={current?.available_bytes ? formatBytes(current.available_bytes) : '-'}
          color="green"
          icon={<span className="text-green-400 text-base sm:text-xl">✓</span>}
        />
        <StatCard
          label={t('monitor.utilization')}
          value={current?.percent != null ? formatNumber(current.percent, 1) : '0'}
          unit="%"
          color="orange"
          icon={<span className="text-orange-400 text-base sm:text-xl">%</span>}
        />

        {/* BaluHost breakdown card */}
        <div className="card border-slate-800/60 bg-slate-900/55 p-3 sm:p-4 flex flex-col">
          <button
            type="button"
            onClick={() => setBreakdownOpen((v) => !v)}
            className="flex items-center justify-between gap-2 text-left"
            aria-expanded={breakdownOpen}
          >
            <span className="flex items-center gap-2 text-xs sm:text-sm text-slate-400">
              <span className="text-cyan-400 text-base sm:text-xl">🏠</span>
              BaluHost
            </span>
            {visibleUnits.length > 0 && (
              breakdownOpen
                ? <ChevronDown className="h-4 w-4 text-slate-500" />
                : <ChevronRight className="h-4 w-4 text-slate-500" />
            )}
          </button>
          <div className="mt-1 text-xl sm:text-2xl font-semibold text-white tabular-nums">
            {current?.baluhost_memory_bytes ? formatBytes(current.baluhost_memory_bytes) : '-'}
          </div>

          {breakdownOpen && visibleUnits.length > 0 && (
            <ul className="mt-3 space-y-1 text-xs sm:text-sm">
              {visibleUnits.map((unit) => (
                <li key={unit.name} className="flex justify-between gap-2">
                  <span className="text-slate-400 truncate">
                    {t(UNIT_LABEL_KEY[unit.name] ?? unit.name)}
                  </span>
                  <span className="text-slate-200 tabular-nums shrink-0">
                    {formatBytes(unit.bytes)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="card border-slate-800/60 bg-slate-900/55 p-4 sm:p-6">
        <h3 className="mb-3 sm:mb-4 text-base sm:text-lg font-semibold text-white">{t('monitor.ramHistory')}</h3>
        <MetricChart
          data={chartData}
          lines={[
            { dataKey: 'usedGb', name: t('monitor.usedGb'), color: '#a855f7' },
            ...(hasBaluhostData
              ? [{ dataKey: 'baluhostGb', name: t('monitor.baluhostGb'), color: '#06b6d4' }]
              : []),
          ]}
          yAxisLabel="GB"
          yAxisDomain={[0, Math.ceil(totalGb)]}
          height={300}
          loading={loading}
          showArea
          timeRange={timeRange}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run:
```powershell
cd client
npx tsc --noEmit
```

Expected: no new errors (translation keys added in Task 8 — TS doesn't validate i18next keys).

- [ ] **Step 3: Build check**

Run:
```powershell
cd client
npm run build
```

Expected: build succeeds.

- [ ] **Step 4: Commit**

```powershell
git add client/src/components/system-monitor/MemoryTab.tsx
git commit -m "feat(ui): per-unit BaluHost memory breakdown in MemoryTab"
```

---

## Task 8: i18n keys (en + de)

**Files:**
- Modify: `client/src/i18n/locales/en/system.json`
- Modify: `client/src/i18n/locales/de/system.json`

- [ ] **Step 1: Locate the `monitor` group in both files**

Both files have a top-level `monitor` object. Add a new `units` sub-group.

- [ ] **Step 2: Add English keys**

In `client/src/i18n/locales/en/system.json`, inside the `monitor` object, add:

```json
    "units": {
      "backend": "Backend (HTTP)",
      "backendLocal": "Backend (Local)",
      "scheduler": "Scheduler",
      "webdav": "WebDAV",
      "monitoring": "Monitoring",
      "tui": "TUI",
      "frontendDev": "Frontend (dev)"
    }
```

(Place inside the `monitor: { ... }` block, before its closing brace. Add a trailing comma to the previous key inside `monitor` if needed.)

- [ ] **Step 3: Add German keys**

In `client/src/i18n/locales/de/system.json`, inside the `monitor` object, add:

```json
    "units": {
      "backend": "Backend (HTTP)",
      "backendLocal": "Backend (Lokal)",
      "scheduler": "Scheduler",
      "webdav": "WebDAV",
      "monitoring": "Monitoring",
      "tui": "TUI",
      "frontendDev": "Frontend (Dev)"
    }
```

- [ ] **Step 4: Validate JSON syntax**

Run:
```powershell
cd client
node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/en/system.json'))"
node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/de/system.json'))"
```

Expected: no output (both parse successfully).

- [ ] **Step 5: Build to verify**

Run:
```powershell
cd client
npm run build
```

Expected: build succeeds.

- [ ] **Step 6: Commit**

```powershell
git add client/src/i18n/locales/en/system.json client/src/i18n/locales/de/system.json
git commit -m "feat(i18n): BaluHost memory unit labels (en/de)"
```

---

## Task 9: Final verification

- [ ] **Step 1: Full backend test suite (monitoring + api)**

Run:
```powershell
cd backend
python -m pytest tests/monitoring/ tests/api/test_monitoring_routes.py -v
```

Expected: all pass.

- [ ] **Step 2: Quick smoke against dev server**

Start dev:
```powershell
python start_dev.py
```

In a separate terminal, log in and hit:
```powershell
curl -s http://localhost:3001/api/monitoring/memory/current -H "Authorization: Bearer <dev-token>" | python -m json.tool
```

Expected response contains a `baluhost_memory_breakdown` object with at least `baluhost-backend` non-zero (Uvicorn dev worker). Other units will likely be zero in dev unless `start_dev.py` runs them.

- [ ] **Step 3: Manual UI check**

Open `http://localhost:5173/system-monitor` → Memory tab. Verify:
- 5th card shows "BaluHost" with total + expandable arrow
- Expanding lists at least `Backend (HTTP)` with a non-zero value
- Chart still shows used + BaluHost lines

- [ ] **Step 4: Update vectordb index**

Use the MCP tool:
```
mcp__vectordb-search__index_update with projectPath D:/Programme (x86)/Baluhost
```

- [ ] **Step 5: Final commit (if any cleanup) and push**

Confirm clean tree:
```powershell
git status
```

If clean, push:
```powershell
git push -u origin feat/memory-per-unit-breakdown
```

- [ ] **Step 6: Open PR**

```powershell
gh pr create --title "feat: per-unit BaluHost RAM breakdown in System Monitor" --body "$(cat <<'EOF'
## Summary

- Fix RAM tracking so all five BaluHost systemd units are counted (scheduler / webdav / monitoring were silently missing)
- Separate `baluhost-backend-local` from `baluhost-backend` via first-match-wins on `--fd 3`
- Expose `baluhost_memory_breakdown` per unit in `/api/monitoring/memory/current`
- System Monitor → Memory tab: BaluHost card is now expandable, showing RSS per unit

## Test plan

- [ ] `python -m pytest backend/tests/monitoring/ backend/tests/api/test_monitoring_routes.py`
- [ ] Manual: open Memory tab, expand BaluHost card, see per-unit values
- [ ] Deploy to BaluNode, curl `/api/monitoring/memory/current` and confirm all five units have non-zero RSS

Spec: docs/superpowers/specs/2026-05-27-baluhost-ram-per-unit-breakdown-design.md
Plan: docs/superpowers/plans/2026-05-27-baluhost-ram-per-unit-breakdown.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review Checklist (already applied)

- Spec coverage: every section of the spec maps to a task (patterns → T1, first-match-wins → T2, breakdown helper → T3, schema/route → T4, SHM regression → T5, frontend type → T6, UI → T7, i18n → T8, verification → T9). ✓
- No placeholders. ✓
- Type consistency: `baluhost_memory_breakdown` named identically across Python/TS, schema, route, SHM, UI consumer. ✓
- File paths and line ranges match what was read in spec preparation. ✓
- Out-of-scope items from spec (per-worker drill-down, cgroup detection, DB persistence of breakdown) are not introduced in any task. ✓
