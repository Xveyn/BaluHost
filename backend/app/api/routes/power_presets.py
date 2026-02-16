"""
Power Presets API Routes.

Provides endpoints for managing power presets that define
CPU clock speeds for each service power property level.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api import deps
from app.core.rate_limiter import user_limiter, get_limit
from app.schemas.power import (
    PowerPresetCreate,
    PowerPresetUpdate,
    PowerPresetResponse,
    PowerPresetListResponse,
    PowerPresetSummary,
    ActivatePresetResponse,
)
from app.schemas.user import UserPublic
from app.services.power_preset_service import get_preset_service

router = APIRouter(prefix="/power/presets", tags=["power-presets"])


@router.get("/", response_model=PowerPresetListResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def list_presets(
    request: Request, response: Response,
    _: UserPublic = Depends(deps.get_current_user)
) -> PowerPresetListResponse:
    """
    List all power presets.

    Returns both system presets (Energy Saver, Balanced, Performance)
    and any custom presets created by admins.
    """
    service = get_preset_service()
    presets = await service.list_presets()
    active = await service.get_active_preset()

    preset_responses = [
        PowerPresetResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            is_system_preset=p.is_system_preset,
            is_active=p.is_active,
            base_clock_mhz=p.base_clock_mhz,
            idle_clock_mhz=p.idle_clock_mhz,
            low_clock_mhz=p.low_clock_mhz,
            medium_clock_mhz=p.medium_clock_mhz,
            surge_clock_mhz=p.surge_clock_mhz,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in presets
    ]

    active_response = None
    if active:
        active_response = PowerPresetResponse(
            id=active.id,
            name=active.name,
            description=active.description,
            is_system_preset=active.is_system_preset,
            is_active=active.is_active,
            base_clock_mhz=active.base_clock_mhz,
            idle_clock_mhz=active.idle_clock_mhz,
            low_clock_mhz=active.low_clock_mhz,
            medium_clock_mhz=active.medium_clock_mhz,
            surge_clock_mhz=active.surge_clock_mhz,
            created_at=active.created_at,
            updated_at=active.updated_at,
        )

    return PowerPresetListResponse(
        presets=preset_responses,
        active_preset=active_response
    )


@router.get("/active", response_model=PowerPresetResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_active_preset(
    request: Request, response: Response,
    _: UserPublic = Depends(deps.get_current_user)
) -> PowerPresetResponse:
    """
    Get the currently active power preset.
    """
    service = get_preset_service()
    preset = await service.get_active_preset()

    if preset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active preset found"
        )

    return PowerPresetResponse(
        id=preset.id,
        name=preset.name,
        description=preset.description,
        is_system_preset=preset.is_system_preset,
        is_active=preset.is_active,
        base_clock_mhz=preset.base_clock_mhz,
        idle_clock_mhz=preset.idle_clock_mhz,
        low_clock_mhz=preset.low_clock_mhz,
        medium_clock_mhz=preset.medium_clock_mhz,
        surge_clock_mhz=preset.surge_clock_mhz,
        created_at=preset.created_at,
        updated_at=preset.updated_at,
    )


@router.get("/{preset_id}", response_model=PowerPresetResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_preset(
    request: Request, response: Response,
    preset_id: int,
    _: UserPublic = Depends(deps.get_current_user)
) -> PowerPresetResponse:
    """
    Get a specific preset by ID.
    """
    service = get_preset_service()
    preset = await service.get_preset_by_id(preset_id)

    if preset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preset not found: {preset_id}"
        )

    return PowerPresetResponse(
        id=preset.id,
        name=preset.name,
        description=preset.description,
        is_system_preset=preset.is_system_preset,
        is_active=preset.is_active,
        base_clock_mhz=preset.base_clock_mhz,
        idle_clock_mhz=preset.idle_clock_mhz,
        low_clock_mhz=preset.low_clock_mhz,
        medium_clock_mhz=preset.medium_clock_mhz,
        surge_clock_mhz=preset.surge_clock_mhz,
        created_at=preset.created_at,
        updated_at=preset.updated_at,
    )


@router.post("/{preset_id}/activate", response_model=ActivatePresetResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def activate_preset(
    request: Request, response: Response,
    preset_id: int,
    user: UserPublic = Depends(deps.get_current_admin)
) -> ActivatePresetResponse:
    """
    Activate a power preset (admin only).

    The selected preset will define the CPU clock speeds used for
    each service power property level.
    """
    service = get_preset_service()

    # Get current active preset
    current = await service.get_active_preset()
    previous_summary = None
    if current:
        previous_summary = PowerPresetSummary(
            id=current.id,
            name=current.name,
            is_system_preset=current.is_system_preset,
            is_active=current.is_active
        )

    # Activate the new preset
    success = await service.activate_preset(preset_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preset not found: {preset_id}"
        )

    # Get the newly activated preset
    new_preset = await service.get_preset_by_id(preset_id)
    new_summary = PowerPresetSummary(
        id=new_preset.id,
        name=new_preset.name,
        is_system_preset=new_preset.is_system_preset,
        is_active=True
    )

    return ActivatePresetResponse(
        success=True,
        message=f"Activated preset: {new_preset.name}",
        previous_preset=previous_summary,
        new_preset=new_summary
    )


@router.post("/", response_model=PowerPresetResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def create_preset(
    request: Request, response: Response,
    data: PowerPresetCreate,
    user: UserPublic = Depends(deps.get_current_admin)
) -> PowerPresetResponse:
    """
    Create a new custom power preset (admin only).

    Custom presets can be modified and deleted. They are useful
    for creating specialized configurations for specific workloads.
    """
    service = get_preset_service()
    preset = await service.create_preset(data)

    if preset is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not create preset. Name '{data.name}' may already exist."
        )

    return PowerPresetResponse(
        id=preset.id,
        name=preset.name,
        description=preset.description,
        is_system_preset=preset.is_system_preset,
        is_active=preset.is_active,
        base_clock_mhz=preset.base_clock_mhz,
        idle_clock_mhz=preset.idle_clock_mhz,
        low_clock_mhz=preset.low_clock_mhz,
        medium_clock_mhz=preset.medium_clock_mhz,
        surge_clock_mhz=preset.surge_clock_mhz,
        created_at=preset.created_at,
        updated_at=preset.updated_at,
    )


@router.put("/{preset_id}", response_model=PowerPresetResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_preset(
    request: Request, response: Response,
    preset_id: int,
    data: PowerPresetUpdate,
    user: UserPublic = Depends(deps.get_current_admin)
) -> PowerPresetResponse:
    """
    Update an existing power preset (admin only).

    Note: System presets can only have clock values updated,
    not their name or description.
    """
    service = get_preset_service()
    preset = await service.update_preset(preset_id, data)

    if preset is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not update preset {preset_id}. It may not exist or name may be duplicate."
        )

    return PowerPresetResponse(
        id=preset.id,
        name=preset.name,
        description=preset.description,
        is_system_preset=preset.is_system_preset,
        is_active=preset.is_active,
        base_clock_mhz=preset.base_clock_mhz,
        idle_clock_mhz=preset.idle_clock_mhz,
        low_clock_mhz=preset.low_clock_mhz,
        medium_clock_mhz=preset.medium_clock_mhz,
        surge_clock_mhz=preset.surge_clock_mhz,
        created_at=preset.created_at,
        updated_at=preset.updated_at,
    )


@router.delete("/{preset_id}")
@user_limiter.limit(get_limit("admin_operations"))
async def delete_preset(
    request: Request, response: Response,
    preset_id: int,
    user: UserPublic = Depends(deps.get_current_admin)
) -> dict:
    """
    Delete a custom power preset (admin only).

    System presets cannot be deleted.
    Active presets cannot be deleted.
    """
    service = get_preset_service()

    # Check if it's a system preset
    preset = await service.get_preset_by_id(preset_id)
    if preset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preset not found: {preset_id}"
        )

    if preset.is_system_preset:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete system presets"
        )

    if preset.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete active preset. Activate another preset first."
        )

    success = await service.delete_preset(preset_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete preset"
        )

    return {"success": True, "message": f"Deleted preset: {preset.name}"}
