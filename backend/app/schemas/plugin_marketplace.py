"""Pydantic schemas for the plugin marketplace API.

These mirror the shapes returned by :mod:`app.services.plugin_marketplace` /
:mod:`app.plugins.installer`, but are kept separate from the marketplace
*index* schemas (``app.plugins.marketplace``) so we can tailor the wire
format for the frontend without leaking installer internals.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class MarketplaceVersionResponse(BaseModel):
    version: str
    min_baluhost_version: Optional[str] = None
    max_baluhost_version: Optional[str] = None
    python_requirements: List[str] = Field(default_factory=list)
    required_permissions: List[str] = Field(default_factory=list)
    download_url: str
    checksum_sha256: str
    size_bytes: int
    released_at: Optional[str] = None


class MarketplacePluginResponse(BaseModel):
    name: str
    latest_version: str
    display_name: str
    description: str
    author: str
    homepage: Optional[str] = None
    category: str = "general"
    versions: List[MarketplaceVersionResponse]


class MarketplaceIndexResponse(BaseModel):
    index_version: int
    generated_at: Optional[str] = None
    plugins: List[MarketplacePluginResponse]


class ConflictResponse(BaseModel):
    package: str
    requirement: str
    found: Optional[str] = None
    source: str
    suggestion: str


class InstallRequest(BaseModel):
    version: Optional[str] = Field(
        None,
        description="Specific version to install. Omit to install the latest version.",
    )
    force: bool = Field(
        False,
        description="Bypass dependency resolver conflicts. Checksum and "
        "manifest verification are still enforced.",
    )


class InstallResponse(BaseModel):
    name: str
    version: str
    installed_path: str
    shared_satisfied: List[str] = Field(default_factory=list)
    isolated_installed: List[str] = Field(default_factory=list)
