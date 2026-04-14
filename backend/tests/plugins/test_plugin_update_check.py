"""Tests for ``app.services.plugin_update_check``.

Uses an in-memory fake marketplace service (no HTTP) and the standard
``db_session`` fixture (in-memory SQLite with all tables created from
metadata, so the new ``available_update`` / ``last_update_check_at``
columns exist without a migration).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple

import pytest
from sqlalchemy.orm import Session

from app.models.plugin import InstalledPlugin
from app.plugins.core_versions import CoreVersions
from app.plugins.marketplace import (
    MarketplaceEntry,
    MarketplaceIndex,
    MarketplaceVersionEntry,
)
from app.services.plugin_update_check import (
    PluginUpdateCheckResult,
    run_plugin_update_check,
)


# --------------------------- fake marketplace ---------------------------


class FakeMarketplaceService:
    """Minimal stand-in for MarketplaceService (only ``get_index`` is used)."""

    def __init__(self, index: Optional[MarketplaceIndex] = None):
        self._index = index
        self.fetches = 0
        self.raise_on_fetch: Optional[Exception] = None

    def get_index(self, *, force_refresh: bool = False) -> MarketplaceIndex:
        self.fetches += 1
        if self.raise_on_fetch is not None:
            raise self.raise_on_fetch
        assert self._index is not None
        return self._index


def _make_index(entries: List[Tuple[str, str, List[str]]]) -> MarketplaceIndex:
    plugins = []
    for name, latest_version, python_requirements in entries:
        plugins.append(
            MarketplaceEntry(
                name=name,
                latest_version=latest_version,
                versions=[
                    MarketplaceVersionEntry(
                        version=latest_version,
                        python_requirements=python_requirements,
                        required_permissions=[],
                        download_url=f"https://example/{name}-{latest_version}.bhplugin",
                        checksum_sha256="0" * 64,
                        size_bytes=1024,
                    )
                ],
                display_name=name.title(),
                description=f"{name} description",
                author="tests",
            )
        )
    return MarketplaceIndex(index_version=1, generated_at=None, plugins=plugins)


# --------------------------- plugin source trees ---------------------------


def _write_plugin_source(
    plugins_dir: Path,
    name: str,
    *,
    version: str = "1.0.0",
    min_baluhost_version: Optional[str] = "1.29.0",
    python_requirements: Optional[list[str]] = None,
) -> Path:
    plugin_dir = plugins_dir / name
    plugin_dir.mkdir(parents=True)
    manifest = {
        "manifest_version": 1,
        "name": name,
        "version": version,
        "display_name": name.title(),
        "description": f"{name} description",
        "author": "tests",
        "category": "general",
        "min_baluhost_version": min_baluhost_version,
        "required_permissions": [],
        "python_requirements": python_requirements or [],
        "entrypoint": "__init__.py",
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
    (plugin_dir / "__init__.py").write_text("# plugin\n")
    return plugin_dir


def _insert_installed(
    db: Session,
    name: str,
    version: str = "1.0.0",
    *,
    available_update: Optional[str] = None,
) -> InstalledPlugin:
    row = InstalledPlugin(
        name=name,
        version=version,
        display_name=name.title(),
        is_enabled=True,
        granted_permissions=[],
        config={},
        available_update=available_update,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def core_versions() -> CoreVersions:
    return CoreVersions(
        baluhost_version="1.29.0",
        python_version="3.11",
        platform="manylinux_2_28_x86_64",
        abi="cp311",
        packages={"fastapi": "0.115.0"},
    )


# --------------------------- tests ---------------------------


class TestUpdateDetection:
    def test_newer_marketplace_version_flags_update(
        self, db_session: Session, tmp_path: Path, core_versions: CoreVersions
    ):
        plugins_dir = tmp_path / "plugins"
        _write_plugin_source(plugins_dir, "weather", version="1.0.0")
        _insert_installed(db_session, "weather", "1.0.0")

        marketplace = FakeMarketplaceService(
            _make_index([("weather", "1.2.0", [])])
        )
        updates: list[tuple[str, str, str]] = []

        result = run_plugin_update_check(
            db_session,
            plugins_dir=plugins_dir,
            core_versions=core_versions,
            marketplace=marketplace,
            notify_update_available=lambda n, c, nv: updates.append((n, c, nv)),
            notify_incompatible=lambda *a, **k: None,
        )

        assert len(result.updates_available) == 1
        assert result.updates_available[0].latest_version == "1.2.0"
        assert updates == [("weather", "1.0.0", "1.2.0")]

        row = db_session.query(InstalledPlugin).filter_by(name="weather").one()
        assert row.available_update == "1.2.0"
        assert row.last_update_check_at is not None

    def test_same_version_no_update(
        self, db_session: Session, tmp_path: Path, core_versions: CoreVersions
    ):
        plugins_dir = tmp_path / "plugins"
        _write_plugin_source(plugins_dir, "weather", version="1.0.0")
        _insert_installed(db_session, "weather", "1.0.0", available_update="1.0.0")

        marketplace = FakeMarketplaceService(
            _make_index([("weather", "1.0.0", [])])
        )
        updates: list = []

        run_plugin_update_check(
            db_session,
            plugins_dir=plugins_dir,
            core_versions=core_versions,
            marketplace=marketplace,
            notify_update_available=lambda *a, **k: updates.append(a),
            notify_incompatible=lambda *a, **k: None,
        )

        row = db_session.query(InstalledPlugin).filter_by(name="weather").one()
        assert row.available_update is None
        assert updates == []

    def test_notification_fires_only_once_per_version(
        self, db_session: Session, tmp_path: Path, core_versions: CoreVersions
    ):
        plugins_dir = tmp_path / "plugins"
        _write_plugin_source(plugins_dir, "weather", version="1.0.0")
        row = _insert_installed(db_session, "weather", "1.0.0")
        # Already recorded on a prior tick.
        row.available_update = "1.2.0"
        db_session.commit()

        marketplace = FakeMarketplaceService(
            _make_index([("weather", "1.2.0", [])])
        )
        updates: list = []

        run_plugin_update_check(
            db_session,
            plugins_dir=plugins_dir,
            core_versions=core_versions,
            marketplace=marketplace,
            notify_update_available=lambda *a, **k: updates.append(a),
            notify_incompatible=lambda *a, **k: None,
        )

        assert updates == []  # no re-notification for the same latest version

    def test_marketplace_fetch_failure_does_not_abort(
        self, db_session: Session, tmp_path: Path, core_versions: CoreVersions
    ):
        from app.services.plugin_marketplace import IndexFetchError

        plugins_dir = tmp_path / "plugins"
        _write_plugin_source(plugins_dir, "weather", version="1.0.0")
        _insert_installed(db_session, "weather", "1.0.0")

        marketplace = FakeMarketplaceService()
        marketplace.raise_on_fetch = IndexFetchError("network down")

        result = run_plugin_update_check(
            db_session,
            plugins_dir=plugins_dir,
            core_versions=core_versions,
            marketplace=marketplace,
            notify_update_available=lambda *a, **k: None,
            notify_incompatible=lambda *a, **k: None,
        )

        assert not result.index_fetched
        assert any("network down" in e for e in result.errors)
        # Compatibility check still ran even though marketplace was down.
        assert len(result.checked) == 1
        assert result.checked[0].latest_version is None


class TestCompatibilityScan:
    def test_core_update_break_emits_incompatible(
        self, db_session: Session, tmp_path: Path
    ):
        """A plugin that needs BaluHost >= 2.0 is broken on Core 1.29.0."""
        plugins_dir = tmp_path / "plugins"
        _write_plugin_source(
            plugins_dir, "weather", version="1.0.0", min_baluhost_version="2.0.0"
        )
        _insert_installed(db_session, "weather", "1.0.0")

        core_versions = CoreVersions(
            baluhost_version="1.29.0",
            python_version="3.11",
            platform="x",
            abi="y",
            packages={},
        )
        marketplace = FakeMarketplaceService(_make_index([]))
        incompat: list = []

        result = run_plugin_update_check(
            db_session,
            plugins_dir=plugins_dir,
            core_versions=core_versions,
            marketplace=marketplace,
            notify_update_available=lambda *a, **k: None,
            notify_incompatible=lambda name, cur, reason: incompat.append(
                (name, cur, reason)
            ),
        )

        assert len(result.incompatible) == 1
        assert result.incompatible[0].name == "weather"
        assert len(incompat) == 1
        assert incompat[0][0] == "weather"
        assert "baluhost" in incompat[0][2].lower()

    def test_compatible_plugin_does_not_emit(
        self, db_session: Session, tmp_path: Path, core_versions: CoreVersions
    ):
        plugins_dir = tmp_path / "plugins"
        _write_plugin_source(
            plugins_dir, "weather", version="1.0.0", min_baluhost_version="1.0.0"
        )
        _insert_installed(db_session, "weather", "1.0.0")

        marketplace = FakeMarketplaceService(_make_index([]))
        incompat: list = []

        run_plugin_update_check(
            db_session,
            plugins_dir=plugins_dir,
            core_versions=core_versions,
            marketplace=marketplace,
            notify_update_available=lambda *a, **k: None,
            notify_incompatible=lambda *a, **k: incompat.append(a),
        )

        assert incompat == []

    def test_missing_plugin_source_recorded_as_error(
        self, db_session: Session, tmp_path: Path, core_versions: CoreVersions
    ):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        # Plugin row exists but source tree was deleted out-of-band.
        _insert_installed(db_session, "ghost", "1.0.0")

        marketplace = FakeMarketplaceService(_make_index([]))

        result = run_plugin_update_check(
            db_session,
            plugins_dir=plugins_dir,
            core_versions=core_versions,
            marketplace=marketplace,
            notify_update_available=lambda *a, **k: None,
            notify_incompatible=lambda *a, **k: None,
        )

        assert any("ghost" in e for e in result.errors)
        assert len(result.checked) == 1
        assert result.checked[0].conflicts == []


class TestEmptyAndNoOp:
    def test_no_installed_plugins(
        self, db_session: Session, tmp_path: Path, core_versions: CoreVersions
    ):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        marketplace = FakeMarketplaceService(_make_index([]))

        result = run_plugin_update_check(
            db_session,
            plugins_dir=plugins_dir,
            core_versions=core_versions,
            marketplace=marketplace,
            notify_update_available=lambda *a, **k: None,
            notify_incompatible=lambda *a, **k: None,
        )

        assert result.checked == []
        assert result.updates_available == []
        assert result.incompatible == []
