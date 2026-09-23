"""The ws bus must start in EVERY worker — that is the whole point of #685."""

import ast
import inspect

import pytest

from app.core import lifespan as lifespan_module
from app.services.websocket_manager import WebSocketManager


class RecordingBus:
    def __init__(self) -> None:
        self.started_with = "not started"
        self.stopped = False

    async def publish(self, env):
        pass

    async def start(self, deliver):
        self.started_with = deliver

    async def stop(self):
        self.stopped = True


@pytest.mark.asyncio
async def test_bus_starts_bound_to_deliver_local(monkeypatch):
    bus = RecordingBus()
    monkeypatch.setattr(lifespan_module, "build_bus", lambda: bus)
    manager = WebSocketManager()

    await lifespan_module._start_ws_bus(manager)

    assert bus.started_with == manager.deliver_local
    assert manager._bus is bus


def _enclosing_if_tests(tree: ast.AST, target: ast.AST) -> list[ast.expr]:
    """Return the `test` expression of every `if` that encloses `target`.

    Builds a child->parent map by walking the whole tree once, then follows
    it up from `target`, collecting the `test` of each `ast.If` ancestor.
    """
    parent_of: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent_of[child] = node

    tests: list[ast.expr] = []
    node: "ast.AST | None" = parent_of.get(target)
    while node is not None:
        if isinstance(node, ast.If):
            tests.append(node.test)
        node = parent_of.get(node)
    return tests


def test_bus_start_is_not_gated_on_primary_worker():
    """The `_start_ws_bus(...)` call site in `_startup()` must not sit inside
    an `if IS_PRIMARY_WORKER` branch — a secondary worker holds connections
    too, and gating this would leave #685 open for the other five API
    processes.

    This cannot run `_startup()` itself and check the resulting side effect:
    the test suite sets SKIP_APP_INIT, which skips it entirely, and the rest
    of `_startup()` needs a real database connection. So this inspects the
    call site's own source instead — walking the AST to find every `if` that
    encloses the call and asserting none of them test IS_PRIMARY_WORKER. A
    prior version of this test called `_start_ws_bus()` directly, which
    proved nothing: that function itself never mentions IS_PRIMARY_WORKER,
    so the test stayed green regardless of how its caller in `_startup()`
    was gated.
    """
    source = inspect.getsource(lifespan_module._startup)
    tree = ast.parse(source)

    call = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_start_ws_bus"
        ),
        None,
    )
    assert call is not None, "_start_ws_bus(...) call not found in _startup()"

    for test in _enclosing_if_tests(tree, call):
        for name in ast.walk(test):
            if isinstance(name, ast.Name) and name.id == "IS_PRIMARY_WORKER":
                pytest.fail(
                    "_start_ws_bus(...) is called inside an "
                    "`if IS_PRIMARY_WORKER` branch in _startup() — this "
                    "would leave #685 open for every secondary worker"
                )


@pytest.mark.asyncio
async def test_stop_stops_the_bus(monkeypatch):
    bus = RecordingBus()
    monkeypatch.setattr(lifespan_module, "build_bus", lambda: bus)
    await lifespan_module._start_ws_bus(WebSocketManager())

    await lifespan_module._stop_ws_bus()

    assert bus.stopped is True


@pytest.mark.asyncio
async def test_start_failure_does_not_break_startup(monkeypatch):
    class ExplodingBus(RecordingBus):
        async def start(self, deliver):
            raise RuntimeError("no database")

    monkeypatch.setattr(lifespan_module, "build_bus", lambda: ExplodingBus())
    await lifespan_module._start_ws_bus(WebSocketManager())  # must not raise
