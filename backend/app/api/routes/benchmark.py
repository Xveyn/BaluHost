"""
API routes for disk benchmarking.

Provides CrystalDiskMark-style disk performance benchmarks using fio.
"""

from typing import Optional
import math

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user
from app.core.database import get_db
from app.models.benchmark import BenchmarkProfile, BenchmarkStatus, BenchmarkTargetType
from app.schemas.benchmark import (
    AvailableDisksResponse,
    BenchmarkConfirmRequest,
    BenchmarkListResponse,
    BenchmarkPrepareRequest,
    BenchmarkPrepareResponse,
    BenchmarkProfileEnum,
    BenchmarkProgressResponse,
    BenchmarkResponse,
    BenchmarkStartRequest,
    BenchmarkStatusEnum,
    BenchmarkSummaryResults,
    BenchmarkTargetTypeEnum,
    ProfileListResponse,
    TestResultSchema,
)
from app.schemas.user import UserPublic
from app.services import benchmark_service

router = APIRouter(prefix="/benchmark", tags=["benchmark"])


def _benchmark_to_response(benchmark) -> BenchmarkResponse:
    """Convert DiskBenchmark model to BenchmarkResponse schema."""
    return BenchmarkResponse(
        id=benchmark.id,
        disk_name=benchmark.disk_name,
        disk_model=benchmark.disk_model,
        disk_size_bytes=benchmark.disk_size_bytes,
        profile=BenchmarkProfileEnum(benchmark.profile.value),
        target_type=BenchmarkTargetTypeEnum(benchmark.target_type.value),
        status=BenchmarkStatusEnum(benchmark.status.value),
        progress_percent=benchmark.progress_percent,
        current_test=benchmark.current_test,
        error_message=benchmark.error_message,
        created_at=benchmark.created_at,
        started_at=benchmark.started_at,
        completed_at=benchmark.completed_at,
        duration_seconds=benchmark.duration_seconds,
        summary=BenchmarkSummaryResults(
            seq_read_mbps=benchmark.seq_read_mbps,
            seq_write_mbps=benchmark.seq_write_mbps,
            seq_read_q1_mbps=benchmark.seq_read_q1_mbps,
            seq_write_q1_mbps=benchmark.seq_write_q1_mbps,
            rand_read_iops=benchmark.rand_read_iops,
            rand_write_iops=benchmark.rand_write_iops,
            rand_read_q1_iops=benchmark.rand_read_q1_iops,
            rand_write_q1_iops=benchmark.rand_write_q1_iops,
        ),
        test_results=[
            TestResultSchema.model_validate(result)
            for result in benchmark.test_results
        ],
    )


@router.get("/disks", response_model=AvailableDisksResponse)
async def get_available_disks(
    current_user: UserPublic = Depends(get_current_user),
) -> AvailableDisksResponse:
    """
    Get list of available disks for benchmarking.

    Returns disk information including size, model, and whether it can be benchmarked.
    """
    disks = benchmark_service.get_available_disks()
    return AvailableDisksResponse(disks=disks)


@router.get("/profiles", response_model=ProfileListResponse)
async def get_benchmark_profiles(
    current_user: UserPublic = Depends(get_current_user),
) -> ProfileListResponse:
    """
    Get available benchmark profiles.

    Returns profile configurations with test details and estimated durations.
    """
    profiles = benchmark_service.get_profile_configs()
    return ProfileListResponse(profiles=profiles)


@router.post("/start", response_model=BenchmarkResponse)
async def start_benchmark(
    request: BenchmarkStartRequest,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user),
) -> BenchmarkResponse:
    """
    Start a new disk benchmark (test file mode).

    Creates a temporary test file on the disk and runs performance tests.
    This is the safe mode that doesn't risk data loss.
    """
    try:
        benchmark = await benchmark_service.start_benchmark(
            db=db,
            disk_name=request.disk_name,
            profile=BenchmarkProfile(request.profile.value),
            target_type=BenchmarkTargetType.TEST_FILE,
            user_id=current_user.id,
            test_directory=request.test_directory,
        )
        return _benchmark_to_response(benchmark)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start benchmark: {str(e)}",
        )


@router.post("/prepare", response_model=BenchmarkPrepareResponse)
async def prepare_raw_benchmark(
    request: BenchmarkPrepareRequest,
    db: Session = Depends(get_db),
    current_admin: UserPublic = Depends(get_current_admin),
) -> BenchmarkPrepareResponse:
    """
    Prepare a raw device benchmark (admin only).

    Returns a confirmation token that must be used to actually start the benchmark.
    This is required for raw device benchmarks which can potentially damage data.
    """
    # Validate disk exists and is not system disk
    disks = benchmark_service.get_available_disks()
    disk_info = next((d for d in disks if d.name == request.disk_name), None)

    if disk_info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Disk '{request.disk_name}' not found",
        )

    if disk_info.is_system_disk:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot run raw device benchmark on system disk",
        )

    if disk_info.is_raid_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot run raw device benchmark on RAID member disk",
        )

    # Generate confirmation token
    token, expires_at = benchmark_service.generate_confirmation_token(
        request.disk_name, request.profile.value
    )

    return BenchmarkPrepareResponse(
        confirmation_token=token,
        expires_at=expires_at,
        disk_name=request.disk_name,
        disk_model=disk_info.model,
        disk_size_bytes=disk_info.size_bytes,
        warning_message=(
            f"WARNING: This will write directly to /dev/{request.disk_name}. "
            "Any existing data on this device will be destroyed. "
            "Only proceed if you are absolutely certain this is the correct disk."
        ),
        profile=request.profile,
    )


@router.post("/start-confirmed", response_model=BenchmarkResponse)
async def start_confirmed_benchmark(
    request: BenchmarkConfirmRequest,
    db: Session = Depends(get_db),
    current_admin: UserPublic = Depends(get_current_admin),
) -> BenchmarkResponse:
    """
    Start a raw device benchmark after confirmation (admin only).

    Requires a valid confirmation token from the /prepare endpoint.
    """
    # Validate confirmation token
    if not benchmark_service.validate_confirmation_token(
        request.confirmation_token, request.disk_name, request.profile.value
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired confirmation token",
        )

    try:
        benchmark = await benchmark_service.start_benchmark(
            db=db,
            disk_name=request.disk_name,
            profile=BenchmarkProfile(request.profile.value),
            target_type=BenchmarkTargetType.RAW_DEVICE,
            user_id=current_admin.id,
        )
        return _benchmark_to_response(benchmark)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start benchmark: {str(e)}",
        )


@router.get("/{benchmark_id}", response_model=BenchmarkResponse)
async def get_benchmark(
    benchmark_id: int,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user),
) -> BenchmarkResponse:
    """
    Get a benchmark by ID.

    Returns full benchmark details including all test results.
    """
    benchmark = benchmark_service.get_benchmark(benchmark_id, db)
    if benchmark is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Benchmark {benchmark_id} not found",
        )
    return _benchmark_to_response(benchmark)


@router.get("/{benchmark_id}/progress", response_model=BenchmarkProgressResponse)
async def get_benchmark_progress(
    benchmark_id: int,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user),
) -> BenchmarkProgressResponse:
    """
    Get progress of a running benchmark.

    Returns lightweight progress information for polling during benchmark runs.
    """
    benchmark = benchmark_service.get_benchmark(benchmark_id, db)
    if benchmark is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Benchmark {benchmark_id} not found",
        )

    # Calculate estimated remaining time
    estimated_remaining = None
    if (
        benchmark.status == BenchmarkStatus.RUNNING
        and benchmark.progress_percent > 0
        and benchmark.started_at
    ):
        from datetime import datetime, timezone

        elapsed = (datetime.now(timezone.utc) - benchmark.started_at).total_seconds()
        if benchmark.progress_percent > 0:
            total_estimated = elapsed / (benchmark.progress_percent / 100)
            estimated_remaining = int(total_estimated - elapsed)

    return BenchmarkProgressResponse(
        id=benchmark.id,
        status=BenchmarkStatusEnum(benchmark.status.value),
        progress_percent=benchmark.progress_percent,
        current_test=benchmark.current_test,
        started_at=benchmark.started_at,
        estimated_remaining_seconds=estimated_remaining,
    )


@router.post("/{benchmark_id}/cancel")
async def cancel_benchmark(
    benchmark_id: int,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user),
) -> dict:
    """
    Cancel a running benchmark.

    The benchmark will be stopped and marked as cancelled.
    """
    benchmark = benchmark_service.get_benchmark(benchmark_id, db)
    if benchmark is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Benchmark {benchmark_id} not found",
        )

    # Check ownership (only owner or admin can cancel)
    if benchmark.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only cancel your own benchmarks",
        )

    if benchmark.status != BenchmarkStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel benchmark with status {benchmark.status.value}",
        )

    success = benchmark_service.cancel_benchmark(benchmark_id, db)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel benchmark",
        )

    return {"message": "Benchmark cancellation requested", "benchmark_id": benchmark_id}


@router.post("/{benchmark_id}/mark-failed")
async def mark_benchmark_failed(
    benchmark_id: int,
    db: Session = Depends(get_db),
    current_admin: UserPublic = Depends(get_current_admin),
) -> dict:
    """
    Manually mark a stuck benchmark as failed (admin only).

    Use this when a benchmark is stuck in running/pending status after a server
    restart or other failure where automatic recovery didn't trigger.
    """
    benchmark = benchmark_service.get_benchmark(benchmark_id, db)
    if benchmark is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Benchmark {benchmark_id} not found",
        )

    if benchmark.status not in (BenchmarkStatus.RUNNING, BenchmarkStatus.PENDING):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot mark benchmark as failed: current status is {benchmark.status.value}",
        )

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    benchmark.status = BenchmarkStatus.FAILED
    benchmark.error_message = "Manually marked as failed by administrator"
    benchmark.completed_at = now
    if benchmark.started_at:
        benchmark.duration_seconds = (now - benchmark.started_at).total_seconds()
    db.commit()

    return {"message": "Benchmark marked as failed", "benchmark_id": benchmark_id}


@router.get("/", response_model=BenchmarkListResponse)
async def list_benchmarks(
    page: int = 1,
    page_size: int = 10,
    disk_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user),
) -> BenchmarkListResponse:
    """
    Get paginated list of benchmarks.

    Returns benchmark history with optional filtering by disk name.
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 10
    if page_size > 100:
        page_size = 100

    benchmarks, total = benchmark_service.get_benchmark_history(
        db=db,
        page=page,
        page_size=page_size,
        disk_name=disk_name,
    )

    return BenchmarkListResponse(
        items=[_benchmark_to_response(b) for b in benchmarks],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 1,
    )
