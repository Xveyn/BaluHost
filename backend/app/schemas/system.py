from datetime import datetime

from pydantic import BaseModel


class CPUStats(BaseModel):
    usage: float
    cores: int
    frequency_mhz: float | None = None  # Aktuelle CPU-Frequenz in MHz
    model: str | None = None  # CPU-Modellname


class MemoryStats(BaseModel):
    total: int
    used: int
    free: int
    speed_mts: int | None = None  # RAM-Geschwindigkeit in MT/s (Megatransfers/second)
    type: str | None = None  # RAM-Typ (z.B. "DDR4", "DDR5")


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
    dev_mode: bool = False


class StorageInfo(BaseModel):
    filesystem: str
    total: int
    used: int
    available: int
    use_percent: str
    mount_point: str


class DiskIOSample(BaseModel):
    """Single disk I/O measurement sample."""
    timestamp: int  # Unix timestamp in milliseconds
    readMbps: float  # Read speed in MB/s
    writeMbps: float  # Write speed in MB/s
    readIops: float  # Read operations per second
    writeIops: float  # Write operations per second
    avgResponseMs: float | None = None  # Durchschnittliche Antwortzeit (ms)
    activeTimePercent: float | None = None  # Anteil der Zeit mit aktiver I/O innerhalb des Intervalls


class DiskIOHistory(BaseModel):
    """Disk I/O history for a single disk."""
    diskName: str
    model: str | None = None  # Geräte/Modellname falls verfügbar
    samples: list[DiskIOSample]


class DiskIOResponse(BaseModel):
    """Complete disk I/O monitoring response."""
    disks: list[DiskIOHistory]
    interval: float  # Sampling interval in seconds


class AggregatedStorageInfo(BaseModel):
    """Aggregierte Speicherinformationen über alle Festplatten hinweg."""
    total_capacity: int  # Gesamtkapazität aller Festplatten (bei RAID: effektive Kapazität)
    total_used: int  # Gesamtnutzung über alle Festplatten
    total_available: int  # Verfügbarer Speicher
    use_percent: float  # Prozentsatz der Nutzung
    device_count: int  # Anzahl der erkannten Festplatten
    raid_effective: bool  # True wenn RAID-effektive Kapazität berechnet wurde


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
    capacity_bytes: int | None = None
    used_bytes: int | None = None  # Genutzte Bytes auf dieser Festplatte
    used_percent: float | None = None  # Prozentsatz der Nutzung
    mount_point: str | None = None  # Mount-Punkt, falls gemountet
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


class SystemHealthResponse(BaseModel):
    status: str
    system: SystemInfo
    smart: SmartStatusResponse | None = None
    raid: RaidStatusResponse | None = None
    disk_io: dict | None = None


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


class AvailableDisk(BaseModel):
    """Represents a disk that can be used for RAID or formatting."""
    name: str
    size_bytes: int
    model: str | None = None
    is_partitioned: bool = False
    partitions: list[str] = []
    in_raid: bool = False


class AvailableDisksResponse(BaseModel):
    disks: list[AvailableDisk]


class FormatDiskRequest(BaseModel):
    disk: str
    filesystem: str = "ext4"  # ext4, xfs, btrfs, etc.
    label: str | None = None


class CreateArrayRequest(BaseModel):
    name: str
    level: str  # raid0, raid1, raid5, raid6, raid10
    devices: list[str]
    spare_devices: list[str] = []


class DeleteArrayRequest(BaseModel):
    array: str
    force: bool = False
