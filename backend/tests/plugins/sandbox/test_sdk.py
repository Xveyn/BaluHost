# backend/tests/plugins/sandbox/test_sdk.py
import pytest

from app.plugins.sandbox.protocol import Message, MsgType
from app.plugins.sandbox.sdk import PluginHost, PluginCapabilityError


class _FakeChannel:
    """Captures cap_calls and returns scripted cap_results."""

    def __init__(self, responses):
        self._responses = responses  # list of body dicts
        self.calls = []

    async def call(self, mtype, body, *, timeout=None):
        assert mtype == MsgType.CAP_CALL
        self.calls.append(body)
        return Message(id=0, type=MsgType.CAP_RESULT, body=self._responses.pop(0))


async def test_route_registration_and_dispatch():
    host = PluginHost()

    @host.route("GET", "/hello")
    async def hello(request):
        return {"status": 200, "body": {"who": request["user"]["username"]}}

    host.bind_channel(_FakeChannel([]))
    out = await host.handle_request(
        {"request_id": 1, "method": "GET", "path": "/hello", "body": b"",
         "context": {"user_id": 3, "username": "kim", "role": "user"}}
    )
    assert out["status"] == 200
    assert out["body"] == {"who": "kim"}


async def test_unknown_route_returns_404():
    host = PluginHost()
    host.bind_channel(_FakeChannel([]))
    out = await host.handle_request(
        {"request_id": 1, "method": "GET", "path": "/nope", "body": b"", "context": {"user_id": 1, "username": "a", "role": "user"}}
    )
    assert out["status"] == 404


async def test_storage_facade_stamps_request_id_and_returns_result():
    host = PluginHost()
    ch = _FakeChannel([{"result": {"v": 1}}])

    @host.route("GET", "/r")
    async def r(request):
        value = await host.storage.get("k")
        return {"status": 200, "body": value}

    host.bind_channel(ch)
    out = await host.handle_request(
        {"request_id": 99, "method": "GET", "path": "/r", "body": b"", "context": {"user_id": 1, "username": "a", "role": "user"}}
    )
    assert out["body"] == {"v": 1}
    assert ch.calls[0] == {"capability": "storage.get", "request_id": 99, "args": {"key": "k"}}


async def test_scopes_notify_and_metrics_capabilities():
    host = PluginHost()
    ch = _FakeChannel([{"result": {"cpu_usage": 5.0}}, {"result": None}])

    @host.route("POST", "/do")
    async def do(request):
        m = await host.scopes.system_metrics()
        await host.scopes.notify("T", "M", type="warning")
        return {"status": 200, "body": m}

    host.bind_channel(ch)
    out = await host.handle_request(
        {"request_id": 7, "method": "POST", "path": "/do", "body": b"", "context": {"user_id": 1, "username": "a", "role": "user"}}
    )
    assert out["body"] == {"cpu_usage": 5.0}
    assert ch.calls[0]["capability"] == "core.system_metrics"
    assert ch.calls[1] == {"capability": "core.notify", "request_id": 7, "args": {"title": "T", "message": "M", "type": "warning"}}


async def test_denied_capability_raises_in_plugin_code():
    host = PluginHost()
    ch = _FakeChannel([{"error": "denied"}])

    @host.route("GET", "/x")
    async def x(request):
        await host.storage.get("k")  # should raise
        return {"status": 200}

    host.bind_channel(ch)
    out = await host.handle_request(
        {"request_id": 1, "method": "GET", "path": "/x", "body": b"", "context": {"user_id": 1, "username": "a", "role": "user"}}
    )
    # an unhandled PluginCapabilityError inside the handler becomes a 500
    assert out["status"] == 500


def test_loader_loads_register_and_routes(tmp_path):
    from app.plugins.sandbox.loader import load_plugin

    plugin = tmp_path / "p"
    plugin.mkdir()
    (plugin / "__init__.py").write_text(
        "def register(host):\n"
        "    @host.route('GET', '/hi')\n"
        "    async def hi(request):\n"
        "        return {'status': 200, 'body': {'ok': True}}\n",
        encoding="utf-8",
    )
    host = load_plugin(str(plugin), "__init__.py", "p")
    assert ("GET", "/hi") in host.routes


def test_loader_missing_register_raises(tmp_path):
    from app.plugins.sandbox.loader import load_plugin, PluginLoadError

    plugin = tmp_path / "p"
    plugin.mkdir()
    (plugin / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(PluginLoadError):
        load_plugin(str(plugin), "__init__.py", "p")
