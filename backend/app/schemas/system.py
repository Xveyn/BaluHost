from datetime import datetime

from pydantic import BaseModel


class CPUStats(BaseModel):
    usage: float
    cores: int


class MemoryStats(BaseModel):
    total: int
    used: int
    free: int


class DiskStats(BaseModel):
    total: int
    used: int
    free: int


class ProcessInfo(BaseModel):
    pid: int
    name: str
    cpu: float
    memory: float
    user: str


class SystemInfo(BaseModel):
    cpu: CPUStats
    memory: MemoryStats
    disk: DiskStats
    uptime: float


class StorageInfo(BaseModel):
    filesystem: str
    total: int
    used: int
    available: int
    use_percent: str
    mount_point: str


class CpuTelemetrySample(BaseModel):
    timestamp: int
    usage: float


class MemoryTelemetrySample(BaseModel):
    timestamp: int
    used: int
    total: int
    percent: float


class NetworkTelemetrySample(BaseModel):
    timestamp: int
    downloadMbps: float
    uploadMbps: float


class TelemetryHistoryResponse(BaseModel):
    cpu: list[CpuTelemetrySample]
    memory: list[MemoryTelemetrySample]
    network: list[NetworkTelemetrySample]


class ProcessListResponse(BaseModel):
    processes: list[ProcessInfo]


class SmartAttribute(BaseModel):
    id: int
    name: str
    value: int
    worst: int
    threshold: int
    raw: str
    status: str


class SmartDevice(BaseModel):
    name: str
    model: str
    serial: str
    temperature: int | None
    status: str
    attributes: list[SmartAttribute]


class SmartStatusResponse(BaseModel):
    checked_at: datetime
    devices: list[SmartDevice]


class QuotaStatus(BaseModel):
    limit_bytes: int | None
    used_bytes: int
    available_bytes: int | None
    percent_used: float | None


class RaidDevice(BaseModel):
    name: str
    state: str


class RaidArray(BaseModel):
    name: str
    level: str
    size_bytes: int
    status: str
    devices: list[RaidDevice]
    resync_progress: float | None = None
    bitmap: str | None = None
    sync_action: str | None = None


class RaidSpeedLimits(BaseModel):
    minimum: int | None = None
    maximum: int | None = None


class RaidStatusResponse(BaseModel):
    arrays: list[RaidArray]
    speed_limits: RaidSpeedLimits | None = None


class RaidSimulationRequest(BaseModel):
    array: str
    device: str | None = None


class RaidActionResponse(BaseModel):
    message: str


class RaidOptionsRequest(BaseModel):
    array: str
    enable_bitmap: bool | None = None
    add_spare: str | None = None
    remove_device: str | None = None
    write_mostly_device: str | None = None
    write_mostly: bool | None = None
    set_speed_limit_min: int | None = None
    set_speed_limit_max: int | None = None
    trigger_scrub: bool | None = None
