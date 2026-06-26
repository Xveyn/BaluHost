"""In-process tests for the sandbox worker entry point (no real subprocess)."""
import asyncio

import pytest

from app.plugins.sandbox.channel import RpcChannel
from app.plugins.sandbox.protocol import Message, MsgType
from app.plugins.sandbox.transport import WorkerListener
from app.plugins.sandbox.worker import build_worker_handler, main, run_worker


async def _host_and_worker(tmp_path):
    """Start a host listener + an in-process run_worker; return (host_channel,
    worker_task, listener) wired and ready."""
    listener = WorkerListener(tmp_path)
    address = await listener.start()
    worker_task = asyncio.create_task(run_worker(address))
    reader, writer = await listener.accept(timeout=5)
    host = RpcChannel(reader, writer)
    host.start()
    return host, worker_task, listener


async def test_worker_answers_health(tmp_path):
    host, worker_task, listener = await _host_and_worker(tmp_path)
    try:
        resp = await host.call(MsgType.LIFECYCLE, {"action": "health"}, timeout=5)
        assert resp.type == MsgType.LIFECYCLE
        assert resp.body == {"status": "ok"}
    finally:
        await host.close()
        await asyncio.wait_for(worker_task, timeout=5)
        await listener.close()


async def test_worker_echoes_http_request(tmp_path):
    host, worker_task, listener = await _host_and_worker(tmp_path)
    try:
        resp = await host.call(
            MsgType.HTTP_REQUEST,
            {"method": "GET", "path": "ping", "body": b"", "context": {"user_id": 7}},
            timeout=5,
        )
        assert resp.type == MsgType.HTTP_RESPONSE
        assert resp.body["status"] == 200
        assert resp.body["echo"]["method"] == "GET"
        assert resp.body["echo"]["path"] == "ping"
        assert resp.body["echo"]["context"] == {"user_id": 7}
    finally:
        await host.close()
        await asyncio.wait_for(worker_task, timeout=5)
        await listener.close()


async def test_worker_run_returns_when_host_closes(tmp_path):
    host, worker_task, listener = await _host_and_worker(tmp_path)
    await host.close()
    # run_worker must observe the closed connection and return on its own.
    await asyncio.wait_for(worker_task, timeout=5)
    assert worker_task.done() and worker_task.exception() is None
    await listener.close()


def test_main_requires_connect_arg():
    with pytest.raises(SystemExit):
        main([])


def test_build_worker_handler_is_async_callable():
    handler = build_worker_handler()
    assert asyncio.iscoroutinefunction(handler)
