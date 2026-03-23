# Release Downgrade Feature — Design Spec

**Date**: 2026-03-23
**Status**: Draft
**Author**: Claude + Xveyn

## Summary

Allow administrators to downgrade BaluHost to any previous release (git tag). The system warns about potential database data loss, creates a mandatory DB backup before proceeding, attempts Alembic downgrade migrations, and falls back to full DB backup restore if migrations fail.

## Requirements

1. Admin can select any previous release from the release list and initiate a downgrade
2. Two-step inline confirmation: warning displayed, then user must type the target version to confirm
3. Mandatory DB backup before every downgrade (even if `skip_backup=True`)
4. Alembic downgrade attempted first; on failure, restore DB from backup as fallback
5. Full async progress tracking via existing `UpdateHistory` + `UpdateProgress` infrastructure
6. Works in both dev mode (simulated) and prod mode (shell script)

## Non-Goals

- Downgrading to arbitrary non-tagged commits (only releases)
- Automatic rollback of file-system data (user files are untouched)
- Multi-step downgrade chains (e.g., 1.19 → 1.17 → 1.15 in sequence)

## Architecture

### Backend

#### New Endpoint

```
POST /api/updates/downgrade
```

- Auth: `Depends(deps.get_current_admin)`
- Rate limit: `@user_limiter.limit(get_limit("admin_operations"))`
- Audit logged (event_type="UPDATE", action="downgrade")

#### New Schema: `DowngradeRequest`

```python
class DowngradeRequest(BaseModel):
    target_tag: str = Field(description="Git tag to downgrade to, e.g. 'v1.17.0'")
    target_commit: str = Field(description="Expected commit hash for validation")
    skip_backup: bool = Field(default=False, description="Skip file/config backup (DB backup is always created)")
    force: bool = Field(default=False, description="Ignore non-critical blockers")
```

Response reuses `UpdateStartResponse` (success, update_id, message, blockers).

#### UpdateChannelEnum Extension

Add `"downgrade"` to `UpdateChannelEnum`:

```python
UpdateChannelEnum = Literal["stable", "unstable", "development", "downgrade"]
```

#### Service Method: `UpdateService.downgrade()`

```python
async def downgrade(
    self,
    request: DowngradeRequest,
    user_id: int,
) -> UpdateStartResponse:
```

**Validation steps:**
1. Verify `target_tag` exists in git tags
2. Verify `target_commit` matches the tag's commit
3. Verify target version < current version (semver comparison)
4. Check blockers (no running update/downgrade)

**On success:** Creates `UpdateHistory` entry with `channel="downgrade"`, launches async task (dev) or shell script (prod).

#### Async Downgrade Flow: `_run_dev_downgrade()`

| Step | Progress | Status | Description |
|------|----------|--------|-------------|
| 1 | 5-10% | `backing_up` | **Mandatory DB backup** via `BackupService.create_backup()` (includes_database=True, includes_config=True). Always runs regardless of `skip_backup`. |
| 2 | 10-25% | `downloading` | `git fetch --all --tags --prune` |
| 3 | 25-40% | `installing` | `git checkout <target_commit>` |
| 4 | 40-55% | `installing` | Install dependencies (pip/npm for the older version) |
| 5 | 55-75% | `migrating` | **Alembic downgrade**: resolve target revision, run `alembic downgrade <rev>`. On failure → restore DB backup, log warning. |
| 6 | 75-85% | `health_check` | Health check |
| 7 | 85-95% | `restarting` | Restart services |
| 8 | 100% | `completed` | Done |

On any failure: attempt rollback to original commit (same as current update error handler).

#### Alembic Revision Resolution

New method on `UpdateBackend`:

```python
@abstractmethod
async def resolve_alembic_revision(self, commit: str) -> Optional[str]:
    """Determine the Alembic head revision at a given git commit."""
    pass
```

**ProdUpdateBackend implementation:**
- Run `git ls-tree -r --name-only <commit> backend/alembic/versions/` to list migration files at that commit
- Parse revision IDs from filenames (pattern: `NNN_description.py` or `<hash>_description.py`)
- Build the revision chain to find the head revision for that commit

**DevUpdateBackend implementation:**
- Returns a mock revision string (e.g., `"mock_downgrade_rev"`)

#### Alembic Downgrade Fallback

```python
async def _run_alembic_downgrade(self, target_rev: str, backup_id: int) -> bool:
    """Run alembic downgrade. On failure, restore DB backup."""
    success, error = await self.backend.run_alembic_downgrade(target_rev)
    if not success:
        logger.warning(f"Alembic downgrade failed: {error}. Restoring backup.")
        backup_service = BackupService(self.db)
        backup_service.restore_backup(backup_id)
        return False
    return True
```

#### Production: `run-update.sh` Extension

New flags:
- `--downgrade` — switches from `alembic upgrade head` to `alembic downgrade <rev>`
- `--alembic-rev <revision>` — target Alembic revision

The script's module runner skips module `08-database-migrate` and instead runs a new downgrade block that executes `alembic downgrade $ALEMBIC_REV`.

### Frontend

#### `UpdateHistoryTab.tsx` — Release List Enhancement

Each release where `version < current_version` gets a "Downgrade" button:

```
v1.19.0  abc1234  2026-03-20  ✅ Stable  [Current]
v1.18.0  def5678  2026-03-15  ✅ Stable  [↩ Downgrade]
v1.17.0  ghi9012  2026-03-08  ✅ Stable  [↩ Downgrade]
```

#### Two-Step Inline Confirmation

**Step 1** — Click "Downgrade": Inline warning expands below the release row.

Content:
- Warning icon + text: "Downgrade to v1.17.0 may cause database data loss. A database backup will be created automatically before proceeding."
- "Continue" button + "Cancel" button

**Step 2** — Click "Continue": Input field replaces the warning.

Content:
- Prompt: "Type `v1.17.0` to confirm the downgrade:"
- Text input field
- "Start Downgrade" button (disabled until input matches target tag)
- "Cancel" button

#### Progress Display

After starting, the user is redirected to the Overview tab. The existing `UpdateProgress` component displays the downgrade progress. The `to_version` field shows the downgrade target, and the channel shows "downgrade" which maps to a distinct label/color (e.g., amber/orange "Downgrade" badge).

#### API Client Addition

```typescript
// client/src/api/updates.ts

export interface DowngradeRequest {
  target_tag: string;
  target_commit: string;
  skip_backup?: boolean;
  force?: boolean;
}

export async function startDowngrade(request: DowngradeRequest): Promise<UpdateStartResponse> {
  const response = await apiClient.post<UpdateStartResponse>('/api/updates/downgrade', request);
  return response.data;
}
```

#### i18n Keys

New keys in `en/updates.json` and `de/updates.json`:

```json
{
  "downgrade": {
    "button": "Downgrade",
    "warning": "Downgrade to {{version}} may cause database data loss. A database backup will be created automatically before proceeding.",
    "confirmPrompt": "Type {{version}} to confirm the downgrade:",
    "startButton": "Start Downgrade",
    "progressLabel": "Downgrading to {{version}}",
    "channel": "Downgrade"
  }
}
```

German equivalents:

```json
{
  "downgrade": {
    "button": "Downgrade",
    "warning": "Ein Downgrade auf {{version}} kann zu Datenverlust in der Datenbank fuehren. Ein Datenbank-Backup wird automatisch vor dem Downgrade erstellt.",
    "confirmPrompt": "Gib {{version}} ein, um den Downgrade zu bestaetigen:",
    "startButton": "Downgrade starten",
    "progressLabel": "Downgrade auf {{version}}",
    "channel": "Downgrade"
  }
}
```

### Security

- Admin-only endpoint with `Depends(deps.get_current_admin)`
- Rate-limited via `@user_limiter.limit(get_limit("admin_operations"))`
- Audit log entry for every downgrade attempt (success and failure)
- `target_commit` validated against `target_tag` to prevent commit injection
- DB backup always created (not skippable for downgrade)

### Tests

#### Unit Tests (backend/tests/services/test_update_service.py)

- `test_downgrade_happy_path` — full flow with DevBackend
- `test_downgrade_alembic_failure_restores_backup` — Alembic fails, backup restored
- `test_downgrade_blocked_by_running_update` — blocker check
- `test_downgrade_target_newer_than_current_rejected` — version validation
- `test_downgrade_invalid_tag_rejected` — tag validation
- `test_downgrade_commit_mismatch_rejected` — commit vs tag validation
- `test_downgrade_creates_mandatory_backup` — backup always created even with skip_backup=True

#### API Tests (backend/tests/api/test_updates_routes.py)

- `test_downgrade_requires_admin` — returns 401/403 for non-admin
- `test_downgrade_rate_limited` — rate limiting works
- `test_downgrade_audit_logged` — audit log entry created

## File Changes Summary

| File | Change |
|------|--------|
| `backend/app/schemas/update.py` | Add `DowngradeRequest`, extend `UpdateChannelEnum` |
| `backend/app/services/update/service.py` | Add `downgrade()`, `_run_dev_downgrade()`, `_run_alembic_downgrade()` |
| `backend/app/services/update/backend.py` | Add abstract `resolve_alembic_revision()`, `run_alembic_downgrade()` |
| `backend/app/services/update/prod_backend.py` | Implement `resolve_alembic_revision()`, `run_alembic_downgrade()` |
| `backend/app/services/update/dev_backend.py` | Mock implementations for downgrade |
| `backend/app/api/routes/updates.py` | Add `POST /downgrade` endpoint |
| `deploy/update/run-update.sh` | Add `--downgrade` + `--alembic-rev` flags |
| `client/src/api/updates.ts` | Add `DowngradeRequest`, `startDowngrade()` |
| `client/src/components/updates/UpdateHistoryTab.tsx` | Downgrade button + two-step inline confirmation |
| `client/src/components/updates/UpdateOverviewTab.tsx` | Handle downgrade channel in progress display |
| `client/src/i18n/locales/en/updates.json` | Downgrade translation keys |
| `client/src/i18n/locales/de/updates.json` | German downgrade translations |
| `backend/tests/services/test_update_service.py` | Downgrade unit tests |
| `backend/tests/api/test_updates_routes.py` | Downgrade API tests |
