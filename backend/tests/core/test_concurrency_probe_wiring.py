"""Die Probe muss im Lifespan hängen — und im Shutdown wieder verschwinden."""
import pytest
from fastapi.testclient import TestClient

from app.core import lifespan as lifespan_module
from app.main import app


@pytest.fixture(autouse=True)
def _drive_the_real_lifespan(monkeypatch):
    """These two tests assert on `_startup()`/`_shutdown()` side effects, so the
    module-wide `SKIP_APP_INIT=1` test default (which makes `lifespan()` a no-op,
    see `tests/conftest.py`) has to be lifted just for them."""
    monkeypatch.delenv("SKIP_APP_INIT", raising=False)


def _probe_tasks() -> list:
    return [
        task
        for task in lifespan_module._BACKGROUND_TASKS
        if task.get_name() == "concurrency_probe"
    ]


def test_probe_task_runs_while_the_app_is_up(client: TestClient):
    """Die `client`-Fixture betritt den TestClient-Kontext und fährt damit den
    echten Lifespan hoch."""
    tasks = _probe_tasks()

    assert len(tasks) == 1, "genau ein Probe-Task pro Worker"
    assert not tasks[0].done()


def test_probe_task_is_cancelled_on_shutdown():
    """Nach dem Verlassen des Kontexts darf kein Task zurückbleiben.

    Bewusst OHNE die `client`-Fixture: die verwaltet ihren TestClient-Kontext
    selbst, ein manuelles __exit__ würde ihn doppelt verlassen. Hier gehört
    der Kontext dem Test, also kann er ihn regulär schließen und danach prüfen.
    """
    with TestClient(app):
        tasks = _probe_tasks()
        assert len(tasks) == 1
        task = tasks[0]

    assert task.cancelled() or task.done()
    assert not _probe_tasks(), "_BACKGROUND_TASKS muss geleert sein"
