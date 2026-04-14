"""Build a marketplace ``index.json`` + ``.bhplugin`` artifacts.

Walks a source directory (``--source``, default ``plugins``) looking for
subdirectories that contain a ``plugin.json``. For each, it:

1. Loads and validates the manifest — minimal schema check, no Pydantic
   dependency so this script runs anywhere Python does.
2. Packages the plugin directory into ``<name>-<version>.bhplugin`` (a
   zip). The archive excludes ``site-packages/`` (populated on install),
   ``__pycache__``, and any ``*.pyc`` files.
3. Computes the SHA-256 of the archive and its size.
4. Collects the metadata into an ``index.json`` that matches the shape
   validated by ``backend/app/plugins/marketplace.py``.

Multi-version coexistence in a single build is out of scope for v1 —
each source checkout emits exactly one version per plugin. Historical
versions are recovered by re-running the script against a tagged
commit in CI.

Run with::

    python scripts/build_index.py --source plugins --dist dist \\
        --base-url https://plugins.baluhost.dev
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

SUPPORTED_MANIFEST_VERSION = 1
INDEX_VERSION = 1

REQUIRED_FIELDS = ("manifest_version", "name", "version", "display_name",
                   "description", "author")
EXCLUDED_DIR_NAMES = {"site-packages", "__pycache__", ".git"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


class BuildError(Exception):
    """Raised when a plugin source tree can't be turned into an artifact."""


@dataclass
class PluginArtifact:
    name: str
    version: str
    display_name: str
    description: str
    author: str
    category: str
    homepage: str | None
    min_baluhost_version: str | None
    max_baluhost_version: str | None
    required_permissions: List[str]
    python_requirements: List[str]
    archive_path: Path
    checksum_sha256: str
    size_bytes: int


def _load_manifest(plugin_dir: Path) -> Dict[str, Any]:
    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.exists():
        raise BuildError(f"{plugin_dir.name}: plugin.json missing")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BuildError(f"{plugin_dir.name}: plugin.json is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise BuildError(f"{plugin_dir.name}: plugin.json must be an object")

    missing = [k for k in REQUIRED_FIELDS if k not in data]
    if missing:
        raise BuildError(
            f"{plugin_dir.name}: plugin.json missing required fields: {missing}"
        )
    if data["manifest_version"] != SUPPORTED_MANIFEST_VERSION:
        raise BuildError(
            f"{plugin_dir.name}: unsupported manifest_version "
            f"{data['manifest_version']!r} (expected {SUPPORTED_MANIFEST_VERSION})"
        )
    if data["name"] != plugin_dir.name:
        raise BuildError(
            f"{plugin_dir.name}: plugin.json name={data['name']!r} does not "
            f"match directory name"
        )
    return data


def _iter_archive_entries(plugin_dir: Path) -> Iterable[Path]:
    """Yield paths (relative to plugin_dir) to include in the archive."""
    for path in sorted(plugin_dir.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(plugin_dir)
        parts = set(rel.parts)
        if parts & EXCLUDED_DIR_NAMES:
            continue
        if path.suffix in EXCLUDED_SUFFIXES:
            continue
        yield rel


def _package_plugin(plugin_dir: Path, dist_dir: Path, manifest: Dict[str, Any]) -> PluginArtifact:
    name = manifest["name"]
    version = manifest["version"]
    archive_name = f"{name}-{version}.bhplugin"
    archive_path = dist_dir / archive_name

    dist_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in _iter_archive_entries(plugin_dir):
            zf.write(plugin_dir / rel, arcname=str(rel).replace("\\", "/"))

    raw = archive_path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()

    return PluginArtifact(
        name=name,
        version=version,
        display_name=manifest["display_name"],
        description=manifest["description"],
        author=manifest["author"],
        category=manifest.get("category", "general"),
        homepage=manifest.get("homepage"),
        min_baluhost_version=manifest.get("min_baluhost_version"),
        max_baluhost_version=manifest.get("max_baluhost_version"),
        required_permissions=list(manifest.get("required_permissions", [])),
        python_requirements=list(manifest.get("python_requirements", [])),
        archive_path=archive_path,
        checksum_sha256=checksum,
        size_bytes=len(raw),
    )


def _render_index(
    artifacts: List[PluginArtifact],
    *,
    base_url: str,
    generated_at: str,
) -> Dict[str, Any]:
    base = base_url.rstrip("/")
    plugins: List[Dict[str, Any]] = []
    for art in artifacts:
        version_entry = {
            "version": art.version,
            "min_baluhost_version": art.min_baluhost_version,
            "max_baluhost_version": art.max_baluhost_version,
            "python_requirements": art.python_requirements,
            "required_permissions": art.required_permissions,
            "download_url": f"{base}/{art.archive_path.name}",
            "checksum_sha256": art.checksum_sha256,
            "size_bytes": art.size_bytes,
            "released_at": generated_at,
        }
        plugins.append(
            {
                "name": art.name,
                "latest_version": art.version,
                "versions": [version_entry],
                "display_name": art.display_name,
                "description": art.description,
                "author": art.author,
                "homepage": art.homepage,
                "category": art.category,
            }
        )
    return {
        "index_version": INDEX_VERSION,
        "generated_at": generated_at,
        "plugins": plugins,
    }


def build(
    source_dir: Path,
    dist_dir: Path,
    *,
    base_url: str,
    now: datetime | None = None,
) -> Dict[str, Any]:
    """Build index + artifacts. Returns the index dict."""
    if not source_dir.exists():
        raise BuildError(f"source directory does not exist: {source_dir}")

    dist_dir.mkdir(parents=True, exist_ok=True)

    generated_at = (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    artifacts: List[PluginArtifact] = []
    for child in sorted(source_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        if not (child / "plugin.json").exists():
            continue
        manifest = _load_manifest(child)
        artifacts.append(_package_plugin(child, dist_dir, manifest))

    index = _render_index(artifacts, base_url=base_url, generated_at=generated_at)
    (dist_dir / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return index


def _parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build a BaluHost marketplace index.")
    p.add_argument(
        "--source",
        type=Path,
        default=Path("plugins"),
        help="Directory containing plugin subdirectories (default: plugins)",
    )
    p.add_argument(
        "--dist",
        type=Path,
        default=Path("dist"),
        help="Output directory for index.json and .bhplugin archives (default: dist)",
    )
    p.add_argument(
        "--base-url",
        default="https://plugins.baluhost.dev",
        help="URL prefix rewritten into download_url fields",
    )
    return p.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        index = build(args.source, args.dist, base_url=args.base_url)
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"built {len(index['plugins'])} plugin(s) -> {args.dist / 'index.json'}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
