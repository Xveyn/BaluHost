import pytest

from app.plugins.sandbox.capabilities import (
    CapabilityContext,
    CapabilityRouter,
)


class _FakeStorage:
    """In-memory stand-in for plugin_storage_service, keyed (plugin, user, key)."""

    def __init__(self):
        self.data: dict[tuple[str, int, str], object] = {}

    def get_value(self, db, plugin_name, user_id, key):
        k = (plugin_name, user_id, key)
        return (k in self.data, self.data.get(k))

    def set_value(self, db, plugin_name, user_id, key, value):
        self.data[(plugin_name, user_id, key)] = value

    def delete_value(self, db, plugin_name, user_id, key):
        return self.data.pop((plugin_name, user_id, key), _MISSING) is not _MISSING

    def list_keys(self, db, plugin_name, user_id):
        return sorted(k for (p, u, k) in self.data if p == plugin_name and u == user_id)


_MISSING = object()
CTX = CapabilityContext(user_id=7, username="alice", role="user")


def _router(monkeypatch, *, scopes, storage=None, audit=None):
    storage = storage or _FakeStorage()
    monkeypatch.setattr("app.plugins.sandbox.capabilities.plugin_storage_service", storage)
    return CapabilityRouter(
        plugin_name="demo",
        granted_scopes=frozenset(scopes),
        session_factory=lambda: object(),  # fake "db"; _FakeStorage ignores it
        audit_logger=audit,
    )


async def test_denied_when_scope_not_granted(monkeypatch):
    audited = []
    audit = type("A", (), {"log_security_event": lambda self, **kw: audited.append(kw)})()
    r = _router(monkeypatch, scopes=set(), audit=audit)
    out = await r.dispatch("storage.get", {"key": "x"}, CTX)
    assert out == {"error": "denied"}
    assert audited and audited[0]["success"] is False
    assert audited[0]["details"]["capability"] == "storage.get"


async def test_unknown_capability(monkeypatch):
    r = _router(monkeypatch, scopes={"storage"})
    out = await r.dispatch("storage.nuke", {}, CTX)
    assert out == {"error": "unknown_capability"}


async def test_storage_set_get_roundtrip_bound_to_context_user(monkeypatch):
    store = _FakeStorage()
    r = _router(monkeypatch, scopes={"storage"}, storage=store)
    assert await r.dispatch("storage.set", {"key": "k", "value": {"n": 1}}, CTX) == {"result": None}
    assert await r.dispatch("storage.get", {"key": "k"}, CTX) == {"result": {"n": 1}}
    # bound to user 7, not whatever the plugin might pass:
    assert ("demo", 7, "k") in store.data
    # plugin attempts to inject a different user_id in args — must be ignored
    await r.dispatch("storage.set", {"key": "k", "user_id": 999, "value": 1}, CTX)
    assert ("demo", 999, "k") not in store.data
    assert ("demo", 7, "k") in store.data


async def test_storage_get_missing_returns_null(monkeypatch):
    r = _router(monkeypatch, scopes={"storage"})
    assert await r.dispatch("storage.get", {"key": "nope"}, CTX) == {"result": None}


async def test_storage_list_and_delete(monkeypatch):
    store = _FakeStorage()
    r = _router(monkeypatch, scopes={"storage"}, storage=store)
    await r.dispatch("storage.set", {"key": "b", "value": 1}, CTX)
    await r.dispatch("storage.set", {"key": "a", "value": 2}, CTX)
    assert await r.dispatch("storage.list", {}, CTX) == {"result": ["a", "b"]}
    assert await r.dispatch("storage.delete", {"key": "a"}, CTX) == {"result": True}
    assert await r.dispatch("storage.delete", {"key": "a"}, CTX) == {"result": False}


async def test_storage_quota_error_is_scrubbed(monkeypatch):
    from app.services.plugin_storage_service import StorageQuotaError

    class _QuotaStorage(_FakeStorage):
        def set_value(self, db, plugin_name, user_id, key, value):
            raise StorageQuotaError("too big")

    r = _router(monkeypatch, scopes={"storage"}, storage=_QuotaStorage())
    assert await r.dispatch("storage.set", {"key": "k", "value": "x"}, CTX) == {"error": "storage_quota"}


async def test_storage_set_rejects_non_string_key(monkeypatch):
    r = _router(monkeypatch, scopes={"storage"})
    assert await r.dispatch("storage.set", {"key": 5, "value": 1}, CTX) == {"error": "invalid_args"}


async def test_system_metrics_returns_reader_snapshot(monkeypatch):
    r = _router(monkeypatch, scopes={"core.system_metrics"})
    r._metrics_reader = lambda: {"cpu_usage": 12.5, "memory": {"used": 1, "total": 4, "percent": 25.0}}
    out = await r.dispatch("core.system_metrics", {}, CTX)
    assert out == {"result": {"cpu_usage": 12.5, "memory": {"used": 1, "total": 4, "percent": 25.0}}}


async def test_system_metrics_unavailable_without_reader(monkeypatch):
    r = _router(monkeypatch, scopes={"core.system_metrics"})  # no metrics_reader injected
    assert await r.dispatch("core.system_metrics", {}, CTX) == {"error": "unavailable"}


async def test_notify_calls_notifier_with_context_user(monkeypatch):
    sent = []
    async def notifier(ctx, payload):
        sent.append((ctx, payload))
    r = _router(monkeypatch, scopes={"core.notify"})
    r._notifier = notifier
    out = await r.dispatch("core.notify", {"title": "Hi", "message": "Body", "type": "warning"}, CTX)
    assert out == {"result": None}
    ctx, payload = sent[0]
    assert ctx.user_id == 7  # host context, not plugin-supplied
    assert payload == {"title": "Hi", "message": "Body", "type": "warning"}


async def test_notify_defaults_type_info_and_rejects_bad_type(monkeypatch):
    sent = []
    async def notifier(ctx, payload):
        sent.append(payload)
    r = _router(monkeypatch, scopes={"core.notify"})
    r._notifier = notifier
    await r.dispatch("core.notify", {"title": "T", "message": "M"}, CTX)
    assert sent[0]["type"] == "info"
    assert await r.dispatch("core.notify", {"title": "T", "message": "M", "type": "critical"}, CTX) == {"error": "invalid_args"}


async def test_notify_rejects_missing_or_oversized_fields(monkeypatch):
    r = _router(monkeypatch, scopes={"core.notify"})
    r._notifier = lambda ctx, payload: None  # not awaited; rejected before call
    assert await r.dispatch("core.notify", {"message": "M"}, CTX) == {"error": "invalid_args"}
    assert await r.dispatch("core.notify", {"title": "x" * 201, "message": "M"}, CTX) == {"error": "invalid_args"}
