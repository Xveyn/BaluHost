"""Static plugin manifest (`plugin.json`) loading and validation.

A manifest is the source of truth that the marketplace and the loader read
*without* importing the plugin's Python code. It mirrors the in-code
``PluginMetadata`` plus a few install-time fields (Python deps, entrypoint,
UI bundle paths).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, ValidationError

from app.plugins.base import PluginMetadata


SUPPORTED_MANIFEST_VERSIONS = {1}


class ManifestError(Exception):
    """Raised when a plugin.json cannot be loaded or fails validation."""


class UnsupportedManifestVersionError(ManifestError):
    """Raised when manifest_version is not in SUPPORTED_MANIFEST_VERSIONS."""


class PluginManifestUI(BaseModel):
    """UI section of a plugin manifest."""

    bundle: str = Field(..., description="Path to the JS bundle, relative to plugin dir")
    styles: Optional[str] = Field(default=None, description="Optional CSS path")


class PluginManifest(BaseModel):
    """Validated representation of a plugin's plugin.json file."""

    manifest_version: int = Field(..., description="Schema version, must be supported")

    name: str
    version: str
    display_name: str
    description: str
    author: str

    category: str = "general"
    homepage: Optional[str] = None
    min_baluhost_version: Optional[str] = None
    max_baluhost_version: Optional[str] = None

    required_permissions: List[str] = Field(default_factory=list)
    plugin_dependencies: List[str] = Field(default_factory=list)
    python_requirements: List[str] = Field(default_factory=list)

    entrypoint: str = "__init__.py"
    ui: Optional[PluginManifestUI] = None

    def to_metadata(self) -> PluginMetadata:
        """Convert to the in-code PluginMetadata used by PluginBase."""
        return PluginMetadata(
            name=self.name,
            version=self.version,
            display_name=self.display_name,
            description=self.description,
            author=self.author,
            required_permissions=list(self.required_permissions),
            category=self.category,
            homepage=self.homepage,
            min_baluhost_version=self.min_baluhost_version,
            dependencies=list(self.plugin_dependencies),
        )


def load_manifest(plugin_dir: Path) -> PluginManifest:
    """Load and validate ``plugin.json`` from a plugin directory.

    Raises:
        ManifestError: file missing, not valid JSON, or fails schema validation.
        UnsupportedManifestVersionError: manifest_version is not supported.
    """
    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.exists():
        raise ManifestError(f"plugin.json not found in {plugin_dir}")

    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"plugin.json is invalid JSON: {exc}") from exc

    version = raw.get("manifest_version")
    if version not in SUPPORTED_MANIFEST_VERSIONS:
        raise UnsupportedManifestVersionError(
            f"Unsupported manifest_version: {version}. "
            f"Supported: {sorted(SUPPORTED_MANIFEST_VERSIONS)}"
        )

    try:
        return PluginManifest(**raw)
    except ValidationError as exc:
        raise ManifestError(f"plugin.json failed validation: {exc}") from exc
