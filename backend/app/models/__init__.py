"""Database models for BaluHost."""
from app.models.base import Base
from app.models.user import User
from app.models.file_metadata import FileMetadata
from app.models.audit_log import AuditLog
from app.models.share_link import ShareLink
from app.models.file_share import FileShare
from app.models.backup import Backup
from app.models.vpn import VPNConfig, VPNClient
from app.models.mobile import MobileDevice
from app.models.rate_limit_config import RateLimitConfig
from app.models.vcl import FileVersion, VersionBlob, VCLSettings, VCLStats
from app.models.server_profile import ServerProfile
from app.models.vpn_profile import VPNProfile, VPNType
from app.models.refresh_token import RefreshToken
from app.models.tapo_device import TapoDevice
from app.models.power_sample import PowerSample
from app.models.monitoring import (
    MetricType,
    CpuSample,
    MemorySample,
    NetworkSample,
    DiskIoSample,
    ProcessSample,
    MonitoringConfig,
)
from app.models.power import (
    PowerProfileLog,
    PowerDemandLog,
    PowerProfileConfig as PowerProfileConfigModel,
    PowerAutoScalingConfig,
)
from app.models.fans import FanConfig, FanSample
from app.models.scheduler_history import (
    SchedulerExecution,
    SchedulerConfig,
    SchedulerStatus,
    TriggerType,
)
from app.models.power_preset import PowerPreset
from app.models.plugin import InstalledPlugin
from app.models.benchmark import (
    DiskBenchmark,
    BenchmarkTestResult,
    BenchmarkStatus,
    BenchmarkProfile,
    BenchmarkTargetType,
)

__all__ = [
    "Base",
    "User",
    "FileMetadata",
    "AuditLog",
    "ShareLink",
    "FileShare",
    "Backup",
    "VPNConfig",
    "VPNClient",
    "MobileDevice",
    "RateLimitConfig",
    "FileVersion",
    "VersionBlob",
    "VCLSettings",
    "VCLStats",
    "ServerProfile",
    "VPNProfile",
    "VPNType",
    "RefreshToken",
    "TapoDevice",
    "PowerSample",
    "MetricType",
    "CpuSample",
    "MemorySample",
    "NetworkSample",
    "DiskIoSample",
    "ProcessSample",
    "MonitoringConfig",
    "PowerProfileLog",
    "PowerDemandLog",
    "PowerProfileConfigModel",
    "PowerAutoScalingConfig",
    "FanConfig",
    "FanSample",
    "SchedulerExecution",
    "SchedulerConfig",
    "SchedulerStatus",
    "TriggerType",
    "PowerPreset",
    "InstalledPlugin",
    "DiskBenchmark",
    "BenchmarkTestResult",
    "BenchmarkStatus",
    "BenchmarkProfile",
    "BenchmarkTargetType",
]
