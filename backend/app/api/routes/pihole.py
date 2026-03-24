"""API routes for Pi-hole DNS integration.

All endpoints are admin-only with rate limiting.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.api import deps
from app.core.rate_limiter import user_limiter, get_limit
from app.models.user import User
from app.schemas.pihole import (
    PiholeStatusResponse,
    PiholeSummaryResponse,
    BlockingRequest,
    BlockingResponse,
    QueryLogResponse,
    TopDomainsResponse,
    TopBlockedResponse,
    TopClientsResponse,
    HistoryResponse,
    DomainListResponse,
    AddDomainRequest,
    RemoveDomainRequest,
    AdlistResponse,
    AddAdlistRequest,
    RemoveAdlistRequest,
    ToggleAdlistRequest,
    LocalDnsResponse,
    AddLocalDnsRequest,
    RemoveLocalDnsRequest,
    ContainerDeployRequest,
    ContainerActionResponse,
    ContainerDeployResponse,
    ContainerLogsResponse,
    PiholeConfigResponse,
    PiholeConfigUpdateRequest,
    FailoverStatusResponse,
    StoredQueryEntry,
    StoredQueryResponse,
    StoredStatsResponse,
    StoredDomainEntry,
    StoredTopDomainsResponse,
    StoredTopBlockedResponse,
    StoredClientEntry,
    StoredTopClientsResponse,
    HourlyCountEntry,
    StoredHistoryResponse,
    QueryCollectorStatusResponse,
    QueryCollectorConfigUpdate,
)
from app.services.pihole.service import get_pihole_service
from app.services.pihole import query_analytics
from app.services.audit import get_audit_logger_db

router = APIRouter(prefix="/pihole", tags=["pihole"])

from app.api.routes.ad_discovery import router as ad_discovery_router
router.include_router(ad_discovery_router)


def _get_service(db: Session = Depends(deps.get_db)):
    """Dependency to create PiholeService."""
    return get_pihole_service(db)


# ── Status & Summary ──────────────────────────────────────────────────

@router.get("/status", response_model=PiholeStatusResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_status(
    request: Request, response: Response,
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get Pi-hole status including blocking state and container info."""
    data = await service.get_status()
    return PiholeStatusResponse(**data)


@router.get("/failover-status", response_model=FailoverStatusResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_failover_status(
    request: Request, response: Response,
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get failover status between remote Pi-hole and local NAS."""
    data = await service.get_failover_status()
    return FailoverStatusResponse(**data)


@router.get("/summary", response_model=PiholeSummaryResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_summary(
    request: Request, response: Response,
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get summary statistics (queries, blocked, percentage, etc.)."""
    data = await service.get_summary()
    return PiholeSummaryResponse(**data)


# ── Blocking Control ──────────────────────────────────────────────────

@router.get("/blocking", response_model=BlockingResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_blocking(
    request: Request, response: Response,
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get current blocking state."""
    data = await service.get_blocking()
    return BlockingResponse(**data)


@router.post("/blocking", response_model=BlockingResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def set_blocking(
    request: Request, response: Response,
    body: BlockingRequest,
    db: Session = Depends(deps.get_db),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Enable or disable DNS blocking."""
    data = await service.set_blocking(body.enabled, body.timer)
    get_audit_logger_db().log_event(
        event_type="PIHOLE", user=current_user.username,
        action="pihole_blocking_changed",
        details={"state": "enabled" if body.enabled else "disabled", "timer": body.timer},
    )
    return BlockingResponse(**data)


# ── Query Log ─────────────────────────────────────────────────────────

@router.get("/queries", response_model=QueryLogResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_queries(
    request: Request, response: Response,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get paginated DNS query log."""
    data = await service.get_queries(limit, offset)
    return QueryLogResponse(**data)


# ── Statistics ────────────────────────────────────────────────────────

@router.get("/top-domains", response_model=TopDomainsResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_top_domains(
    request: Request, response: Response,
    count: int = Query(10, ge=1, le=100),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get top permitted domains."""
    data = await service.get_top_domains(count)
    return TopDomainsResponse(**data)


@router.get("/top-blocked", response_model=TopBlockedResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_top_blocked(
    request: Request, response: Response,
    count: int = Query(10, ge=1, le=100),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get top blocked domains."""
    data = await service.get_top_blocked(count)
    return TopBlockedResponse(**data)


@router.get("/top-clients", response_model=TopClientsResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_top_clients(
    request: Request, response: Response,
    count: int = Query(10, ge=1, le=100),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get top clients by query count."""
    data = await service.get_top_clients(count)
    return TopClientsResponse(**data)


@router.get("/history", response_model=HistoryResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_history(
    request: Request, response: Response,
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get query history timeline."""
    data = await service.get_history()
    return HistoryResponse(**data)


# ── Domain Management ─────────────────────────────────────────────────

@router.get("/domains", response_model=DomainListResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_domains(
    request: Request, response: Response,
    list_type: str = Query(..., pattern="^(allow|deny)$"),
    kind: str = Query(..., pattern="^(exact|regex)$"),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get domains from allow/deny lists."""
    data = await service.get_domains(list_type, kind)
    return DomainListResponse(**data)


@router.post("/domains", status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("admin_operations"))
async def add_domain(
    request: Request, response: Response,
    body: AddDomainRequest,
    db: Session = Depends(deps.get_db),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Add a domain to allow/deny list."""
    result = await service.add_domain(body.list_type, body.kind, body.domain, body.comment)
    get_audit_logger_db().log_event(
        event_type="PIHOLE", user=current_user.username,
        action="pihole_domain_added",
        details={"domain": body.domain, "list": f"{body.list_type}/{body.kind}"},
    )
    return result


@router.delete("/domains")
@user_limiter.limit(get_limit("admin_operations"))
async def remove_domain(
    request: Request, response: Response,
    body: RemoveDomainRequest,
    db: Session = Depends(deps.get_db),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Remove a domain from allow/deny list."""
    result = await service.remove_domain(body.list_type, body.kind, body.domain)
    get_audit_logger_db().log_event(
        event_type="PIHOLE", user=current_user.username,
        action="pihole_domain_removed",
        details={"domain": body.domain, "list": f"{body.list_type}/{body.kind}"},
    )
    return result


# ── Adlist Management ─────────────────────────────────────────────────

@router.get("/lists", response_model=AdlistResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_adlists(
    request: Request, response: Response,
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get all configured adlists (blocklists)."""
    data = await service.get_adlists()
    return AdlistResponse(**data)


@router.post("/lists", status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("admin_operations"))
async def add_adlist(
    request: Request, response: Response,
    body: AddAdlistRequest,
    db: Session = Depends(deps.get_db),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Add a new adlist URL."""
    result = await service.add_adlist(body.url, body.comment)
    get_audit_logger_db().log_event(
        event_type="PIHOLE", user=current_user.username,
        action="pihole_adlist_added",
        details={"url": body.url},
    )
    return result


@router.delete("/lists")
@user_limiter.limit(get_limit("admin_operations"))
async def remove_adlist(
    request: Request, response: Response,
    body: RemoveAdlistRequest,
    db: Session = Depends(deps.get_db),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Remove an adlist by its URL address."""
    result = await service.remove_adlist(body.address)
    get_audit_logger_db().log_event(
        event_type="PIHOLE", user=current_user.username,
        action="pihole_adlist_removed",
        details={"address": body.address},
    )
    return result


@router.patch("/lists/toggle")
@user_limiter.limit(get_limit("admin_operations"))
async def toggle_adlist(
    request: Request, response: Response,
    body: ToggleAdlistRequest,
    db: Session = Depends(deps.get_db),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Enable or disable an adlist."""
    result = await service.toggle_adlist(body.address, body.enabled)
    get_audit_logger_db().log_event(
        event_type="PIHOLE", user=current_user.username,
        action="pihole_adlist_toggled",
        details={"address": body.address, "enabled": body.enabled},
    )
    return result


@router.post("/gravity")
@user_limiter.limit(get_limit("admin_operations"))
async def update_gravity(
    request: Request, response: Response,
    db: Session = Depends(deps.get_db),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Trigger gravity database update."""
    result = await service.update_gravity()
    get_audit_logger_db().log_event(
        event_type="PIHOLE", user=current_user.username,
        action="pihole_gravity_update",
        details={"action": "gravity_update"},
    )
    return result


# ── Local DNS ─────────────────────────────────────────────────────────

@router.get("/dns-records", response_model=LocalDnsResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_local_dns(
    request: Request, response: Response,
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get custom local DNS A-records."""
    data = await service.get_local_dns()
    return LocalDnsResponse(**data)


@router.post("/dns-records", status_code=status.HTTP_201_CREATED)
@user_limiter.limit(get_limit("admin_operations"))
async def add_local_dns(
    request: Request, response: Response,
    body: AddLocalDnsRequest,
    db: Session = Depends(deps.get_db),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Add a custom local DNS A-record."""
    result = await service.add_local_dns(body.domain, body.ip)
    get_audit_logger_db().log_event(
        event_type="PIHOLE", user=current_user.username,
        action="pihole_dns_record_added",
        details={"domain": body.domain, "ip": body.ip},
    )
    return result


@router.delete("/dns-records")
@user_limiter.limit(get_limit("admin_operations"))
async def remove_local_dns(
    request: Request, response: Response,
    body: RemoveLocalDnsRequest,
    db: Session = Depends(deps.get_db),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Remove a custom local DNS A-record."""
    result = await service.remove_local_dns(body.domain, body.ip)
    get_audit_logger_db().log_event(
        event_type="PIHOLE", user=current_user.username,
        action="pihole_dns_record_removed",
        details={"domain": body.domain, "ip": body.ip},
    )
    return result


# ── Actions ───────────────────────────────────────────────────────────

@router.post("/restart-dns")
@user_limiter.limit(get_limit("admin_operations"))
async def restart_dns(
    request: Request, response: Response,
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Restart the Pi-hole DNS resolver."""
    return await service.restart_dns()


# ── Container Lifecycle ───────────────────────────────────────────────

@router.post("/container/deploy", response_model=ContainerDeployResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def deploy_container(
    request: Request, response: Response,
    body: ContainerDeployRequest,
    db: Session = Depends(deps.get_db),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Deploy (pull + create + start) the Pi-hole Docker container."""
    result = await service.deploy_container(body.model_dump())
    get_audit_logger_db().log_event(
        event_type="PIHOLE", user=current_user.username,
        action="pihole_container_deployed",
        details={"image_tag": body.image_tag},
    )
    # Re-register .local DNS records after fresh container deploy
    if result.get("success"):
        try:
            await service.ensure_local_dns_records()
        except Exception:
            pass  # Logged inside the method
    return ContainerDeployResponse(**result)


@router.post("/container/start", response_model=ContainerActionResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def start_container(
    request: Request, response: Response,
    db: Session = Depends(deps.get_db),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Start the Pi-hole container."""
    result = await service.start_container()
    get_audit_logger_db().log_event(
        event_type="PIHOLE", user=current_user.username,
        action="pihole_container_started",
        details={"action": "start"},
    )
    return ContainerActionResponse(**result)


@router.post("/container/stop", response_model=ContainerActionResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def stop_container(
    request: Request, response: Response,
    db: Session = Depends(deps.get_db),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Stop the Pi-hole container."""
    result = await service.stop_container()
    get_audit_logger_db().log_event(
        event_type="PIHOLE", user=current_user.username,
        action="pihole_container_stopped",
        details={"action": "stop"},
    )
    return ContainerActionResponse(**result)


@router.delete("/container", response_model=ContainerActionResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def remove_container(
    request: Request, response: Response,
    db: Session = Depends(deps.get_db),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Remove the Pi-hole container."""
    result = await service.remove_container()
    get_audit_logger_db().log_event(
        event_type="PIHOLE", user=current_user.username,
        action="pihole_container_removed",
        details={"action": "remove"},
    )
    return ContainerActionResponse(**result)


@router.post("/container/update", response_model=ContainerActionResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_container(
    request: Request, response: Response,
    db: Session = Depends(deps.get_db),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Pull latest image and recreate the container."""
    result = await service.update_container()
    get_audit_logger_db().log_event(
        event_type="PIHOLE", user=current_user.username,
        action="pihole_container_updated",
        details={"action": "update"},
    )
    return ContainerActionResponse(**result)


@router.get("/container/logs", response_model=ContainerLogsResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_container_logs(
    request: Request, response: Response,
    lines: int = Query(100, ge=1, le=5000),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get recent container log lines."""
    data = await service.get_container_logs(lines)
    return ContainerLogsResponse(**data)


# ── Configuration ─────────────────────────────────────────────────────

@router.get("/config", response_model=PiholeConfigResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_config(
    request: Request, response: Response,
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get current Pi-hole configuration."""
    config = service.get_config()
    result = PiholeConfigResponse.model_validate(config)
    result.has_password = config.password_encrypted is not None
    result.has_remote_password = config.remote_password_encrypted is not None
    return result


@router.put("/config", response_model=PiholeConfigResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_config(
    request: Request, response: Response,
    body: PiholeConfigUpdateRequest,
    db: Session = Depends(deps.get_db),
    service=Depends(_get_service),
    current_user: User = Depends(deps.get_current_admin),
):
    """Update Pi-hole configuration."""
    update_data = body.model_dump(exclude_unset=True)
    config = service.update_config(**update_data)
    get_audit_logger_db().log_event(
        event_type="PIHOLE", user=current_user.username,
        action="pihole_config_updated",
        details={"fields": list(update_data.keys())},
    )
    return PiholeConfigResponse.model_validate(config)


# ── Stored Queries (PostgreSQL) ──────────────────────────────────────

@router.get("/stored-queries", response_model=StoredQueryResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_stored_queries(
    request: Request, response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    domain: Optional[str] = Query(None, max_length=253),
    client: Optional[str] = Query(None, max_length=45),
    query_status: Optional[str] = Query(None, alias="status", max_length=20),
    period: str = Query("24h", pattern="^(24h|7d|30d)$"),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get paginated DNS query history from PostgreSQL."""
    result = query_analytics.get_stored_queries(
        db, page=page, page_size=page_size, period=period,
        domain=domain, client=client, query_status=query_status,
    )
    return StoredQueryResponse(
        queries=[StoredQueryEntry.model_validate(r) for r in result["rows"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/stored-stats", response_model=StoredStatsResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_stored_stats(
    request: Request, response: Response,
    period: str = Query("24h", pattern="^(24h|7d|30d)$"),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get aggregated DNS stats for a time period from PostgreSQL."""
    return StoredStatsResponse(**query_analytics.get_stored_stats(db, period=period))


@router.get("/stored-top-domains", response_model=StoredTopDomainsResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_stored_top_domains(
    request: Request, response: Response,
    count: int = Query(10, ge=1, le=100),
    period: str = Query("24h", pattern="^(24h|7d|30d)$"),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get top queried domains from PostgreSQL."""
    rows = query_analytics.get_stored_top_domains(db, count=count, period=period)
    return StoredTopDomainsResponse(
        top_domains=[StoredDomainEntry(domain=r.domain, count=r.cnt) for r in rows],
        period=period,
    )


@router.get("/stored-top-blocked", response_model=StoredTopBlockedResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_stored_top_blocked(
    request: Request, response: Response,
    count: int = Query(10, ge=1, le=100),
    period: str = Query("24h", pattern="^(24h|7d|30d)$"),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get top blocked domains from PostgreSQL."""
    rows = query_analytics.get_stored_top_blocked(db, count=count, period=period)
    return StoredTopBlockedResponse(
        top_blocked=[StoredDomainEntry(domain=r.domain, count=r.cnt) for r in rows],
        period=period,
    )


@router.get("/stored-top-clients", response_model=StoredTopClientsResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_stored_top_clients(
    request: Request, response: Response,
    count: int = Query(10, ge=1, le=100),
    period: str = Query("24h", pattern="^(24h|7d|30d)$"),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get top clients from PostgreSQL."""
    rows = query_analytics.get_stored_top_clients(db, count=count, period=period)
    return StoredTopClientsResponse(
        top_clients=[StoredClientEntry(client=r.client, count=r.cnt) for r in rows],
        period=period,
    )


@router.get("/stored-history", response_model=StoredHistoryResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_stored_history(
    request: Request, response: Response,
    period: str = Query("24h", pattern="^(24h|7d|30d)$"),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Get hourly query timeline from pre-aggregated stats."""
    rows = query_analytics.get_stored_history(db, period=period)
    return StoredHistoryResponse(
        history=[HourlyCountEntry.model_validate(r) for r in rows],
        period=period,
    )


# ── Query Collector Management ───────────────────────────────────────

@router.get("/query-collector/status", response_model=QueryCollectorStatusResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_collector_status(
    request: Request, response: Response,
    current_user: User = Depends(deps.get_current_admin),
):
    """Get DNS query collector status."""
    from app.services.pihole.query_collector import get_dns_query_collector
    data = get_dns_query_collector().get_status()
    return QueryCollectorStatusResponse(**data)


@router.put("/query-collector/config", response_model=QueryCollectorStatusResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_collector_config(
    request: Request, response: Response,
    body: QueryCollectorConfigUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_admin),
):
    """Update DNS query collector configuration."""
    update = body.model_dump(exclude_unset=True)
    query_analytics.update_collector_config(db, update)

    get_audit_logger_db().log_event(
        event_type="PIHOLE", user=current_user.username,
        action="pihole_collector_config_updated",
        details={"fields": list(update.keys())},
    )

    from app.services.pihole.query_collector import get_dns_query_collector
    data = get_dns_query_collector().get_status()
    return QueryCollectorStatusResponse(**data)
