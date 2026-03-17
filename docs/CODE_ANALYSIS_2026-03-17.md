# Code Analysis Report — 2026-03-17

Static analysis of `backend/app/` using **ruff 0.6.9** and **mypy 1.19.1**.

---

## Summary

| Tool | Total Errors | Critical | Medium | Low |
|------|-------------|----------|--------|-----|
| Ruff | 337 | 2 | 67 | 268 |
| Mypy | 361 (filtered) | ~20 | ~15 | rest is type noise |

---

## Ruff Findings

### Statistics

| Rule | Count | Description |
|------|-------|-------------|
| F401 | 164 | Unused imports |
| E402 | 71 | Module-level import not at top of file |
| E712 | 52 | `== True`/`== False` instead of `is True`/`is False` |
| F821 | 18 | Undefined name (mostly SQLAlchemy forward refs — false positives) |
| F841 | 15 | Unused variable |
| F541 | 11 | f-string without placeholders |
| E401 | 2 | Multiple imports on one line |
| F811 | 2 | Redefined while unused |
| E711 | 1 | `== None` instead of `is None` |
| E721 | 1 | `type()` comparison instead of `isinstance()` |

### Unused Variables (F841) — Medium

```
backend/app/api/routes/samba.py:123          — user = user_service.get_user(...) never used
backend/app/api/routes/users.py:180          — deleted = user_service.delete_user(...) never used
backend/app/api/routes/vcl_admin.py:117      — except Exception as e: (e unused)
backend/app/api/routes/vcl_admin.py:188      — vcl_service = VCLService(db) never used
backend/app/services/files/ownership.py:718  — except Exception as e: (e unused)
backend/app/services/notifications/firebase.py:47 — settings = get_settings() never used
backend/app/services/power/sleep.py:704      — prev_state = self._current_state never used
backend/app/services/ssh_service.py:72       — except AuthenticationException as e: (e unused)
backend/app/services/ssh_service.py:75       — except NoValidConnectionsError as e: (e unused)
backend/app/services/update/service.py:657   — backup_service = BackupService(self.db) never used
backend/app/services/versioning/cache.py:205 — version = vcl_service.create_version(...) never used
backend/app/services/versioning/tracking.py:82 — parent_path never used
```

### Wrong Comparisons — Medium

```
backend/app/services/power/manager.py:286    — type(new_backend) == type(self._backend) → use isinstance()
backend/app/services/versioning/vcl.py:540   — VCLSettings.user_id == None → use is None
```

---

## Mypy Findings (Critical & High)

Filtered out: SQLAlchemy `Column[T]` assignment noise, `var-annotated`, forward reference false positives (`"User"`, `"MobileDevice"`, etc. in relationship strings).

### HIGH — Likely Runtime Crashes

#### 1. `middleware/error_counter.py:32,39` — @property on non-instance methods

```
error: Only instance methods can be decorated with @property  [misc]
```

`@property` used on class methods or static methods — will raise `TypeError` at access time.

#### 2. `services/sync/file_sync.py:145` — str > None comparison

```
error: Unsupported operand types for > ("str" and "None")  [operator]
```

Will raise `TypeError` at runtime when comparing string to `None`.

#### 3. `services/notifications/scheduler.py:70` — None - timedelta

```
error: Unsupported operand types for - ("None" and "timedelta")  [operator]
```

Will crash if the variable is `None` when subtraction is attempted.

#### 4. `services/notifications/scheduler.py:90,93,101,106` — object + int / object.append()

```
error: Unsupported operand types for + ("object" and "int")  [operator]
error: "object" has no attribute "append"  [attr-defined]
```

Multiple lines where operations are performed on untyped/wrong-typed objects.

#### 5. `services/versioning/priority.py:484,488` — object + int / object.append()

```
error: Unsupported operand types for + ("object" and "int")  [operator]
error: "object" has no attribute "append"  [attr-defined]
```

Same pattern — arithmetic/list operations on `object` type.

#### 6. `services/files/ownership.py:394,413` — int not iterable

```
error: "int" has no attribute "__iter__"; maybe "__int__"? (not iterable)  [attr-defined]
```

Attempting to iterate over an `int` value — will crash at runtime.

#### 7. `core/rate_limiter.py:182` — bool not callable

```
error: "bool" not callable  [operator]
```

A boolean value is being called as a function — will raise `TypeError`.

#### 8. `services/power/sleep.py:256,268,519` — Non-existent methods

```
:256  error: Module "app.services.disk_monitor" has no attribute "get_latest_io_stats"  [attr-defined]
:268  error: "UploadProgressManager" has no attribute "get_all_progress"; maybe "get_progress"?  [attr-defined]
:519  error: "FanControlService" has no attribute "_fans"  [attr-defined]
```

Calling methods that don't exist on their respective classes/modules.

#### 9. `services/power/monitor.py:172` — object.update() doesn't exist

```
error: "object" has no attribute "update"  [attr-defined]
```

#### 10. `api/routes/system.py:363,381` — AuditLoggerDB.enable/.disable don't exist

```
:363  error: "AuditLoggerDB" has no attribute "enable"; maybe "_enabled"?  [attr-defined]
:381  error: "AuditLoggerDB" has no attribute "disable"  [attr-defined]
```

Public methods called that don't exist — the attribute is `_enabled` (private).

#### 11. `api/routes/system_raid.py:242,252,262` — DeleteArrayRequest.name doesn't exist

```
error: "DeleteArrayRequest" has no attribute "name"  [attr-defined]
```

Schema field accessed that doesn't exist on the Pydantic model.

#### 12. `api/routes/pihole.py:538,539` — Response attributes don't exist

```
:538  error: "Response" has no attribute "has_password"  [attr-defined]
:539  error: "Response" has no attribute "has_remote_password"  [attr-defined]
```

### MEDIUM — Potential Issues

#### 13. `services/benchmark/lifecycle.py:72` — signal.SIGKILL on Windows

```
error: Module has no attribute "SIGKILL"; maybe "SIGILL"?  [attr-defined]
```

`signal.SIGKILL` is not available on Windows. Will crash if this code path is hit on Windows.

#### 14. `services/power/cpu_linux_backend.py:305` — BaseException not iterable

```
error: "BaseException" object is not iterable  [misc]
```

#### 15. `compat/__init__.py:24` — asyncio.AbstractEventLoopPolicy removed

```
error: Name "asyncio.AbstractEventLoopPolicy" is not defined  [name-defined]
```

Removed in Python 3.14 — will fail on newer Python versions.

#### 16. `services/backup/service.py:681` — Returns None instead of Path

```
error: Incompatible return value type (got "Path | None", expected "Path")  [return-value]
```

Callers expecting `Path` may crash on `None`.

#### 17. `services/power/energy.py:348` — Returns None instead of dict

```
error: Incompatible return value type (got "None", expected "dict[Any, Any]")  [return-value]
```

#### 18. `services/scheduler/worker.py:381` — Returns str instead of dict | None

```
error: Incompatible return value type (got "str", expected "dict[Any, Any] | None")  [return-value]
```

#### 19. `core/power_rating.py:96,102` — Incompatible await / return type

```
:96   error: Incompatible types in "await" (actual type "T", expected type "Awaitable[Any]")  [misc]
:102  error: Incompatible return value type  [return-value]
```

#### 20. `services/monitoring/worker_service.py:96,170,239,374` — Wrong module attribute

```
error: Module "app.services" has no attribute "power_monitor"; maybe "_power_monitor"?  [attr-defined]
```

#### 21. `api/routes/benchmark.py:33` — Wrong module attribute

```
error: Module "app.services" has no attribute "benchmark_service"; maybe "_benchmark_service"?  [attr-defined]
```

### LOW — Type Annotation Issues (Not Runtime Bugs)

- Optical drive plugin: ~40 errors — Mixin classes reference parent class methods (works at runtime via MRO, mypy can't resolve)
- `services/monitoring/base.py`: `Base.timestamp` — generic base class, actual models have the attribute
- Various `Column[T]` assignment mismatches — SQLAlchemy runtime behavior is correct
- `core/lifespan.py:88` — `fcntl.flock`/`LOCK_EX`/`LOCK_NB` — Linux-only, expected on Windows

---

## Recommended Fix Priority

1. **Sofort fixen** (HIGH): Items 1-12 — können Runtime-Crashes verursachen
2. **Bald fixen** (MEDIUM): Items 13-21 — Edge-Cases und falsche Return-Types
3. **Bei Gelegenheit** (LOW): Unused imports, unused variables, f-string cleanup
4. **Ignorieren**: SQLAlchemy Column-Type-Noise, Mixin forward refs, Linux-only code auf Windows
