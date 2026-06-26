"""Cross-platform host<->worker socket transport for the plugin sandbox.

Prod (Linux): a Unix-domain socket whose path lives in the worker's working
directory, so it works across a network-namespace boundary (the worker needs
no host-loopback access — only the bind-mounted socket file). Dev (Windows, or
any platform without AF_UNIX in asyncio): a loopback-TCP socket on 127.0.0.1.

Either way the result is an (asyncio.StreamReader, asyncio.StreamWriter) pair
that an RpcChannel wraps; the channel itself is transport-agnostic.
"""
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional, Tuple


def _use_unix_socket() -> bool:
    """True iff asyncio AF_UNIX servers are available (Linux/macOS, not Windows)."""
    return hasattr(asyncio, "start_unix_server") and sys.platform != "win32"


class WorkerListener:
    """Host side: listen for the worker's callback connection and accept one.

    The worker is spawned with the string returned by ``start()`` and connects
    back exactly once. ``accept()`` resolves with that single connection.
    """

    def __init__(self, socket_dir: "str | os.PathLike[str]") -> None:
        self._socket_dir = Path(socket_dir)
        self._server: Optional[asyncio.AbstractServer] = None
        self._accepted: Optional[asyncio.Future] = None
        self.connect_address: str = ""

    async def start(self) -> str:
        loop = asyncio.get_running_loop()
        self._accepted = loop.create_future()

        def _on_conn(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            # Accept only the first connection; ignore any extras defensively.
            if self._accepted is not None and not self._accepted.done():
                self._accepted.set_result((reader, writer))
            else:
                writer.close()

        if _use_unix_socket():
            path = str(self._socket_dir / "plugin.sock")
            # Stale socket file from a crashed prior worker would block bind.
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            self._server = await asyncio.start_unix_server(_on_conn, path=path)
            self.connect_address = f"unix:{path}"
        else:
            self._server = await asyncio.start_server(_on_conn, "127.0.0.1", 0)
            host, port = self._server.sockets[0].getsockname()[:2]
            self.connect_address = f"tcp:{host}:{port}"

        return self.connect_address

    async def accept(
        self, *, timeout: float
    ) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        if self._accepted is None:
            raise RuntimeError("WorkerListener.accept() called before start()")
        return await asyncio.wait_for(asyncio.shield(self._accepted), timeout)

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            # Do NOT await server.wait_closed() here.  In Python 3.12.1+ that
            # call correctly blocks until every *accepted* connection is dropped,
            # which means it would deadlock when called from _spawn_and_connect:
            # the accepted connection is still open (it's now owned by an
            # RpcChannel) while the finally-close runs.  Our contract is only
            # "stop accepting new connections" — the caller owns the lifetime of
            # any already-accepted streams.
            self._server = None


async def connect_to_host(
    address: str,
) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Worker side: connect back to the host using a ``start()`` address."""
    scheme, _, rest = address.partition(":")
    if scheme == "unix":
        return await asyncio.open_unix_connection(path=rest)
    if scheme == "tcp":
        host, _, port = rest.rpartition(":")
        return await asyncio.open_connection(host, int(port))
    raise ValueError(f"unknown connect address scheme: {address!r}")
