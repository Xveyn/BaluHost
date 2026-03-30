"""API routes for serving project documentation as a user manual."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api import deps
from app.core.rate_limiter import limiter, get_limit
from app.schemas.docs import DocsArticleResponse, DocsIndexResponse
from app.schemas.user import UserPublic
from app.services.docs import DocsService
from app.services.permissions import is_privileged

router = APIRouter(prefix="/docs", tags=["docs"])

_docs_service: DocsService | None = None


def _get_docs_service() -> DocsService:
    global _docs_service
    if _docs_service is None:
        _docs_service = DocsService()
    return _docs_service


@router.get("/index", response_model=DocsIndexResponse)
@limiter.limit(get_limit("docs_index"))
def get_docs_index(
    request: Request,
    response: Response,
    lang: str = "de",
    user: UserPublic = Depends(deps.get_current_user),
) -> DocsIndexResponse:
    """Return the documentation index, filtered by user role."""
    svc = _get_docs_service()
    groups = svc.get_index(lang=lang, is_admin=is_privileged(user))
    return DocsIndexResponse(groups=groups)


@router.get("/article/{slug}", response_model=DocsArticleResponse)
@limiter.limit(get_limit("docs_article"))
def get_docs_article(
    request: Request,
    response: Response,
    slug: str,
    lang: str = "de",
    user: UserPublic = Depends(deps.get_current_user),
) -> DocsArticleResponse:
    """Return a single documentation article by slug."""
    svc = _get_docs_service()
    admin = is_privileged(user)
    article = svc.get_article(slug=slug, lang=lang, is_admin=admin)

    if article is None:
        exists = svc.get_article(slug=slug, lang=lang, is_admin=True)
        if exists is not None and not admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article '{slug}' not found",
        )
    return article
