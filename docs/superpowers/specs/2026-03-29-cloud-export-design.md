# Cloud Export — Design Spec

**Date**: 2026-03-29
**Status**: Approved
**Scope**: Share BaluHost files externally via Google Drive / OneDrive upload + sharing link

## Overview

Cloud Export is the counterpart to the existing Cloud Import. Users select a file or folder on BaluHost, which gets uploaded to their connected Google Drive or OneDrive account. A sharing link is generated and returned. This allows sharing files with people outside the NAS without requiring VPN access.

iCloud is explicitly excluded due to unreliable API support (no official REST API, experimental rclone backend with 30-day token expiry, no sharing link API).

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| UI location | Unified Share Modal with tabs (Intern / Cloud Export) | Single entry point for all sharing |
| Cloud connections | Reuse existing Import connections, scope-upgrade when needed | Less friction, one connection per provider |
| Target folder | Default `BaluHost Shares/`, user-changeable | Good default with flexibility |
| File + folder support | Both from day one | Consistent with internal sharing, rclone handles both |
| SharesPage integration | New "Cloud-Shares" tab with StatCards | Matches existing design patterns |
| Providers | Google Drive, OneDrive | Both have excellent APIs and rclone support |

## Architecture

```
FileManager → ShareFileModal (Tab: Cloud Export) → POST /api/cloud-export/
    → CloudExportService.start_export() → Background task
    → RcloneAdapter.upload_file/folder() → rclone copy
    → RcloneAdapter.create_share_link() → rclone link
    → DB update (share_link, status=ready)

SharesPage (Tab: Cloud-Shares) → GET /api/cloud-export/jobs
    → List, Stats, Copy Link, Revoke, Retry
```

### Components

- **Backend**: `CloudExportService` + `CloudExportJob` model + `/api/cloud-export/` routes
- **Frontend**: Refactored `ShareFileModal` with tabs + new tab on `SharesPage`
- **RcloneAdapter**: New methods `upload_file`, `upload_folder`, `create_share_link`
- **OAuth**: Scope-upgrade mechanism on existing `CloudConnection`

## Data Model

### CloudExportJob (new table: `cloud_export_jobs`)

```python
class CloudExportJob(Base):
    __tablename__ = "cloud_export_jobs"

    id: Mapped[int]                          # PK
    user_id: Mapped[int]                     # FK → users
    connection_id: Mapped[int]               # FK → cloud_connections

    # Source (NAS)
    source_path: Mapped[str]                 # Relative path on NAS
    is_directory: Mapped[bool]               # File or folder
    file_name: Mapped[str]                   # Display name
    file_size_bytes: Mapped[int | None]      # Size for progress tracking

    # Destination (Cloud)
    cloud_folder: Mapped[str]                # Target folder in cloud (default: "BaluHost Shares/")
    cloud_path: Mapped[str | None]           # Full path in cloud (after upload)

    # Sharing
    share_link: Mapped[str | None]           # Generated sharing link
    link_type: Mapped[str]                   # "view" | "edit"
    link_password: Mapped[str | None]        # Optional (OneDrive Personal only)

    # Status
    status: Mapped[str]                      # pending | uploading | creating_link | ready | failed | revoked
    progress_bytes: Mapped[int]              # Upload progress
    error_message: Mapped[str | None]        # Error details on failure

    # Timestamps
    created_at: Mapped[datetime]
    completed_at: Mapped[datetime | None]
    expires_at: Mapped[datetime | None]      # Link expiration
```

No new model for connections — reuses existing `CloudConnection` with scope upgrade.

## Backend

### RcloneAdapter — New Methods

Added to `backend/app/services/cloud/adapters/rclone.py`:

```python
async def upload_file(
    self, local_path: Path, remote_path: str,
    progress_callback: Callable[[int], None] | None = None
) -> None:
    """Upload a single file using rclone copyto (reverse of download_file)."""
    # rclone copyto <local_path> <remote>:<remote_path>
    # Progress parsing from stderr (same pattern as download_file)

async def upload_folder(
    self, local_path: Path, remote_path: str,
    progress_callback: Callable[[int, str | None], None] | None = None
) -> UploadResult:
    """Upload a folder using rclone copy (reverse of download_folder)."""
    # rclone copy <local_path> <remote>:<remote_path>

async def create_share_link(self, remote_path: str, link_type: str = "view") -> str:
    """Create a sharing link using rclone link."""
    # rclone link <remote>:<remote_path>
    # Returns the URL from the last line of stdout
```

Also added to `CloudAdapter` base class and `DevCloudAdapter` (mock implementation).

### UploadResult (new dataclass in base.py)

```python
@dataclass
class UploadResult:
    files_transferred: int = 0
    bytes_transferred: int = 0
    errors: list[str] = field(default_factory=list)
```

### CloudExportService (`backend/app/services/cloud/export_service.py`)

```python
class CloudExportService:
    def __init__(self, db: Session): ...

    def start_export(
        self, connection_id: int, user_id: int,
        source_path: str, cloud_folder: str,
        link_type: str, expires_at: datetime | None
    ) -> CloudExportJob:
        """Create export job. Validates source_path via _jail_path()."""

    async def execute_export(self, job_id: int) -> None:
        """Background task: upload → create_link → update DB."""

    def revoke_export(self, job_id: int, user_id: int) -> bool:
        """Delete cloud file (rclone delete), set status=revoked."""

    def retry_export(self, job_id: int, user_id: int) -> CloudExportJob:
        """Reset failed job to pending, re-execute."""

    def get_user_exports(self, user_id: int, limit: int = 50) -> list[CloudExportJob]: ...
    def get_export_status(self, job_id: int, user_id: int) -> CloudExportJob | None: ...
    def get_export_statistics(self, user_id: int) -> CloudExportStatistics: ...
```

### OAuth Scope Upgrade (`backend/app/services/cloud/service.py`)

```python
def get_oauth_url(self, provider: str, user_id: int, scopes: str | None = None) -> str:
    """Extended: accepts optional scopes parameter for export."""
    # Export uses: "https://www.googleapis.com/auth/drive.file" (GDrive)
    #              "Files.ReadWrite offline_access" (OneDrive)

def check_connection_scope(self, connection_id: int, user_id: int) -> dict:
    """Check if connection has ReadWrite scope."""
    # Returns {"has_export_scope": bool, "provider": str}
```

On successful OAuth callback with upgraded scope, the existing `CloudConnection` token is replaced. The callback distinguishes upgrade from new-connect via a `"upgrade_connection_id"` field in the OAuth `state` JSON. If present, the callback updates the existing connection's `encrypted_config` instead of creating a new `CloudConnection`.

### API Routes (`backend/app/api/routes/cloud_export.py`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/cloud-export/` | Start export (background job) |
| `GET` | `/api/cloud-export/jobs` | List user's export jobs |
| `GET` | `/api/cloud-export/jobs/{id}` | Get single job status |
| `POST` | `/api/cloud-export/jobs/{id}/revoke` | Revoke (delete cloud file + link) |
| `POST` | `/api/cloud-export/jobs/{id}/retry` | Retry failed job |
| `GET` | `/api/cloud-export/statistics` | Stats for SharesPage |
| `POST` | `/api/cloud-export/check-scope` | Check if connection has export scope |

All endpoints: `Depends(get_current_user)`, `@limiter.limit(get_limit(...))`, Pydantic schemas, audit logging.

### Pydantic Schemas (`backend/app/schemas/cloud_export.py`)

```python
class CloudExportRequest(BaseModel):
    connection_id: int
    source_path: str          # Validated via _jail_path()
    cloud_folder: str = "BaluHost Shares/"
    link_type: Literal["view", "edit"] = "view"
    expires_at: datetime | None = None

class CloudExportJobResponse(BaseModel):
    id: int
    connection_id: int
    provider: str             # Resolved from connection
    source_path: str
    file_name: str
    is_directory: bool
    file_size_bytes: int | None
    cloud_folder: str
    share_link: str | None
    link_type: str
    status: str
    progress_bytes: int
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None

class CloudExportStatistics(BaseModel):
    total_exports: int
    active_exports: int       # status=ready and not expired
    failed_exports: int
    total_upload_bytes: int
```

## Frontend

### ShareFileModal (refactored from CreateFileShareModal)

File: `client/src/components/ShareFileModal.tsx`

The existing `CreateFileShareModal` is refactored into `ShareFileModal` with two tabs:

- **Tab "Intern"**: Existing internal sharing UI (user selection, permissions, expiration) — code stays largely the same
- **Tab "Cloud Export"**: New panel with:
  - Provider dropdown (lists user's connected `CloudConnection`s)
  - Target folder input (default: `BaluHost Shares/`, optional cloud folder browser)
  - Link type radio: "View only" / "Edit"
  - Expiration date picker (optional)
  - Scope-upgrade prompt if connection lacks ReadWrite scope
  - "No cloud account?" hint with link to `/cloud-import`

Props change: `fileId` required (always opened from context with a specific file).

On submit: calls `POST /api/cloud-export/`, shows toast "Upload started...", closes modal.

### SharesPage — New Tab "Cloud-Shares"

File: `client/src/pages/SharesPage.tsx`

New third tab added to the existing tab bar:

```typescript
const tabs = [
  { key: 'shares', label: 'My Shares', icon: Users },
  { key: 'shared-with-me', label: 'Shared with Me', icon: Share2 },
  { key: 'cloud-exports', label: 'Cloud Shares', icon: Cloud },
];
```

**StatCards** (when cloud-exports tab active):
- Active Cloud Shares (count)
- Upload Volume (total bytes)

**Table columns**: Provider (icon), File name, Link (copy button), Status (with progress bar), Created, Expires, Actions (Revoke/Cancel/Retry)

**Mobile**: Card view following existing pattern from other tabs.

### API Client (`client/src/api/cloud-export.ts`)

```typescript
export function startCloudExport(data: CloudExportRequest): Promise<CloudExportJob>
export function listCloudExports(limit?: number): Promise<CloudExportJob[]>
export function getCloudExportStatus(jobId: number): Promise<CloudExportJob>
export function revokeCloudExport(jobId: number): Promise<void>
export function retryCloudExport(jobId: number): Promise<CloudExportJob>
export function getCloudExportStatistics(): Promise<CloudExportStatistics>
export function checkConnectionScope(connectionId: number): Promise<{ has_export_scope: boolean }>
```

### i18n

New keys in `client/src/i18n/locales/{en,de}/shares.json` for:
- Tab labels, form labels, status texts, toast messages, empty states
- Cloud-specific: provider names, scope upgrade prompts, link copy confirmation

## Security

- **Path validation**: Every `source_path` goes through `_jail_path()` — users can only export their own files, admins everything
- **Token encryption**: OAuth tokens stay encrypted in `CloudConnection.encrypted_config` (Fernet). No tokens in frontend or logs
- **Link passwords**: `CloudExportJob.link_password` added to `REDACT_PATTERN` in `admin_db.py`
- **Revoke = cloud deletion**: `rclone delete` removes the file from the cloud, invalidating the link. Confirm dialog required
- **Scope upgrade**: Non-destructive. Existing import functionality continues regardless. Only upgrades token scope, not connection ID
- **Rate limits**: rclone handles Google Drive (3 writes/sec, 750 GB/day) and OneDrive (dynamic throttling) with built-in backoff
- **Large files**: rclone uses chunked upload automatically (GDrive: >8MB, OneDrive: >10MB). Max 5TB (GDrive) / 250GB (OneDrive)
- **Audit logging**: All export/revoke actions logged via `get_audit_logger_db()`
- **Dev mode**: `DevCloudAdapter` gets mock `upload_file`, `upload_folder`, `create_share_link` (simulated delay, fake URL)

## Edge Cases

- **Expired links**: Optional scheduler job marks expired jobs as `status="expired"` and cleans up cloud files
- **Connection deleted during upload**: Export job fails gracefully, status set to "failed" with clear error message
- **File deleted from NAS during upload**: rclone fails, job marked as "failed"
- **Scope upgrade declined**: Import continues to work readonly, export tab shows "Berechtigung erweitern" prompt
- **Cloud storage full**: rclone error propagated, job marked "failed" with quota error message
- **Concurrent exports**: Multiple jobs can run in parallel (FastAPI BackgroundTasks), each with own progress tracking

## Out of Scope

- iCloud support (no reliable API)
- Automatic re-sharing when NAS file updates (one-time upload snapshot)
- Public link generation without cloud provider (would need port forwarding / relay)
- Scheduled/recurring exports
