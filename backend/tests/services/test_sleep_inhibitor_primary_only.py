"""Die logind-Sperre gehoert dem Worker mit dem Schedule-Loop (#817).

`enter_soft_sleep()` und `enter_true_suspend()` raeumen eine aktive
Always-Awake-Uebersteuerung ab und gleichen die Sperre danach sofort ab. Die
Routen laufen aber in dem Worker, der die Anfrage gerade bedient -- bei vier
Uvicorn-Workern in drei von vier Faellen ein Follower. War dann noch ein
anderer Grund aktiv (Anwesenheit, Kernbetriebszeit, Gaming), erwarb der
Follower eine Block-Sperre. Freigeben kann sie nur der Abgleich im
Schedule-Loop, und der laeuft ausschliesslich im Primary: die Sperre blieb
stehen, bis das Backend neu startete.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import service_registry
from app.models.sleep import SleepConfig
from app.schemas.sleep import SleepState, SleepTrigger
from app.services import service_status
from app.services.power import sleep as sleep_mode
from app.services.power.sleep import SleepManagerService
from app.services.power.sleep_backend_dev import DevSleepBackend


def _config() -> SleepConfig:
    return SleepConfig(
        id=1,
        auto_idle_enabled=False,
        idle_timeout_minutes=15,
        idle_cpu_threshold=99.0,
        idle_disk_io_threshold=99.0,
        idle_http_threshold=999.0,
        auto_escalation_enabled=False,
        escalation_after_minutes=1,
        schedule_enabled=False,
        schedule_sleep_time="23:00",
        schedule_wake_time="06:00",
        schedule_mode="soft",
        wol_mac_address=None,
        wol_broadcast_address=None,
        pause_monitoring=False,
        pause_disk_io=False,
        reduced_telemetry_interval=30.0,
        disk_spindown_enabled=False,
        core_uptime_enabled=False,
        always_awake_enabled=True,
        always_awake_until=None,
    )


def _build_service() -> tuple[SleepManagerService, MagicMock]:
    SleepManagerService._instance = None
    svc = SleepManagerService(DevSleepBackend())
    inhibitor = MagicMock()
    inhibitor.is_held.return_value = False
    svc._core_uptime_inhibitor = inhibitor
    return svc, inhibitor


async def _start(svc: SleepManagerService, *, monitoring: bool) -> None:
    """Startet den Dienst in der gewuenschten Rolle, ohne Loops und ohne DB.

    Beim Start ist nichts aktiv, das eine Sperre rechtfertigt -- was die Tests
    danach am Inhibitor sehen, stammt also nicht aus dem Start.
    """
    with patch.object(svc, "_load_config", return_value=None), \
         patch.object(svc, "_load_core_uptime", return_value=(False, [])), \
         patch.object(svc, "_is_gaming_active", return_value=False), \
         patch.object(svc._core_uptime_rtc_guard, "start", new=AsyncMock()), \
         patch("app.services.power.sleep.asyncio.create_task",
               side_effect=lambda coro: coro.close() or None):
        await svc.start(monitoring=monitoring)


def _manual_sleep_patches(svc: SleepManagerService):
    """Lage aus dem Issue: Always-Awake aktiv, dazu ist jemand anwesend.

    Der erste Blick auf Always-Awake sieht die Uebersteuerung noch, jeder
    weitere (nach dem Abraeumen) nicht mehr. Anwesenheit bleibt als Grund
    stehen -- der Abgleich will die Sperre also halten.
    """
    seen = {"always_awake": 0}

    def always_awake(_cfg) -> bool:
        seen["always_awake"] += 1
        return seen["always_awake"] == 1

    return (
        patch.object(svc, "_load_config", return_value=_config()),
        patch.object(svc, "_load_core_uptime", return_value=(False, [])),
        patch.object(svc, "_clear_always_awake", new=MagicMock()),
        patch.object(svc, "_log_state_change", new=MagicMock()),
        patch.object(svc, "_is_always_awake", side_effect=always_awake),
        patch.object(svc, "_is_user_present", return_value=True),
        patch.object(svc, "_is_gaming_active", return_value=False),
        patch.object(svc._backend, "suspend_system", new=AsyncMock(return_value=True)),
    )


async def _manual_soft_sleep(svc: SleepManagerService) -> None:
    # Schon im Soft-Sleep: der Aufruf endet nach dem Abgleich, ohne die ganze
    # Einschlaf-Sequenz zu durchlaufen.
    svc._current_state = SleepState.SOFT_SLEEP
    p = _manual_sleep_patches(svc)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7]:
        await svc.enter_soft_sleep("test", SleepTrigger.MANUAL)


async def _manual_suspend(svc: SleepManagerService) -> None:
    svc._current_state = SleepState.SOFT_SLEEP
    p = _manual_sleep_patches(svc)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7]:
        await svc.enter_true_suspend("test", SleepTrigger.MANUAL)


# ─── Follower ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_follower_manual_soft_sleep_takes_no_lock():
    svc, inhibitor = _build_service()
    await _start(svc, monitoring=False)

    await _manual_soft_sleep(svc)

    inhibitor.acquire.assert_not_called()
    inhibitor.update_reason.assert_not_called()


@pytest.mark.asyncio
async def test_follower_manual_suspend_takes_no_lock():
    svc, inhibitor = _build_service()
    await _start(svc, monitoring=False)

    await _manual_suspend(svc)

    inhibitor.acquire.assert_not_called()
    inhibitor.update_reason.assert_not_called()


def test_instance_that_was_never_started_takes_no_lock():
    """Fail-closed: ohne ausdrueckliche Primary-Rolle wird nichts erworben."""
    svc, inhibitor = _build_service()

    with patch.object(svc, "_is_always_awake", return_value=True), \
         patch.object(svc, "_is_user_present", return_value=False), \
         patch.object(svc, "_is_gaming_active", return_value=False):
        svc._reconcile_sleep_inhibitor(_config(), in_core=True)

    inhibitor.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_follower_drops_a_lock_it_should_never_have_held():
    """Eine Sperre in einem Follower ist immer verwaist -- sie wird freigegeben,
    auch wenn die Gruende fuer eine Sperre weiter bestehen (der Primary haelt
    dann seine eigene)."""
    svc, inhibitor = _build_service()
    await _start(svc, monitoring=False)
    inhibitor.is_held.return_value = True

    with patch.object(svc, "_is_always_awake", return_value=True), \
         patch.object(svc, "_is_user_present", return_value=True), \
         patch.object(svc, "_is_gaming_active", return_value=False):
        svc._reconcile_sleep_inhibitor(_config(), in_core=True)

    inhibitor.release.assert_called_once_with()
    inhibitor.acquire.assert_not_called()
    inhibitor.update_reason.assert_not_called()


# ─── Primary ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_primary_manual_soft_sleep_still_reconciles_at_once():
    """Gegenprobe: im Primary bleibt der sofortige Abgleich erhalten."""
    svc, inhibitor = _build_service()
    await _start(svc, monitoring=True)

    await _manual_soft_sleep(svc)

    inhibitor.acquire.assert_called_once_with("user_present_active")


@pytest.mark.asyncio
async def test_primary_manual_suspend_still_reconciles_at_once():
    svc, inhibitor = _build_service()
    await _start(svc, monitoring=True)

    await _manual_suspend(svc)

    inhibitor.acquire.assert_called_once_with("user_present_active")


@pytest.mark.asyncio
async def test_stopped_service_no_longer_owns_the_lock():
    """Nach stop() darf ein spaeter Abgleich (etwa aus einer noch laufenden
    Anfrage) nichts mehr erwerben -- es gaebe keinen Loop, der es freigibt."""
    svc, inhibitor = _build_service()
    await _start(svc, monitoring=True)
    with patch.object(svc._core_uptime_rtc_guard, "stop", new=AsyncMock()):
        await svc.stop()
    inhibitor.reset_mock()
    inhibitor.is_held.return_value = False

    with patch.object(svc, "_is_always_awake", return_value=True), \
         patch.object(svc, "_is_user_present", return_value=False), \
         patch.object(svc, "_is_gaming_active", return_value=False):
        svc._reconcile_sleep_inhibitor(_config(), in_core=False)

    inhibitor.acquire.assert_not_called()


# ─── Admin-Neustart des Dienstes (gleiches Muster wie #555) ──────────


@pytest.fixture
def registry_snapshot():
    """register_all_services schreibt in ein Modul-Dict -- danach aufraeumen."""
    previous = dict(service_status._service_registry)
    yield
    service_status._service_registry.clear()
    service_status._service_registry.update(previous)


def _registered_start(monkeypatch, *, primary: bool) -> AsyncMock:
    """Gepatcht wird VOR der Registrierung: registriert war die nackte
    Funktion, ein spaeterer Patch haette diese Referenz nicht mehr erreicht."""
    started = AsyncMock()
    monkeypatch.setattr(sleep_mode, "start_sleep_manager", started)
    service_registry.register_all_services(
        is_primary_worker=primary, discovery_service=None
    )
    return started


@pytest.mark.asyncio
async def test_follower_service_restart_does_not_become_a_second_primary(
    monkeypatch, registry_snapshot
):
    """`restart_service` ruft start_fn() ohne Argument. Der Default von
    start_sleep_manager ist monitoring=True -- ein Follower startete damit
    Idle- und Schedule-Loop, RTC-Guard und eine eigene logind-Sperre."""
    started = _registered_start(monkeypatch, primary=False)
    start_fn = service_status._service_registry["sleep_mode"]["start"]

    await start_fn()

    assert started.await_count == 1
    assert started.await_args.kwargs.get("monitoring") is False


@pytest.mark.asyncio
async def test_primary_service_restart_keeps_the_primary_role(
    monkeypatch, registry_snapshot
):
    started = _registered_start(monkeypatch, primary=True)
    start_fn = service_status._service_registry["sleep_mode"]["start"]

    await start_fn()

    assert started.await_args.kwargs.get("monitoring") is True
