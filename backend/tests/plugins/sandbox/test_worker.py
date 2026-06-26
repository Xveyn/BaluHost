"""In-process tests for the sandbox worker entry point (no real subprocess)."""
import asyncio

import pytest

from app.plugins.sandbox.channel import RpcChannel
from app.plugins.sandbox.protocol import Message, MsgType
from app.plugins.sandbox.sdk import PluginHost
from app.plugins.sandbox.transport import WorkerListener
from app.plugins.sandbox.worker import build_worker_handler, main, run_worker


def _make_echo_host() -> PluginHost:
    """A PluginHost with one route that echoes method, path, and user context."""
    host = PluginHost()

    @host.route("GET", "ping")
    async def echo(request):  # noqa: RUF029
        return {
            "status": 200,
            "body": {
                "method": request["method"],
                "path": request["path"],
                "context": request["user"],
            },
        }

    return host


async def _host_and_worker(tmp_path, plugin_host=None):
    """Start a host listener + an in-process run_worker; return (host_channel,
    worker_task, listener) wired and ready."""
    if plugin_host is None:
        plugin_host = _make_echo_host()
    listener = WorkerListener(tmp_path)
    address = await listener.start()
    worker_task = asyncio.create_task(run_worker(address, plugin_host))
    reader, writer = await listener.accept(timeout=5)
    host = RpcChannel(reader, writer)
    host.start()
    return host, worker_task, listener


async def test_worker_answers_health(tmp_path):
    host, worker_task, listener = await _host_and_worker(tmp_path)
    try:
        resp = await host.call(MsgType.LIFECYCLE, {"action": "health"}, timeout=5)
        assert resp.type == MsgType.LIFECYCLE_RESULT
        assert resp.body == {"status": "ok"}
    finally:
        await host.close()
        await asyncio.wait_for(worker_task, timeout=5)
        await listener.close()


async def test_worker_dispatches_http_request_via_sdk(tmp_path):
    """Phase 3: HTTP requests are routed through the PluginHost SDK, not echoed."""
    host, worker_task, listener = await _host_and_worker(tmp_path)
    try:
        resp = await host.call(
            MsgType.HTTP_REQUEST,
            {
                "request_id": 1,
                "method": "GET",
                "path": "ping",
                "body": b"",
                "context": {"user_id": 7, "username": "alice", "role": "user"},
            },
            timeout=5,
        )
        assert resp.type == MsgType.HTTP_RESPONSE
        assert resp.body["status"] == 200
        assert resp.body["body"]["method"] == "GET"
        assert resp.body["body"]["path"] == "ping"
        assert resp.body["body"]["context"]["user_id"] == 7
    finally:
        await host.close()
        await asyncio.wait_for(worker_task, timeout=5)
        await listener.close()


async def test_worker_unknown_route_returns_404(tmp_path):
    """Requests for unregistered routes return a 404 HTTP_RESPONSE (not an error frame)."""
    host, worker_task, listener = await _host_and_worker(tmp_path)
    try:
        resp = await host.call(
            MsgType.HTTP_REQUEST,
            {"request_id": 2, "method": "GET", "path": "/no-such-route", "body": b"", "context": {}},
            timeout=5,
        )
        assert resp.type == MsgType.HTTP_RESPONSE
        assert resp.body["status"] == 404
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
    host = PluginHost()
    handler = build_worker_handler(host)
    assert asyncio.iscoroutinefunction(handler)
