"""TDD tests: enable_plugin persists declared api_scopes into granted_api_scopes."""
from app.services import plugin_service


def test_enable_plugin_create_sets_api_scopes(db_session):
    """CREATE branch: api_scopes passed to enable_plugin are stored."""
    record = plugin_service.enable_plugin(
        db_session,
        name="weather",
        version="1.0.0",
        display_name="Weather",
        permissions=["read:files"],
        default_config={},
        installed_by="admin",
        api_scopes=["read:storage"],
    )
    db_session.refresh(record)
    assert record.granted_api_scopes == ["read:storage"]


def test_enable_plugin_update_replaces_api_scopes(db_session):
    """UPDATE branch: calling enable_plugin again replaces granted_api_scopes."""
    # First call — create
    plugin_service.enable_plugin(
        db_session,
        name="weather",
        version="1.0.0",
        display_name="Weather",
        permissions=["read:files"],
        default_config={},
        installed_by="admin",
        api_scopes=["read:storage"],
    )
    # Second call — update with different scopes
    record = plugin_service.enable_plugin(
        db_session,
        name="weather",
        version="1.0.1",
        display_name="Weather",
        permissions=["read:files"],
        default_config={},
        installed_by="admin",
        api_scopes=["read:power"],
    )
    db_session.refresh(record)
    assert record.granted_api_scopes == ["read:power"]


def test_enable_plugin_none_api_scopes_yields_empty_list(db_session):
    """Default (api_scopes=None) results in granted_api_scopes == []."""
    record = plugin_service.enable_plugin(
        db_session,
        name="legacy-plugin",
        version="0.1.0",
        display_name="Legacy",
        permissions=[],
        default_config={},
        installed_by="admin",
        # api_scopes not passed — default None
    )
    db_session.refresh(record)
    assert record.granted_api_scopes == []
