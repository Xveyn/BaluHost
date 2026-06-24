"""Database models for BaluHost."""
from app.models.base import Base
from app.models.user import User
from app.models.file_metadata import FileMetadata
from app.models.audit_log import AuditLog
from app.models.file_share import FileShare
from app.models.backup import Backup
from app.models.vpn import VPNConfig, VPNClient
from app.models.mobile import MobileDevice
from app.models.rate_limit_config import RateLimitConfig
from app.models.vcl import FileVersion, VersionBlob, VCLSettings, VCLStats
from app.models.server_profile import ServerProfile
from app.models.vpn_profile import VPNProfile, VPNType
from app.models.refresh_token import RefreshToken
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
    PowerRuntimeState,
    PowerDemand,
    PowerCommand,
    PowerAuthorityConfig,
)
from app.models.gpu_power import (
    GpuPowerLog,
    GpuPowerConfigDb,
    GpuPowerRuntimeState,
    GpuPowerDemand,
    GpuPowerCommand,
)
from app.models.fans import FanConfig, FanSample, FanScheduleEntry, FanCurveProfile, TempSensorLabel, CompositeTempSensor
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
from app.models.plugin_storage import PluginStorage  # noqa: F401
from app.models.smart_device import SmartDevice, SmartDeviceSample
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
from app.models.ssd_file_cache import SSDCacheConfig
from app.models.cloud import CloudOAuthConfig, CloudConnection, CloudImportJob
from app.models.cloud_export import CloudExportJob
from app.models.sleep import SleepConfig, SleepStateLog, CoreUptimeWindow, PresenceSession
from app.models.system_lifecycle import SystemLifecycleEvent
from app.models.api_key import ApiKey
from app.models.desktop_pairing import DesktopPairingCode
from app.models.desktop_sync_folder import DesktopSyncFolder
from app.models.service_heartbeat import ServiceHeartbeat
from app.models.version_history import VersionHistory
from app.models.migration_job import MigrationJob
from app.models.pihole import PiholeConfig
from app.models.dns_queries import DnsQuery, DnsQueryHourlyStat, DnsQueryCollectorState
from app.models.ad_discovery import (
    AdDiscoveryPattern,
    AdDiscoveryReferenceList,
    AdDiscoverySuspect,
    AdDiscoveryCustomList,
    AdDiscoveryCustomListDomain,
    AdDiscoveryConfig,
)
from app.models.file_activity import FileActivity
from app.models.nfs_export import NfsExport
from app.models.fritzbox import FritzBoxConfig
from app.models.power_permissions import UserPowerPermission
from app.models.power_boost_rule import PowerBoostRule
from app.models.notification_routing import UserNotificationRouting
from app.models.sync_progress import ChunkedUpload, SyncBandwidthLimit, SyncSchedule, SelectiveSync
from app.models.sync_state import SyncState, SyncMetadata, SyncFileVersion
from app.models.status_bar import StatusBarPillConfig, StatusBarSettings
from app.models.auth_policy import AuthPolicy

__all__ = [
    "Base",
    "User",
    "AuthPolicy",
    "FileMetadata",
    "AuditLog",
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
    "PowerRuntimeState",
    "PowerDemand",
    "PowerCommand",
    "PowerAuthorityConfig",
    "GpuPowerLog",
    "GpuPowerConfigDb",
    "GpuPowerRuntimeState",
    "GpuPowerDemand",
    "GpuPowerCommand",
    "FanConfig",
    "FanSample",
    "FanScheduleEntry",
    "FanCurveProfile",
    "TempSensorLabel",
    "CompositeTempSensor",
    "SchedulerExecution",
    "SchedulerConfig",
    "SchedulerStatus",
    "TriggerType",
    "SchedulerState",
    "WebdavState",
    "PowerPreset",
    "InstalledPlugin",
    "PluginStorage",
    "SmartDevice",
    "SmartDeviceSample",
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
    "SSDCacheConfig",
    "CloudOAuthConfig",
    "CloudConnection",
    "CloudImportJob",
    "CloudExportJob",
    "SleepConfig",
    "SleepStateLog",
    "CoreUptimeWindow",
    "PresenceSession",
    "SystemLifecycleEvent",
    "ApiKey",
    "DesktopPairingCode",
    "DesktopSyncFolder",
    "ServiceHeartbeat",
    "VersionHistory",
    "MigrationJob",
    "PiholeConfig",
    "DnsQuery",
    "DnsQueryHourlyStat",
    "DnsQueryCollectorState",
    "AdDiscoveryPattern",
    "AdDiscoveryReferenceList",
    "AdDiscoverySuspect",
    "AdDiscoveryCustomList",
    "AdDiscoveryCustomListDomain",
    "AdDiscoveryConfig",
    "FileActivity",
    "NfsExport",
    "FritzBoxConfig",
    "UserPowerPermission",
    "PowerBoostRule",
    "UserNotificationRouting",
    "ChunkedUpload",
    "SyncBandwidthLimit",
    "SyncSchedule",
    "SelectiveSync",
    "SyncState",
    "SyncMetadata",
    "SyncFileVersion",
    "StatusBarPillConfig",
    "StatusBarSettings",
]
