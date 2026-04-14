"""Marketplace API routes — list upstream plugins and install/uninstall them.

Mounted at ``/api/plugins/marketplace`` alongside the regular
``/api/plugins`` routes. Admin-only; every route is rate-limited with the
``admin_operations`` bucket.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.api.deps import get_current_admin
from app.core.rate_limiter import get_limit, user_limiter
from app.models.user import User
from app.plugins.installer import (
    ArchiveError,
    ChecksumError,
    DownloadError,
    ManifestMismatchError,
    PipInstallError,
    ResolverConflictError,
)
from app.plugins.resolver import InstalledPluginRequirement
from app.schemas.plugin_marketplace import (
    ConflictResponse,
    InstallRequest,
    InstallResponse,
    MarketplaceIndexResponse,
    MarketplacePluginResponse,
    MarketplaceVersionResponse,
)
from app.services.plugin_marketplace import (
    IndexFetchError,
    IndexParseError,
    MarketplaceService,
    PluginNotFoundError,
    get_marketplace_service,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plugins/marketplace", tags=["plugins-marketplace"])


def _serialize_index(service: MarketplaceService) -> MarketplaceIndexResponse:
    index = service.get_index()
    return MarketplaceIndexResponse(
        index_version=index.index_version,
        generated_at=index.generated_at,
        plugins=[
            MarketplacePluginResponse(
                name=p.name,
                latest_version=p.latest_version,
                display_name=p.display_name,
                description=p.description,
                author=p.author,
                homepage=p.homepage,
                category=p.category,
                versions=[
                    MarketplaceVersionResponse(**v.model_dump())
                    for v in p.versions
                ],
            )
            for p in index.plugins
        ],
    )


def _conflicts_to_http(exc: ResolverConflictError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": "resolver_conflict",
            "conflicts": [
                ConflictResponse(
                    package=c.package,
                    requirement=c.requirement,
                    found=c.found,
                    source=c.source,
                    suggestion=c.suggestion,
                ).model_dump()
                for c in exc.result.conflicts
            ],
        },
    )


@router.get("", response_model=MarketplaceIndexResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def list_marketplace(
    request: Request,
    response: Response,
    refresh: bool = Query(False, description="Force-refresh the cached index"),
    current_user: User = Depends(get_current_admin),
    service: MarketplaceService = Depends(get_marketplace_service),
) -> MarketplaceIndexResponse:
    """List plugins available in the upstream marketplace index."""
    try:
        if refresh:
            service.invalidate_cache()
        return _serialize_index(service)
    except IndexFetchError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"failed to fetch marketplace index: {exc}",
        ) from exc
    except IndexParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"malformed marketplace index: {exc}",
        ) from exc


@router.post(
    "/{plugin_name}/install",
    response_model=InstallResponse,
    status_code=status.HTTP_201_CREATED,
)
@user_limiter.limit(get_limit("admin_operations"))
async def install_plugin(
    request: Request,
    response: Response,
    plugin_name: str,
    payload: InstallRequest,
    current_user: User = Depends(get_current_admin),
    service: MarketplaceService = Depends(get_marketplace_service),
) -> InstallResponse:
    """Install a plugin from the marketplace by name + optional version."""
    # v1: we don't yet cross-check against already-installed external plugin
    # requirements (that hooks into PluginManager discovery later). Pass an
    # empty list for now — the resolver still checks core versions and
    # C-extension blacklist.
    installed: list[InstalledPluginRequirement] = []

    try:
        artifact = service.install(
            plugin_name,
            version=payload.version,
            installed=installed,
            force=payload.force,
        )
    except PluginNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ResolverConflictError as exc:
        raise _conflicts_to_http(exc) from exc
    except ChecksumError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"checksum mismatch: {exc}",
        ) from exc
    except (DownloadError, IndexFetchError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"download failed: {exc}",
        ) from exc
    except (ArchiveError, ManifestMismatchError, IndexParseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid plugin artifact: {exc}",
        ) from exc
    except PipInstallError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"pip install failed: {exc}",
        ) from exc

    logger.info(
        "Installed marketplace plugin %s v%s at %s",
        artifact.name,
        artifact.version,
        artifact.path,
    )
    return InstallResponse(
        name=artifact.name,
        version=artifact.version,
        installed_path=str(artifact.path),
        shared_satisfied=artifact.shared_satisfied,
        isolated_installed=artifact.isolated_installed,
    )


@router.delete("/{plugin_name}", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("admin_operations"))
async def uninstall_plugin(
    request: Request,
    response: Response,
    plugin_name: str,
    current_user: User = Depends(get_current_admin),
    service: MarketplaceService = Depends(get_marketplace_service),
) -> Response:
    """Remove an installed marketplace plugin from the filesystem."""
    removed = service.uninstall(plugin_name)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"plugin {plugin_name!r} is not installed",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
