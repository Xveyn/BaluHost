"""Plugin-facing SDK that runs INSIDE the sandbox worker.

A plugin's entrypoint defines ``def register(host: PluginHost)`` and declares
routes with ``@host.route(method, path)``. Inside a route handler the plugin
uses ``host.storage`` and ``host.scopes`` — each call is forwarded to the host
over RPC as a ``cap_call`` and gated there (default-deny). The plugin writes no
raw msgpack and never sees a token.
"""
import contextvars
from typing import Any, Awaitable, Callable

from app.plugins.sandbox.protocol import MsgType

_current_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("plugin_request_id")

RouteHandler = Callable[[dict], Awaitable[Any]]


class PluginCapabilityError(Exception):
    """Raised in plugin code when a capability call is denied or errors."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class _Caps:
    def __init__(self, host: "PluginHost"):
        self._host = host

    async def _call(self, capability: str, args: dict) -> Any:
        body = {
            "capability": capability,
            "request_id": _current_request_id.get(),
            "args": args,
        }
        resp = await self._host._channel.call(MsgType.CAP_CALL, body)
        if "error" in resp.body:
            raise PluginCapabilityError(resp.body["error"])
        return resp.body.get("result")


class _Storage(_Caps):
    async def get(self, key: str) -> Any:
        return await self._call("storage.get", {"key": key})

    async def set(self, key: str, value: Any) -> None:
        await self._call("storage.set", {"key": key, "value": value})

    async def delete(self, key: str) -> bool:
        return await self._call("storage.delete", {"key": key})

    async def list(self) -> list:
        return await self._call("storage.list", {})


class _Scopes(_Caps):
    async def system_metrics(self) -> dict:
        return await self._call("core.system_metrics", {})

    async def notify(self, title: str, message: str, type: str = "info") -> None:  # noqa: A002
        await self._call("core.notify", {"title": title, "message": message, "type": type})


class PluginHost:
    def __init__(self) -> None:
        self._routes: dict[tuple[str, str], RouteHandler] = {}
        self._channel = None
        self.storage = _Storage(self)
        self.scopes = _Scopes(self)

    @property
    def routes(self) -> dict[tuple[str, str], RouteHandler]:
        return dict(self._routes)

    def route(self, method: str, path: str) -> Callable[[RouteHandler], RouteHandler]:
        key = (method.upper(), path)

        def decorator(fn: RouteHandler) -> RouteHandler:
            self._routes[key] = fn
            return fn

        return decorator

    def bind_channel(self, channel: Any) -> None:
        self._channel = channel

    async def handle_request(self, body: dict) -> dict:
        handler = self._routes.get(
            (str(body.get("method", "")).upper(), body.get("path", ""))
        )
        if handler is None:
            return {"status": 404, "headers": {}, "body": {"error": "not_found"}}
        request = {
            "method": body.get("method"),
            "path": body.get("path"),
            "query": body.get("query") or {},
            "headers": body.get("headers") or {},
            "body": body.get("body"),
            "user": body.get("context") or {},
        }
        token = _current_request_id.set(body.get("request_id"))
        try:
            result = await handler(request)
        except PluginCapabilityError:
            return {"status": 500, "headers": {}, "body": {"error": "capability_error"}}
        except Exception:
            return {"status": 500, "headers": {}, "body": {"error": "plugin_error"}}
        finally:
            _current_request_id.reset(token)
        return _normalize_response(result)


def _normalize_response(result: Any) -> dict:
    if not isinstance(result, dict):
        return {"status": 200, "headers": {}, "body": result}
    return {
        "status": int(result.get("status", 200)),
        "headers": result.get("headers") or {},
        "body": result.get("body"),
    }
