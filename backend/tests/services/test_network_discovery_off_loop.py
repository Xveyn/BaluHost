"""mDNS-Registrierung darf nicht im Event-Loop-Thread laufen (#714).

zeroconf's synchrone `register_service()` / `unregister_service()` werfen
`EventLoopBlocked`, wenn im aufrufenden Thread ein Event-Loop laeuft. Der
Lifespan rief `start()` aus genau so einem Thread -- in Produktion startete die
Discovery deshalb bei keinem Start. Der Fake bildet diese Pruefung nach.
"""
import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import network_discovery as nd


class EventLoopBlocked(Exception):
    """Wie zeroconf._exceptions.EventLoopBlocked: str(e) ist leer."""


class _LoopSensitiveZeroconf:
    def __init__(self):
        self.registered = []
        self.unregistered = []
        self.closed = False

    @staticmethod
    def _refuse_inside_loop():
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise EventLoopBlocked()

    def register_service(self, info):
        self._refuse_inside_loop()
        self.registered.append(info)

    def unregister_service(self, info):
        self._refuse_inside_loop()
        self.unregistered.append(info)

    def close(self):
        self.closed = True


@pytest.fixture
def zc(monkeypatch):
    instance = _LoopSensitiveZeroconf()
    monkeypatch.setattr(nd, "Zeroconf", lambda: instance)
    monkeypatch.setattr(nd, "settings", SimpleNamespace(is_dev_mode=False, mdns_force_enabled=False))
    monkeypatch.setattr(nd.NetworkDiscoveryService, "get_local_ip", lambda self: "192.0.2.10")
    return instance


@pytest.mark.asyncio
async def test_async_start_registers_all_three_services_inside_a_running_loop(zc):
    service = nd.NetworkDiscoveryService(hostname="baluhost")

    await service.async_start()

    assert len(zc.registered) == 3
    assert service.get_status()["is_running"] is True


@pytest.mark.asyncio
async def test_async_stop_unregisters_inside_a_running_loop(zc):
    service = nd.NetworkDiscoveryService(hostname="baluhost")
    await service.async_start()

    await service.async_stop()

    assert len(zc.unregistered) == 3
    assert zc.closed is True


@pytest.mark.asyncio
async def test_failure_log_names_the_exception_even_when_its_message_is_empty(
    monkeypatch, caplog
):
    zc = MagicMock()
    zc.register_service.side_effect = EventLoopBlocked()
    monkeypatch.setattr(nd, "Zeroconf", lambda: zc)
    monkeypatch.setattr(nd, "settings", SimpleNamespace(is_dev_mode=False, mdns_force_enabled=False))
    monkeypatch.setattr(nd.NetworkDiscoveryService, "get_local_ip", lambda self: "192.0.2.10")

    with caplog.at_level(logging.ERROR, logger=nd.logger.name):
        await nd.NetworkDiscoveryService(hostname="baluhost").async_start()

    assert any("EventLoopBlocked" in r.getMessage() for r in caplog.records)
