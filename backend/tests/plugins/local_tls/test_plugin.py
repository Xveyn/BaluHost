"""Tests fuer die Plugin-Klasse local_tls (Metadaten, Aufgaben, Events, Konfiguration)."""
from unittest.mock import patch

from app.plugins.installed.local_tls import LocalTlsPlugin
from app.plugins.installed.local_tls.config import LocalTlsConfig
from app.plugins.manager import BUNDLED_PLUGINS_DIR, PluginManager


def test_plugin_metadata_and_tasks():
    plugin = LocalTlsPlugin()
    meta = plugin.metadata
    assert meta.name == "local_tls"
    assert meta.display_name == "Feste Adresse im Heimnetz"
    assert meta.required_permissions == [
        "network:outbound", "system:execute", "db:write",
        "task:background", "notification:send",
    ]
    assert plugin.get_config_schema() is LocalTlsConfig
    assert plugin.get_default_config() == LocalTlsConfig().model_dump()

    tasks = {t.name: t for t in plugin.get_background_tasks()}
    assert set(tasks) == {"address_check", "cert_check"}
    assert tasks["address_check"].interval_seconds == 300
    assert tasks["cert_check"].interval_seconds == 86400
    assert tasks["address_check"].run_on_startup is True
    assert tasks["cert_check"].run_on_startup is True


def test_permissions_are_known():
    from app.plugins.permissions import PluginPermission

    known = {p.value for p in PluginPermission}
    assert set(LocalTlsPlugin().metadata.required_permissions) <= known


def test_notification_events():
    events = {e.id: e for e in LocalTlsPlugin().get_notification_events()}
    assert set(events) == {"cert_expiring", "renew_failed", "dns_update_failed", "address_changed"}
    assert (events["cert_expiring"].notification_type, events["cert_expiring"].cooldown_seconds) == ("warning", 86400)
    assert (events["renew_failed"].notification_type, events["renew_failed"].cooldown_seconds) == ("critical", 86400)
    assert (events["dns_update_failed"].notification_type, events["dns_update_failed"].cooldown_seconds) == ("warning", 3600)
    assert (events["address_changed"].notification_type, events["address_changed"].cooldown_seconds) == ("info", 0)
    for e in events.values():
        assert e.action_url == "/settings?tab=integrations"
        assert e.default_target == "admins"
    # Platzhalter passen zu dem, was der Service uebergibt
    kwargs = {
        "cert_expiring": {"domain": "d", "days": 3},
        "renew_failed": {"domain": "d", "reason": "r"},
        "dns_update_failed": {"domain": "d", "reason": "r"},
        "address_changed": {"domain": "d", "ip": "192.168.1.2"},
    }
    for eid, kw in kwargs.items():
        events[eid].title_template.format(**kw)
        events[eid].message_template.format(**kw)


async def test_background_tasks_use_run_check():
    plugin = LocalTlsPlugin()
    tasks = {t.name: t for t in plugin.get_background_tasks()}
    from app.plugins.installed.local_tls import service

    with patch.object(service, "run_check") as run_check:
        async def fake(check, load_config, **kw):
            fake.calls.append((check, kw))
            return []
        fake.calls = []
        run_check.side_effect = fake
        await tasks["address_check"].func()
        await tasks["cert_check"].func()
    assert [c[0] for c in fake.calls] == [service.run_address_check, service.run_cert_check]
    # Hintergrund: kein raise_if_running, kein force
    assert all(not c[1].get("raise_if_running") and not c[1].get("force") for c in fake.calls)


def test_load_config_reads_stored_config(db_session):
    from app.services import plugin_service

    plugin = LocalTlsPlugin()
    assert plugin.load_config(db_session) == LocalTlsConfig()
    plugin_service.update_config(
        db_session, name="local_tls",
        validated_config={"domain": "box.duckdns.org", "staging": True},
    )
    cfg = plugin.load_config(db_session)
    assert cfg.domain == "box.duckdns.org" and cfg.staging is True


async def test_plugin_is_not_enabled_by_default(db_session):
    """Mitgelieferte Plugins sind aus, bis ein Admin sie aktiviert: der Manager
    laedt nur Zeilen mit ``is_enabled`` und legt selbst keine an. local_tls
    wird entdeckt, aber nicht aktiviert, und es entsteht keine Zeile."""
    from app.models.plugin import InstalledPlugin

    mgr = PluginManager(plugins_dirs=[BUNDLED_PLUGINS_DIR])
    await mgr.load_enabled_plugins(db_session, start_background_tasks=False)
    try:
        assert "local_tls" in mgr.discover_plugins()
        assert "local_tls" not in dict(mgr.iter_enabled_plugins())
        assert db_session.query(InstalledPlugin).filter_by(name="local_tls").first() is None
    finally:
        await mgr.shutdown_all()


def test_router_is_importable():
    assert LocalTlsPlugin().get_router() is not None
