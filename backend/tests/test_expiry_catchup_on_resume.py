"""enter_true_suspend triggers a device-expiration catch-up after wake (#229)."""

import asyncio
from unittest.mock import patch, AsyncMock

from app.schemas.sleep import SleepTrigger


def test_resume_triggers_expiry_catchup():
    from app.services.power.sleep import SleepManagerService
    from app.services.power.sleep_backend_dev import DevSleepBackend

    backend = DevSleepBackend()
    svc = SleepManagerService(backend)

    # emit_system_suspend/resume are awaited inside enter_true_suspend, so they
    # MUST be AsyncMock (a plain MagicMock is not awaitable → asyncio.wait_for
    # would raise).
    with patch(
        "app.services.notifications.scheduler.NotificationScheduler.check_and_send_warnings",
        return_value={"checked": 0, "sent": 0, "skipped": 0, "failed": 0, "errors": []},
    ) as mock_check, patch(
        "app.services.notifications.events.emit_system_suspend", new=AsyncMock(),
    ), patch(
        "app.services.notifications.events.emit_system_resume", new=AsyncMock(),
    ):
        result = asyncio.run(svc.enter_true_suspend("test", SleepTrigger.MANUAL))

    assert result is True
    assert mock_check.call_count == 1
