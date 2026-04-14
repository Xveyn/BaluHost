"""Tests for plugins/installer.py.

All tests use a local fake marketplace (a dict of URL → bytes) and a no-op
pip runner, so they exercise the real install pipeline (checksum, extract,
manifest cross-check, resolver gate, atomic swap) without touching the
network or running pip.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Dict, Sequence

import pytest

from app.plugins.core_versions import CoreVersions
from app.plugins.installer import (
    ArchiveError,
    ChecksumError,
    DownloadError,
    InstalledArtifact,
    ManifestMismatchError,
    PipInstallError,
    PluginInstaller,
    ResolverConflictError,
)
from app.plugins.marketplace import MarketplaceVersionEntry
from app.plugins.resolver import InstalledPluginRequirement


# --------------------------- helpers / fixtures ---------------------------


def _build_plugin_zip(
    plugin_name: str,
    *,
    version: str = "1.0.0",
    python_requirements: list[str] | None = None,
    wrapped_in_subdir: bool = False,
    with_invalid_manifest: bool = False,
    extra_files: Dict[str, bytes] | None = None,
) -> bytes:
    """Build a .bhplugin archive (zip) in memory."""
    manifest = {
        "manifest_version": 1,
        "name": plugin_name,
        "version": version,
        "display_name": plugin_name.title(),
        "description": "test plugin",
        "author": "tests",
        "category": "general",
        "required_permissions": [],
        "plugin_dependencies": [],
        "python_requirements": python_requirements or [],
        "entrypoint": "__init__.py",
    }

    buf = io.BytesIO()
    prefix = f"{plugin_name}/" if wrapped_in_subdir else ""
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if with_invalid_manifest:
            zf.writestr(f"{prefix}plugin.json", "{not valid json")
        else:
            zf.writestr(f"{prefix}plugin.json", json.dumps(manifest))
        zf.writestr(f"{prefix}__init__.py", "# plugin entrypoint\n")
        for name, content in (extra_files or {}).items():
            zf.writestr(f"{prefix}{name}", content)
    return buf.getvalue()


def _make_entry(
    archive: bytes,
    *,
    version: str = "1.0.0",
    url: str = "https://plugins.example/test-1.0.0.bhplugin",
    override_checksum: str | None = None,
    override_size: int | None = None,
) -> MarketplaceVersionEntry:
    checksum = override_checksum or hashlib.sha256(archive).hexdigest()
    return MarketplaceVersionEntry(
        version=version,
        python_requirements=[],
        required_permissions=[],
        download_url=url,
        checksum_sha256=checksum,
        size_bytes=override_size if override_size is not None else len(archive),
    )


@pytest.fixture
def core() -> CoreVersions:
    return CoreVersions(
        baluhost_version="1.30.0",
        python_version="3.11",
        platform="linux_x86_64",
        abi="cp311",
        packages={"httpx": "0.27.2"},
    )


@pytest.fixture
def plugins_dir(tmp_path: Path) -> Path:
    d = tmp_path / "installed-plugins"
    d.mkdir()
    return d


class _PipCallRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], Path]] = []

    def __call__(
        self,
        requirements: Sequence[str],
        target: Path,
        core_versions: CoreVersions,
    ) -> None:
        # Record the call and pretend pip created site-packages/ successfully.
        target.mkdir(parents=True, exist_ok=True)
        self.calls.append((list(requirements), target))


def _installer_with_fake(
    plugins_dir: Path,
    core: CoreVersions,
    archive_map: Dict[str, bytes],
    *,
    pip_recorder: _PipCallRecorder | None = None,
    max_bytes: int | None = None,
) -> PluginInstaller:
    def fake_fetcher(url: str) -> bytes:
        if url not in archive_map:
            raise RuntimeError(f"unexpected fetch: {url}")
        return archive_map[url]

    return PluginInstaller(
        plugins_dir=plugins_dir,
        core_versions=core,
        fetcher=fake_fetcher,
        pip_runner=pip_recorder or _PipCallRecorder(),
        **({"max_download_bytes": max_bytes} if max_bytes is not None else {}),
    )


# ------------------------------- happy path -------------------------------


class TestHappyPath:
    def test_install_flat_archive(self, plugins_dir: Path, core: CoreVersions):
        archive = _build_plugin_zip("demo")
        entry = _make_entry(archive)
        inst = _installer_with_fake(plugins_dir, core, {entry.download_url: archive})

        result = inst.install(entry, "demo")

        assert isinstance(result, InstalledArtifact)
        assert result.name == "demo"
        assert result.version == "1.0.0"
        assert result.path == plugins_dir / "demo"
        assert (result.path / "plugin.json").exists()
        assert (result.path / "__init__.py").exists()

    def test_install_subdir_archive(self, plugins_dir: Path, core: CoreVersions):
        archive = _build_plugin_zip("wrapped", wrapped_in_subdir=True)
        entry = _make_entry(archive)
        inst = _installer_with_fake(plugins_dir, core, {entry.download_url: archive})

        result = inst.install(entry, "wrapped")
        assert (result.path / "plugin.json").exists()

    def test_isolated_deps_trigger_pip(self, plugins_dir: Path, core: CoreVersions):
        archive = _build_plugin_zip(
            "weather", python_requirements=["pyowm==3.3.0", "httpx>=0.27"]
        )
        entry = _make_entry(archive)
        pip = _PipCallRecorder()
        inst = _installer_with_fake(
            plugins_dir, core, {entry.download_url: archive}, pip_recorder=pip
        )

        result = inst.install(entry, "weather")

        # httpx is in core → shared, pyowm → isolated
        assert result.shared_satisfied == ["httpx>=0.27"]
        assert result.isolated_installed == ["pyowm==3.3.0"]
        # pip was called exactly once with the isolated deps
        assert len(pip.calls) == 1
        reqs, target = pip.calls[0]
        assert reqs == ["pyowm==3.3.0"]
        assert target.name == "site-packages"
        # target was inside staging (temp dir now gone); site-packages/ was
        # moved into the final plugin directory as part of the atomic swap.
        assert (result.path / "site-packages").exists()

    def test_no_pip_call_when_only_shared_deps(
        self, plugins_dir: Path, core: CoreVersions
    ):
        archive = _build_plugin_zip("lean", python_requirements=["httpx>=0.27"])
        entry = _make_entry(archive)
        pip = _PipCallRecorder()
        inst = _installer_with_fake(
            plugins_dir, core, {entry.download_url: archive}, pip_recorder=pip
        )

        inst.install(entry, "lean")

        # pip runner still invoked, but with an empty list — the default
        # runner short-circuits on empty; the recorder records the call
        # but requirements list is empty.
        if pip.calls:
            assert pip.calls[0][0] == []

    def test_overwrites_existing_install(self, plugins_dir: Path, core: CoreVersions):
        first = _build_plugin_zip("demo", version="1.0.0")
        first_entry = _make_entry(first, version="1.0.0")
        inst1 = _installer_with_fake(
            plugins_dir, core, {first_entry.download_url: first}
        )
        inst1.install(first_entry, "demo")
        (plugins_dir / "demo" / "marker").write_text("v1")

        second = _build_plugin_zip("demo", version="2.0.0")
        second_entry = _make_entry(
            second,
            version="2.0.0",
            url="https://plugins.example/demo-2.0.0.bhplugin",
        )
        inst2 = _installer_with_fake(
            plugins_dir, core, {second_entry.download_url: second}
        )
        result = inst2.install(second_entry, "demo")

        assert result.version == "2.0.0"
        assert not (plugins_dir / "demo" / "marker").exists()


# ------------------------------ failure modes ------------------------------


class TestFailureModes:
    def test_checksum_mismatch(self, plugins_dir: Path, core: CoreVersions):
        archive = _build_plugin_zip("demo")
        entry = _make_entry(archive, override_checksum="a" * 64)
        inst = _installer_with_fake(plugins_dir, core, {entry.download_url: archive})

        with pytest.raises(ChecksumError):
            inst.install(entry, "demo")
        assert not (plugins_dir / "demo").exists()

    def test_declared_size_exceeds_limit(
        self, plugins_dir: Path, core: CoreVersions
    ):
        archive = _build_plugin_zip("demo")
        entry = _make_entry(archive, override_size=999_999_999)
        inst = _installer_with_fake(
            plugins_dir,
            core,
            {entry.download_url: archive},
            max_bytes=1024,
        )
        with pytest.raises(DownloadError, match="exceeds limit"):
            inst.install(entry, "demo")

    def test_fetcher_error_becomes_download_error(
        self, plugins_dir: Path, core: CoreVersions
    ):
        archive = _build_plugin_zip("demo")
        entry = _make_entry(archive)
        # Empty archive_map → fetcher raises → wrapped in DownloadError
        inst = _installer_with_fake(plugins_dir, core, {})
        with pytest.raises(DownloadError):
            inst.install(entry, "demo")

    def test_manifest_name_mismatch(self, plugins_dir: Path, core: CoreVersions):
        archive = _build_plugin_zip("actually_named_foo")
        entry = _make_entry(archive)
        inst = _installer_with_fake(plugins_dir, core, {entry.download_url: archive})

        with pytest.raises(ManifestMismatchError, match="name"):
            inst.install(entry, "expected_bar")

    def test_manifest_version_mismatch(self, plugins_dir: Path, core: CoreVersions):
        archive = _build_plugin_zip("demo", version="1.0.0")
        entry = _make_entry(archive, version="9.9.9")
        inst = _installer_with_fake(plugins_dir, core, {entry.download_url: archive})

        with pytest.raises(ManifestMismatchError, match="version"):
            inst.install(entry, "demo")

    def test_invalid_manifest_in_archive(
        self, plugins_dir: Path, core: CoreVersions
    ):
        archive = _build_plugin_zip("demo", with_invalid_manifest=True)
        entry = _make_entry(archive)
        inst = _installer_with_fake(plugins_dir, core, {entry.download_url: archive})
        with pytest.raises(ManifestMismatchError):
            inst.install(entry, "demo")

    def test_non_zip_rejected(self, plugins_dir: Path, core: CoreVersions):
        archive = b"not a zip"
        entry = _make_entry(archive)
        inst = _installer_with_fake(plugins_dir, core, {entry.download_url: archive})
        with pytest.raises(ArchiveError):
            inst.install(entry, "demo")

    def test_path_traversal_archive_rejected(
        self, plugins_dir: Path, core: CoreVersions
    ):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("../escape.txt", "nope")
            zf.writestr("plugin.json", json.dumps({"manifest_version": 1}))
        archive = buf.getvalue()
        entry = _make_entry(archive)
        inst = _installer_with_fake(plugins_dir, core, {entry.download_url: archive})

        with pytest.raises(ArchiveError, match="Unsafe"):
            inst.install(entry, "demo")

    def test_resolver_conflict_blocks_install(
        self, plugins_dir: Path, core: CoreVersions
    ):
        # core has httpx==0.27.2; plugin demands >=0.30 → conflict
        archive = _build_plugin_zip("demo", python_requirements=["httpx>=0.30"])
        entry = _make_entry(archive)
        pip = _PipCallRecorder()
        inst = _installer_with_fake(
            plugins_dir, core, {entry.download_url: archive}, pip_recorder=pip
        )

        with pytest.raises(ResolverConflictError) as excinfo:
            inst.install(entry, "demo")
        assert not excinfo.value.result.ok
        assert not (plugins_dir / "demo").exists()
        assert pip.calls == []  # never reached pip

    def test_force_bypasses_resolver_conflict(
        self, plugins_dir: Path, core: CoreVersions
    ):
        archive = _build_plugin_zip("demo", python_requirements=["httpx>=0.30"])
        entry = _make_entry(archive)
        inst = _installer_with_fake(plugins_dir, core, {entry.download_url: archive})

        result = inst.install(entry, "demo", force=True)
        assert result.path.exists()

    def test_cross_plugin_conflict_blocks_install(
        self, plugins_dir: Path, core: CoreVersions
    ):
        archive = _build_plugin_zip("forecast", python_requirements=["pyowm==3.2.0"])
        entry = _make_entry(archive)
        installed = [
            InstalledPluginRequirement(
                name="weather", python_requirements=["pyowm==3.3.0"]
            )
        ]
        inst = _installer_with_fake(plugins_dir, core, {entry.download_url: archive})

        with pytest.raises(ResolverConflictError) as excinfo:
            inst.install(entry, "forecast", installed=installed)
        assert any(
            c.source == "plugin:weather" for c in excinfo.value.result.conflicts
        )

    def test_pip_runner_failure(self, plugins_dir: Path, core: CoreVersions):
        archive = _build_plugin_zip("demo", python_requirements=["pyowm==3.3.0"])
        entry = _make_entry(archive)

        def boom(requirements, target, cv):
            raise PipInstallError("pip said no")

        inst = PluginInstaller(
            plugins_dir=plugins_dir,
            core_versions=core,
            fetcher=lambda url: archive,
            pip_runner=boom,
        )

        with pytest.raises(PipInstallError, match="pip said no"):
            inst.install(entry, "demo")
        assert not (plugins_dir / "demo").exists()


# --------------------------------- uninstall ---------------------------------


class TestUninstall:
    def test_removes_plugin_dir(self, plugins_dir: Path, core: CoreVersions):
        archive = _build_plugin_zip("demo")
        entry = _make_entry(archive)
        inst = _installer_with_fake(plugins_dir, core, {entry.download_url: archive})
        inst.install(entry, "demo")
        assert (plugins_dir / "demo").exists()

        assert inst.uninstall("demo") is True
        assert not (plugins_dir / "demo").exists()

    def test_uninstall_missing_is_noop(self, plugins_dir: Path, core: CoreVersions):
        inst = _installer_with_fake(plugins_dir, core, {})
        assert inst.uninstall("never_installed") is False
