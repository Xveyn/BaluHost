# Release Downgrade Feature — Design Spec

**Date**: 2026-03-23
**Status**: Reviewed
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
- Multi-step downgrade chains (e.g., 1.19 -> 1.17 -> 1.15 in sequence)

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
    target_tag: str = Field(
        description="Git tag to downgrade to, e.g. 'v1.17.0'",
        pattern=r"^v\d+\.\d+\.\d+(-[\w.]+)?$",
    )
    target_commit: str = Field(description="Expected commit hash for validation")
    skip_backup: bool = Field(default=False, description="Skip file/config backup (DB backup is always created)")
    force: bool = Field(default=False, description="Ignore non-critical blockers")
```

The `target_tag` field has a regex validator to ensure it matches the expected tag format (`v1.17.0`, `v1.18.0-beta.1`, etc.). This prevents injection of arbitrary git refs.

Response reuses `UpdateStartResponse` (success, update_id, message, blockers).

#### UpdateChannelEnum Extension

Add `"downgrade"` to both the schema Literal AND the ORM enum:

Schema (`schemas/update.py`):
```python
UpdateChannelEnum = Literal["stable", "unstable", "development", "downgrade"]
```

ORM model (`models/update_history.py`):
```python
class UpdateChannel(str, enum.Enum):
    STABLE = "stable"
    BETA = "beta"
    DEVELOPMENT = "development"
    DOWNGRADE = "downgrade"
```

**Note**: The `channel` column in `update_history` is `String(20)`, not a PostgreSQL enum type, so no Alembic migration is needed — any string value up to 20 chars is accepted. The existing mismatch between schema `"unstable"` and ORM `"beta"` is a pre-existing issue and out of scope for this feature.

#### `ReleaseInfo` Schema Extension

The existing `ReleaseInfo` only has `commit_short` (7-char hash). The frontend needs the full commit hash to populate `DowngradeRequest.target_commit`. Add a `commit` field:

```python
class ReleaseInfo(BaseModel):
    tag: str
    version: str
    date: Optional[str] = None
    is_prerelease: bool = False
    commit_short: str
    commit: str = Field(description="Full commit hash for downgrade validation")
```

Update `ProdUpdateBackend.get_all_releases()` to fetch the full hash (change `--short=7` to full `rev-parse`). Update `DevUpdateBackend.get_all_releases()` to include mock full hashes.

Update `ReleaseInfo` TypeScript interface in `client/src/api/updates.ts`:
```typescript
export interface ReleaseInfo {
  tag: string;
  version: string;
  date: string | null;
  is_prerelease: boolean;
  commit_short: string;
  commit: string;
}
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
3. Verify target version < current version (semver comparison via existing `parse_version()` from `services/update/utils.py`)
4. Check blockers (no running update/downgrade)

**On success:** Creates `UpdateHistory` entry with `channel="downgrade"`, launches async task (dev) or shell script (prod).

**Semantics of `from_version` / `to_version`:** Same convention as updates — `from_version` = current version, `to_version` = target version. For downgrades, `from_version` > `to_version`. The frontend already displays both fields; no special handling needed.

#### Async Downgrade Flow: `_run_dev_downgrade()`

| Step | Progress | Status | Description |
|------|----------|--------|-------------|
| 1 | 5-10% | `backing_up` | **Mandatory DB backup** via `BackupService.create_backup()` (includes_database=True, includes_config=True). Always runs regardless of `skip_backup`. |
| 2 | 10-25% | `downloading` | `git fetch --all --tags --prune` |
| 3 | 25-40% | `installing` | `git checkout <target_commit>` |
| 4 | 40-55% | `installing` | Install dependencies (pip/npm for the older version) |
| 5 | 55-75% | `migrating` | **Alembic downgrade**: resolve target revision, run `alembic downgrade <rev>`. On failure -> restore DB backup, log warning. |
| 6 | 75-85% | `health_check` | Health check |
| 7 | 85-95% | `restarting` | Restart services |
| 8 | 100% | `completed` | Done |

**On failure at any step:** Attempt rollback to original commit (same as current update error handler). If the Alembic downgrade failed AND the DB backup restore also fails, abort the entire downgrade, rollback git checkout to original commit, and mark as `failed` with a descriptive error message.

**Cancellation:** The existing `cancel_update()` flow works for downgrades since they share the `UpdateHistory` model and async task infrastructure. Downgrade tasks are tracked in `_running_tasks` and can be cancelled via the same `POST /cancel/{id}` endpoint.

**WebSocket events:** Downgrades emit the same `update_progress`, `update_complete`, and `update_failed` WebSocket events as updates. The `channel="downgrade"` field distinguishes them.

#### Alembic Revision Resolution

New method on `UpdateBackend`:

```python
@abstractmethod
async def resolve_alembic_revision(self, commit: str) -> Optional[str]:
    """Determine the Alembic head revision at a given git commit."""
    pass
```

**ProdUpdateBackend implementation:**

The codebase has mixed migration naming conventions (numbered like `001_xxx.py`, hex-hash like `9c00b193b5bd_xxx.py`, plain names). Revision IDs are embedded inside each file as Python variables (`revision = "..."`), not reliably derivable from filenames. Additionally, merge migrations exist with multiple `down_revision` values.

Therefore, the approach is NOT to parse filenames but to:

1. List migration files at the target commit: `git ls-tree -r --name-only <commit> backend/alembic/versions/`
2. For each file, extract the `revision` variable: `git show <commit>:backend/alembic/versions/<filename>` and grep for `^revision\s*=`
3. Also extract `down_revision` to build the revision chain
4. Walk the chain to find the head (the revision that no other revision points to as its `down_revision`)

This is more expensive (one `git show` per migration file) but reliable. The number of migration files is bounded (currently ~40) so this completes in under a second.

**Alternative shortcut for prod:** After `git checkout <target_commit>` in Step 3, simply run `alembic heads` against the checked-out code. This is the simplest and most reliable approach since Alembic itself resolves the chain. The `resolve_alembic_revision()` call can happen after checkout instead of before.

**Recommended approach:** Use the post-checkout `alembic heads` shortcut in production. The `git show`-based approach is a fallback for cases where we need the revision before checkout (e.g., for pre-flight validation).

**DevUpdateBackend implementation:**
- Returns a mock revision string (e.g., `"mock_downgrade_rev"`)

#### Alembic Downgrade Fallback

```python
async def _run_alembic_downgrade(
    self, target_rev: str, backup_id: int, admin_username: str
) -> bool:
    """Run alembic downgrade. On failure, restore DB backup."""
    success, error = await self.backend.run_alembic_downgrade(target_rev)
    if not success:
        logger.warning(f"Alembic downgrade failed: {error}. Restoring backup.")
        backup_service = BackupService(self.db)
        restore_ok = backup_service.restore_backup(
            backup_id=backup_id,
            user=admin_username,
            restore_database=True,
            restore_files=False,
            restore_config=False,
        )
        if not restore_ok:
            logger.error(
                f"DB backup restore also failed for backup {backup_id}. "
                "Manual intervention required."
            )
            raise Exception(
                f"Alembic downgrade failed ({error}) AND backup restore failed. "
                "Database may be in inconsistent state."
            )
        return False
    return True
```

The `admin_username` is threaded from `downgrade()` via the `user_id` parameter (resolved to username via a DB query at the start of the downgrade flow).

#### Production: `run-update.sh` Extension

New flags parsed alongside existing ones:
- `--downgrade` — boolean flag, switches migration step from upgrade to downgrade
- `--alembic-rev <revision>` — target Alembic revision for downgrade

**`ProdUpdateBackend.launch_update_script()` changes:**

The method signature gains two optional parameters:

```python
def launch_update_script(
    self,
    update_id: int,
    from_commit: str,
    to_commit: str,
    from_version: str,
    to_version: str,
    downgrade: bool = False,
    alembic_rev: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
```

When `downgrade=True`, the additional flags `--downgrade --alembic-rev <rev>` are appended to the `systemd-run` command.

**Shell script changes:**

```bash
# New argument parsing
DOWNGRADE=false
ALEMBIC_REV=""

case "$1" in
    # ...existing cases...
    --downgrade)    DOWNGRADE=true;    shift ;;
    --alembic-rev)  ALEMBIC_REV="$2";  shift 2 ;;
esac

# Step 3 (database): replace module 08 when downgrading
if [[ "$DOWNGRADE" == "true" && -n "$ALEMBIC_REV" ]]; then
    write_status "migrating" 45 "Running alembic downgrade to $ALEMBIC_REV..."
    sudo -u "$BALUHOST_USER" "$VENV_DIR/bin/alembic" -c "$INSTALL_DIR/backend/alembic.ini" \
        downgrade "$ALEMBIC_REV"
else
    run_module "08" "database-migrate" 45 55
fi
```

**Dependency installation (Step 2):** The older version's `pyproject.toml` may have different dependency constraints. The shell script already runs module `05-python-venv` which does `pip install -e ".[dev]"` in the venv — this works because it installs from the checked-out (older) code. If pip fails due to conflicts, the error handler triggers a rollback to the original commit.

### Frontend

#### `UpdateHistoryTab.tsx` — Release List Enhancement

Each release where `version < current_version` gets a "Downgrade" button:

```
v1.19.0  abc1234  2026-03-20  Stable  [Current]
v1.18.0  def5678  2026-03-15  Stable  [Downgrade]
v1.17.0  ghi9012  2026-03-08  Stable  [Downgrade]
```

The component receives the current version as a new prop to determine which releases are eligible for downgrade.

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

German equivalents (proper UTF-8 umlauts, matching existing i18n convention):

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

Note: Verify umlaut convention in existing `de/updates.json` at implementation time and match it (either `ue`/`ae` ASCII or proper `u`/`a` UTF-8).

### Security

- Admin-only endpoint with `Depends(deps.get_current_admin)`
- Rate-limited via `@user_limiter.limit(get_limit("admin_operations"))`
- Audit log entry for every downgrade attempt (success and failure)
- `target_commit` validated against `target_tag` to prevent commit injection
- `target_tag` validated with regex pattern to prevent arbitrary git ref injection
- DB backup always created (not skippable for downgrade)

### Tests

#### Unit Tests (backend/tests/services/test_update_service.py)

- `test_downgrade_happy_path` — full flow with DevBackend
- `test_downgrade_alembic_failure_restores_backup` — Alembic fails, backup restored
- `test_downgrade_alembic_and_restore_both_fail` — both fail, downgrade aborted, git rolled back
- `test_downgrade_blocked_by_running_update` — blocker check
- `test_downgrade_target_newer_than_current_rejected` — version validation
- `test_downgrade_invalid_tag_rejected` — tag validation
- `test_downgrade_commit_mismatch_rejected` — commit vs tag validation
- `test_downgrade_creates_mandatory_backup` — backup always created even with skip_backup=True
- `test_downgrade_cancellation` — cancelling a running downgrade works

#### API Tests (backend/tests/api/test_updates_routes.py)

- `test_downgrade_requires_admin` — returns 401/403 for non-admin
- `test_downgrade_rate_limited` — rate limiting works
- `test_downgrade_audit_logged` — audit log entry created

#### ProdUpdateBackend Tests (backend/tests/services/test_prod_update_backend.py)

- `test_resolve_alembic_revision_with_mocked_git` — mock `_run_git` calls, verify correct head resolution from migration chain

## File Changes Summary

| File | Change |
|------|--------|
| `backend/app/schemas/update.py` | Add `DowngradeRequest`, extend `UpdateChannelEnum`, add `commit` to `ReleaseInfo` |
| `backend/app/models/update_history.py` | Add `DOWNGRADE = "downgrade"` to `UpdateChannel` enum |
| `backend/app/services/update/service.py` | Add `downgrade()`, `_run_dev_downgrade()`, `_run_alembic_downgrade()` |
| `backend/app/services/update/backend.py` | Add abstract `resolve_alembic_revision()`, `run_alembic_downgrade()` |
| `backend/app/services/update/prod_backend.py` | Implement `resolve_alembic_revision()`, `run_alembic_downgrade()`, update `get_all_releases()` for full hash, extend `launch_update_script()` |
| `backend/app/services/update/dev_backend.py` | Mock implementations for downgrade, update `get_all_releases()` for full hash |
| `backend/app/api/routes/updates.py` | Add `POST /downgrade` endpoint |
| `deploy/update/run-update.sh` | Add `--downgrade` + `--alembic-rev` flags, conditional migration step |
| `client/src/api/updates.ts` | Add `DowngradeRequest`, `startDowngrade()`, add `commit` to `ReleaseInfo` |
| `client/src/components/updates/UpdateHistoryTab.tsx` | Downgrade button + two-step inline confirmation |
| `client/src/components/updates/UpdateOverviewTab.tsx` | Handle downgrade channel in progress display |
| `client/src/i18n/locales/en/updates.json` | Downgrade translation keys |
| `client/src/i18n/locales/de/updates.json` | German downgrade translations |
| `backend/tests/services/test_update_service.py` | Downgrade unit tests |
| `backend/tests/api/test_updates_routes.py` | Downgrade API tests |
| `backend/tests/services/test_prod_update_backend.py` | `resolve_alembic_revision` tests |
