"""Tests for the cross-platform host<->worker transport."""
import asyncio

import pytest

from app.plugins.sandbox.protocol import Message, MsgType, read_frame, write_frame
from app.plugins.sandbox.transport import (
    WorkerListener,
    _use_unix_socket,
    connect_to_host,
)


async def test_connect_address_scheme_matches_platform(tmp_path):
    listener = WorkerListener(tmp_path)
    address = await listener.start()
    try:
        expected = "unix:" if _use_unix_socket() else "tcp:"
        assert address.startswith(expected)
    finally:
        await listener.close()


async def test_accept_roundtrip_carries_a_frame(tmp_path):
    listener = WorkerListener(tmp_path)
    address = await listener.start()
    try:
        # Worker side connects back; host accepts the one connection.
        w_reader, w_writer = await connect_to_host(address)
        h_reader, h_writer = await listener.accept(timeout=5)

        # Worker -> host
        await write_frame(w_writer, Message(id=1, type=MsgType.LIFECYCLE, body={"ping": True}))
        got = await read_frame(h_reader)
        assert got == Message(id=1, type=MsgType.LIFECYCLE, body={"ping": True})

        # Host -> worker
        await write_frame(h_writer, Message(id=2, type=MsgType.HTTP_RESPONSE, body={"ok": 1}))
        back = await read_frame(w_reader)
        assert back == Message(id=2, type=MsgType.HTTP_RESPONSE, body={"ok": 1})

        w_writer.close()
        h_writer.close()
    finally:
        await listener.close()


async def test_connect_to_host_rejects_unknown_scheme():
    with pytest.raises(ValueError):
        await connect_to_host("carrierpigeon:/nope")


@pytest.mark.skipif(not _use_unix_socket(), reason="UDS only (Linux/macOS)")
def test_two_listeners_same_dir_get_distinct_sockets(tmp_path):
    """Two WorkerListeners on the same plugin dir must not share a socket path."""
    import asyncio

    async def run():
        a = WorkerListener(tmp_path)
        b = WorkerListener(tmp_path)
        addr_a = await a.start()
        addr_b = await b.start()
        try:
            assert addr_a != addr_b
            assert addr_a.startswith("unix:") and addr_b.startswith("unix:")
        finally:
            await a.close()
            await b.close()

    asyncio.run(run())
