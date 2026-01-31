"""Pydantic models for the Optical Drive Plugin.

Defines data structures for drive information, jobs, and API requests.
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class MediaType(str, Enum):
    """Types of optical media."""
    CD_AUDIO = "cd_audio"
    CD_DATA = "cd_data"
    DVD_DATA = "dvd_data"
    CD_BLANK = "cd_blank"
    DVD_BLANK = "dvd_blank"
    BD_DATA = "bd_data"
    BD_BLANK = "bd_blank"
    UNKNOWN = "unknown"
    NONE = "none"


class JobType(str, Enum):
    """Types of optical drive jobs."""
    READ_ISO = "read_iso"
    RIP_AUDIO = "rip_audio"
    RIP_TRACK = "rip_track"
    BURN_ISO = "burn_iso"
    BURN_AUDIO = "burn_audio"
    BLANK = "blank"


class JobStatus(str, Enum):
    """Status of an optical drive job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BlankMode(str, Enum):
    """Modes for blanking rewritable discs."""
    FAST = "fast"
    ALL = "all"


class AudioTrack(BaseModel):
    """Information about a single audio track."""
    number: int = Field(..., description="Track number (1-indexed)")
    duration_seconds: int = Field(..., description="Track duration in seconds")
    start_sector: int = Field(..., description="Starting sector on disc")
    end_sector: int = Field(..., description="Ending sector on disc")


class DriveInfo(BaseModel):
    """Information about an optical drive and its current media."""
    device: str = Field(..., description="Device path (e.g., /dev/sr0)")
    name: str = Field(..., description="Full drive name")
    vendor: str = Field(default="", description="Drive manufacturer")
    model: str = Field(default="", description="Drive model")
    can_write: bool = Field(default=False, description="Whether drive can burn discs")
    is_ready: bool = Field(default=False, description="Whether media is inserted and ready")
    media_type: Optional[MediaType] = Field(default=None, description="Type of inserted media")
    media_label: Optional[str] = Field(default=None, description="Volume label of data disc")
    total_tracks: Optional[int] = Field(default=None, description="Number of tracks on audio CD")
    tracks: List[AudioTrack] = Field(default_factory=list, description="Track list for audio CDs")
    total_size_bytes: Optional[int] = Field(default=None, description="Total size of media content")
    is_blank: Optional[bool] = Field(default=None, description="Whether media is blank/writable")
    is_rewritable: Optional[bool] = Field(default=None, description="Whether media is rewritable (RW)")


class BlankMediaInfo(BaseModel):
    """Information about blank writable media."""
    media_type: str = Field(..., description="Media type (CD-R, CD-RW, DVD-R, etc.)")
    capacity_bytes: int = Field(..., description="Capacity in bytes")
    capacity_mb: float = Field(..., description="Capacity in megabytes")
    is_rewritable: bool = Field(default=False, description="Whether media is rewritable")
    is_blank: bool = Field(default=True, description="Whether media is blank")
    write_speeds: List[int] = Field(default_factory=list, description="Available write speeds")


class OpticalJob(BaseModel):
    """A rip/burn job with progress tracking."""
    id: str = Field(..., description="Unique job identifier")
    device: str = Field(..., description="Device path")
    job_type: JobType = Field(..., description="Type of operation")
    status: JobStatus = Field(default=JobStatus.PENDING, description="Current status")
    progress_percent: float = Field(default=0.0, description="Progress percentage (0-100)")
    input_path: Optional[str] = Field(default=None, description="Source path for burn operations")
    output_path: Optional[str] = Field(default=None, description="Destination path for read operations")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(default=None)
    error: Optional[str] = Field(default=None, description="Error message if failed")
    current_track: Optional[int] = Field(default=None, description="Current track being processed")
    total_tracks: Optional[int] = Field(default=None, description="Total tracks to process")


# Request Models

class ReadIsoRequest(BaseModel):
    """Request to copy a data disc to an ISO file."""
    output_path: str = Field(..., description="Destination path for the ISO file")


class RipAudioRequest(BaseModel):
    """Request to rip an audio CD to WAV files."""
    output_dir: str = Field(..., description="Destination directory for WAV files")


class RipTrackRequest(BaseModel):
    """Request to rip a single audio track."""
    track_number: int = Field(..., ge=1, description="Track number to rip")
    output_path: str = Field(..., description="Destination path for the WAV file")


class BurnIsoRequest(BaseModel):
    """Request to burn an ISO image to disc."""
    iso_path: str = Field(..., description="Source ISO file path")
    speed: int = Field(default=0, ge=0, description="Burn speed (0 = auto)")


class BurnAudioRequest(BaseModel):
    """Request to burn WAV files as an audio CD."""
    wav_files: List[str] = Field(..., min_length=1, description="List of WAV file paths")
    speed: int = Field(default=0, ge=0, description="Burn speed (0 = auto)")


class BlankDiscRequest(BaseModel):
    """Request to blank a rewritable disc."""
    mode: BlankMode = Field(default=BlankMode.FAST, description="Blanking mode")


# Configuration Model

class OpticalDriveConfig(BaseModel):
    """Configuration for the Optical Drive plugin."""
    default_output_dir: str = Field(
        default="/storage/optical",
        description="Default output directory suggestion"
    )
    default_burn_speed: int = Field(
        default=0,
        ge=0,
        description="Default burn speed (0 = auto)"
    )
    auto_eject_after_operation: bool = Field(
        default=True,
        description="Automatically eject disc after operation completes"
    )
    scan_interval_seconds: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Interval for polling drive status"
    )
    max_concurrent_jobs: int = Field(
        default=2,
        ge=1,
        le=4,
        description="Maximum concurrent jobs per drive"
    )


# Response Models

class JobListResponse(BaseModel):
    """Response containing list of jobs."""
    jobs: List[OpticalJob]
    total: int


class DriveListResponse(BaseModel):
    """Response containing list of drives."""
    drives: List[DriveInfo]
    total: int


class OperationResponse(BaseModel):
    """Response for simple operations."""
    success: bool
    message: str
