"""TDD test: InstalledPlugin.granted_api_scopes column roundtrip."""
from app.models.plugin import InstalledPlugin


def test_granted_api_scopes_roundtrip(db_session):
    p = InstalledPlugin(name="weather", version="1.0.0", display_name="Weather",
                        granted_api_scopes=["read:storage"])
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    assert p.granted_api_scopes == ["read:storage"]
