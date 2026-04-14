"""Tests for the plugin SDK (``app.plugins.sdk``).

Covers ``validate_plugin``, ``dry_install``, and the click CLI. Uses
``CliRunner`` for end-to-end command coverage and isolated ``tmp_path``
plugin trees for all fixtures.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pytest
from click.testing import CliRunner

from app.plugins.core_versions import CoreVersions
from app.plugins.sdk import dry_install, validate_plugin
from app.plugins.sdk.cli import cli


def _write_plugin(
    plugin_dir: Path,
    *,
    name: str = "weather",
    version: str = "1.0.0",
    min_baluhost_version: Optional[str] = "1.30.0",
    python_requirements: Optional[list[str]] = None,
    manifest_version: int = 1,
    extra_manifest: Optional[dict] = None,
) -> Path:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "manifest_version": manifest_version,
        "name": name,
        "version": version,
        "display_name": name.replace("_", " ").title(),
        "description": f"{name} test plugin",
        "author": "tests",
        "category": "general",
        "min_baluhost_version": min_baluhost_version,
        "required_permissions": [],
        "python_requirements": python_requirements or [],
        "entrypoint": "__init__.py",
    }
    if extra_manifest:
        manifest.update(extra_manifest)
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
    (plugin_dir / "__init__.py").write_text("# entrypoint\n")
    return plugin_dir


@pytest.fixture
def fake_core_versions() -> CoreVersions:
    return CoreVersions(
        baluhost_version="1.30.0",
        python_version="3.11",
        platform="manylinux_2_28_x86_64",
        abi="cp311",
        packages={
            "fastapi": "0.115.0",
            "pydantic": "2.6.0",
            "cryptography": "43.0.0",
        },
    )


class TestValidatePlugin:
    def test_valid_plugin_has_no_issues(self, tmp_path: Path):
        plugin_dir = _write_plugin(tmp_path / "weather")

        report = validate_plugin(plugin_dir)

        assert report.ok is True
        assert report.issues == []
        assert report.manifest is not None
        assert report.manifest.name == "weather"

    def test_missing_plugin_dir(self, tmp_path: Path):
        report = validate_plugin(tmp_path / "nope")

        assert report.ok is False
        assert len(report.errors) == 1
        assert report.errors[0].code == "plugin_dir_missing"
        assert report.manifest is None

    def test_missing_manifest_file(self, tmp_path: Path):
        plugin_dir = tmp_path / "weather"
        plugin_dir.mkdir()

        report = validate_plugin(plugin_dir)

        assert report.ok is False
        assert report.errors[0].code == "manifest_missing"

    def test_invalid_json(self, tmp_path: Path):
        plugin_dir = tmp_path / "weather"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text("{not json")

        report = validate_plugin(plugin_dir)

        assert report.ok is False
        assert report.errors[0].code == "manifest_invalid"

    def test_unsupported_manifest_version(self, tmp_path: Path):
        plugin_dir = _write_plugin(tmp_path / "weather", manifest_version=99)

        report = validate_plugin(plugin_dir)

        assert report.ok is False
        assert report.errors[0].code == "manifest_version_unsupported"

    def test_missing_min_baluhost_version(self, tmp_path: Path):
        plugin_dir = _write_plugin(tmp_path / "weather", min_baluhost_version=None)

        report = validate_plugin(plugin_dir)

        assert report.ok is False
        codes = [i.code for i in report.errors]
        assert "min_baluhost_version_missing" in codes

    def test_invalid_pep508_requirement(self, tmp_path: Path):
        plugin_dir = _write_plugin(
            tmp_path / "weather",
            python_requirements=["not a valid requirement!!"],
        )

        report = validate_plugin(plugin_dir)

        assert report.ok is False
        assert any(i.code == "requirement_invalid" for i in report.errors)

    def test_c_extension_produces_warning_not_error(self, tmp_path: Path):
        plugin_dir = _write_plugin(
            tmp_path / "weather",
            python_requirements=["numpy>=1.26"],
        )

        report = validate_plugin(plugin_dir)

        assert report.ok is True  # warnings don't fail validation
        assert any(
            i.code == "requirement_c_extension" and i.level == "warning"
            for i in report.warnings
        )

    def test_reports_multiple_issues(self, tmp_path: Path):
        plugin_dir = _write_plugin(
            tmp_path / "weather",
            min_baluhost_version=None,
            python_requirements=["numpy>=1.26", "not valid!!"],
        )

        report = validate_plugin(plugin_dir)

        assert report.ok is False
        error_codes = [i.code for i in report.errors]
        assert "min_baluhost_version_missing" in error_codes
        assert "requirement_invalid" in error_codes
        assert any(i.code == "requirement_c_extension" for i in report.warnings)


class TestDryInstall:
    def test_happy_path(self, tmp_path: Path, fake_core_versions: CoreVersions):
        plugin_dir = _write_plugin(
            tmp_path / "weather",
            python_requirements=["httpx>=0.27"],
        )

        report = dry_install(plugin_dir, core_versions=fake_core_versions)

        assert report.ok is True
        assert report.resolution is not None
        assert "httpx>=0.27" in report.resolution.isolated_to_install

    def test_shared_dep_is_classified_correctly(
        self, tmp_path: Path, fake_core_versions: CoreVersions
    ):
        plugin_dir = _write_plugin(
            tmp_path / "weather",
            python_requirements=["fastapi>=0.115"],
        )

        report = dry_install(plugin_dir, core_versions=fake_core_versions)

        assert report.ok is True
        assert "fastapi>=0.115" in report.resolution.shared_satisfied
        assert "fastapi>=0.115" not in report.resolution.isolated_to_install

    def test_baluhost_version_gate_fails(
        self, tmp_path: Path, fake_core_versions: CoreVersions
    ):
        plugin_dir = _write_plugin(
            tmp_path / "weather",
            min_baluhost_version="99.0.0",
        )

        report = dry_install(plugin_dir, core_versions=fake_core_versions)

        assert report.ok is False
        assert any(
            c.source == "baluhost_version" for c in report.resolution.conflicts
        )

    def test_validation_failure_short_circuits_resolver(
        self, tmp_path: Path, fake_core_versions: CoreVersions
    ):
        plugin_dir = tmp_path / "weather"
        plugin_dir.mkdir()
        # Missing plugin.json
        report = dry_install(plugin_dir, core_versions=fake_core_versions)

        assert report.ok is False
        assert report.resolution is None
        assert report.validation.errors[0].code == "manifest_missing"


class TestCliValidate:
    def test_exit_zero_on_success(self, tmp_path: Path):
        plugin_dir = _write_plugin(tmp_path / "weather")

        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(plugin_dir)])

        assert result.exit_code == 0
        assert "ok" in result.output.lower()

    def test_exit_one_on_failure(self, tmp_path: Path):
        plugin_dir = _write_plugin(tmp_path / "weather", min_baluhost_version=None)

        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(plugin_dir)])

        assert result.exit_code == 1
        assert "min_baluhost_version_missing" in result.output

    def test_missing_dir_is_click_usage_error(self, tmp_path: Path):
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(tmp_path / "nope")])

        # click raises a usage error (exit 2) on non-existent path,
        # because click.Path(exists=True) rejects it up front.
        assert result.exit_code == 2

    def test_warnings_do_not_fail(self, tmp_path: Path):
        plugin_dir = _write_plugin(
            tmp_path / "weather",
            python_requirements=["numpy>=1.26"],
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(plugin_dir)])

        assert result.exit_code == 0
        assert "warning" in result.output.lower()


class TestCliDryInstall:
    def _core_versions_file(self, tmp_path: Path, fake: CoreVersions) -> Path:
        path = tmp_path / "core_versions.json"
        path.write_text(
            json.dumps(
                {
                    "baluhost_version": fake.baluhost_version,
                    "python_version": fake.python_version,
                    "platform": fake.platform,
                    "abi": fake.abi,
                    "packages": fake.packages,
                }
            )
        )
        return path

    def test_happy_path(self, tmp_path: Path, fake_core_versions: CoreVersions):
        plugin_dir = _write_plugin(
            tmp_path / "weather",
            python_requirements=["httpx>=0.27"],
        )
        cv_path = self._core_versions_file(tmp_path, fake_core_versions)

        runner = CliRunner()
        result = runner.invoke(
            cli, ["dry-install", str(plugin_dir), "--core-versions", str(cv_path)]
        )

        assert result.exit_code == 0
        assert "Isolated" in result.output
        assert "httpx>=0.27" in result.output

    def test_prints_shared_section(
        self, tmp_path: Path, fake_core_versions: CoreVersions
    ):
        plugin_dir = _write_plugin(
            tmp_path / "weather",
            python_requirements=["fastapi>=0.115"],
        )
        cv_path = self._core_versions_file(tmp_path, fake_core_versions)

        runner = CliRunner()
        result = runner.invoke(
            cli, ["dry-install", str(plugin_dir), "--core-versions", str(cv_path)]
        )

        assert result.exit_code == 0
        assert "Shared" in result.output

    def test_reports_conflicts_and_exits_one(
        self, tmp_path: Path, fake_core_versions: CoreVersions
    ):
        plugin_dir = _write_plugin(
            tmp_path / "weather",
            min_baluhost_version="99.0.0",
        )
        cv_path = self._core_versions_file(tmp_path, fake_core_versions)

        runner = CliRunner()
        result = runner.invoke(
            cli, ["dry-install", str(plugin_dir), "--core-versions", str(cv_path)]
        )

        assert result.exit_code == 1
        assert "Conflicts" in result.output
        assert "baluhost" in result.output.lower()

    def test_invalid_core_versions_file(self, tmp_path: Path):
        plugin_dir = _write_plugin(tmp_path / "weather")
        bad_cv = tmp_path / "bad.json"
        bad_cv.write_text("{not json")

        runner = CliRunner()
        result = runner.invoke(
            cli, ["dry-install", str(plugin_dir), "--core-versions", str(bad_cv)]
        )

        assert result.exit_code == 1
        assert "core_versions" in result.output
