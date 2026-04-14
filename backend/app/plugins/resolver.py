"""Plugin dependency resolver — pure functions, no I/O.

Given a plugin's static manifest, the Core's locked-version snapshot, and the
list of already-installed plugins, decide whether the new plugin can be
installed. Used in three places (see
``docs/superpowers/specs/2026-04-13-plugin-marketplace-design.md``):

- Marketplace UI dry-run before the user clicks Install.
- ``installer.py`` hard gate before download.
- Background check after a Core update, to flag broken plugins.

The resolver is intentionally mechanical: it never talks to PyPI, never runs
pip, never imports plugin code. Given the same inputs it always produces the
same ``ResolveResult``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Sequence, Union

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from app.plugins.core_versions import CoreVersions
from app.plugins.manifest import PluginManifest


# Packages that ship C extensions or need a source build on common
# plugin-target platforms. Declaring one of these in ``python_requirements``
# is almost always a mistake — either the Core already provides it (and the
# plugin should rely on the shared copy) or it simply won't install into
# ``site-packages/`` with ``--only-binary=:all:`` on ARM.
#
# The check runs *after* the core-shared check, so a plugin that declares
# ``cryptography>=43`` (already in Core) is routed to ``shared_satisfied``
# and never hits the blacklist.
C_EXTENSION_BLACKLIST: frozenset[str] = frozenset(
    {
        "numpy",
        "pandas",
        "scipy",
        "pillow",
        "lxml",
        "psycopg2",
        "mysqlclient",
        "grpcio",
        "cryptography",
        "bcrypt",
        "cffi",
        "orjson",
        "ujson",
    }
)


ConflictSource = Union[Literal["core", "baluhost_version"], str]
# ``"core"`` — Core version violates the requirement.
# ``"baluhost_version"`` — manifest min/max_baluhost_version mismatch.
# ``"plugin:<name>"`` — another installed plugin declares an incompatible pin.


@dataclass(frozen=True)
class Conflict:
    """A single resolution failure. Multiple conflicts may be returned at once."""

    package: str
    requirement: str
    found: str
    source: ConflictSource
    suggestion: str


@dataclass(frozen=True)
class ResolveResult:
    """Outcome of ``resolve_install``.

    ``ok=True`` iff ``conflicts`` is empty. ``shared_satisfied`` lists the
    requirement names that can be served by the Core environment; the
    installer must **not** install those into the plugin's isolated
    ``site-packages/``. ``isolated_to_install`` lists the requirements the
    installer will pass to ``pip install --target``.
    """

    ok: bool
    shared_satisfied: List[str] = field(default_factory=list)
    isolated_to_install: List[str] = field(default_factory=list)
    conflicts: List[Conflict] = field(default_factory=list)


@dataclass(frozen=True)
class InstalledPluginRequirement:
    """Minimal view of an already-installed plugin, for cross-plugin checks.

    The resolver doesn't need the full ``PluginManifest`` of other plugins —
    only their name and the PEP 508 requirement strings they declared.
    """

    name: str
    python_requirements: Sequence[str] = ()


def _parse_requirement(raw: str) -> Requirement | None:
    try:
        return Requirement(raw)
    except InvalidRequirement:
        return None


def _version_within_manifest_range(manifest: PluginManifest, core_version: Version) -> Conflict | None:
    """Check ``min_baluhost_version`` / ``max_baluhost_version`` gate."""
    if manifest.min_baluhost_version:
        try:
            lower = Version(manifest.min_baluhost_version)
        except InvalidVersion:
            return Conflict(
                package="baluhost",
                requirement=f">={manifest.min_baluhost_version}",
                found=str(core_version),
                source="baluhost_version",
                suggestion=f"Plugin declares invalid min_baluhost_version '{manifest.min_baluhost_version}'",
            )
        if core_version < lower:
            return Conflict(
                package="baluhost",
                requirement=f">={manifest.min_baluhost_version}",
                found=str(core_version),
                source="baluhost_version",
                suggestion=(
                    f"Plugin '{manifest.name}' requires BaluHost "
                    f">= {manifest.min_baluhost_version}; current is {core_version}. "
                    "Update BaluHost and try again."
                ),
            )

    if manifest.max_baluhost_version:
        try:
            upper = Version(manifest.max_baluhost_version)
        except InvalidVersion:
            return Conflict(
                package="baluhost",
                requirement=f"<={manifest.max_baluhost_version}",
                found=str(core_version),
                source="baluhost_version",
                suggestion=f"Plugin declares invalid max_baluhost_version '{manifest.max_baluhost_version}'",
            )
        if core_version > upper:
            return Conflict(
                package="baluhost",
                requirement=f"<={manifest.max_baluhost_version}",
                found=str(core_version),
                source="baluhost_version",
                suggestion=(
                    f"Plugin '{manifest.name}' is only compatible with BaluHost "
                    f"<= {manifest.max_baluhost_version}; current is {core_version}. "
                    "Wait for a plugin update."
                ),
            )
    return None


def _specifiers_compatible(a: SpecifierSet, b: SpecifierSet) -> bool:
    """Best-effort intersection check for two PEP 508 specifier sets.

    We can't enumerate every version, so we use a deterministic heuristic:

    1. If either set contains a pinned ``==X``, that ``X`` must satisfy the
       other set (and of course its own). If it doesn't, the two requirements
       cannot be simultaneously satisfied — conflict.
    2. Otherwise (no pins on either side), assume compatible. The installer
       will ultimately pick *a* version that satisfies both ranges, and pip's
       target-install step will either succeed or surface a clear error.

    This is intentionally lenient for the range-vs-range case: it matches how
    hobby devs actually write ``python_requirements`` (pinning the
    top-level dep, leaving transitives loose) and keeps the UX firmly in
    "only warn when we're sure there's a conflict" territory.
    """
    combined = SpecifierSet(f"{a},{b}") if str(a) and str(b) else a or b

    pinned: list[Version] = []
    for spec in list(a) + list(b):
        if spec.operator == "==":
            try:
                pinned.append(Version(spec.version))
            except InvalidVersion:
                return True  # unparseable pin — be lenient, let pip decide
    for v in pinned:
        if v not in combined:
            return False
    return True


def _check_cross_plugin_conflict(
    our_req: Requirement,
    installed: Sequence[InstalledPluginRequirement],
) -> Conflict | None:
    """See if any already-installed plugin's requirement conflicts with ours."""
    our_name = our_req.name.lower()
    for other in installed:
        for raw in other.python_requirements:
            other_req = _parse_requirement(raw)
            if other_req is None:
                continue
            if other_req.name.lower() != our_name:
                continue
            if _specifiers_compatible(our_req.specifier, other_req.specifier):
                continue
            return Conflict(
                package=our_req.name,
                requirement=str(our_req.specifier) or "any",
                found=f"{other.name} requires {str(other_req.specifier) or 'any'}",
                source=f"plugin:{other.name}",
                suggestion=(
                    f"Plugin '{other.name}' already requires "
                    f"{our_req.name}{other_req.specifier}; the two cannot coexist. "
                    "Ask one of the plugin authors to relax their pin."
                ),
            )
    return None


def resolve_install(
    manifest: PluginManifest,
    core_versions: CoreVersions,
    installed: Sequence[InstalledPluginRequirement] = (),
) -> ResolveResult:
    """Resolve a plugin install against Core and other installed plugins.

    Args:
        manifest: The candidate plugin's parsed manifest.
        core_versions: Snapshot of Core's locked environment.
        installed: Already-installed plugins (their declared requirements).

    Returns:
        A ``ResolveResult``. When ``ok`` is ``True``, ``shared_satisfied``
        and ``isolated_to_install`` describe what the installer should do
        next. When ``ok`` is ``False``, ``conflicts`` explains why — the
        Marketplace UI renders these messages directly.
    """
    shared: list[str] = []
    isolated: list[str] = []
    conflicts: list[Conflict] = []

    # 1. Core version gate (runs even if python_requirements is empty).
    try:
        core_version = core_versions.baluhost_version_parsed
    except InvalidVersion:
        core_version = Version("0.0.0")
    version_conflict = _version_within_manifest_range(manifest, core_version)
    if version_conflict is not None:
        conflicts.append(version_conflict)

    # 2. Walk each PEP 508 requirement.
    for raw in manifest.python_requirements:
        req = _parse_requirement(raw)
        if req is None:
            conflicts.append(
                Conflict(
                    package=raw,
                    requirement=raw,
                    found="invalid",
                    source="core",
                    suggestion=f"'{raw}' is not a valid PEP 508 requirement string",
                )
            )
            continue

        try:
            specifier = req.specifier
        except InvalidSpecifier:
            specifier = SpecifierSet("")

        name_lower = req.name.lower()

        # 2a. Core-provided shared dep?
        if core_versions.has_package(name_lower):
            core_ver = core_versions.get_version(name_lower)
            if core_ver is not None and (not specifier or core_ver in specifier):
                shared.append(raw)
                continue
            conflicts.append(
                Conflict(
                    package=req.name,
                    requirement=str(specifier) or "any",
                    found=str(core_ver) if core_ver else "unknown",
                    source="core",
                    suggestion=(
                        f"BaluHost Core ships {req.name} {core_ver} which does not "
                        f"satisfy '{raw}'. Update BaluHost to a version where "
                        f"{req.name} matches, or relax the plugin's pin."
                    ),
                )
            )
            continue

        # 2b. C-extension blacklist — surfaces a friendly error before pip.
        if name_lower in C_EXTENSION_BLACKLIST:
            conflicts.append(
                Conflict(
                    package=req.name,
                    requirement=str(specifier) or "any",
                    found="not installed",
                    source="core",
                    suggestion=(
                        f"{req.name} ships C extensions and cannot be installed "
                        "into an isolated plugin environment. Use a pure-Python "
                        "alternative or request that BaluHost Core bundle it."
                    ),
                )
            )
            continue

        # 2c. Cross-plugin conflict with something already installed?
        cross = _check_cross_plugin_conflict(req, installed)
        if cross is not None:
            conflicts.append(cross)
            continue

        isolated.append(raw)

    return ResolveResult(
        ok=not conflicts,
        shared_satisfied=shared,
        isolated_to_install=isolated,
        conflicts=conflicts,
    )
