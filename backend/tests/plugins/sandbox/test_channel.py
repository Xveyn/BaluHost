"""Tests for the duplex RpcChannel (happy path)."""
import asyncio
import socket
import struct

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


async def test_reentrant_cap_call_during_request():
    # Host answers cap_call; plugin issues a cap_call while serving http_request.
    async def host_handler(msg: Message) -> Message:
        assert msg.type == MsgType.CAP_CALL
        return Message(id=msg.id, type=MsgType.CAP_RESULT, body={"value": "42"})

    channels: dict[str, RpcChannel] = {}

    async def plugin_handler(msg: Message) -> Message:
        result = await channels["plugin"].call(
            MsgType.CAP_CALL, {"capability": "storage.get"}, timeout=5
        )
        return Message(id=msg.id, type=MsgType.HTTP_RESPONSE, body={"got": result.body["value"]})

    ch_a, ch_b = await _connect(handler_a=host_handler, handler_b=plugin_handler)
    channels["plugin"] = ch_b
    try:
        resp = await ch_a.call(MsgType.HTTP_REQUEST, {}, timeout=5)
        assert resp.body == {"got": "42"}
    finally:
        await ch_a.close()
        await ch_b.close()


async def test_malformed_frame_drops_connection():
    # Ein roher Loopback-Client schickt ein bogus Oversize-Längenpräfix; der
    # RpcChannel auf der Server-Seite muss FrameError auslösen und abbauen
    # (statt 4 GiB zu allokieren). Loopback-TCP wie im _connect-Helper.
    accepted: dict[str, tuple] = {}
    ready = asyncio.Event()

    async def _on_client(reader, writer):
        accepted["pair"] = (reader, writer)
        ready.set()

    server = await asyncio.start_server(_on_client, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    raw = socket.create_connection((host, port))
    await ready.wait()
    s_reader, s_writer = accepted["pair"]
    server.close()

    ch = RpcChannel(s_reader, s_writer)
    ch.start()
    try:
        raw.sendall(struct.pack(">I", 0xFFFFFFFF))
        await asyncio.sleep(0.1)
        with pytest.raises(ConnectionError):
            await ch.call(MsgType.HTTP_REQUEST, {}, timeout=2)
    finally:
        await ch.close()
        raw.close()


async def test_garbage_msgpack_body_drops_connection():
    # A raw loopback client sends a VALID small length prefix + invalid msgpack
    # body (0xc1).  The RpcChannel read loop must decode_payload → FrameError →
    # drop the connection cleanly (no escaped exception); a pending call then
    # raises ConnectionError.
    accepted: dict[str, tuple] = {}
    ready = asyncio.Event()

    async def _on_client(reader, writer):
        accepted["pair"] = (reader, writer)
        ready.set()

    server = await asyncio.start_server(_on_client, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    raw = socket.create_connection((host, port))
    await ready.wait()
    s_reader, s_writer = accepted["pair"]
    server.close()

    ch = RpcChannel(s_reader, s_writer)
    ch.start()
    try:
        # Valid 4-byte length prefix (1 byte payload) + 1 invalid msgpack byte.
        raw.sendall(struct.pack(">I", 1) + b"\xc1")
        await asyncio.sleep(0.1)
        with pytest.raises(ConnectionError):
            await ch.call(MsgType.HTTP_REQUEST, {}, timeout=2)
    finally:
        await ch.close()
        raw.close()


async def test_close_fails_inflight_call():
    async def never(msg: Message) -> Message:
        await asyncio.sleep(100)
        return Message(id=msg.id, type=MsgType.HTTP_RESPONSE, body={})

    ch_a, ch_b = await _connect(handler_b=never)
    task = asyncio.create_task(ch_a.call(MsgType.HTTP_REQUEST, {}))
    await asyncio.sleep(0.05)
    await ch_a.close()
    with pytest.raises(ConnectionError):
        await task
    await ch_b.close()
