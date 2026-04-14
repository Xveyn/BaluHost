"""Static validator for a plugin source tree.

Runs offline, without a Core environment. Used by the ``baluhost-sdk validate``
CLI to give plugin authors fast feedback on the most common mistakes:

- missing or malformed ``plugin.json``
- unsupported manifest_version
- ``min_baluhost_version`` not set (marketplace requires an explicit floor)
- ``python_requirements`` that are not PEP 508 parseable
- packages in ``python_requirements`` that ship C extensions (warning — if
  the Core actually provides the package, ``dry-install`` will reclassify
  it as ``shared_satisfied`` and no conflict is raised)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Literal, Optional

from packaging.requirements import InvalidRequirement, Requirement

from app.plugins.manifest import (
    ManifestError,
    PluginManifest,
    UnsupportedManifestVersionError,
    load_manifest,
)
from app.plugins.resolver import C_EXTENSION_BLACKLIST


IssueLevel = Literal["error", "warning"]


@dataclass(frozen=True)
class ValidationIssue:
    """A single finding from ``validate_plugin``."""

    level: IssueLevel
    code: str
    message: str


@dataclass
class ValidationReport:
    """Aggregated result of validating one plugin directory."""

    plugin_dir: Path
    manifest: Optional[PluginManifest] = None
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(issue.level == "error" for issue in self.issues)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.level == "warning"]


def _err(code: str, message: str) -> ValidationIssue:
    return ValidationIssue(level="error", code=code, message=message)


def _warn(code: str, message: str) -> ValidationIssue:
    return ValidationIssue(level="warning", code=code, message=message)


def validate_plugin(plugin_dir: Path) -> ValidationReport:
    """Run all static checks against a plugin source directory.

    Returns a ``ValidationReport`` — callers inspect ``ok`` to decide whether
    to proceed. The report always contains the parsed manifest when the
    ``plugin.json`` could be loaded, even when additional checks flagged
    issues, so downstream tooling (``dry-install``) can reuse it.
    """
    report = ValidationReport(plugin_dir=plugin_dir)

    if not plugin_dir.exists() or not plugin_dir.is_dir():
        report.issues.append(
            _err("plugin_dir_missing", f"Plugin directory does not exist: {plugin_dir}")
        )
        return report

    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.exists():
        report.issues.append(
            _err(
                "manifest_missing",
                f"plugin.json not found in {plugin_dir}. "
                "Every plugin must ship a top-level plugin.json.",
            )
        )
        return report

    try:
        manifest = load_manifest(plugin_dir)
    except UnsupportedManifestVersionError as exc:
        report.issues.append(_err("manifest_version_unsupported", str(exc)))
        return report
    except ManifestError as exc:
        report.issues.append(_err("manifest_invalid", str(exc)))
        return report

    report.manifest = manifest

    if not manifest.min_baluhost_version:
        report.issues.append(
            _err(
                "min_baluhost_version_missing",
                "min_baluhost_version must be set so the marketplace can gate "
                "installs against incompatible Core releases.",
            )
        )

    for raw in manifest.python_requirements:
        try:
            req = Requirement(raw)
        except InvalidRequirement as exc:
            report.issues.append(
                _err(
                    "requirement_invalid",
                    f"'{raw}' is not a valid PEP 508 requirement string: {exc}",
                )
            )
            continue

        if req.name.lower() in C_EXTENSION_BLACKLIST:
            report.issues.append(
                _warn(
                    "requirement_c_extension",
                    f"'{req.name}' ships C extensions and will not install into an "
                    "isolated plugin environment. If BaluHost Core already provides "
                    "this package, dry-install will reclassify it as shared; otherwise "
                    "choose a pure-Python alternative.",
                )
            )

    return report
