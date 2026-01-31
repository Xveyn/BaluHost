"""Optical Drive Plugin for BaluHost.

Provides functionality for:
- Detecting optical drives (CD/DVD/Blu-ray)
- Reading data discs (ISO copy)
- Ripping audio CDs (WAV format)
- Burning data discs (ISO to disc)
- Burning audio CDs (WAV to disc)
- Blanking rewritable media
- Eject/load control
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter

from app.plugins.base import (
    PluginBase,
    PluginMetadata,
    PluginNavItem,
    PluginUIManifest,
)

from .models import OpticalDriveConfig
from .service import OpticalDriveService, get_optical_drive_service


class OpticalDrivePlugin(PluginBase):
    """Optical Drive plugin implementation."""

    _router: Optional[APIRouter] = None

    def __init__(self):
        self._service: Optional[OpticalDriveService] = None

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="optical_drive",
            version="1.0.0",
            display_name="Optical Drive",
            description="Read, rip, and burn CDs/DVDs with full disc management",
            author="BaluHost Team",
            category="storage",
            required_permissions=[
                "system:execute",  # For shell commands (cdparanoia, wodim, etc.)
                "system:info",     # For drive detection
                "file:write",      # For output files (ripped tracks, ISOs)
            ],
            homepage="https://github.com/baluhost/optical-drive",
        )

    def get_router(self) -> APIRouter:
        """Create and return the router with all routes.

        Routes are created lazily to avoid circular imports during plugin loading.
        """
        if self._router is not None:
            return self._router

        # Import dependencies here to avoid circular imports at module load time
        from fastapi import Depends, HTTPException, status
        from app.api.deps import get_current_user

        from .models import (
            BlankDiscRequest,
            BlankMediaInfo,
            BurnAudioRequest,
            BurnIsoRequest,
            DriveInfo,
            DriveListResponse,
            JobListResponse,
            OperationResponse,
            OpticalJob,
            ReadIsoRequest,
            RipAudioRequest,
            RipTrackRequest,
        )

        router = APIRouter()

        def get_service() -> OpticalDriveService:
            """Dependency to get the optical drive service."""
            return get_optical_drive_service()

        # === Drive Management Endpoints ===

        @router.get("/drives", response_model=DriveListResponse)
        async def list_drives(
            current_user=Depends(get_current_user),
            service: OpticalDriveService = Depends(get_service),
        ) -> DriveListResponse:
            """List all optical drives on the system."""
            drives = await service.list_drives()
            return DriveListResponse(drives=drives, total=len(drives))

        @router.get("/drives/{device:path}/info", response_model=DriveInfo)
        async def get_drive_info(
            device: str,
            current_user=Depends(get_current_user),
            service: OpticalDriveService = Depends(get_service),
        ) -> DriveInfo:
            """Get detailed information about a specific drive."""
            device = f"/dev/{device}" if not device.startswith("/dev/") else device
            try:
                return await service.get_drive_info(device)
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        @router.post("/drives/{device:path}/eject", response_model=OperationResponse)
        async def eject_drive(
            device: str,
            current_user=Depends(get_current_user),
            service: OpticalDriveService = Depends(get_service),
        ) -> OperationResponse:
            """Eject/open the drive tray."""
            device = f"/dev/{device}" if not device.startswith("/dev/") else device
            try:
                success = await service.eject(device)
                return OperationResponse(
                    success=success,
                    message="Tray ejected" if success else "Eject failed"
                )
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        @router.post("/drives/{device:path}/close", response_model=OperationResponse)
        async def close_tray(
            device: str,
            current_user=Depends(get_current_user),
            service: OpticalDriveService = Depends(get_service),
        ) -> OperationResponse:
            """Close the drive tray."""
            device = f"/dev/{device}" if not device.startswith("/dev/") else device
            try:
                success = await service.close_tray(device)
                return OperationResponse(
                    success=success,
                    message="Tray closed" if success else "Close failed"
                )
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        @router.get("/drives/{device:path}/blank-info", response_model=Optional[BlankMediaInfo])
        async def get_blank_media_info(
            device: str,
            current_user=Depends(get_current_user),
            service: OpticalDriveService = Depends(get_service),
        ) -> Optional[BlankMediaInfo]:
            """Get information about blank writable media."""
            device = f"/dev/{device}" if not device.startswith("/dev/") else device
            try:
                return await service.get_blank_media_info(device)
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        # === Read/Rip Endpoints ===

        @router.post("/drives/{device:path}/read/iso", response_model=OpticalJob)
        async def read_iso(
            device: str,
            request: ReadIsoRequest,
            current_user=Depends(get_current_user),
            service: OpticalDriveService = Depends(get_service),
        ) -> OpticalJob:
            """Copy a data disc to an ISO file."""
            device = f"/dev/{device}" if not device.startswith("/dev/") else device
            try:
                return await service.read_iso(device, request.output_path)
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        @router.post("/drives/{device:path}/read/audio", response_model=OpticalJob)
        async def rip_audio_cd(
            device: str,
            request: RipAudioRequest,
            current_user=Depends(get_current_user),
            service: OpticalDriveService = Depends(get_service),
        ) -> OpticalJob:
            """Rip all tracks from an audio CD to WAV files."""
            device = f"/dev/{device}" if not device.startswith("/dev/") else device
            try:
                return await service.rip_audio_cd(device, request.output_dir)
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        @router.post("/drives/{device:path}/read/audio/{track_number}", response_model=OpticalJob)
        async def rip_audio_track(
            device: str,
            track_number: int,
            request: RipTrackRequest,
            current_user=Depends(get_current_user),
            service: OpticalDriveService = Depends(get_service),
        ) -> OpticalJob:
            """Rip a single audio track to a WAV file."""
            device = f"/dev/{device}" if not device.startswith("/dev/") else device
            try:
                return await service.rip_audio_track(device, track_number, request.output_path)
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        # === Burn Endpoints ===

        @router.post("/drives/{device:path}/burn/iso", response_model=OpticalJob)
        async def burn_iso(
            device: str,
            request: BurnIsoRequest,
            current_user=Depends(get_current_user),
            service: OpticalDriveService = Depends(get_service),
        ) -> OpticalJob:
            """Burn an ISO image to disc."""
            device = f"/dev/{device}" if not device.startswith("/dev/") else device
            try:
                return await service.burn_iso(device, request.iso_path, request.speed)
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        @router.post("/drives/{device:path}/burn/audio", response_model=OpticalJob)
        async def burn_audio_cd(
            device: str,
            request: BurnAudioRequest,
            current_user=Depends(get_current_user),
            service: OpticalDriveService = Depends(get_service),
        ) -> OpticalJob:
            """Burn WAV files as an audio CD."""
            device = f"/dev/{device}" if not device.startswith("/dev/") else device
            try:
                return await service.burn_audio_cd(device, request.wav_files, request.speed)
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        @router.post("/drives/{device:path}/blank", response_model=OpticalJob)
        async def blank_disc(
            device: str,
            request: BlankDiscRequest,
            current_user=Depends(get_current_user),
            service: OpticalDriveService = Depends(get_service),
        ) -> OpticalJob:
            """Blank a rewritable disc."""
            device = f"/dev/{device}" if not device.startswith("/dev/") else device
            try:
                return await service.blank_disc(device, request.mode)
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        # === Job Management Endpoints ===

        @router.get("/jobs", response_model=JobListResponse)
        async def list_jobs(
            current_user=Depends(get_current_user),
            service: OpticalDriveService = Depends(get_service),
        ) -> JobListResponse:
            """Get all active and recent jobs."""
            jobs = service.get_jobs()
            return JobListResponse(jobs=jobs, total=len(jobs))

        @router.get("/jobs/{job_id}", response_model=OpticalJob)
        async def get_job(
            job_id: str,
            current_user=Depends(get_current_user),
            service: OpticalDriveService = Depends(get_service),
        ) -> OpticalJob:
            """Get a specific job by ID."""
            job = service.get_job(job_id)
            if job is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Job not found: {job_id}"
                )
            return job

        @router.post("/jobs/{job_id}/cancel", response_model=OperationResponse)
        async def cancel_job(
            job_id: str,
            current_user=Depends(get_current_user),
            service: OpticalDriveService = Depends(get_service),
        ) -> OperationResponse:
            """Cancel a running job."""
            success = await service.cancel_job(job_id)
            if success:
                return OperationResponse(success=True, message="Job cancelled")
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Job not found or not running"
                )

        self._router = router
        return router

    async def on_startup(self) -> None:
        """Initialize the plugin."""
        self._service = get_optical_drive_service()

    async def on_shutdown(self) -> None:
        """Cleanup on shutdown."""
        if self._service:
            await self._service.cleanup()

    def get_ui_manifest(self) -> PluginUIManifest:
        return PluginUIManifest(
            enabled=True,
            nav_items=[
                PluginNavItem(
                    path="drives",
                    label="Optical Drives",
                    icon="disc",
                    admin_only=False,
                    order=60,
                )
            ],
            bundle_path="bundle.js",
            dashboard_widgets=["OpticalDriveWidget"],
        )

    def get_config_schema(self) -> type:
        return OpticalDriveConfig

    def get_default_config(self) -> Dict[str, Any]:
        return OpticalDriveConfig().model_dump()
