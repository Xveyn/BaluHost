"""Plugin SDK — developer-facing tooling for third-party plugin authors.

The SDK is a thin layer over the same plugin infrastructure the Core uses at
runtime (``manifest``, ``resolver``, ``core_versions``). Exposing it via a
separate package + ``baluhost-sdk`` CLI means hobby devs get a pre-flight
check (``validate``) and a full conflict report (``dry-install``) without
having to spin up the Core.

See ``docs/superpowers/specs/2026-04-13-plugin-marketplace-design.md`` Phase 7.
"""
from app.plugins.sdk.dry_install import DryInstallReport, dry_install
from app.plugins.sdk.validator import ValidationIssue, ValidationReport, validate_plugin

__all__ = [
    "DryInstallReport",
    "ValidationIssue",
    "ValidationReport",
    "dry_install",
    "validate_plugin",
]
