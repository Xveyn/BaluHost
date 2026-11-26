"""SMART- und Health-Route laufen im Threadpool, nicht auf dem Event-Loop (#872)."""
import threading
from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_smart_status_route_reads_off_event_loop(async_client, user_headers, monkeypatch):
    from app.services.hardware import smart as smart_service   # derselbe Import wie api/routes/system.py:31
    from app.schemas.system import SmartStatusResponse
    seen = []
    def fake():
        seen.append(threading.get_ident())
        return SmartStatusResponse(checked_at=datetime.now(tz=timezone.utc), devices=[])
    monkeypatch.setattr(smart_service, "get_smart_status", fake)
    r = await async_client.get("/api/system/smart/status", headers=user_headers)
    assert r.status_code == 200
    assert seen and threading.get_ident() not in seen
