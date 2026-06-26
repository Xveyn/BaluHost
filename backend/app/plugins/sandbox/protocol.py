"""Frame codec and message envelope for the plugin sandbox RPC layer.

A frame on the wire is a 4-byte big-endian length prefix followed by a
msgpack-encoded envelope ``{"id": int, "type": str, "body": dict}``. The same
codec is used by both ends of the channel (host and sandbox worker).
"""
import asyncio
import struct
from dataclasses import dataclass, field
from typing import Any, Optional

import msgpack

# Hard cap on a single frame's payload to bound memory and reject malformed
# length prefixes from an untrusted peer.
MAX_FRAME_BYTES: int = 16 * 1024 * 1024  # 16 MiB

_LENGTH_PREFIX = struct.Struct(">I")  # 4-byte big-endian unsigned length


class MsgType:
    """Envelope ``type`` values. Requests expect a correlated response."""

    HTTP_REQUEST = "http_request"
    HTTP_RESPONSE = "http_response"
    CAP_CALL = "cap_call"
    CAP_RESULT = "cap_result"
    LIFECYCLE = "lifecycle"
    ERROR = "error"


# A side routes inbound frames by category: request types go to the request
# handler, response types resolve a pending outbound call.
REQUEST_TYPES = frozenset({MsgType.HTTP_REQUEST, MsgType.CAP_CALL, MsgType.LIFECYCLE})
RESPONSE_TYPES = frozenset({MsgType.HTTP_RESPONSE, MsgType.CAP_RESULT, MsgType.ERROR})


class FrameError(Exception):
    """Raised when a frame is malformed, truncated, or exceeds MAX_FRAME_BYTES."""


@dataclass
class Message:
    """A single RPC envelope."""

    id: int
    type: str
    body: dict[str, Any] = field(default_factory=dict)


def encode_frame(msg: Message) -> bytes:
    """Serialize a Message to a length-prefixed msgpack frame."""
    payload = msgpack.packb(
        {"id": msg.id, "type": msg.type, "body": msg.body},
        use_bin_type=True,
    )
    if len(payload) > MAX_FRAME_BYTES:
        raise FrameError(f"frame too large: {len(payload)} > {MAX_FRAME_BYTES}")
    return _LENGTH_PREFIX.pack(len(payload)) + payload


def decode_payload(payload: bytes) -> Message:
    """Decode a msgpack payload (without length prefix) into a Message.

    Any corruption — bad msgpack, wrong envelope shape, or non-coercible
    fields — is normalized to FrameError so the read loop can drop the
    connection cleanly instead of crashing on an untrusted peer's garbage.
    """
    try:
        obj = msgpack.unpackb(payload, raw=False)
    except Exception as exc:  # msgpack FormatError/StackError/ExtraData/etc.
        raise FrameError("invalid msgpack payload") from exc
    if not isinstance(obj, dict) or "id" not in obj or "type" not in obj:
        raise FrameError("malformed envelope")
    body = obj.get("body")
    if body is None:
        body = {}
    elif not isinstance(body, dict):
        raise FrameError("envelope body must be a map")
    try:
        return Message(id=int(obj["id"]), type=str(obj["type"]), body=body)
    except (TypeError, ValueError) as exc:
        raise FrameError("invalid envelope fields") from exc


async def read_frame(reader: asyncio.StreamReader) -> Optional[Message]:
    """Read one frame. Returns None on a clean EOF (peer closed cleanly)."""
    try:
        prefix = await reader.readexactly(4)
    except asyncio.IncompleteReadError as exc:
        if not exc.partial:
            return None  # clean EOF at a frame boundary
        raise FrameError("truncated length prefix") from exc

    (length,) = _LENGTH_PREFIX.unpack(prefix)
    if length > MAX_FRAME_BYTES:
        raise FrameError(f"frame too large: {length} > {MAX_FRAME_BYTES}")

    try:
        payload = await reader.readexactly(length)
    except asyncio.IncompleteReadError as exc:
        raise FrameError("truncated frame body") from exc

    return decode_payload(payload)


async def write_frame(writer: asyncio.StreamWriter, msg: Message) -> None:
    """Serialize and write one frame, flushing the transport."""
    writer.write(encode_frame(msg))
    await writer.drain()
