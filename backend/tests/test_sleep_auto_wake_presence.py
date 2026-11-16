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
    from app.services.power.sleep import SleepActionResult, SleepActionStatus

    manager = MagicMock()
    manager.effective_state.return_value = (SleepState.SOFT_SLEEP, None)
    manager.request_wake = AsyncMock(return_value=SleepActionResult(SleepActionStatus.DONE))
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
    manager.request_wake.assert_not_called()


def test_other_request_still_auto_wakes_from_soft_sleep():
    app = _make_app()
    manager = _sleeping_manager()
    with patch("app.services.power.sleep.record_http_request"), \
         patch("app.services.power.sleep.get_sleep_manager", return_value=manager):
        TestClient(app).post("/api/files/upload")
    manager.request_wake.assert_called_once()
