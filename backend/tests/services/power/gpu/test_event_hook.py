"""Tests for the deep-idle event hook registry."""
import asyncio
import pytest

from app.services.power.gpu import events


@pytest.fixture(autouse=True)
def _reset_hooks():
    events._deep_idle_entering_callbacks.clear()
    events._deep_idle_exiting_callbacks.clear()
    yield
    events._deep_idle_entering_callbacks.clear()
    events._deep_idle_exiting_callbacks.clear()


@pytest.mark.asyncio
async def test_register_and_emit_entering():
    called = []

    async def cb():
        called.append("hit")

    events.register_deep_idle_entering(cb)
    await events.emit_deep_idle_entering()
    assert called == ["hit"]


@pytest.mark.asyncio
async def test_multiple_callbacks_run_in_parallel():
    order = []

    async def slow():
        await asyncio.sleep(0.05)
        order.append("slow")

    async def fast():
        order.append("fast")

    events.register_deep_idle_entering(slow)
    events.register_deep_idle_entering(fast)
    await events.emit_deep_idle_entering()
    # Fast should finish first if running in parallel
    assert order == ["fast", "slow"]


@pytest.mark.asyncio
async def test_callback_exception_does_not_block_others():
    called = []

    async def boom():
        raise RuntimeError("kaboom")

    async def survives():
        called.append("survived")

    events.register_deep_idle_entering(boom)
    events.register_deep_idle_entering(survives)
    await events.emit_deep_idle_entering()
    assert called == ["survived"]


@pytest.mark.asyncio
async def test_exiting_hook_separate_from_entering():
    enter_called = []
    exit_called = []

    async def on_enter():
        enter_called.append("e")

    async def on_exit():
        exit_called.append("x")

    events.register_deep_idle_entering(on_enter)
    events.register_deep_idle_exiting(on_exit)

    await events.emit_deep_idle_exiting()
    assert enter_called == []
    assert exit_called == ["x"]
