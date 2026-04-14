"""Tests for plugins/resolver.py and plugins/core_versions.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.plugins.core_versions import (
    CoreVersions,
    CoreVersionsError,
    load_core_versions,
)
from app.plugins.manifest import PluginManifest
from app.plugins.resolver import (
    C_EXTENSION_BLACKLIST,
    InstalledPluginRequirement,
    resolve_install,
)


def _make_manifest(
    *,
    name: str = "demo",
    version: str = "1.0.0",
    python_requirements: list[str] | None = None,
    min_baluhost_version: str | None = None,
    max_baluhost_version: str | None = None,
) -> PluginManifest:
    return PluginManifest(
        manifest_version=1,
        name=name,
        version=version,
        display_name=name.title(),
        description="test",
        author="tests",
        min_baluhost_version=min_baluhost_version,
        max_baluhost_version=max_baluhost_version,
        python_requirements=python_requirements or [],
    )


@pytest.fixture
def core() -> CoreVersions:
    return CoreVersions(
        baluhost_version="1.30.0",
        python_version="3.11",
        platform="linux_x86_64",
        abi="cp311",
        packages={
            "httpx": "0.27.2",
            "pydantic": "2.6.4",
            "plugp100": "5.1.7",
        },
    )


class TestCoreVersionsLoader:
    def test_load_ships_with_core(self):
        cv = load_core_versions()
        assert cv.baluhost_version
        assert cv.has_package("fastapi")

    def test_load_custom_path(self, tmp_path: Path):
        f = tmp_path / "cv.json"
        f.write_text(
            json.dumps(
                {
                    "baluhost_version": "2.0.0",
                    "python_version": "3.12",
                    "platform": "linux_aarch64",
                    "abi": "cp312",
                    "packages": {"httpx": "0.28.0"},
                }
            )
        )
        cv = load_core_versions(f)
        assert cv.baluhost_version == "2.0.0"
        assert cv.get_version("httpx") is not None
        assert str(cv.get_version("httpx")) == "0.28.0"

    def test_missing_file(self, tmp_path: Path):
        with pytest.raises(CoreVersionsError, match="not found"):
            load_core_versions(tmp_path / "missing.json")

    def test_invalid_json(self, tmp_path: Path):
        f = tmp_path / "cv.json"
        f.write_text("{not json")
        with pytest.raises(CoreVersionsError, match="not valid JSON"):
            load_core_versions(f)

    def test_missing_keys(self, tmp_path: Path):
        f = tmp_path / "cv.json"
        f.write_text(json.dumps({"packages": {}}))
        with pytest.raises(CoreVersionsError, match="validation"):
            load_core_versions(f)

    def test_case_insensitive_lookup(self, core: CoreVersions):
        assert core.has_package("HTTPX")
        assert core.has_package("HttpX")


class TestHappyPath:
    def test_empty_requirements(self, core: CoreVersions):
        result = resolve_install(_make_manifest(), core)
        assert result.ok
        assert result.shared_satisfied == []
        assert result.isolated_to_install == []
        assert result.conflicts == []

    def test_core_satisfies_requirement(self, core: CoreVersions):
        manifest = _make_manifest(python_requirements=["httpx>=0.25,<0.30"])
        result = resolve_install(manifest, core)
        assert result.ok
        assert result.shared_satisfied == ["httpx>=0.25,<0.30"]
        assert result.isolated_to_install == []

    def test_isolated_dep(self, core: CoreVersions):
        manifest = _make_manifest(python_requirements=["pyowm==3.3.0"])
        result = resolve_install(manifest, core)
        assert result.ok
        assert result.shared_satisfied == []
        assert result.isolated_to_install == ["pyowm==3.3.0"]

    def test_mixed_shared_and_isolated(self, core: CoreVersions):
        manifest = _make_manifest(
            python_requirements=["httpx>=0.27", "pyowm==3.3.0"]
        )
        result = resolve_install(manifest, core)
        assert result.ok
        assert "httpx>=0.27" in result.shared_satisfied
        assert "pyowm==3.3.0" in result.isolated_to_install


class TestCoreVersionMismatch:
    def test_core_version_below_plugin_pin(self, core: CoreVersions):
        manifest = _make_manifest(python_requirements=["httpx>=0.30"])
        result = resolve_install(manifest, core)
        assert not result.ok
        assert len(result.conflicts) == 1
        c = result.conflicts[0]
        assert c.package == "httpx"
        assert c.source == "core"
        assert "0.27.2" in c.found

    def test_core_version_above_plugin_ceiling(self, core: CoreVersions):
        manifest = _make_manifest(python_requirements=["httpx<0.20"])
        result = resolve_install(manifest, core)
        assert not result.ok
        assert result.conflicts[0].source == "core"


class TestBaluhostVersionGate:
    def test_min_version_satisfied(self, core: CoreVersions):
        manifest = _make_manifest(min_baluhost_version="1.29.0")
        result = resolve_install(manifest, core)
        assert result.ok

    def test_min_version_too_high(self, core: CoreVersions):
        manifest = _make_manifest(min_baluhost_version="2.0.0")
        result = resolve_install(manifest, core)
        assert not result.ok
        assert any(c.source == "baluhost_version" for c in result.conflicts)
        assert any("2.0.0" in c.suggestion for c in result.conflicts)

    def test_max_version_satisfied(self, core: CoreVersions):
        manifest = _make_manifest(max_baluhost_version="1.30.0")
        assert resolve_install(manifest, core).ok

    def test_max_version_too_low(self, core: CoreVersions):
        manifest = _make_manifest(max_baluhost_version="1.0.0")
        result = resolve_install(manifest, core)
        assert not result.ok
        assert result.conflicts[0].source == "baluhost_version"

    def test_invalid_min_version_string(self, core: CoreVersions):
        manifest = _make_manifest(min_baluhost_version="not-a-version")
        result = resolve_install(manifest, core)
        assert not result.ok
        assert any("invalid" in c.suggestion for c in result.conflicts)


class TestCExtensionBlacklist:
    @pytest.mark.parametrize("pkg", ["numpy", "pandas", "pillow", "lxml", "scipy"])
    def test_blacklisted_package_rejected(self, core: CoreVersions, pkg: str):
        manifest = _make_manifest(python_requirements=[f"{pkg}>=1.0"])
        result = resolve_install(manifest, core)
        assert not result.ok
        assert any(pkg in c.suggestion.lower() or pkg == c.package for c in result.conflicts)

    def test_core_shadowed_blacklist_is_ok(self, core: CoreVersions):
        """A plugin may depend on a blacklisted name if Core already provides it.

        ``plugp100`` isn't in the blacklist but this models the pattern: the
        shared-satisfied check runs first, so blacklisted names that happen to
        be in Core resolve cleanly. We exercise this with a synthetic core
        that lists a blacklisted name."""
        core_with_numpy = CoreVersions(
            baluhost_version="1.30.0",
            python_version="3.11",
            platform="linux_x86_64",
            abi="cp311",
            packages={"numpy": "1.26.4"},
        )
        manifest = _make_manifest(python_requirements=["numpy>=1.20"])
        result = resolve_install(manifest, core_with_numpy)
        assert result.ok
        assert result.shared_satisfied == ["numpy>=1.20"]


class TestCrossPluginConflicts:
    def test_compatible_pins_no_conflict(self, core: CoreVersions):
        other = InstalledPluginRequirement(
            name="weather", python_requirements=["pyowm==3.3.0"]
        )
        manifest = _make_manifest(
            name="forecast", python_requirements=["pyowm>=3.0,<4.0"]
        )
        result = resolve_install(manifest, core, [other])
        assert result.ok

    def test_incompatible_pins_conflict(self, core: CoreVersions):
        other = InstalledPluginRequirement(
            name="weather", python_requirements=["pyowm==3.3.0"]
        )
        manifest = _make_manifest(
            name="forecast", python_requirements=["pyowm==3.2.0"]
        )
        result = resolve_install(manifest, core, [other])
        assert not result.ok
        assert len(result.conflicts) == 1
        c = result.conflicts[0]
        assert c.source == "plugin:weather"
        assert c.package == "pyowm"

    def test_unrelated_plugin_ignored(self, core: CoreVersions):
        other = InstalledPluginRequirement(
            name="other", python_requirements=["something_else==1.0"]
        )
        manifest = _make_manifest(python_requirements=["pyowm==3.3.0"])
        assert resolve_install(manifest, core, [other]).ok

    def test_range_vs_range_lenient(self, core: CoreVersions):
        """Two open-ended ranges without pins are assumed compatible (best-effort)."""
        other = InstalledPluginRequirement(
            name="a", python_requirements=["pyowm>=3.0"]
        )
        manifest = _make_manifest(python_requirements=["pyowm<4.0"])
        assert resolve_install(manifest, core, [other]).ok


class TestInvalidRequirements:
    def test_garbage_requirement_reported(self, core: CoreVersions):
        manifest = _make_manifest(python_requirements=["not a valid requirement!!"])
        result = resolve_install(manifest, core)
        assert not result.ok
        assert "not a valid PEP 508" in result.conflicts[0].suggestion


class TestBlacklistConstant:
    def test_contains_common_extensions(self):
        for pkg in ("numpy", "pandas", "pillow", "lxml"):
            assert pkg in C_EXTENSION_BLACKLIST
