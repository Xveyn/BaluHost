"""Dev instances must not announce baluhost.local over mDNS (#678).

start_dev.py runs NAS_MODE=dev and the process becomes primary worker, so
without a guard every dev start on the LAN announces the production hostname.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import network_discovery as nd


def _settings(*, dev: bool, force: bool = False) -> SimpleNamespace:
    return SimpleNamespace(is_dev_mode=dev, mdns_force_enabled=force)


@pytest.fixture
def fake_zeroconf(monkeypatch):
    """Replace Zeroconf so no socket is ever opened, and pin the local IP."""
    zc_class = MagicMock(name="Zeroconf")
    monkeypatch.setattr(nd, "Zeroconf", zc_class)
    monkeypatch.setattr(nd.NetworkDiscoveryService, "get_local_ip", lambda self: "192.0.2.10")
    return zc_class


def test_dev_mode_does_not_register(monkeypatch, fake_zeroconf):
    monkeypatch.setattr(nd, "settings", _settings(dev=True))
    service = nd.NetworkDiscoveryService(hostname="baluhost")

    service.start()

    fake_zeroconf.assert_not_called()
    assert service.zeroconf is None
    assert service.get_status()["is_running"] is False


def test_dev_mode_with_force_registers_all_three_services(monkeypatch, fake_zeroconf):
    monkeypatch.setattr(nd, "settings", _settings(dev=True, force=True))
    service = nd.NetworkDiscoveryService(hostname="baluhost")

    service.start()

    fake_zeroconf.assert_called_once()
    assert fake_zeroconf.return_value.register_service.call_count == 3
    assert service.get_status()["is_running"] is True


def test_prod_mode_registers_all_three_services(monkeypatch, fake_zeroconf):
    monkeypatch.setattr(nd, "settings", _settings(dev=False))
    service = nd.NetworkDiscoveryService(hostname="baluhost")

    service.start()

    assert fake_zeroconf.return_value.register_service.call_count == 3


def test_prod_mode_ignores_the_force_flag(monkeypatch, fake_zeroconf):
    monkeypatch.setattr(nd, "settings", _settings(dev=False, force=True))
    service = nd.NetworkDiscoveryService(hostname="baluhost")

    service.start()

    assert fake_zeroconf.return_value.register_service.call_count == 3


def test_stop_after_skipped_start_is_a_noop(monkeypatch, fake_zeroconf):
    monkeypatch.setattr(nd, "settings", _settings(dev=True))
    service = nd.NetworkDiscoveryService(hostname="baluhost")
    service.start()

    service.stop()  # must not raise with zeroconf is None

    fake_zeroconf.assert_not_called()
