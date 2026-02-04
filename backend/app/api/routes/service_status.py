"""
Admin API routes for service status and debugging.

Provides endpoints for monitoring background services, checking system
dependencies, and accessing application metrics for debugging.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from starlette import status

from app.api import deps
from app.schemas.service_status import (
    ServiceStatusResponse,
    DependencyStatusResponse,
    ApplicationMetricsResponse,
    AdminDebugResponse,
    ServiceRestartRequest,
    ServiceRestartResponse,
    ServiceStopRequest,
    ServiceStopResponse,
    ServiceStartRequest,
    ServiceStartResponse,
)
from app.services.service_status import get_service_status_collector

router = APIRouter()


@router.get(
    "/admin/services",
    response_model=List[ServiceStatusResponse],
    tags=["admin"],
    summary="Get all service statuses"
)
async def get_all_services(
    current_user=Depends(deps.get_current_admin)
) -> List[ServiceStatusResponse]:
    """
    Get status information for all registered background services.

    Admin only. Returns state, uptime, sample counts, and error information
    for each service.
    """
    collector = get_service_status_collector()
    return collector.get_all_services()


@router.get(
    "/admin/services/{service_name}",
    response_model=ServiceStatusResponse,
    tags=["admin"],
    summary="Get single service status"
)
async def get_service(
    service_name: str,
    current_user=Depends(deps.get_current_admin)
) -> ServiceStatusResponse:
    """
    Get detailed status for a specific service.

    Admin only.
    """
    collector = get_service_status_collector()
    service = collector.get_service(service_name)

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{service_name}' not found"
        )

    return service


@router.post(
    "/admin/services/{service_name}/restart",
    response_model=ServiceRestartResponse,
    tags=["admin"],
    summary="Restart a service"
)
async def restart_service(
    service_name: str,
    request: ServiceRestartRequest = None,
    current_user=Depends(deps.get_current_admin)
) -> ServiceRestartResponse:
    """
    Restart a specific background service.

    Admin only. Performs a graceful stop and start of the service.
    Not all services support restart.
    """
    from app.services.audit_logger_db import get_audit_logger_db

    collector = get_service_status_collector()

    # Check if service exists
    service = collector.get_service(service_name)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{service_name}' not found"
        )

    # Perform restart
    force = request.force if request else False
    result = await collector.restart_service(service_name, force=force)

    # Audit log
    audit = get_audit_logger_db()
    audit.log_event(
        event_type="ADMIN",
        user=current_user.username,
        action="service_restart",
        resource=service_name,
        details={
            "force": force,
            "success": result.success,
            "previous_state": result.previous_state.value,
            "current_state": result.current_state.value,
        },
        success=result.success,
        error_message=result.message if not result.success else None,
    )

    return result


@router.post(
    "/admin/services/{service_name}/stop",
    response_model=ServiceStopResponse,
    tags=["admin"],
    summary="Stop a service"
)
async def stop_service(
    service_name: str,
    request: ServiceStopRequest = None,
    current_user=Depends(deps.get_current_admin)
) -> ServiceStopResponse:
    """
    Stop a specific background service.

    Admin only. Performs a graceful shutdown of the service.
    Not all services support stop.
    """
    from app.services.audit_logger_db import get_audit_logger_db

    collector = get_service_status_collector()

    # Check if service exists
    service = collector.get_service(service_name)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{service_name}' not found"
        )

    # Perform stop
    force = request.force if request else False
    result = await collector.stop_service(service_name, force=force)

    # Audit log
    audit = get_audit_logger_db()
    audit.log_event(
        event_type="ADMIN",
        user=current_user.username,
        action="service_stop",
        resource=service_name,
        details={
            "force": force,
            "success": result.success,
            "previous_state": result.previous_state.value,
            "current_state": result.current_state.value,
        },
        success=result.success,
        error_message=result.message if not result.success else None,
    )

    return result


@router.post(
    "/admin/services/{service_name}/start",
    response_model=ServiceStartResponse,
    tags=["admin"],
    summary="Start a service"
)
async def start_service(
    service_name: str,
    request: ServiceStartRequest = None,
    current_user=Depends(deps.get_current_admin)
) -> ServiceStartResponse:
    """
    Start a specific background service.

    Admin only. Starts the service if it is currently stopped.
    Not all services support start.
    """
    from app.services.audit_logger_db import get_audit_logger_db

    collector = get_service_status_collector()

    # Check if service exists
    service = collector.get_service(service_name)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{service_name}' not found"
        )

    # Perform start
    force = request.force if request else False
    result = await collector.start_service(service_name, force=force)

    # Audit log
    audit = get_audit_logger_db()
    audit.log_event(
        event_type="ADMIN",
        user=current_user.username,
        action="service_start",
        resource=service_name,
        details={
            "force": force,
            "success": result.success,
            "previous_state": result.previous_state.value,
            "current_state": result.current_state.value,
        },
        success=result.success,
        error_message=result.message if not result.success else None,
    )

    return result


@router.get(
    "/admin/dependencies",
    response_model=List[DependencyStatusResponse],
    tags=["admin"],
    summary="Get system dependencies"
)
async def get_dependencies(
    current_user=Depends(deps.get_current_admin)
) -> List[DependencyStatusResponse]:
    """
    Check availability of system tools and dependencies.

    Admin only. Checks for smartctl, mdadm, wg, ipmitool, hwmon, etc.
    """
    collector = get_service_status_collector()
    return collector.get_dependencies()


@router.get(
    "/admin/metrics",
    response_model=ApplicationMetricsResponse,
    tags=["admin"],
    summary="Get application metrics"
)
async def get_metrics(
    current_user=Depends(deps.get_current_admin)
) -> ApplicationMetricsResponse:
    """
    Get application-level metrics for debugging.

    Admin only. Returns server uptime, error counts, memory usage,
    DB pool status, and cache statistics.
    """
    collector = get_service_status_collector()
    return collector.get_app_metrics()


@router.get(
    "/admin/debug",
    response_model=AdminDebugResponse,
    tags=["admin"],
    summary="Get combined debug snapshot"
)
async def get_debug_snapshot(
    current_user=Depends(deps.get_current_user)
) -> AdminDebugResponse:
    """
    Get a complete debug snapshot combining all status information.

    Available to all authenticated users (read-only).
    Returns services, dependencies, and metrics in a single response.
    """
    collector = get_service_status_collector()
    return collector.get_debug_snapshot()
