"""Plugin sandbox worker entry point — runs inside the isolated child process.

Phase 3 wires the worker to a real PluginHost loaded from the plugin's
entrypoint via loader.load_plugin(). The host.handle_request() method
dispatches http_request messages to registered plugin routes, and capability
calls (storage, scopes) are forwarded to the host process over RPC.
"""
import argparse
import asyncio
import sys
from typing import List, Optional

from app.plugins.sandbox.channel import RequestHandler, RpcChannel
from app.plugins.sandbox.protocol import Message, MsgType
from app.plugins.sandbox.transport import connect_to_host


def build_worker_handler(host) -> RequestHandler:
    """Return the request handler that delegates to the loaded PluginHost."""

    async def handler(msg: Message) -> Message:
        if msg.type == MsgType.LIFECYCLE:
            action = msg.body.get("action")
            status = {"health": "ok", "shutdown": "stopping"}.get(action, "unknown_action")
            return Message(id=msg.id, type=MsgType.LIFECYCLE_RESULT, body={"status": status})
        if msg.type == MsgType.HTTP_REQUEST:
            resp = await host.handle_request(msg.body)
            return Message(id=msg.id, type=MsgType.HTTP_RESPONSE, body=resp)
        return Message(id=msg.id, type=MsgType.ERROR, body={"error": "unsupported"})

    return handler


async def run_worker(address: str, host) -> None:
    """Connect back to the host, bind the channel, serve requests until closed."""
    reader, writer = await connect_to_host(address)
    channel = RpcChannel(reader, writer, request_handler=build_worker_handler(host))
    host.bind_channel(channel)
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
    parser.add_argument("--plugin-dir", required=True, help="directory containing the plugin entrypoint")
    parser.add_argument("--plugin-name", required=True, help="unique plugin identifier")
    parser.add_argument("--entrypoint", default="__init__.py", help="entrypoint filename (default: __init__.py)")
    args = parser.parse_args(argv)

    from app.plugins.sandbox.loader import load_plugin, PluginLoadError  # noqa: PLC0415

    try:
        host = load_plugin(args.plugin_dir, args.entrypoint, args.plugin_name)
    except PluginLoadError as exc:
        print(f"plugin load failed: {exc}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run_worker(args.connect, host))


if __name__ == "__main__":
    main()
