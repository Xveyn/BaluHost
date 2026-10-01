"""Network Discovery shows as DISABLED, not STOPPED, when dev mode skips it (#678).

With the dev guard in NetworkDiscoveryService.start() the service is silent on
every dev start. Without a `config_enabled` hook the admin dashboard reported
that as a stopped (failed-looking) service instead of a deliberately disabled one.
"""
import pytest

from app.core import service_registry
from app.core.config import settings
from app.services import service_status
from app.services.service_status import ServiceStateEnum, ServiceStatusCollector


@pytest.fixture
def registry_snapshot():
    """register_all_services writes into a module dict -- restore it afterwards."""
    previous = dict(service_status._service_registry)
    yield
    service_status._service_registry.clear()
    service_status._service_registry.update(previous)


def _state(monkeypatch, *, dev: bool, force: bool) -> ServiceStateEnum:
    monkeypatch.setattr(settings, "is_dev_mode", dev)
    monkeypatch.setattr(settings, "mdns_force_enabled", force)
    service_registry.register_all_services(is_primary_worker=True, discovery_service=None)
    service = ServiceStatusCollector().get_service("network_discovery")
    assert service is not None
    return service.state


def test_dev_mode_reports_disabled(monkeypatch, registry_snapshot):
    assert _state(monkeypatch, dev=True, force=False) == ServiceStateEnum.DISABLED


def test_dev_mode_with_force_is_not_disabled(monkeypatch, registry_snapshot):
    # discovery_service is None here, so the status reader says "not running";
    # the point is only that the config hook no longer masks it as disabled.
    assert _state(monkeypatch, dev=True, force=True) == ServiceStateEnum.STOPPED


def test_prod_mode_is_not_disabled(monkeypatch, registry_snapshot):
    assert _state(monkeypatch, dev=False, force=False) == ServiceStateEnum.STOPPED
