"""The janitor for abandoned chunked uploads runs in the primary only.

Chunked upload sessions are files in a directory all API processes share. One
process cleaning it is enough — and before this, none did: the cleanup loop
existed but nothing started it.

Tests `_start_chunked_upload_cleanup_if_primary()` directly rather than
through the real lifespan: `tests/conftest.py` sets `SKIP_APP_INIT=1`, so
`_startup()` never runs in the suite. Its call site is checked from the source.
"""
from __future__ import annotations

import ast
import inspect

import pytest

import app.services.files.chunked_upload as cu
from app.core import lifespan as lifespan_module


@pytest.fixture
def manager(monkeypatch, tmp_path):
    monkeypatch.setattr(cu, "TMP_UPLOAD_DIR", tmp_path / "uploads")
    fresh = cu.ChunkedUploadManager()
    monkeypatch.setattr(cu, "_manager", fresh)
    return fresh


@pytest.mark.asyncio
async def test_the_primary_starts_the_cleanup_loop(monkeypatch, manager):
    monkeypatch.setattr(lifespan_module, "IS_PRIMARY_WORKER", True)

    lifespan_module._start_chunked_upload_cleanup_if_primary()

    task = manager._cleanup_task
    assert task is not None and not task.done()
    await manager.shutdown()
    assert task.done()


@pytest.mark.asyncio
async def test_a_secondary_worker_starts_nothing(monkeypatch, manager):
    monkeypatch.setattr(lifespan_module, "IS_PRIMARY_WORKER", False)

    lifespan_module._start_chunked_upload_cleanup_if_primary()

    assert manager._cleanup_task is None


def test_startup_starts_it_only_after_the_primary_is_elected():
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

    assert line_of_call("_start_chunked_upload_cleanup_if_primary") > line_of_call(
        "_try_become_primary"
    )


@pytest.mark.asyncio
async def test_cleanup_loop_cleans_soon_after_start_and_survives_an_error(monkeypatch, manager):
    """Not only after the first full hour: the service restarts with every
    deploy, and an hourly timer that starts over each time may never fire."""
    sleeps: list[float] = []
    runs: list[int] = []

    async def _sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= 3:
            raise cu.asyncio.CancelledError

    async def _cleanup():
        runs.append(1)
        if len(runs) == 1:
            raise RuntimeError("disk hiccup")

    monkeypatch.setattr(cu.asyncio, "sleep", _sleep)
    monkeypatch.setattr(manager, "_cleanup_stale", _cleanup)

    await manager._cleanup_loop()

    assert sleeps[0] <= 300
    assert len(runs) == 2  # the first one failing did not end the loop
