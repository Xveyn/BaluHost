"""Plugin installer — download, verify, extract, pip-install, atomic swap.

The installer is the only plugin-system component that performs real I/O
(network, filesystem, subprocess). Every side-effect step is implemented as
a small method so tests can substitute deterministic fakes:

- ``fetcher`` — callable ``(url) -> bytes``. Production default uses ``httpx``.
- ``pip_runner`` — callable ``(requirements, target, core_versions) -> None``.
  Production default shells out to ``{python} -m pip install --target ...``
  with the platform/abi flags from ``core_versions``. Tests use a no-op.

Everything else (checksum verification, zip extraction, manifest cross-check,
atomic rename, resolver gate) is pure enough to run inside tests without any
injection at all.

See ``docs/superpowers/specs/2026-04-13-plugin-marketplace-design.md`` for the
surrounding spec.
"""
from __future__ import annotations

import hashlib
import io
import logging
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from app.plugins.core_versions import CoreVersions
from app.plugins.manifest import ManifestError, load_manifest
from app.plugins.marketplace import MarketplaceVersionEntry
from app.plugins.resolver import (
    InstalledPluginRequirement,
    ResolveResult,
    resolve_install,
)


logger = logging.getLogger(__name__)


DEFAULT_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


class InstallError(Exception):
    """Base class for all installer failures."""


class DownloadError(InstallError):
    """Raised when the plugin archive cannot be fetched or is too large."""


class ChecksumError(InstallError):
    """Raised when the SHA-256 of the downloaded archive does not match."""


class ArchiveError(InstallError):
    """Raised when the archive is not a valid zip or has a malicious layout."""


class ManifestMismatchError(InstallError):
    """Raised when ``plugin.json`` inside the archive disagrees with the index."""


class ResolverConflictError(InstallError):
    """Raised when the resolver refuses the install.

    The caller should inspect ``result`` to render per-conflict messages.
    """

    def __init__(self, result: ResolveResult):
        self.result = result
        super().__init__(
            "Dependency resolver refused install: "
            + "; ".join(c.suggestion for c in result.conflicts)
        )


class PipInstallError(InstallError):
    """Raised when ``pip install --target`` fails for isolated deps."""


@dataclass
class InstalledArtifact:
    """Result of a successful install."""

    name: str
    version: str
    path: Path
    shared_satisfied: list[str]
    isolated_installed: list[str]


Fetcher = Callable[[str], bytes]
PipRunner = Callable[[Sequence[str], Path, CoreVersions], None]


def _default_fetcher(url: str) -> bytes:
    """Fetch ``url`` to bytes. Used in production; tests inject a fake."""
    import httpx  # local import so tests without httpx still pass

    with httpx.Client(follow_redirects=True, timeout=30.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content


def _default_pip_runner(
    requirements: Sequence[str],
    target: Path,
    core_versions: CoreVersions,
) -> None:
    """Run ``pip install --target`` with platform-locked binary flags.

    The platform/python_version/abi/implementation flags are passed *together*
    with ``--only-binary=:all:``. Without the latter, pip silently falls back
    to a source build even when platform flags are set — the most common
    ARM-install footgun, explicitly prevented here.
    """
    if not requirements:
        return
    target.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-deps",
        "--only-binary=:all:",
        "--platform",
        core_versions.platform,
        "--python-version",
        core_versions.python_version,
        "--implementation",
        "cp",
        "--abi",
        core_versions.abi,
        "--target",
        str(target),
        *requirements,
    ]
    logger.info("Running pip: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise PipInstallError(
            f"pip install failed (exit {exc.returncode}): {exc.stderr.strip()}"
        ) from exc


class PluginInstaller:
    """Install, update, and uninstall plugins under a managed directory."""

    def __init__(
        self,
        plugins_dir: Path,
        core_versions: CoreVersions,
        *,
        fetcher: Optional[Fetcher] = None,
        pip_runner: Optional[PipRunner] = None,
        max_download_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
    ):
        self._plugins_dir = Path(plugins_dir)
        self._core_versions = core_versions
        self._fetcher = fetcher or _default_fetcher
        self._pip_runner = pip_runner or _default_pip_runner
        self._max_download_bytes = max_download_bytes

    @property
    def plugins_dir(self) -> Path:
        return self._plugins_dir

    @property
    def core_versions(self) -> CoreVersions:
        return self._core_versions

    def install(
        self,
        entry: MarketplaceVersionEntry,
        plugin_name: str,
        installed: Sequence[InstalledPluginRequirement] = (),
        *,
        force: bool = False,
    ) -> InstalledArtifact:
        """Perform a full install for a single marketplace version entry.

        Args:
            entry: The version entry from the marketplace index.
            plugin_name: Plugin name (the parent ``MarketplaceEntry.name``).
            installed: Already-installed plugins, for cross-plugin resolver checks.
            force: If ``True``, bypass the resolver's conflict gate. Does **not**
                bypass checksum or manifest verification.

        Returns:
            Metadata describing the landed artifact.

        Raises:
            DownloadError, ChecksumError, ArchiveError, ManifestMismatchError,
            ResolverConflictError, PipInstallError.
        """
        archive = self._download(entry)
        self._verify_checksum(archive, entry.checksum_sha256)

        with tempfile.TemporaryDirectory(
            prefix=f"baluhost-install-{plugin_name}-"
        ) as staging_str:
            staging = Path(staging_str)
            extracted_root = staging / "extracted"
            self._extract(archive, extracted_root)

            plugin_dir_in_archive = self._locate_plugin_dir(extracted_root, plugin_name)

            try:
                manifest = load_manifest(plugin_dir_in_archive)
            except ManifestError as exc:
                raise ManifestMismatchError(
                    f"plugin.json in archive is invalid: {exc}"
                ) from exc

            if manifest.name != plugin_name:
                raise ManifestMismatchError(
                    f"Archive manifest name '{manifest.name}' does not match "
                    f"index entry '{plugin_name}'"
                )
            if manifest.version != entry.version:
                raise ManifestMismatchError(
                    f"Archive manifest version '{manifest.version}' does not "
                    f"match index entry '{entry.version}'"
                )

            resolve = resolve_install(manifest, self._core_versions, installed)
            if not resolve.ok and not force:
                raise ResolverConflictError(resolve)

            site_packages = plugin_dir_in_archive / "site-packages"
            try:
                self._pip_runner(
                    list(resolve.isolated_to_install),
                    site_packages,
                    self._core_versions,
                )
            except PipInstallError:
                raise

            final_path = self._plugins_dir / plugin_name
            self._atomic_swap(plugin_dir_in_archive, final_path)

            return InstalledArtifact(
                name=manifest.name,
                version=manifest.version,
                path=final_path,
                shared_satisfied=list(resolve.shared_satisfied),
                isolated_installed=list(resolve.isolated_to_install),
            )

    def uninstall(self, name: str) -> bool:
        """Remove a plugin directory (code + isolated site-packages).

        Returns ``True`` if something was removed, ``False`` if the plugin
        directory did not exist. Does **not** touch the ``InstalledPlugin``
        database row or call ``on_uninstall`` — those belong to the API layer.
        """
        target = self._plugins_dir / name
        if not target.exists():
            return False
        shutil.rmtree(target)
        logger.info("Uninstalled plugin %s (%s)", name, target)
        return True

    # ------------------------- internal steps -------------------------

    def _download(self, entry: MarketplaceVersionEntry) -> bytes:
        if entry.size_bytes > self._max_download_bytes:
            raise DownloadError(
                f"Plugin archive declared size {entry.size_bytes} exceeds "
                f"limit {self._max_download_bytes}"
            )
        try:
            data = self._fetcher(entry.download_url)
        except Exception as exc:  # httpx / network errors bubble up here
            raise DownloadError(f"Failed to fetch {entry.download_url}: {exc}") from exc
        if len(data) > self._max_download_bytes:
            raise DownloadError(
                f"Downloaded archive is {len(data)} bytes, exceeds limit "
                f"{self._max_download_bytes}"
            )
        return data

    @staticmethod
    def _verify_checksum(data: bytes, expected: str) -> None:
        actual = hashlib.sha256(data).hexdigest()
        if actual.lower() != expected.lower():
            raise ChecksumError(
                f"Checksum mismatch: expected {expected}, got {actual}"
            )

    @staticmethod
    def _extract(archive: bytes, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(io.BytesIO(archive)) as zf:
                for member in zf.infolist():
                    # Refuse absolute paths and path-traversal attempts.
                    name = member.filename
                    if name.startswith("/") or ".." in Path(name).parts:
                        raise ArchiveError(f"Unsafe path in archive: {name!r}")
                zf.extractall(dest)
        except zipfile.BadZipFile as exc:
            raise ArchiveError(f"Not a valid zip archive: {exc}") from exc

    @staticmethod
    def _locate_plugin_dir(extracted_root: Path, plugin_name: str) -> Path:
        """Find the plugin directory inside an extracted archive.

        Supports two layouts:

        - ``archive.zip`` contains ``plugin.json`` at its root.
        - ``archive.zip`` contains a single top-level folder (commonly named
          ``{plugin_name}/``) with the manifest inside it.
        """
        root_manifest = extracted_root / "plugin.json"
        if root_manifest.exists():
            return extracted_root

        named = extracted_root / plugin_name
        if (named / "plugin.json").exists():
            return named

        subdirs = [p for p in extracted_root.iterdir() if p.is_dir()]
        if len(subdirs) == 1 and (subdirs[0] / "plugin.json").exists():
            return subdirs[0]

        raise ArchiveError(
            f"Archive does not contain a plugin.json for '{plugin_name}'"
        )

    def _atomic_swap(self, staging_plugin_dir: Path, final_path: Path) -> None:
        """Move the staged plugin directory into place.

        On success, ``final_path`` contains the new plugin. If a previous
        version is already installed at ``final_path``, it is removed first.
        We don't use ``os.replace`` on directories cross-drive — ``shutil.move``
        handles the copy-then-delete fallback when the staging temp dir and
        the plugins dir are on different filesystems.
        """
        self._plugins_dir.mkdir(parents=True, exist_ok=True)
        if final_path.exists():
            shutil.rmtree(final_path)
        shutil.move(str(staging_plugin_dir), str(final_path))
