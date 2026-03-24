"""API routes for Ad Discovery feature."""

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api import deps
from app.core.rate_limiter import user_limiter, get_limit
from app.models.user import User
from app.schemas.ad_discovery import (
    AnalyzeRequest, AnalyzeResponse,
    SuspectEntry, SuspectListResponse, SuspectStatusUpdate,
    SuspectManualAdd, SuspectBlockRequest, SuspectBulkActionRequest,
    PatternEntry, PatternCreateRequest, PatternUpdateRequest, PatternListResponse,
    ReferenceListEntry, ReferenceListCreateRequest, ReferenceListUpdateRequest, ReferenceListResponse,
    CustomListEntry, CustomListCreateRequest, CustomListUpdateRequest, CustomListResponse,
    CustomListDomainEntry, CustomListDomainsResponse, CustomListAddDomainsRequest,
    AdDiscoveryStatusResponse, AdDiscoveryConfigResponse, AdDiscoveryConfigUpdate,
)
from app.services.audit import get_audit_logger_db

router = APIRouter(prefix="/ad-discovery", tags=["ad-discovery"])


def _make_analyzer(db: Session):
    """Create a fully wired Analyzer instance."""
    from app.services.pihole.ad_discovery.scorer import Scorer
    from app.services.pihole.ad_discovery.community_matcher import get_community_matcher
    from app.services.pihole.ad_discovery.analyzer import Analyzer

    scorer = Scorer()
    scorer.load_patterns_from_db(db)
    matcher = get_community_matcher()
    return Analyzer(db, scorer, matcher)


def _get_pihole_backend(db: Session):
    """Return the Pi-hole protocol backend from the service."""
    from app.services.pihole.service import get_pihole_service

    service = get_pihole_service(db)
    return service._backend


def _get_custom_lists_service():
    """Return a CustomListsService instance."""
    from app.services.pihole.ad_discovery.custom_lists import CustomListsService

    return CustomListsService()


# ── Analysis ──────────────────────────────────────────────────────────

@router.post("/analyze", response_model=AnalyzeResponse)
@user_limiter.limit(get_limit("ad_discovery"))
async def trigger_analysis(
    request: Request, response: Response,
    body: AnalyzeRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Manually trigger ad domain analysis for a given time period."""
    analyzer = _make_analyzer(db)
    result = analyzer.analyze_queries(period=body.period, min_score=body.min_score)
    get_audit_logger_db().log_event(
        event_type="AD_DISCOVERY", user=current_user.username,
        action="ad_discovery_analyze",
        details={"period": body.period, "min_score": body.min_score, **result},
    )
    return AnalyzeResponse(**result)


# ── Suspects ──────────────────────────────────────────────────────────

@router.get("/suspects", response_model=SuspectListResponse)
@user_limiter.limit(get_limit("ad_discovery"))
async def list_suspects(
    request: Request, response: Response,
    suspect_status: Optional[str] = Query(None, alias="status"),
    source: Optional[str] = Query(None),
    sort_by: str = Query("heuristic_score"),
    order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get paginated list of ad domain suspects with optional filters."""
    from app.models.ad_discovery import AdDiscoverySuspect
    import sqlalchemy as sa

    q = db.query(AdDiscoverySuspect)
    if suspect_status:
        q = q.filter(AdDiscoverySuspect.status == suspect_status)
    if source:
        q = q.filter(AdDiscoverySuspect.source == source)

    total = q.count()

    # Apply ordering
    col = getattr(AdDiscoverySuspect, sort_by, None)
    if col is not None:
        q = q.order_by(col.desc() if order == "desc" else col.asc())
    else:
        q = q.order_by(AdDiscoverySuspect.heuristic_score.desc())

    suspects = q.offset((page - 1) * page_size).limit(page_size).all()

    return SuspectListResponse(
        suspects=[SuspectEntry.model_validate(s) for s in suspects],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/suspects/{domain:path}", response_model=SuspectEntry)
@user_limiter.limit(get_limit("ad_discovery"))
async def update_suspect_status(
    request: Request, response: Response,
    domain: str,
    body: SuspectStatusUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Update the status of a suspect domain (confirm/dismiss/blocked)."""
    analyzer = _make_analyzer(db)
    suspect = analyzer.update_suspect_status(domain, body.status)
    if not suspect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suspect not found")
    get_audit_logger_db().log_event(
        event_type="AD_DISCOVERY", user=current_user.username,
        action="ad_discovery_suspect_status_updated",
        details={"domain": domain, "status": body.status},
    )
    return SuspectEntry.model_validate(suspect)


@router.post("/suspects/manual", response_model=SuspectEntry, status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("ad_discovery"))
async def add_manual_suspect(
    request: Request, response: Response,
    body: SuspectManualAdd,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Manually add a domain as a suspect."""
    analyzer = _make_analyzer(db)
    suspect = analyzer.add_manual_suspect(body.domain)
    get_audit_logger_db().log_event(
        event_type="AD_DISCOVERY", user=current_user.username,
        action="ad_discovery_suspect_manual_add",
        details={"domain": body.domain},
    )
    return SuspectEntry.model_validate(suspect)


@router.post("/suspects/block", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("ad_discovery"))
async def block_suspect(
    request: Request, response: Response,
    body: SuspectBlockRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Block a suspect domain via Pi-hole deny list or a custom blocklist."""
    analyzer = _make_analyzer(db)
    pihole_backend = _get_pihole_backend(db)
    custom_lists_service = _get_custom_lists_service() if body.target == "custom_list" else None
    await analyzer.block_suspect(
        domain=body.domain,
        target=body.target,
        list_id=body.list_id,
        pihole_backend=pihole_backend,
        custom_lists_service=custom_lists_service,
    )
    get_audit_logger_db().log_event(
        event_type="AD_DISCOVERY", user=current_user.username,
        action="ad_discovery_suspect_blocked",
        details={"domain": body.domain, "target": body.target, "list_id": body.list_id},
    )


@router.post("/suspects/bulk-action", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("ad_discovery"))
async def bulk_action_suspects(
    request: Request, response: Response,
    body: SuspectBulkActionRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Apply a bulk action (block/dismiss/confirm) to multiple suspect domains."""
    analyzer = _make_analyzer(db)
    pihole_backend = _get_pihole_backend(db) if body.action == "block" else None
    custom_lists_service = (
        _get_custom_lists_service()
        if body.action == "block" and body.target == "custom_list"
        else None
    )

    for domain in body.domains:
        if body.action == "block":
            await analyzer.block_suspect(
                domain=domain,
                target=body.target or "deny_list",
                list_id=body.list_id,
                pihole_backend=pihole_backend,
                custom_lists_service=custom_lists_service,
            )
        elif body.action == "dismiss":
            analyzer.update_suspect_status(domain, "dismissed")
        elif body.action == "confirm":
            analyzer.update_suspect_status(domain, "confirmed")

    get_audit_logger_db().log_event(
        event_type="AD_DISCOVERY", user=current_user.username,
        action="ad_discovery_bulk_action",
        details={"action": body.action, "count": len(body.domains)},
    )


# ── Patterns ──────────────────────────────────────────────────────────

@router.get("/patterns", response_model=PatternListResponse)
@user_limiter.limit(get_limit("ad_discovery"))
async def list_patterns(
    request: Request, response: Response,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """List all heuristic patterns."""
    from app.models.ad_discovery import AdDiscoveryPattern

    patterns = db.query(AdDiscoveryPattern).all()
    return PatternListResponse(patterns=[PatternEntry.model_validate(p) for p in patterns])


@router.post("/patterns", response_model=PatternEntry, status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("ad_discovery"))
async def create_pattern(
    request: Request, response: Response,
    body: PatternCreateRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Create a new heuristic pattern."""
    from app.models.ad_discovery import AdDiscoveryPattern

    if body.is_regex:
        try:
            compiled = re.compile(body.pattern)
            # Timeout test: match against a benign string
            compiled.search("safe-test-domain.example.com")
        except re.error as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid regex pattern: {exc}",
            )

    pattern = AdDiscoveryPattern(
        pattern=body.pattern,
        is_regex=body.is_regex,
        weight=body.weight,
        category=body.category,
        is_default=False,
        enabled=True,
    )
    db.add(pattern)
    db.commit()
    db.refresh(pattern)

    get_audit_logger_db().log_event(
        event_type="AD_DISCOVERY", user=current_user.username,
        action="ad_discovery_pattern_created",
        details={"pattern": body.pattern, "category": body.category},
    )
    return PatternEntry.model_validate(pattern)


@router.patch("/patterns/{pattern_id}", response_model=PatternEntry)
@user_limiter.limit(get_limit("ad_discovery"))
async def update_pattern(
    request: Request, response: Response,
    pattern_id: int,
    body: PatternUpdateRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Update a heuristic pattern's weight, enabled state, or category."""
    from app.models.ad_discovery import AdDiscoveryPattern

    pattern = db.query(AdDiscoveryPattern).filter(AdDiscoveryPattern.id == pattern_id).first()
    if not pattern:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pattern not found")

    if body.weight is not None:
        pattern.weight = body.weight
    if body.enabled is not None:
        pattern.enabled = body.enabled
    if body.category is not None:
        pattern.category = body.category

    db.commit()
    db.refresh(pattern)
    return PatternEntry.model_validate(pattern)


@router.delete("/patterns/{pattern_id}", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("ad_discovery"))
async def delete_pattern(
    request: Request, response: Response,
    pattern_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Delete a custom pattern. Default patterns can only be disabled, not deleted."""
    from app.models.ad_discovery import AdDiscoveryPattern

    pattern = db.query(AdDiscoveryPattern).filter(AdDiscoveryPattern.id == pattern_id).first()
    if not pattern:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pattern not found")
    if pattern.is_default:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Default patterns cannot be deleted; disable them instead.",
        )

    db.delete(pattern)
    db.commit()

    get_audit_logger_db().log_event(
        event_type="AD_DISCOVERY", user=current_user.username,
        action="ad_discovery_pattern_deleted",
        details={"pattern_id": pattern_id},
    )


# ── Reference Lists ───────────────────────────────────────────────────

@router.get("/reference-lists", response_model=ReferenceListResponse)
@user_limiter.limit(get_limit("ad_discovery"))
async def list_reference_lists(
    request: Request, response: Response,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """List all community reference blocklists."""
    from app.models.ad_discovery import AdDiscoveryReferenceList

    lists = db.query(AdDiscoveryReferenceList).all()
    return ReferenceListResponse(lists=[ReferenceListEntry.model_validate(lst) for lst in lists])


@router.post("/reference-lists", response_model=ReferenceListEntry, status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("ad_discovery"))
async def create_reference_list(
    request: Request, response: Response,
    body: ReferenceListCreateRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Add a new community reference blocklist."""
    from app.models.ad_discovery import AdDiscoveryReferenceList
    from app.services.pihole.ad_discovery.community_matcher import _validate_url

    try:
        _validate_url(body.url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    ref_list = AdDiscoveryReferenceList(
        name=body.name,
        url=body.url,
        is_default=False,
        enabled=False,
        domain_count=0,
        fetch_interval_hours=body.fetch_interval_hours,
    )
    db.add(ref_list)
    db.commit()
    db.refresh(ref_list)

    get_audit_logger_db().log_event(
        event_type="AD_DISCOVERY", user=current_user.username,
        action="ad_discovery_reference_list_created",
        details={"name": body.name, "url": body.url},
    )
    return ReferenceListEntry.model_validate(ref_list)


@router.patch("/reference-lists/{list_id}", response_model=ReferenceListEntry)
@user_limiter.limit(get_limit("ad_discovery"))
async def update_reference_list(
    request: Request, response: Response,
    list_id: int,
    body: ReferenceListUpdateRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Update a reference list's enabled state or fetch interval."""
    from app.models.ad_discovery import AdDiscoveryReferenceList

    ref_list = db.query(AdDiscoveryReferenceList).filter(AdDiscoveryReferenceList.id == list_id).first()
    if not ref_list:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference list not found")

    if body.enabled is not None:
        ref_list.enabled = body.enabled
    if body.fetch_interval_hours is not None:
        ref_list.fetch_interval_hours = body.fetch_interval_hours

    db.commit()
    db.refresh(ref_list)
    return ReferenceListEntry.model_validate(ref_list)


@router.delete("/reference-lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("ad_discovery"))
async def delete_reference_list(
    request: Request, response: Response,
    list_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Delete a custom reference list. Default lists cannot be deleted."""
    from app.models.ad_discovery import AdDiscoveryReferenceList

    ref_list = db.query(AdDiscoveryReferenceList).filter(AdDiscoveryReferenceList.id == list_id).first()
    if not ref_list:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference list not found")
    if ref_list.is_default:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Default reference lists cannot be deleted; disable them instead.",
        )

    db.delete(ref_list)
    db.commit()

    get_audit_logger_db().log_event(
        event_type="AD_DISCOVERY", user=current_user.username,
        action="ad_discovery_reference_list_deleted",
        details={"list_id": list_id},
    )


@router.post("/reference-lists/refresh", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("ad_discovery"))
async def refresh_reference_lists(
    request: Request, response: Response,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Force-refresh all enabled reference lists."""
    from app.services.pihole.ad_discovery.community_matcher import get_community_matcher

    matcher = get_community_matcher()
    await matcher.refresh_all(db)

    get_audit_logger_db().log_event(
        event_type="AD_DISCOVERY", user=current_user.username,
        action="ad_discovery_reference_lists_refreshed",
        details={},
    )


# ── Custom Lists ──────────────────────────────────────────────────────

@router.get("/custom-lists", response_model=CustomListResponse)
@user_limiter.limit(get_limit("ad_discovery"))
async def list_custom_lists(
    request: Request, response: Response,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """List all custom blocklists."""
    svc = _get_custom_lists_service()
    lists = svc.get_all_lists(db)
    return CustomListResponse(lists=[CustomListEntry.model_validate(lst) for lst in lists])


@router.post("/custom-lists", response_model=CustomListEntry, status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("ad_discovery"))
async def create_custom_list(
    request: Request, response: Response,
    body: CustomListCreateRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Create a new custom blocklist."""
    svc = _get_custom_lists_service()
    try:
        lst = svc.create_list(db, name=body.name, description=body.description)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Could not create list: {exc}",
        )
    get_audit_logger_db().log_event(
        event_type="AD_DISCOVERY", user=current_user.username,
        action="ad_discovery_custom_list_created",
        details={"name": body.name},
    )
    return CustomListEntry.model_validate(lst)


@router.patch("/custom-lists/{list_id}", response_model=CustomListEntry)
@user_limiter.limit(get_limit("ad_discovery"))
async def update_custom_list(
    request: Request, response: Response,
    list_id: int,
    body: CustomListUpdateRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Update a custom list's name or description."""
    svc = _get_custom_lists_service()
    lst = svc.update_list(db, list_id, name=body.name, description=body.description)
    if not lst:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom list not found")
    return CustomListEntry.model_validate(lst)


@router.delete("/custom-lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("ad_discovery"))
async def delete_custom_list(
    request: Request, response: Response,
    list_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Delete a custom blocklist. If deployed, it will be undeployed first."""
    from app.models.ad_discovery import AdDiscoveryCustomList

    lst = db.query(AdDiscoveryCustomList).filter(AdDiscoveryCustomList.id == list_id).first()
    if not lst:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom list not found")

    if lst.deployed:
        pihole_backend = _get_pihole_backend(db)
        svc = _get_custom_lists_service()
        try:
            await svc.undeploy_from_pihole(db, list_id, pihole_backend)
        except Exception:
            pass  # Best-effort undeploy before deletion

    svc = _get_custom_lists_service()
    svc.delete_list(db, list_id)

    get_audit_logger_db().log_event(
        event_type="AD_DISCOVERY", user=current_user.username,
        action="ad_discovery_custom_list_deleted",
        details={"list_id": list_id},
    )


@router.get("/custom-lists/{list_id}/domains", response_model=CustomListDomainsResponse)
@user_limiter.limit(get_limit("ad_discovery"))
async def list_custom_list_domains(
    request: Request, response: Response,
    list_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get paginated domains for a custom blocklist."""
    from app.models.ad_discovery import AdDiscoveryCustomList, AdDiscoveryCustomListDomain

    lst = db.query(AdDiscoveryCustomList).filter(AdDiscoveryCustomList.id == list_id).first()
    if not lst:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom list not found")

    q = db.query(AdDiscoveryCustomListDomain).filter(
        AdDiscoveryCustomListDomain.list_id == list_id
    ).order_by(AdDiscoveryCustomListDomain.domain)

    total = q.count()
    domains = q.offset((page - 1) * page_size).limit(page_size).all()

    return CustomListDomainsResponse(
        domains=[CustomListDomainEntry.model_validate(d) for d in domains],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/custom-lists/{list_id}/domains", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("ad_discovery"))
async def add_custom_list_domains(
    request: Request, response: Response,
    list_id: int,
    body: CustomListAddDomainsRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Add domains to a custom blocklist."""
    svc = _get_custom_lists_service()
    try:
        svc.add_domains(db, list_id, body.domains, comment=body.comment)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    get_audit_logger_db().log_event(
        event_type="AD_DISCOVERY", user=current_user.username,
        action="ad_discovery_custom_list_domains_added",
        details={"list_id": list_id, "count": len(body.domains)},
    )


@router.delete("/custom-lists/{list_id}/domains/{domain:path}", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("ad_discovery"))
async def remove_custom_list_domain(
    request: Request, response: Response,
    list_id: int,
    domain: str,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Remove a domain from a custom blocklist."""
    svc = _get_custom_lists_service()
    removed = svc.remove_domain(db, list_id, domain)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found in the specified list",
        )

    get_audit_logger_db().log_event(
        event_type="AD_DISCOVERY", user=current_user.username,
        action="ad_discovery_custom_list_domain_removed",
        details={"list_id": list_id, "domain": domain},
    )


@router.post("/custom-lists/{list_id}/deploy")
@user_limiter.limit(get_limit("ad_discovery"))
async def deploy_custom_list(
    request: Request, response: Response,
    list_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Deploy a custom blocklist to Pi-hole as an adlist."""
    svc = _get_custom_lists_service()
    pihole_backend = _get_pihole_backend(db)
    base_url = str(request.base_url).rstrip("/")
    try:
        adlist_url = await svc.deploy_to_pihole(db, list_id, base_url, pihole_backend)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    get_audit_logger_db().log_event(
        event_type="AD_DISCOVERY", user=current_user.username,
        action="ad_discovery_custom_list_deployed",
        details={"list_id": list_id, "adlist_url": adlist_url},
    )
    return {"adlist_url": adlist_url}


@router.post("/custom-lists/{list_id}/undeploy", status_code=status.HTTP_204_NO_CONTENT)
@user_limiter.limit(get_limit("ad_discovery"))
async def undeploy_custom_list(
    request: Request, response: Response,
    list_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Remove a custom blocklist from Pi-hole."""
    svc = _get_custom_lists_service()
    pihole_backend = _get_pihole_backend(db)
    try:
        await svc.undeploy_from_pihole(db, list_id, pihole_backend)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    get_audit_logger_db().log_event(
        event_type="AD_DISCOVERY", user=current_user.username,
        action="ad_discovery_custom_list_undeployed",
        details={"list_id": list_id},
    )


@router.get("/custom-lists/{list_id}/export")
@user_limiter.limit(get_limit("ad_discovery"))
async def export_custom_list(
    request: Request, response: Response,
    list_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Download a custom blocklist as a plain-text .txt file."""
    svc = _get_custom_lists_service()
    try:
        content = svc.export_list(db, list_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return Response(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=\"blocklist-{list_id}.txt\""},
    )


@router.get("/custom-lists/{list_id}/adlist.txt")
async def get_adlist_file(
    list_id: int,
    token: str = Query(...),
    db: Session = Depends(deps.get_db),
):
    """Serve the adlist file for Pi-hole. Token-authenticated, no admin required."""
    from app.models.ad_discovery import AdDiscoveryCustomList

    lst = db.query(AdDiscoveryCustomList).filter(AdDiscoveryCustomList.id == list_id).first()
    if not lst or lst.adlist_token != token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")

    svc = _get_custom_lists_service()
    try:
        content = svc.generate_adlist_content(db, list_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return Response(content=content, media_type="text/plain")


# ── Status & Config ───────────────────────────────────────────────────

@router.get("/status", response_model=AdDiscoveryStatusResponse)
@user_limiter.limit(get_limit("ad_discovery"))
async def get_status(
    request: Request, response: Response,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get Ad Discovery dashboard status summary."""
    from app.models.ad_discovery import (
        AdDiscoverySuspect, AdDiscoveryConfig,
        AdDiscoveryReferenceList, AdDiscoveryCustomList,
    )

    config = db.query(AdDiscoveryConfig).filter(AdDiscoveryConfig.id == 1).first()

    suspects_new = db.query(AdDiscoverySuspect).filter(AdDiscoverySuspect.status == "new").count()
    suspects_confirmed = db.query(AdDiscoverySuspect).filter(AdDiscoverySuspect.status == "confirmed").count()
    suspects_dismissed = db.query(AdDiscoverySuspect).filter(AdDiscoverySuspect.status == "dismissed").count()
    suspects_blocked = db.query(AdDiscoverySuspect).filter(AdDiscoverySuspect.status == "blocked").count()

    ref_lists_total = db.query(AdDiscoveryReferenceList).count()
    ref_lists_active = db.query(AdDiscoveryReferenceList).filter(
        AdDiscoveryReferenceList.enabled == True  # noqa: E712
    ).count()

    custom_lists_total = db.query(AdDiscoveryCustomList).count()
    custom_lists_deployed = db.query(AdDiscoveryCustomList).filter(
        AdDiscoveryCustomList.deployed == True  # noqa: E712
    ).count()

    from app.services.pihole.ad_discovery.background import get_ad_discovery_task
    bg_running = get_ad_discovery_task().is_running

    return AdDiscoveryStatusResponse(
        suspects_new=suspects_new,
        suspects_confirmed=suspects_confirmed,
        suspects_dismissed=suspects_dismissed,
        suspects_blocked=suspects_blocked,
        last_analysis_at=config.last_analysis_at if config else None,
        background_task_running=bg_running,
        reference_lists_active=ref_lists_active,
        reference_lists_total=ref_lists_total,
        custom_lists_total=custom_lists_total,
        custom_lists_deployed=custom_lists_deployed,
    )


@router.get("/config", response_model=AdDiscoveryConfigResponse)
@user_limiter.limit(get_limit("ad_discovery"))
async def get_config(
    request: Request, response: Response,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get current Ad Discovery configuration."""
    from app.models.ad_discovery import AdDiscoveryConfig

    config = db.query(AdDiscoveryConfig).filter(AdDiscoveryConfig.id == 1).first()
    if not config:
        return AdDiscoveryConfigResponse()
    return AdDiscoveryConfigResponse(
        background_interval_hours=config.background_interval_hours,
        heuristic_weight=config.heuristic_weight,
        community_weight=config.community_weight,
        min_score=config.min_score,
        re_evaluation_threshold=config.re_evaluation_threshold,
        background_enabled=config.background_enabled,
    )


@router.patch("/config", response_model=AdDiscoveryConfigResponse)
@user_limiter.limit(get_limit("ad_discovery"))
async def update_config(
    request: Request, response: Response,
    body: AdDiscoveryConfigUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Update Ad Discovery configuration."""
    from app.models.ad_discovery import AdDiscoveryConfig

    config = db.query(AdDiscoveryConfig).filter(AdDiscoveryConfig.id == 1).first()
    if not config:
        config = AdDiscoveryConfig(id=1)
        db.add(config)

    updates = body.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(config, field_name, value)

    db.commit()
    db.refresh(config)

    get_audit_logger_db().log_event(
        event_type="AD_DISCOVERY", user=current_user.username,
        action="ad_discovery_config_updated",
        details={"fields": list(updates.keys())},
    )
    return AdDiscoveryConfigResponse(
        background_interval_hours=config.background_interval_hours,
        heuristic_weight=config.heuristic_weight,
        community_weight=config.community_weight,
        min_score=config.min_score,
        re_evaluation_threshold=config.re_evaluation_threshold,
        background_enabled=config.background_enabled,
    )
