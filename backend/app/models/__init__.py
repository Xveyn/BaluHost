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
    PowerDynamicModeConfig,
)
from app.models.fans import FanConfig, FanSample, FanScheduleEntry
from app.models.scheduler_history import (
    SchedulerExecution,
    SchedulerConfig,
    SchedulerStatus,
    TriggerType,
)
from app.models.scheduler_state import SchedulerState
from app.models.webdav_state import WebdavState
from app.models.power_preset import PowerPreset
from app.models.plugin import InstalledPlugin
from app.models.benchmark import (
    DiskBenchmark,
    BenchmarkTestResult,
    BenchmarkStatus,
    BenchmarkProfile,
    BenchmarkTargetType,
)
from app.models.notification import (
    Notification,
    NotificationPreferences,
    NotificationType,
    NotificationCategory,
)
from app.models.update_history import (
    UpdateHistory,
    UpdateConfig,
    UpdateStatus,
    UpdateChannel,
)
from app.models.energy_price_config import EnergyPriceConfig
from app.models.ssd_cache import SsdCacheConfig
from app.models.cloud import CloudOAuthConfig, CloudConnection, CloudImportJob
from app.models.sleep import SleepConfig, SleepStateLog
from app.models.api_key import ApiKey
from app.models.desktop_pairing import DesktopPairingCode

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
    "PowerDynamicModeConfig",
    "FanConfig",
    "FanSample",
    "FanScheduleEntry",
    "SchedulerExecution",
    "SchedulerConfig",
    "SchedulerStatus",
    "TriggerType",
    "SchedulerState",
    "WebdavState",
    "PowerPreset",
    "InstalledPlugin",
    "DiskBenchmark",
    "BenchmarkTestResult",
    "BenchmarkStatus",
    "BenchmarkProfile",
    "BenchmarkTargetType",
    "Notification",
    "NotificationPreferences",
    "NotificationType",
    "NotificationCategory",
    "UpdateHistory",
    "UpdateConfig",
    "UpdateStatus",
    "UpdateChannel",
    "EnergyPriceConfig",
    "SsdCacheConfig",
    "CloudOAuthConfig",
    "CloudConnection",
    "CloudImportJob",
    "SleepConfig",
    "SleepStateLog",
    "ApiKey",
    "DesktopPairingCode",
]
