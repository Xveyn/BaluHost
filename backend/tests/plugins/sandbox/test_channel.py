"""Tests for the duplex RpcChannel (happy path)."""
import asyncio

import pytest

from app.plugins.sandbox.channel import RpcChannel
from app.plugins.sandbox.protocol import Message, MsgType


async def _connect(handler_a=None, handler_b=None):
    # Loopback-TCP-Paar statt socket.socketpair()+open_connection(sock=…):
    # portabel über Linux UND Windows (ProactorEventLoop akzeptiert ein
    # vorab-connectetes `sock=` nicht zuverlässig); kein Subprozess nötig.
    accepted: dict[str, tuple] = {}
    ready = asyncio.Event()

    async def _on_client(reader, writer):
        accepted["pair"] = (reader, writer)
        ready.set()

    server = await asyncio.start_server(_on_client, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    a_reader, a_writer = await asyncio.open_connection(host, port)
    await ready.wait()
    b_reader, b_writer = accepted["pair"]
    server.close()

    ch_a = RpcChannel(a_reader, a_writer, request_handler=handler_a)
    ch_b = RpcChannel(b_reader, b_writer, request_handler=handler_b)
    ch_a.start()
    ch_b.start()
    return ch_a, ch_b


async def test_call_returns_handler_response():
    async def handler(msg: Message) -> Message:
        return Message(id=msg.id, type=MsgType.HTTP_RESPONSE, body={"echo": msg.body["v"]})

    ch_a, ch_b = await _connect(handler_b=handler)
    try:
        resp = await ch_a.call(MsgType.HTTP_REQUEST, {"v": "hi"}, timeout=5)
        assert resp.type == MsgType.HTTP_RESPONSE
        assert resp.body == {"echo": "hi"}
    finally:
        await ch_a.close()
        await ch_b.close()


async def test_call_times_out_when_handler_is_slow():
    async def slow(msg: Message) -> Message:
        await asyncio.sleep(10)
        return Message(id=msg.id, type=MsgType.HTTP_RESPONSE, body={})

    ch_a, ch_b = await _connect(handler_b=slow)
    try:
        with pytest.raises(asyncio.TimeoutError):
            await ch_a.call(MsgType.HTTP_REQUEST, {}, timeout=0.1)
    finally:
        await ch_a.close()
        await ch_b.close()
