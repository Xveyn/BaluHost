"""Pydantic schemas for the marketplace ``index.json`` file.

The index is a single static JSON file built by the ``baluhost-plugins`` repo's
CI and published to a known URL (spec: one official index in v1). This module
only defines the *shape* — fetching and caching live in ``installer.py`` /
the API route; they reuse these models as the validation layer.

Schema version: ``index_version = 1``.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


SUPPORTED_INDEX_VERSIONS = {1}


class MarketplaceVersionEntry(BaseModel):
    """A single published version of a plugin.

    ``checksum_sha256`` is the SHA-256 hex digest of the ``.bhplugin`` archive;
    the installer verifies every download against this value. ``download_url``
    may point anywhere — the marketplace index is the only place that vouches
    for the artifact, so the checksum is the only trust anchor in v1 (signing
    is a tracked follow-up).
    """

    version: str
    min_baluhost_version: Optional[str] = None
    max_baluhost_version: Optional[str] = None
    python_requirements: List[str] = Field(default_factory=list)
    required_permissions: List[str] = Field(default_factory=list)
    download_url: str
    checksum_sha256: str = Field(..., min_length=64, max_length=64)
    size_bytes: int = Field(..., ge=0)
    released_at: Optional[str] = None


class MarketplaceEntry(BaseModel):
    """Marketplace listing for one plugin (name + all its versions)."""

    name: str
    latest_version: str
    versions: List[MarketplaceVersionEntry]
    display_name: str
    description: str
    author: str
    homepage: Optional[str] = None
    category: str = "general"

    def get_version(self, version: str) -> Optional[MarketplaceVersionEntry]:
        for v in self.versions:
            if v.version == version:
                return v
        return None


class MarketplaceIndex(BaseModel):
    """Top-level ``index.json`` shape."""

    index_version: int
    generated_at: Optional[str] = None
    plugins: List[MarketplaceEntry] = Field(default_factory=list)

    def get_plugin(self, name: str) -> Optional[MarketplaceEntry]:
        for p in self.plugins:
            if p.name == name:
                return p
        return None
