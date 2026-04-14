"""Dry-run install resolver for the ``baluhost-sdk dry-install`` CLI.

Combines the static ``validator`` pass with the ``resolver`` pass against the
Core's locked environment snapshot (``core_versions.json``). The resulting
``DryInstallReport`` mirrors the shape the marketplace UI renders, so authors
see exactly what users would see before shipping.

Unlike the runtime ``installer``, this command never downloads, never writes
to disk, never mutates anything. It is pure analysis.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.plugins.core_versions import CoreVersions, load_core_versions
from app.plugins.resolver import ResolveResult, resolve_install
from app.plugins.sdk.validator import ValidationReport, validate_plugin


@dataclass
class DryInstallReport:
    """Combined validator + resolver output.

    ``validation`` is always populated. ``resolution`` is ``None`` when the
    validator failed before we could get a usable manifest — in that case
    ``ok`` is ``False`` and callers should display the validator errors.
    """

    validation: ValidationReport
    resolution: Optional[ResolveResult] = None
    core_versions: Optional[CoreVersions] = None

    @property
    def ok(self) -> bool:
        if not self.validation.ok:
            return False
        if self.resolution is None:
            return False
        return self.resolution.ok


def dry_install(
    plugin_dir: Path,
    *,
    core_versions: Optional[CoreVersions] = None,
) -> DryInstallReport:
    """Run the full install preflight against the given plugin directory.

    Args:
        plugin_dir: The plugin source tree to check (must contain
            ``plugin.json``).
        core_versions: Optional override. Defaults to the Core snapshot
            shipped with the installed BaluHost backend
            (``app/plugins/core_versions.json``).

    Returns:
        A ``DryInstallReport``. ``ok`` is ``True`` iff the validator reports
        no errors *and* the resolver returns ``ok=True`` against the Core.
    """
    validation = validate_plugin(plugin_dir)
    if validation.manifest is None:
        return DryInstallReport(validation=validation)

    cv = core_versions or load_core_versions()
    resolution = resolve_install(validation.manifest, cv, installed=())

    return DryInstallReport(
        validation=validation,
        resolution=resolution,
        core_versions=cv,
    )
