# Backend Services Refactoring Plan

## Overview

**Status:** 46 Service-Dateien, ~17.600 Zeilen Code
**Priority:** Medium (Software runs stable, but structural weaknesses exist)
**Production Since:** January 2026

---

## Quick Wins (Low Effort, High Value)

### 1. Unify Audit Logger

**Problem:** Duplicate code across two implementations
**Files:**
- `backend/app/services/audit_logger.py` (380 lines)
- `backend/app/services/audit_logger_db.py` (575 lines)

**Tasks:**
- [ ] Create abstract interface `AuditLogger` (Protocol or ABC)
- [ ] Implement `FileAuditLogger` and `DatabaseAuditLogger`
- [ ] Add factory function: `get_audit_logger(backend='db' | 'file')`
- [ ] Merge duplicate code from both files

**Estimated Effort:** 1-2 hours

---

### 2. Replace Generic Exception Handlers

**Problem:** 154 `except Exception:` blocks make debugging difficult
**Focus Areas:**
- `power_manager.py` (39 generic handlers)
- `fan_control.py`
- `raid.py`

**Tasks:**
- [ ] Create custom exception hierarchy:
  ```python
  class BaluHostError(Exception): pass
  class ServiceError(BaluHostError): pass
  class ConfigError(BaluHostError): pass
  class HardwareError(BaluHostError): pass
  class ValidationError(BaluHostError): pass
  ```
- [ ] Replace generic handlers with specific exceptions
- [ ] Add proper error context and logging

**Estimated Effort:** 2-3 hours

---

### 3. Replace Singletons with Dependency Injection

**Problem:** 7 manual singletons make testing difficult
**Affected:**
- `FanControlService._instance`
- `PowerManagerService._instance`
- `MonitoringOrchestrator._instance`
- `service_status._service_registry`
- `scheduler_service`

**Tasks:**
- [ ] Identify all singleton usages
- [ ] Convert to FastAPI dependencies or simple DI container
- [ ] Update all import sites

**Estimated Effort:** 2-3 hours

---

## Medium Priority (Structural Improvements)

### 4. Split `power_manager.py` (1,224 lines)

**Problem:** God class with 704-line `__init__` method

**New Structure:**
```
backend/app/services/power/
├── __init__.py
├── backend.py          # LinuxCpuPowerBackend, DevPowerBackend
├── validator.py        # PowerProfileValidator
├── manager.py          # PowerProfileManager
├── auto_scaling.py     # AutoScalingManager
├── state_tracker.py    # PowerStateTracker
└── models.py           # Value objects, enums
```

**Tasks:**
- [ ] Extract `PowerProfileValidator` class
- [ ] Extract `PowerProfileManager` for profile management
- [ ] Extract `AutoScalingManager` for automatic scaling
- [ ] Extract `PowerStateTracker` for state tracking
- [ ] Break down `__init__` into smaller setup methods
- [ ] Update imports in routes and other services

**Estimated Effort:** 4-6 hours

---

### 5. Split `fan_control.py` (1,101 lines)

**Problem:** `_persist_samples` method is 353 lines

**New Structure:**
```
backend/app/services/fans/
├── __init__.py
├── service.py          # Main FanControlService
├── persistence.py      # FanSamplePersistence
├── hysteresis.py       # HysteresisController
├── curves.py           # Temperature curve logic
└── models.py           # Value objects
```

**Tasks:**
- [ ] Extract `FanSamplePersistence` class
- [ ] Extract `HysteresisController` for temperature curves
- [ ] Apply Repository pattern for sample storage
- [ ] Update imports in routes

**Estimated Effort:** 3-4 hours

---

### 6. Split `raid.py` (1,376 lines)

**Problem:** Mixed concerns - parsing, state, simulation

**New Structure:**
```
backend/app/services/raid/
├── __init__.py
├── service.py          # Main RaidService
├── state.py            # RaidStateManager
├── parser.py           # RaidParser (mdstat/mdadm output)
├── simulation.py       # DevRaidBackend
├── linux.py            # MdadmRaidBackend
└── models.py           # RaidConfiguration value object
```

**Tasks:**
- [ ] Extract `RaidStateManager` for state management
- [ ] Extract `RaidParser` for output parsing
- [ ] Move simulation backend to separate file
- [ ] Create `RaidConfiguration` value object
- [ ] Update imports in routes

**Estimated Effort:** 4-5 hours

---

### 7. Clean Up `service_status.py` (650 lines)

**Problem:** Global dictionary instead of proper class

**New Structure:**
```
backend/app/services/status/
├── __init__.py
├── registry.py         # ServiceRegistry class
├── manager.py          # ServiceRestartManager
├── collector.py        # ServiceHealthCollector
└── models.py           # ServiceStatus, HealthReport
```

**Tasks:**
- [ ] Create `ServiceRegistry` class (replace global dict)
- [ ] Extract `ServiceRestartManager` for restart/stop/start logic
- [ ] Extract `ServiceHealthCollector` for aggregation
- [ ] Update imports in routes

**Estimated Effort:** 2-3 hours

---

## Low Priority (Optional)

### 8. Increase Test Coverage

**Problem:** Critical services have 0 tests

**Tasks:**
- [ ] Add unit tests for `scheduler_service.py` (0 tests, 582 lines)
- [ ] Add unit tests for `power_manager.py` (0 tests, 1,224 lines)
- [ ] Add unit tests for `fan_control.py` (0 tests, 1,101 lines)
- [ ] Target: Minimum 80% coverage for refactored services

**Files to Create:**
- `backend/tests/test_scheduler_service.py`
- `backend/tests/test_power_manager.py`
- `backend/tests/test_fan_control.py`

---

### 9. Async/Await Consistency

**Tasks:**
- [ ] Convert `audit_logger.py` to async
- [ ] Review `files.py` for async I/O opportunities
- [ ] Replace threading in `disk_monitor`, `power_monitor`, `fan_control` with asyncio

---

### 10. Code Quality Tools

**Tasks:**
- [ ] Add `pytest-cov` for coverage reports
- [ ] Enable `mypy` for static type checks
- [ ] Complete `ruff` configuration

**Add to `pyproject.toml`:**
```toml
[tool.pytest.ini_options]
addopts = "--cov=app --cov-report=html"

[tool.mypy]
strict = true
ignore_missing_imports = true
```

---

## No Refactoring Needed (Already Clean)

- `monitoring/` subdirectory - well structured
- Type hints - consistently present
- Docstrings - consistent throughout
- `vcl.py` - good structure
- `backup.py` - well organized

---

## Recommended Order

| Step | Task | Effort | Risk |
|------|------|--------|------|
| 1 | Unify Audit Logger | 1-2h | Low |
| 2 | Custom Exceptions | 2-3h | Low |
| 3 | Split `power_manager.py` | 4-6h | Medium |
| 4 | Split `fan_control.py` | 3-4h | Medium |
| 5 | Split `raid.py` | 4-5h | Medium |
| 6 | Clean `service_status.py` | 2-3h | Low |
| 7 | Add Tests (parallel) | 4-6h | None |

**Total Estimated Effort:** 20-30 hours

---

## Risk Mitigation

### Risks
- **Regressions:** Production system stable since Jan 2026
- **Breaking Changes:** API contracts must remain unchanged

### Mitigation Strategy
1. Work on `development` branch
2. Refactor one service at a time
3. Run full test suite after each change
4. Manual testing in dev mode
5. Thorough code review before merge

---

## Verification Checklist

After each refactoring step:

```bash
# 1. Run existing tests (364 tests)
cd backend && python -m pytest -v

# 2. Start dev server
python start_dev.py

# 3. Test affected endpoints
# Open http://localhost:3001/docs

# 4. Check for import errors
python -c "from app.main import app"

# 5. Verify no type errors (if mypy enabled)
mypy app/
```

---

## File Reference

| Service | Lines | Priority | Issues |
|---------|-------|----------|--------|
| `power_manager.py` | 1,224 | High | 704-line `__init__`, 39 generic exceptions |
| `raid.py` | 1,376 | High | Mixed concerns |
| `fan_control.py` | 1,101 | High | 353-line method |
| `service_status.py` | 650 | Medium | Global state |
| `audit_logger_db.py` | 575 | Medium | Duplicate code |
| `scheduler_service.py` | 582 | Low | No tests |
| `audit_logger.py` | 380 | Medium | Duplicate code |

---

## Progress Tracking

### Quick Wins
- [ ] Audit Logger unified
- [ ] Custom exceptions implemented
- [ ] Singletons replaced with DI

### Structural
- [ ] `power_manager.py` split
- [ ] `fan_control.py` split
- [ ] `raid.py` split
- [ ] `service_status.py` cleaned

### Quality
- [ ] Test coverage > 80%
- [ ] mypy passing
- [ ] All generic exceptions replaced

---

*Last Updated: January 31, 2026*
