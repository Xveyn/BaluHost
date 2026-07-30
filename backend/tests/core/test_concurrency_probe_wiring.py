"""Die Probe muss im Lifespan hängen — und im Shutdown wieder verschwinden.

Testet `_start_concurrency_probe()` direkt statt über den echten Lifespan:
`tests/conftest.py` setzt `SKIP_APP_INIT=1` für die gesamte Session, wodurch
`lifespan()` `_startup()` nie ausführt. Ein Test, der die App trotzdem real
hochfährt, würde ~43s kosten und Modul-Globals für den Rest der Session
verschmutzen — daher die extrahierte, direkt testbare Funktion.
"""
import asyncio

import pytest

from app.core import lifespan as lifespan_module
from app.core.config import settings


def _probe_tasks() -> list:
    return [
        task
        for task in lifespan_module._BACKGROUND_TASKS
        if task.get_name() == "concurrency_probe"
    ]


@pytest.fixture(autouse=True)
async def _clean_background_tasks():
    """`_BACKGROUND_TASKS` is a module-level global shared with the rest of
    the suite. Cancel and await anything a test spawned so a leaked probe
    task can't keep ticking through every later test in the session — even
    if the test body fails before reaching its own cleanup."""
    yield
    tasks = _probe_tasks()
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    for task in tasks:
        lifespan_module._BACKGROUND_TASKS.discard(task)


async def test_enabled_starts_a_named_task_referenced_in_background_tasks():
    task = lifespan_module._start_concurrency_probe()

    assert task is not None
    assert task.get_name() == "concurrency_probe"
    assert task in lifespan_module._BACKGROUND_TASKS


async def test_cancelled_on_shutdown():
    task = lifespan_module._start_concurrency_probe()
    assert task is not None

    await lifespan_module._cancel_background_tasks()

    assert task.cancelled() or task.done()
    assert not _probe_tasks(), "_BACKGROUND_TASKS muss geleert sein"


async def test_disabled_returns_none_and_spawns_nothing(monkeypatch):
    monkeypatch.setattr(settings, "concurrency_probe_enabled", False)

    task = lifespan_module._start_concurrency_probe()

    assert task is None
    assert not _probe_tasks()


def _middleware_classes(monkeypatch) -> list:
    """App bauen und die registrierten Middleware-Klassen zurückgeben.

    `setup_logging()` wird dabei stillgelegt: es entfernt sämtliche
    Root-Handler und würde das Log-Capturing der restlichen Session
    mitreißen."""
    monkeypatch.setattr("app.core.logging_config.setup_logging", lambda: None)
    from app.main import create_app

    return [middleware.cls for middleware in create_app().user_middleware]


async def test_middleware_is_registered_when_the_probe_is_enabled(monkeypatch):
    from app.middleware.inflight import InFlightMiddleware

    monkeypatch.setattr(settings, "concurrency_probe_enabled", True)

    assert InFlightMiddleware in _middleware_classes(monkeypatch)


async def test_disabled_also_removes_the_middleware_from_the_hot_path(monkeypatch):
    """Der dokumentierte Aus-Schalter muss BEIDE Hälften abschalten.

    Bliebe die Middleware registriert, liefe der Zähler auf dem Pfad jedes
    Requests weiter — ohne dass je jemand `drain()` ruft, also mit unbegrenzt
    wachsenden Zählern und einem `_in_flight_max`, das zum Allzeithoch wird.
    """
    from app.middleware.inflight import InFlightMiddleware

    monkeypatch.setattr(settings, "concurrency_probe_enabled", False)

    assert InFlightMiddleware not in _middleware_classes(monkeypatch)
