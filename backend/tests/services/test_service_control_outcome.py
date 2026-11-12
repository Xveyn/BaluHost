"""Start/Stop/Restart melden, was danach wirklich der Fall ist (#764).

Erfolg wurde allein daraus abgeleitet, dass die Steuerfunktion keine Exception
warf. Viele Dienste behandeln Fehler aber intern: `NetworkDiscoveryService.start()`
loggt nur, und im Dev-Mode ueberspringt es die mDNS-Registrierung bewusst. Die
Admin-Oberflaeche meldete dann "Service started successfully" neben einem
Dienst, der weiter gestoppt war.
"""
import pytest

from app.schemas.service_status import ServiceStateEnum
from app.services.service_status import (
    ServiceStatusCollector,
    _service_registry,
    register_service,
)


@pytest.fixture(autouse=True)
def clear_registry():
    _service_registry.clear()
    yield
    _service_registry.clear()


@pytest.fixture(autouse=True)
def no_settle_delay(monkeypatch):
    """Die Stabilisierungspause (0,5 s) traegt zu diesen Aussagen nichts bei."""
    async def _instant(_seconds):
        return None

    monkeypatch.setattr("app.services.service_status.asyncio.sleep", _instant)


@pytest.fixture
def collector():
    return ServiceStatusCollector()


class _Service:
    """Ein Dienst, dessen Steuerfunktionen nie werfen -- wie die echten."""

    def __init__(self, *, running: bool, start_works: bool = True,
                 stop_works: bool = True, enabled: bool = True) -> None:
        self.running = running
        self.start_works = start_works
        self.stop_works = stop_works
        self.enabled = enabled
        self.calls: list[str] = []

    def start(self) -> None:
        self.calls.append("start")
        if self.start_works:
            self.running = True

    def stop(self) -> None:
        self.calls.append("stop")
        if self.stop_works:
            self.running = False

    def register(self, name: str = "svc", *, with_restart_fn: bool = False) -> None:
        register_service(
            name=name,
            display_name=name,
            get_status_fn=lambda: {"is_running": self.running},
            start_fn=self.start,
            stop_fn=self.stop,
            restart_fn=(lambda: self.calls.append("restart")) if with_restart_fn else None,
            config_enabled_fn=lambda: self.enabled,
        )


# ─── start ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_that_leaves_the_service_stopped_is_not_a_success(collector):
    svc = _Service(running=False, start_works=False)
    svc.register()

    result = await collector.start_service("svc")

    assert svc.calls == ["start"]
    assert result.success is False
    assert result.current_state == ServiceStateEnum.STOPPED
    assert "did not reach running state" in result.message


@pytest.mark.asyncio
async def test_start_that_works_is_still_a_success(collector):
    svc = _Service(running=False)
    svc.register()

    result = await collector.start_service("svc")

    assert result.success is True
    assert result.current_state == ServiceStateEnum.RUNNING
    assert result.message == "Service started successfully"


@pytest.mark.asyncio
async def test_start_of_a_config_disabled_service_names_the_reason(collector):
    """Der Fall aus dem Issue: mDNS im Dev-Mode. Der Zustand heisst dann
    DISABLED, nicht STOPPED -- die Meldung muss trotzdem ehrlich sein."""
    svc = _Service(running=False, start_works=False, enabled=False)
    svc.register()

    result = await collector.start_service("svc")

    assert result.success is False
    assert result.current_state == ServiceStateEnum.DISABLED
    assert "disabled by configuration" in result.message


@pytest.mark.asyncio
async def test_start_of_a_config_disabled_service_that_runs_anyway_is_a_success(collector):
    """DISABLED ueberdeckt in der Anzeige, ob der Dienst laeuft. Massgeblich
    ist, was der Dienst selbst meldet: laeuft er, war der Start erfolgreich."""
    svc = _Service(running=False, enabled=False)
    svc.register()

    result = await collector.start_service("svc")

    assert result.success is True
    assert result.current_state == ServiceStateEnum.DISABLED


# ─── restart ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_restart_that_leaves_the_service_stopped_is_not_a_success(collector):
    svc = _Service(running=True, start_works=False)
    svc.register()

    result = await collector.restart_service("svc")

    assert svc.calls == ["stop", "start"]
    assert result.success is False
    assert result.current_state == ServiceStateEnum.STOPPED
    assert "did not reach running state" in result.message


@pytest.mark.asyncio
async def test_restart_via_restart_fn_that_leaves_the_service_stopped_is_not_a_success(collector):
    svc = _Service(running=False)
    svc.register(with_restart_fn=True)

    result = await collector.restart_service("svc")

    assert svc.calls == ["restart"]
    assert result.success is False


@pytest.mark.asyncio
async def test_restart_that_works_is_still_a_success(collector):
    svc = _Service(running=True)
    svc.register()

    result = await collector.restart_service("svc")

    assert result.success is True
    assert result.message == "Service restarted successfully"


# ─── stop ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stop_that_leaves_the_service_running_is_not_a_success(collector):
    svc = _Service(running=True, stop_works=False)
    svc.register()

    result = await collector.stop_service("svc")

    assert svc.calls == ["stop"]
    assert result.success is False
    assert result.current_state == ServiceStateEnum.RUNNING
    assert "still running" in result.message


@pytest.mark.asyncio
async def test_stop_that_works_is_still_a_success(collector):
    svc = _Service(running=True)
    svc.register()

    result = await collector.stop_service("svc")

    assert result.success is True
    assert result.message == "Service stopped successfully"


# ─── Statusfunktion selbst kaputt ────────────────────────────────────


@pytest.mark.asyncio
async def test_start_is_not_a_success_when_the_status_cannot_be_read(collector):
    """Ohne lesbaren Zustand gibt es keinen Beleg fuer einen Erfolg."""
    def broken_status():
        raise RuntimeError("status backend down")

    register_service(
        name="svc",
        display_name="svc",
        get_status_fn=broken_status,
        start_fn=lambda: None,
    )

    result = await collector.start_service("svc")

    assert result.success is False
    assert result.current_state == ServiceStateEnum.ERROR


@pytest.mark.asyncio
async def test_stop_is_not_a_success_when_the_status_cannot_be_read(collector):
    def broken_status():
        raise RuntimeError("status backend down")

    register_service(
        name="svc",
        display_name="svc",
        get_status_fn=broken_status,
        stop_fn=lambda: None,
    )

    result = await collector.stop_service("svc")

    assert result.success is False
    assert "could not be determined" in result.message
