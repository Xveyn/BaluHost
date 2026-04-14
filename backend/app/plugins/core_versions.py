"""Loader for ``core_versions.json`` — the locked Core dependency snapshot.

The Core ships a static JSON file that lists every package currently installed
in the BaluHost Core environment, plus the Core's own version, target Python
version, and wheel platform/abi tags. The plugin resolver reads this file to
decide whether a plugin's ``python_requirements`` are already satisfied by
the Core or need to be installed into the plugin's isolated ``site-packages/``.

Keeping this snapshot *static* (not ``importlib.metadata.version()`` at runtime)
is important for two reasons:

- It is what the plugin build-time ``--platform``/``--python-version``/``--abi``
  flags have to match. Reading live runtime versions would drift from the
  declared build environment on a dev machine.
- It lets the SDK ``dry-install`` command run the same resolver against the
  same snapshot shipped with the Core release, without importing the Core.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

from packaging.version import InvalidVersion, Version


CORE_VERSIONS_PATH = Path(__file__).parent / "core_versions.json"


class CoreVersionsError(Exception):
    """Raised when ``core_versions.json`` is missing or malformed."""


@dataclass(frozen=True)
class CoreVersions:
    """Parsed representation of ``core_versions.json``.

    Attributes:
        baluhost_version: The Core's own semantic version.
        python_version: The target Python minor version (e.g. ``"3.11"``).
        platform: PEP 425 platform tag used by ``pip install --target``.
        abi: PEP 425 ABI tag used by ``pip install --target``.
        packages: Mapping of distribution name (lowercased) → installed version.
    """

    baluhost_version: str
    python_version: str
    platform: str
    abi: str
    packages: Dict[str, str] = field(default_factory=dict)

    @property
    def baluhost_version_parsed(self) -> Version:
        return Version(self.baluhost_version)

    def has_package(self, name: str) -> bool:
        return name.lower() in self.packages

    def get_version(self, name: str) -> Version | None:
        raw = self.packages.get(name.lower())
        if raw is None:
            return None
        try:
            return Version(raw)
        except InvalidVersion:
            return None


def load_core_versions(path: Path | None = None) -> CoreVersions:
    """Load and parse ``core_versions.json``.

    Args:
        path: Optional override. Defaults to the module-local
            ``core_versions.json`` shipped with the Core.

    Raises:
        CoreVersionsError: If the file is missing, not JSON, or fails schema
            validation (missing required keys, wrong types).
    """
    target = path or CORE_VERSIONS_PATH
    if not target.exists():
        raise CoreVersionsError(f"core_versions.json not found at {target}")

    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CoreVersionsError(f"core_versions.json is not valid JSON: {exc}") from exc

    try:
        packages_raw = raw["packages"]
        if not isinstance(packages_raw, dict):
            raise TypeError("'packages' must be an object")
        packages = {str(k).lower(): str(v) for k, v in packages_raw.items()}

        cv = CoreVersions(
            baluhost_version=str(raw["baluhost_version"]),
            python_version=str(raw["python_version"]),
            platform=str(raw["platform"]),
            abi=str(raw["abi"]),
            packages=packages,
        )
    except (KeyError, TypeError) as exc:
        raise CoreVersionsError(f"core_versions.json failed validation: {exc}") from exc

    # Eager-validate the baluhost_version so resolver logic can rely on it.
    try:
        _ = cv.baluhost_version_parsed
    except InvalidVersion as exc:
        raise CoreVersionsError(
            f"core_versions.json has invalid baluhost_version: {exc}"
        ) from exc

    return cv
