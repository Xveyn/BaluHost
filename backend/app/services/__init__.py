"""
Services package.

This module provides backward-compatible re-exports for all services
that have been moved to subdirectories. Old import paths continue to work.
"""
import sys

# ============================================================
# Versioning services (moved to versioning/)
# ============================================================
from app.services.versioning.vcl import VCLService
from app.services.versioning.cache import VCLCache, VCLCacheSync, PendingVersion
from app.services.versioning.priority import VCLPriorityMode, VCLMonitor

# Import actual modules for aliasing
from app.services.versioning import vcl as _vcl
from app.services.versioning import cache as _vcl_cache
from app.services.versioning import priority as _vcl_priority

# Register backward-compatible module paths in sys.modules
sys.modules["app.services.vcl"] = _vcl
sys.modules["app.services.vcl_cache"] = _vcl_cache
sys.modules["app.services.vcl_priority"] = _vcl_priority

# ============================================================
# VPN services (moved to vpn/)
# ============================================================
from app.services.vpn.service import VPNService
from app.services.vpn.profiles import VPNService as VPNProfileService
from app.services.vpn.encryption import VPNEncryption

# Import actual modules for aliasing
from app.services.vpn import service as _vpn_service_module
from app.services.vpn import profiles as _vpn_profiles_module
from app.services.vpn import encryption as _vpn_encryption_module

# Register backward-compatible module paths in sys.modules
# Note: app.services.vpn is a package, so it's handled by its own __init__.py
sys.modules["app.services.vpn_service"] = _vpn_profiles_module
sys.modules["app.services.vpn_encryption"] = _vpn_encryption_module

# ============================================================
# Audit services (moved to audit/)
# ============================================================
from app.services.audit.logger import AuditLogger, get_audit_logger
from app.services.audit.logger_db import AuditLoggerDB, get_audit_logger_db
from app.services.audit.admin_db import AdminDBService

# Import actual modules for aliasing
from app.services.audit import logger as _audit_logger
from app.services.audit import logger_db as _audit_logger_db
from app.services.audit import admin_db as _admin_db

# Register backward-compatible module paths in sys.modules
sys.modules["app.services.audit_logger"] = _audit_logger
sys.modules["app.services.audit_logger_db"] = _audit_logger_db
sys.modules["app.services.admin_db"] = _admin_db

# ============================================================
# Hardware services (moved to hardware/)
# ============================================================
from app.services.hardware import raid as _raid
from app.services.hardware import smart as _smart
from app.services.hardware import sensors as _sensors

# Register backward-compatible module paths in sys.modules
sys.modules["app.services.raid"] = _raid
sys.modules["app.services.smart"] = _smart
sys.modules["app.services.sensors"] = _sensors

# ============================================================
# Backup services (moved to backup/)
# ============================================================
from app.services.backup import service as _backup_service
from app.services.backup import scheduler as _backup_scheduler

# Register backward-compatible module paths in sys.modules
sys.modules["app.services.backup"] = _backup_service
sys.modules["app.services.backup_scheduler"] = _backup_scheduler

# ============================================================
# Files services (moved to files/)
# ============================================================
from app.services.files import operations as _files
from app.services.files import metadata as _file_metadata
from app.services.files import metadata_db as _file_metadata_db
from app.services.files import shares as _shares

# Register backward-compatible module paths in sys.modules
sys.modules["app.services.files"] = _files
sys.modules["app.services.file_metadata"] = _file_metadata
sys.modules["app.services.file_metadata_db"] = _file_metadata_db
sys.modules["app.services.shares"] = _shares

# ============================================================
# Notifications services (moved to notifications/)
# ============================================================
from app.services.notifications import service as _notification_service
from app.services.notifications import scheduler as _notification_scheduler
from app.services.notifications import events as _event_emitter
from app.services.notifications import firebase as _firebase_service

# Register backward-compatible module paths in sys.modules
sys.modules["app.services.notification_service"] = _notification_service
sys.modules["app.services.notification_scheduler"] = _notification_scheduler
sys.modules["app.services.event_emitter"] = _event_emitter
sys.modules["app.services.firebase_service"] = _firebase_service

# ============================================================
# Power services (moved to power/)
# ============================================================
from app.services.power import manager as _power_manager
from app.services.power import monitor as _power_monitor
from app.services.power import presets as _power_preset_service
from app.services.power import energy as _energy_stats
from app.services.power import fan_control as _fan_control

# Register backward-compatible module paths in sys.modules
sys.modules["app.services.power_manager"] = _power_manager
sys.modules["app.services.power_monitor"] = _power_monitor
sys.modules["app.services.power_preset_service"] = _power_preset_service
sys.modules["app.services.energy_stats"] = _energy_stats
sys.modules["app.services.fan_control"] = _fan_control

# ============================================================
# Sync services (moved to sync/)
# ============================================================
from app.services.sync import file_sync as _file_sync
from app.services.sync import progressive as _progressive_sync
from app.services.sync import background as _sync_background
from app.services.sync import scheduler as _sync_scheduler

# Register backward-compatible module paths in sys.modules
sys.modules["app.services.file_sync"] = _file_sync
sys.modules["app.services.progressive_sync"] = _progressive_sync
sys.modules["app.services.sync_background"] = _sync_background
sys.modules["app.services.sync_scheduler"] = _sync_scheduler

__all__ = [
    # Versioning
    "VCLService",
    "VCLCache",
    "VCLCacheSync",
    "PendingVersion",
    "VCLPriorityMode",
    "VCLMonitor",
    # VPN
    "VPNService",
    "VPNProfileService",
    "VPNEncryption",
    # Audit
    "AuditLogger",
    "get_audit_logger",
    "AuditLoggerDB",
    "get_audit_logger_db",
    "AdminDBService",
]
