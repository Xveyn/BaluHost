Backend tests — Quick Guide

Overview
- Tests use pytest + pytest-asyncio. Backend is FastAPI with SQLAlchemy and Pydantic.
- Dev-mode helpers: `SKIP_APP_INIT=1` avoids full app startup for isolated tests.

Running tests
- Run full backend suite (from repo root):

```bash
python -m pytest backend -q
```

- Run a single test file or test:

```bash
python -m pytest backend/tests/test_sync_integration.py::TestSyncIntegration::test_complete_sync_workflow -q
```

Test environment notes
- Many tests use an in-memory SQLite DB and dependency override for `get_db`.
- If tests interact with filesystem, dev storage is used. Ensure `NAS_MODE=dev` when running dev-only scenarios.
- To run tests that require skipping global startup, the test fixtures set `SKIP_APP_INIT=1` — do not remove unless you want the full background services to start.

Common flags
- `-q` quiet, `-k <expr>` select tests by substring, `-x` stop after first failure.
- Use `-s` to see stdout prints when debugging.

Debugging tips
- If you see `Task was destroyed but it is pending!`, ensure the app lifespan is cleaning up background tasks. The test harness sets `SKIP_APP_INIT=1` for isolation — check lifespan finalizer if background tasks leak.
- For DB schema issues like `no such table`, verify the test fixture created tables (Base.metadata.create_all) or that the test overrides `get_db` correctly.
- For permission failures (403) in sync tests, inspect `file_metadata_db` writes (create_metadata) and ensure owner IDs are created in the same DB session used by the test client.

Useful commands
- Run with verbose output and full traceback:

```bash
python -m pytest backend -vv -s
```

- Run single fast failing test loop (run until pass):

```bash
python -m pytest backend/tests/test_sync_integration.py::TestSyncIntegration::test_multiple_device_sync -q -k test_multiple_device_sync
```

Contact / Notes
- The test harness in `backend/tests/conftest.py` contains fixtures for `client`, `async_client`, and temporary storage helpers. Inspect it when adding or modifying tests.
- If you change app startup/lifespan behavior, update tests that rely on `SKIP_APP_INIT`.
