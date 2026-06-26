"""Tests for the sandbox RPC frame codec and message types."""
import asyncio

import msgpack
import pytest

from app.plugins.sandbox.protocol import (
    FrameError,
    MAX_FRAME_BYTES,
    Message,
    MsgType,
    REQUEST_TYPES,
    RESPONSE_TYPES,
    _LENGTH_PREFIX,
    decode_payload,
    encode_frame,
    read_frame,
)


def _reader(data: bytes) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return reader


async def test_frame_roundtrip():
    msg = Message(id=7, type=MsgType.HTTP_REQUEST, body={"method": "GET", "path": "x"})
    out = await read_frame(_reader(encode_frame(msg)))
    assert out == msg


async def test_read_frame_returns_none_on_clean_eof():
    reader = asyncio.StreamReader()
    reader.feed_eof()
    assert await read_frame(reader) is None


async def test_read_frame_rejects_oversize_length():
    reader = _reader(_LENGTH_PREFIX.pack(MAX_FRAME_BYTES + 1))
    with pytest.raises(FrameError):
        await read_frame(reader)


async def test_decode_payload_rejects_non_envelope():
    with pytest.raises(FrameError):
        decode_payload(msgpack.packb([1, 2, 3], use_bin_type=True))


def test_request_response_type_partition():
    assert REQUEST_TYPES.isdisjoint(RESPONSE_TYPES)
    assert MsgType.HTTP_REQUEST in REQUEST_TYPES
    assert MsgType.HTTP_RESPONSE in RESPONSE_TYPES
