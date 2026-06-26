"""Plugin sandbox worker entry point — runs inside the isolated child process.

Phase 2 ships a minimal built-in request handler (health + echo) so the
host<->worker round-trip can be exercised end-to-end. Real plugin loading and
the capability SDK arrive in Phase 3, which replaces build_worker_handler().
"""
import argparse
import asyncio
from typing import List, Optional

from app.plugins.sandbox.channel import RequestHandler, RpcChannel
from app.plugins.sandbox.protocol import Message, MsgType
from app.plugins.sandbox.transport import connect_to_host


def build_worker_handler() -> RequestHandler:
    """Return the Phase-2 placeholder handler: health pings + request echo."""

    async def handler(msg: Message) -> Message:
        if msg.type == MsgType.LIFECYCLE:
            action = msg.body.get("action")
            if action == "health":
                return Message(id=msg.id, type=MsgType.LIFECYCLE_RESULT, body={"status": "ok"})
            if action == "shutdown":
                return Message(
                    id=msg.id, type=MsgType.LIFECYCLE_RESULT, body={"status": "stopping"}
                )
            return Message(
                id=msg.id, type=MsgType.LIFECYCLE_RESULT, body={"status": "unknown_action"}
            )
        if msg.type == MsgType.HTTP_REQUEST:
            # Phase-2 echo: prove the request contract round-trips intact.
            return Message(
                id=msg.id,
                type=MsgType.HTTP_RESPONSE,
                body={
                    "status": 200,
                    "headers": {},
                    "echo": {
                        "method": msg.body.get("method"),
                        "path": msg.body.get("path"),
                        "body": msg.body.get("body"),
                        "context": msg.body.get("context"),
                    },
                },
            )
        return Message(id=msg.id, type=MsgType.ERROR, body={"error": "unsupported"})

    return handler


async def run_worker(address: str) -> None:
    """Connect back to the host, serve requests until the connection closes."""
    reader, writer = await connect_to_host(address)
    channel = RpcChannel(reader, writer, request_handler=build_worker_handler())
    channel.start()
    try:
        await channel.wait_closed()
    finally:
        await channel.close()


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="plugin-sandbox-worker")
    parser.add_argument(
        "--connect",
        required=True,
        help="host callback address: 'unix:<path>' or 'tcp:<host>:<port>'",
    )
    args = parser.parse_args(argv)
    asyncio.run(run_worker(args.connect))


if __name__ == "__main__":
    main()
