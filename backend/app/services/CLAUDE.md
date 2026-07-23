# Services

Business logic layer. Routes delegate to services — services contain the actual implementation. Organized as top-level files for simple services and subdirectories for complex feature domains.

## Structure

### Top-level Services
| File | Purpose |
|---|---|
| `auth.py` | JWT auth, login/register, password change, token decode |
| `users.py` | User CRUD, admin ensure, home directory management |
| `permissions.py` | `is_privileged()`, `ensure_owner_or_privileged()` — ownership checks |
| `telemetry.py` | System metrics collection (CPU, RAM, network) on interval |
| `disk_monitor.py` | Real-time disk I/O sampling |
| `mobile.py` | Mobile device registration, QR code pairing |
| `service_status.py` | Background service health registry for admin dashboard |
| `network_discovery.py` | mDNS/Bonjour local network discovery |
| `jobs.py` | Health monitor background task (disk space, SMART) |
| `websocket_manager.py` | WebSocket connection management, broadcast |
| `file_activity.py` | File activity tracking (uploads, downloads, deletes) |
| `desktop_pairing.py` | Desktop client device-code pairing flow |
| `upload_progress.py` | SSE-based upload progress tracking |
| `api_key_service.py` | API key CRUD, validation, usage tracking |
| `totp_service.py` | TOTP 2FA setup, verification, backup codes |
| `recovery_code_service.py` | Password recovery codes — generate/verify/consume single-use codes (hash+encrypt at rest), timing-equalized username verify |
| `token_service.py` | Refresh token management, rotation |
| `plugin_service.py` | Plugin install/uninstall/toggle operations |
| `plugin_enablement.py` | Single source of truth for "which plugins are enabled" across the four Uvicorn workers (#448) — TTL-cached DB read (`refresh()`/`enabled_plugins()`/`is_enabled()`) plus `reconcile_worker()`, which aligns THIS worker's loaded plugins (`PluginManager._enabled`) with the DB on the next request via `Depends(deps.reconciled_plugin_state)`. Single-flight per worker; a plugin whose `enable_plugin()` fails is backed off `FAILED_RETRY_SECONDS` (60s) until `invalidate()` (called after a local toggle) clears the backoff early |
| `power_permissions.py` | Per-user power action permissions (get, update, check), incl. `can_toggle_desktop`. UI name: "System Permissions / Systemberechtigungen"; backend identifiers stay `power_permissions` (deliberate — no rename/migration). |
| `samba_service.py` | Samba/SMB share management |
| `webdav_service.py` | WebDAV server lifecycle control |
| `rate_limit_config.py` | DB-backed rate limit configuration |
| `system.py` | System info (OS, hardware, storage) |
| `seed.py` | Dev-mode seed data (test users, demo files) |
| `log_buffer.py` | In-memory ring buffer for SSE log streaming |
| `env_config.py` | Runtime environment variable management |
| `docs.py` | Documentation article serving from markdown files |
| `storage_breakdown.py` | Per-user storage usage calculation |
| `server_profile_service.py` | Server connection profiles for login screen |
| `ssh_service.py` | SSH key management |
| `snapshot_export.py` | Shutdown snapshot for BaluPi handoff |
| `version_tracker.py` | App version history tracking |
| `user_metadata_cache.py` | Cached user metadata for file operations |
| `balupi_handshake.py` | BaluPi companion device startup/shutdown notifications |
| `dashboard_panel_bridge.py` | Plugin dashboard panel SHM-to-WebSocket bridge |
| `plugin_marketplace.py` | `MarketplaceService`: fetches upstream `index.json`, fail-closed ed25519 signature gate (Track C), drives install/uninstall via `PluginInstaller` |
| `plugin_storage_service.py` | Sandboxed plugin KV storage with per-plugin quota enforcement |
| `plugin_update_check.py` | Plugin update checker — compares installed versions against marketplace index |
| `auth_policy.py` | Auth policy CRUD and evaluation (per-user/per-route policy rules) |
| `nfs_service.py` | NFS share management (export config, mount lifecycle) |
| `notification_routing.py` | Notification routing rules — maps event types to per-user delivery channels |
| `pin_service.py` | Device PIN management (set, verify, clear) |

### Service Subdirectories

**`files/`** — File operations, the core of the NAS
- `operations.py` — Upload, download, delete, rename, move, copy
- `shares.py` — Public/user file sharing
- `metadata.py` / `metadata_db.py` — File metadata (JSON + DB)
- `ownership.py` — File ownership tracking
- `chunked_upload.py` — Resumable chunked uploads
- `folder_size.py` — Recursive folder size calculation
- `storage.py` — Storage info, mountpoints, quota
- `storage_permissions.py` — POSIX permission management
- `path_utils.py` — Path normalization utilities
- `access.py` — File access control helpers

**`hardware/raid/`** — RAID management (mdadm)
- `protocol.py` — Abstract backend interface
- `dev_backend.py` — Simulated RAID for dev mode (7 mock disks)
- `mdadm_backend.py` — Real mdadm commands for production
- `api.py` — Public API functions (auto-selects backend)
- `parsing.py` — `/proc/mdstat` parser
- `confirmation.py` — Destructive operation confirmation tokens
- `scrub.py` — RAID scrub scheduling

**`hardware/smart/`** — Disk health monitoring (smartctl)

**`monitoring/`** — Unified monitoring system
- `orchestrator.py` — Starts/stops all collectors
- `cpu_collector.py`, `memory_collector.py`, `network_collector.py`, `disk_io_collector.py` — Metric collectors
- `process_tracker.py` — BaluHost process monitoring
- `retention_manager.py` — Old sample cleanup
- `worker_service.py` — Separate monitoring worker process (prod)
- `shm.py` — Shared memory (JSON files in `/tmp/`) for inter-process communication

**`power/`** — CPU frequency scaling, fan control, energy, sleep
- `manager.py` — PowerManager: demand-based CPU profile selection
- `fan_control.py` — Temperature-based fan speed control with curves
- `sleep.py` — Soft/hard sleep modes with idle detection
- `presence.py` — user-presence tracker (heartbeats → presence_sessions table; blocks auto true-suspend, issue #214)
- `energy.py` — Power consumption tracking and cost estimation
- `cpu_protocol.py` / `cpu_dev_backend.py` / `cpu_linux_backend.py` — Platform abstraction
- `presets.py` — Saved power configuration presets
- `fritzbox_wol.py` — Wake-on-LAN via FritzBox TR-064

**`vpn/`** — WireGuard VPN: key management, client config, Fernet encryption

**`cloud/`** — Cloud import/export (rclone, iCloud, OAuth), adapter pattern

**`backup/`** — Backup/restore with scheduling

**`sync/`** — Desktop sync client coordination, progressive sync

**`scheduler/`** — Unified scheduler: config, execution history, worker process

**`notifications/`** — Firebase push notifications, in-app events

**`audit/`** — Audit logging (DB-backed), admin DB inspection with column redaction

**`versioning/`** — File versioning (VCL): version tracking, blob storage, reconciliation

**`pihole/`** — Pi-hole DNS integration: API client, query analytics, ad discovery, failover

**`cache/`** — SSD file caching with LRU eviction

**`benchmark/`** — Disk benchmarking (fio backend + dev mock)

**`update/`** — Self-hosted update mechanism with rollback

**`status_bar/`** — Topbar status strip: catalog-driven collectors and strip service

**`setup/`** — First-run setup wizard: detection, step tracking, completion
- `service.py` — Setup required detection, completed step tracking, completion flag

**`game_libraries/`** — Game library storage usage (Steam now, provider-extensible)
- `provider.py` — `GameLibraryProvider` protocol + registry seam
- `steam.py` — Steam discovery via `libraryfolders.vdf` + `appmanifest_*.acf` (metadata only)
- `vdf.py` — minimal Valve KeyValues parser (stdlib)
- `service.py` — aggregate across providers, dev-mode mock

## Key Patterns

- **Dev/Prod backends**: Hardware services use a protocol/interface with separate `dev_backend` (mocks) and `linux_backend` (real commands). Selected based on `settings.is_dev_mode`
- **Singletons**: Long-running services use `_instance` class attribute with `get_instance()` classmethod
- **Background tasks**: Started via `asyncio.create_task()` in lifespan, stopped via cancellation
- **Inter-process comms**: Monitoring worker writes JSON to `/tmp/baluhost_shm/`, web workers read it (`monitoring/shm.py`)
- **DB access in services**: Use `SessionLocal()` with try/finally for standalone calls, or accept `db: Session` parameter when called from routes
