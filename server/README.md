# Legacy Express Backend

This Express + TypeScript backend has been superseded by the FastAPI implementation under `../backend`.

## When to use it?
- Only if you need to compare previous behaviour or prototype TypeScript middleware quickly.
- It no longer receives new features (quota, SMART, RAID, telemetry).

## Recommended alternative
- Switch to the FastAPI service (`backend/app`) and run it with `uvicorn app.main:app --reload --port 3001` or `python start_dev.py` from the repo root.

## Removal plan
- Update remaining documentation to drop references to this package.
- Migrate any outstanding scripts/tests to the FastAPI service.
- Once consumers have switched, delete the `server/` directory.
