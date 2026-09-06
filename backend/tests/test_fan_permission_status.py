"""permission_status und sein Weg bis in die Antwort (#554).

Dieser Pfad war vollstaendig ungetestet -- und genau er hat in #552 gelogen:
die Fan-Control-Seite pollt ihn alle 5 Sekunden, `isReadOnly` sperrt daraufhin
die Bedienelemente. Ein Fehler darin ist fuer den Nutzer nicht von einem
kaputten Backend zu unterscheiden.

Die Route wird ueber `__wrapped__` aufgerufen, also ohne den slowapi-Dekorator:
geprueft wird die Ableitung, nicht das Rate-Limit.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.routes import fans as fans_routes
from app.services.power.fan_backend_linux import LinuxFanControlBackend
from app.services.power.fan_control import FanControlService


def _service(*, backend, use_linux: bool) -> FanControlService:
    FanControlService._instance = None
    config = MagicMock()
    config.is_dev_mode = False
    svc = FanControlService(config, MagicMock())
    svc._backend = backend
    svc._use_linux_backend = use_linux
    return svc


def _linux_backend(*, may_write: bool) -> LinuxFanControlBackend:
    backend = LinuxFanControlBackend(MagicMock())
    backend._has_write_permission = may_write
    backend.get_fans = AsyncMock(return_value=[])
    return backend


@pytest.mark.asyncio
async def test_without_a_backend_the_status_is_unavailable():
    svc = _service(backend=None, use_linux=False)

    status = await svc.get_status()

    assert status["permission_status"] == "unavailable"
    assert status["backend_available"] is False


@pytest.mark.asyncio
async def test_the_dev_backend_is_always_ok():
    """Im Dev-Backend gibt es keine sysfs-Rechte, an denen etwas scheitern koennte."""
    dev = SimpleNamespace(get_fans=AsyncMock(return_value=[]))
    svc = _service(backend=dev, use_linux=False)

    status = await svc.get_status()

    assert status["permission_status"] == "ok"


@pytest.mark.asyncio
async def test_a_writable_linux_backend_is_ok():
    svc = _service(backend=_linux_backend(may_write=True), use_linux=True)

    status = await svc.get_status()

    assert status["permission_status"] == "ok"


@pytest.mark.asyncio
async def test_a_linux_backend_without_write_permission_is_readonly():
    """Der Zustand, der in #552 faelschlich in allen vier Workern anlag."""
    svc = _service(backend=_linux_backend(may_write=False), use_linux=True)

    status = await svc.get_status()

    assert status["permission_status"] == "readonly"


async def _response_for(status: str):
    service = SimpleNamespace(get_status=AsyncMock(return_value={
        "fans": [],
        "is_dev_mode": False,
        "is_using_linux_backend": True,
        "permission_status": status,
        "backend_available": True,
    }))
    handler = fans_routes.get_permission_status.__wrapped__
    return await handler(
        request=SimpleNamespace(),
        response=SimpleNamespace(),
        current_user=MagicMock(),
        service=service,
    )


@pytest.mark.asyncio
async def test_ok_answers_without_suggestions():
    body = await _response_for("ok")

    assert body.has_write_permission is True
    assert body.status == "ok"
    assert body.suggestions == []


@pytest.mark.asyncio
async def test_readonly_answers_with_the_sudoers_hint():
    """Die Vorschlaege sind die einzige Hilfe, die der Nutzer an der Stelle bekommt."""
    body = await _response_for("readonly")

    assert body.has_write_permission is False
    assert body.status == "readonly"
    assert body.suggestions, "readonly ohne Handlungshinweis"
    assert any("tee" in hint for hint in body.suggestions)


@pytest.mark.asyncio
async def test_unavailable_points_at_the_sensor_setup():
    body = await _response_for("unavailable")

    assert body.has_write_permission is False
    assert body.status == "unavailable"
    assert any("sensors-detect" in hint for hint in body.suggestions)
