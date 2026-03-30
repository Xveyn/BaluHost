# Backend Dev Mode Checklist

## Environment & Configuration
- [x] Add environment flag (e.g. `NAS_MODE=dev`) to `app.core.config.Settings` and document sample `.env` entries.
- [x] Ensure `settings.nas_storage_path` defaults to a dev sandbox (e.g. `./dev-storage`) when `NAS_MODE=dev`.
- [x] Seed fixtures in dev mode: create demo folders/files and admin user credentials on startup (runs once).

## Storage & Quotas
- [x] Implement configurable quota limit (`NAS_QUOTA_BYTES`); enforce in `app.services.files.save_uploads`.
- [x] Extend `get_storage_info()` to return simulated totals (10 GB) and actual usage via `Path` traversal in dev mode.
- [x] Provide mock RAID status service returning healthy/failed scenarios for UI testing (Linux-only execution for real commands).

## System Monitoring
- [x] Enhance `app.services.system.get_system_info` to supply deterministic mock metrics when `NAS_MODE=dev`.
- [x] Add SMART diagnostics service with dev-mode fixture data.
- [x] Create background job hooks (placeholder) for scheduled health checks.

## API Layer
- [x] Expose new endpoints (`/api/storage/quota`, `/api/raid/status`, `/api/smart/devices`) with mock responses in dev mode.
- [x] Add admin-only POST endpoints to trigger simulated rebuild/failure scenarios for frontend testing.
- [x] Document API schema differences between dev/prod in README.

## Tooling & Docs
- [x] Update `start_dev.py` to set `NAS_MODE=dev` automatically when running on Windows.
- [x] Extend README with dev-mode instructions, including required Python/Node steps on Windows.
- [x] Add integration tests (Pytest) that validate dev-mode mocks behave consistently.
- [x] Provide backend test script/CLI to trigger and debug NAS functions during development.
- [x] Provide teardown script to reset dev storage directory between test runs.
