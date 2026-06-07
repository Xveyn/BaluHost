"""HTTP client for the rebuilt TUI.

Speaks to the backend over a Unix socket (production, channel=local) or
TCP loopback (dev, where BALUHOST_LOCAL_LOOPBACK_FALLBACK makes 127.0.0.1
count as local). One client, two bindings, identical API.
"""
from __future__ import annotations

import os
from typing import Any, Callable

import httpx

DEFAULT_SOCKET = "/run/baluhost/local.sock"
DEFAULT_SERVER = "http://127.0.0.1:8000"


def resolve_transport(
    socket_path: str | None,
    server: str | None,
    exists: Callable[[str], bool] = os.path.exists,
) -> tuple[str, str]:
    """Decide the transport binding.

    Precedence:
      1. explicit ``server``      -> ("tcp", server)
      2. explicit ``socket_path`` -> ("uds", socket_path)  (honored even if missing)
      3. default socket exists    -> ("uds", DEFAULT_SOCKET)
      4. otherwise                -> ("tcp", DEFAULT_SERVER)
    """
    if server is not None:
        return "tcp", server
    if socket_path is not None:
        return "uds", socket_path
    if exists(DEFAULT_SOCKET):
        return "uds", DEFAULT_SOCKET
    return "tcp", DEFAULT_SERVER


class BackendClient:
    """Thin wrapper over httpx.Client.

    Exposes ``get/post/put/delete`` that take API paths and return
    ``httpx.Response`` — drop-in for the FakeClient interface used by the
    existing screen helpers. Holds the JWT and injects the Authorization
    header on every request.
    """

    def __init__(
        self,
        socket_path: str | None = None,
        server: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
        *,
        _client: httpx.Client | None = None,
    ) -> None:
        if _client is not None:
            # Injected transport (tests).
            self._client = _client
        else:
            mode, target = resolve_transport(socket_path, server)
            if mode == "uds":
                self._client = httpx.Client(
                    transport=httpx.HTTPTransport(uds=target),
                    base_url="http://localhost",
                    timeout=timeout,
                )
            else:
                self._client = httpx.Client(base_url=target, timeout=timeout)
        if token:
            self.set_token(token)

    def set_token(self, token: str) -> None:
        """Set/replace the bearer token used for all subsequent requests."""
        self._client.headers["Authorization"] = f"Bearer {token}"

    def clear_token(self) -> None:
        self._client.headers.pop("Authorization", None)

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._client.get(path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._client.post(path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._client.put(path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return self._client.delete(path, **kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BackendClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
