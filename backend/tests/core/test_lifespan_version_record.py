"""Only the primary worker counts a start in `version_history` (#715).

`times_started` is meant to count service starts. Recorded in every process it
counted workers instead — six per deploy on the production box (four TCP
workers, two on the local channel).

Tests `_record_version_if_primary()` directly rather than through the real
lifespan: `tests/conftest.py` sets `SKIP_APP_INIT=1`, so `_startup()` never
runs in the suite. Its call site is checked from the source instead.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from app.core import lifespan as lifespan_module
from app.services import version_tracker


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    calls: list[object] = []
    monkeypatch.setattr(version_tracker, "record_version_on_startup", calls.append)
    return calls


def test_the_primary_records_the_start(monkeypatch, recorded):
    monkeypatch.setattr(lifespan_module, "IS_PRIMARY_WORKER", True)

    lifespan_module._record_version_if_primary()

    assert len(recorded) == 1


def test_a_secondary_worker_records_nothing(monkeypatch, recorded):
    monkeypatch.setattr(lifespan_module, "IS_PRIMARY_WORKER", False)

    lifespan_module._record_version_if_primary()

    assert recorded == []


def test_startup_records_only_after_the_primary_is_elected():
    """Called before `_try_become_primary()`, the helper would see the module
    default (`IS_PRIMARY_WORKER = False`) in every worker and no start would
    ever be recorded — silently, because that is also the correct behaviour of
    a secondary."""
    tree = ast.parse(inspect.getsource(lifespan_module._startup))

    def line_of_call(name: str) -> int:
        lines = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        ]
        assert len(lines) == 1, f"expected exactly one {name}(...) call in _startup(), found {lines}"
        return lines[0]

    assert line_of_call("_record_version_if_primary") > line_of_call("_try_become_primary")
