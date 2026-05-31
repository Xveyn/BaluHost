import asyncio

from app.services.power.desktop import DesktopService, get_desktop_service
from app.services.power.desktop_backend import DevDesktopBackend
from app.schemas.desktop import DesktopState


def test_service_delegates_to_backend():
    svc = DesktopService(backend=DevDesktopBackend())
    assert asyncio.run(svc.get_status()).state is DesktopState.RUNNING
    ok, _ = asyncio.run(svc.disable())
    assert ok
    assert asyncio.run(svc.get_status()).state is DesktopState.STOPPED


def test_get_desktop_service_is_singleton():
    a = get_desktop_service()
    b = get_desktop_service()
    assert a is b
