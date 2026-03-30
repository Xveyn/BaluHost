# Models

SQLAlchemy 2.0 ORM models. All models inherit from `Base` (declarative base in `base.py`) and are registered in `__init__.py` for Alembic auto-detection.

## Conventions

- Use `Mapped[T]` + `mapped_column()` (SQLAlchemy 2.0 typed style)
- Table names: plural snake_case (`users`, `audit_logs`, `fan_config`)
- Timestamps: `DateTime(timezone=True)` with `server_default=func.now()`
- Relationships: defined with `TYPE_CHECKING` guard for circular import avoidance
- Enums: Python `enum.Enum` subclasses stored as strings (e.g., `SchedulerStatus`, `BenchmarkStatus`)

## Model Groups

**Auth & Users**: `user.py`, `refresh_token.py`, `api_key.py`, `desktop_pairing.py`

**Files & Storage**: `file_metadata.py`, `file_share.py`, `file_activity.py`, `ssd_file_cache.py`, `migration_job.py`

**Monitoring & Metrics**: `monitoring.py` (CpuSample, MemorySample, NetworkSample, DiskIoSample, ProcessSample, MonitoringConfig), `service_heartbeat.py`

**Power & Hardware**: `power.py` (profiles, demands, auto-scaling), `power_preset.py`, `fans.py` (config, samples, schedules, curve profiles), `sleep.py`, `smart_device.py`

**Networking**: `vpn.py` (VPNConfig, VPNClient), `vpn_profile.py`, `mobile.py`, `server_profile.py`, `fritzbox.py`, `webdav_state.py`

**System Services**: `scheduler_history.py` (SchedulerExecution, SchedulerConfig), `scheduler_state.py`, `backup.py`, `audit_log.py`, `notification.py`, `update_history.py`, `version_history.py`

**Versioning**: `vcl.py` (FileVersion, VersionBlob, VCLSettings, VCLStats)

**Plugins & Integrations**: `plugin.py`, `pihole.py`, `dns_queries.py`, `ad_discovery.py`, `cloud.py`, `cloud_export.py`, `benchmark.py`, `energy_price_config.py`

**Desktop Sync**: `desktop_sync_folder.py`, `sync_progress.py`, `sync_state.py`

## Adding a Model

1. Create `models/my_model.py` with class inheriting from `Base`
2. Import and add to `__init__.py` (both import and `__all__`)
3. Create Alembic migration: `alembic revision --autogenerate -m "add my_model table"`
4. Add corresponding schema in `schemas/`
