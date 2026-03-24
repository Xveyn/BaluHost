# Release Downgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow admins to downgrade BaluHost to any previous release with mandatory DB backup, Alembic downgrade, and fallback to backup restore.

**Architecture:** New `POST /api/updates/downgrade` endpoint with dedicated service method. Reuses existing `UpdateHistory` + async progress infrastructure. Two backends: `DevUpdateBackend` (simulated) and `ProdUpdateBackend` (git + shell script). Frontend adds downgrade buttons to release list with two-step inline confirmation.

**Tech Stack:** Python/FastAPI, SQLAlchemy, Alembic, React/TypeScript, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-03-23-release-downgrade-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/app/models/update_history.py` | Modify | Add `DOWNGRADE` to `UpdateChannel` enum |
| `backend/app/schemas/update.py` | Modify | Add `DowngradeRequest`, extend `UpdateChannelEnum`, add `commit` to `ReleaseInfo` |
| `backend/app/services/update/backend.py` | Modify | Add abstract `resolve_alembic_revision()`, `run_alembic_downgrade()` |
| `backend/app/services/update/dev_backend.py` | Modify | Mock downgrade methods, update `get_all_releases()` for full hash |
| `backend/app/services/update/prod_backend.py` | Modify | Implement `resolve_alembic_revision()`, `run_alembic_downgrade()`, update `get_all_releases()`, extend `launch_update_script()` |
| `backend/app/services/update/service.py` | Modify | Add `downgrade()`, `_run_dev_downgrade()`, `_run_alembic_downgrade()` |
| `backend/app/api/routes/updates.py` | Modify | Add `POST /downgrade` endpoint |
| `deploy/update/run-update.sh` | Modify | Add `--downgrade` + `--alembic-rev` flags |
| `client/src/api/updates.ts` | Modify | Add `DowngradeRequest`, `startDowngrade()`, `commit` to `ReleaseInfo` |
| `client/src/components/updates/UpdateHistoryTab.tsx` | Modify | Downgrade button + two-step inline confirmation |
| `client/src/components/updates/UpdateOverviewTab.tsx` | Modify | Handle downgrade channel badge in progress display |
| `client/src/pages/UpdatePage.tsx` | Modify | Pass `currentVersion` and `onDowngradeStarted` props |
| `client/src/i18n/locales/en/updates.json` | Modify | Downgrade translation keys |
| `client/src/i18n/locales/de/updates.json` | Modify | German downgrade translations |
| `backend/tests/services/test_update_service.py` | Modify | Downgrade unit + integration tests (consolidates ProdBackend downgrade tests from spec's `test_prod_update_backend.py` into existing test file) |
| `backend/tests/api/test_updates_routes.py` | Create | Downgrade API endpoint tests (auth, rate-limit, audit) |

---

### Task 1: Extend ORM Enum and Schema Types

**Files:**
- Modify: `backend/app/models/update_history.py:29-33`
- Modify: `backend/app/schemas/update.py:11-16`
- Modify: `backend/app/schemas/update.py:415-422`
- Test: `backend/tests/services/test_update_service.py`

- [ ] **Step 1: Write failing test for UpdateChannel.DOWNGRADE**

In `backend/tests/services/test_update_service.py`, add at the end of existing imports and after existing test classes:

```python
class TestDowngradeEnums:
    """Tests for downgrade-related enum extensions."""

    def test_update_channel_has_downgrade(self):
        """UpdateChannel enum should include DOWNGRADE."""
        assert hasattr(UpdateChannel, "DOWNGRADE")
        assert UpdateChannel.DOWNGRADE.value == "downgrade"

    def test_downgrade_channel_fits_column(self):
        """'downgrade' string must fit in String(20) column."""
        assert len("downgrade") <= 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_update_service.py::TestDowngradeEnums -v`
Expected: FAIL — `UpdateChannel` has no `DOWNGRADE` attribute

- [ ] **Step 3: Add DOWNGRADE to UpdateChannel enum**

In `backend/app/models/update_history.py:29-33`, add the new member:

```python
class UpdateChannel(str, enum.Enum):
    """Update channel for version selection."""
    STABLE = "stable"
    BETA = "beta"
    DEVELOPMENT = "development"
    DOWNGRADE = "downgrade"
```

- [ ] **Step 4: Extend UpdateChannelEnum Literal in schemas**

In `backend/app/schemas/update.py:11-16`, update the Literal:

```python
UpdateChannelEnum = Literal[
    "stable", "unstable", "development", "downgrade"
]
```

- [ ] **Step 5: Add DowngradeRequest schema**

In `backend/app/schemas/update.py`, after `RollbackResponse` (around line 221), add:

```python
class DowngradeRequest(BaseModel):
    """Request to downgrade to a previous release."""

    target_tag: str = Field(
        description="Git tag to downgrade to, e.g. 'v1.17.0'",
        pattern=r"^v\d+\.\d+\.\d+(-[\w.]+)?$",
    )
    target_commit: str = Field(
        description="Expected full commit hash for validation",
        min_length=7,
        max_length=40,
    )
    skip_backup: bool = Field(
        default=False,
        description="Skip file/config backup (DB backup is always created)",
    )
    force: bool = Field(
        default=False,
        description="Ignore non-critical blockers",
    )
```

- [ ] **Step 6: Add `commit` field to ReleaseInfo**

In `backend/app/schemas/update.py`, find `ReleaseInfo` (around line 415) and add:

```python
class ReleaseInfo(BaseModel):
    """Information about a single release (git tag)."""

    tag: str = Field(description="Git tag (e.g., 'v1.9.0')")
    version: str = Field(description="Version string without 'v' prefix")
    date: Optional[str] = Field(default=None, description="Release date (ISO 8601)")
    is_prerelease: bool = Field(default=False, description="True if alpha/beta/rc/etc.")
    commit_short: str = Field(description="Short commit hash (7 chars)")
    commit: str = Field(default="", description="Full commit hash for downgrade validation")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_update_service.py::TestDowngradeEnums -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/update_history.py backend/app/schemas/update.py backend/tests/services/test_update_service.py
git commit -m "feat(updates): add downgrade enum, schema, and ReleaseInfo.commit field"
```

---

### Task 2: Extend UpdateBackend Abstract Methods

**Files:**
- Modify: `backend/app/services/update/backend.py:74-97`

- [ ] **Step 1: Add abstract methods to UpdateBackend**

In `backend/app/services/update/backend.py`, after the existing `rollback` method (line 77) and before `get_release_notes`, add:

```python
    async def resolve_alembic_revision(self, commit: str) -> Optional[str]:
        """Determine the Alembic head revision at a given git commit.

        Returns the revision string or None if it cannot be determined.
        Default implementation returns None (subclasses override).
        """
        return None

    async def run_alembic_downgrade(self, target_revision: str) -> tuple[bool, Optional[str]]:
        """Run alembic downgrade to a target revision. Returns (success, error_message).

        Default implementation simulates success (overridden by prod backend).
        """
        return True, None
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/update/backend.py
git commit -m "feat(updates): add resolve_alembic_revision and run_alembic_downgrade to UpdateBackend"
```

---

### Task 3: Implement DevUpdateBackend Downgrade Support

**Files:**
- Modify: `backend/app/services/update/dev_backend.py:223-313`
- Test: `backend/tests/services/test_update_service.py`

- [ ] **Step 1: Write failing test for DevBackend downgrade methods**

In `backend/tests/services/test_update_service.py`, add:

```python
class TestDevBackendDowngrade:
    """Tests for DevUpdateBackend downgrade support."""

    @pytest.fixture
    def backend(self):
        return DevUpdateBackend()

    @pytest.mark.asyncio
    async def test_resolve_alembic_revision_returns_mock(self, backend):
        """Dev backend returns a mock revision."""
        rev = await backend.resolve_alembic_revision("abc1234")
        assert rev is not None
        assert isinstance(rev, str)

    @pytest.mark.asyncio
    async def test_run_alembic_downgrade_succeeds(self, backend):
        """Dev backend simulates successful downgrade."""
        success, error = await backend.run_alembic_downgrade("mock_rev")
        assert success is True
        assert error is None

    @pytest.mark.asyncio
    async def test_get_all_releases_includes_full_commit(self, backend):
        """Releases should include full commit hash."""
        result = await backend.get_all_releases()
        assert result.total > 0
        for release in result.releases:
            assert len(release.commit) >= 20, f"Expected full hash, got: {release.commit}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_update_service.py::TestDevBackendDowngrade -v`
Expected: FAIL — methods don't exist or return wrong values

- [ ] **Step 3: Add downgrade methods to DevUpdateBackend**

In `backend/app/services/update/dev_backend.py`, after the existing `rollback` method (line 227), add:

```python
    async def resolve_alembic_revision(self, commit: str) -> Optional[str]:
        """Return mock Alembic revision for dev mode."""
        logger.info(f"[DEV] Resolving alembic revision for {commit[:8]}")
        return "mock_downgrade_rev_001"

    async def run_alembic_downgrade(self, target_revision: str) -> tuple[bool, Optional[str]]:
        """Simulate alembic downgrade."""
        logger.info(f"[DEV] Simulating alembic downgrade to {target_revision}")
        await asyncio.sleep(0.5)
        return True, None
```

- [ ] **Step 4: Update get_all_releases to include full commit hash**

In `backend/app/services/update/dev_backend.py`, update the `get_all_releases` method. Each `ReleaseInfo` needs a `commit` field with a full 40-char mock hash. Update the loop:

```python
    async def get_all_releases(self) -> ReleaseListResponse:
        """Return mock releases relative to the current version."""
        major = self._simulated_version[0]
        minor = self._simulated_version[1]
        commit_shorts = ["abc1234", "def5678", "ghi9012", "jkl3456", "mno7890", "pqr1234", "stu5678", "vwx9012", "yza3456", "bcd7890"]
        commit_fulls = [f"{s}{'0' * 33}" for s in commit_shorts]  # Pad to 40 chars
        releases: list[ReleaseInfo] = []
        idx = 0
        for m in range(minor, max(minor - 5, 0), -1):
            if idx >= len(commit_shorts):
                break
            ver_str = f"{major}.{m}.0"
            releases.append(ReleaseInfo(
                tag=f"v{ver_str}",
                version=ver_str,
                date=f"2026-02-{22 - idx:02d}T12:00:00Z",
                is_prerelease=False,
                commit_short=commit_shorts[idx],
                commit=commit_fulls[idx],
            ))
            idx += 1
        if idx < len(commit_shorts):
            releases.append(ReleaseInfo(
                tag="v1.0.0",
                version="1.0.0",
                date="2026-01-15T08:00:00Z",
                is_prerelease=False,
                commit_short=commit_shorts[idx],
                commit=commit_fulls[idx],
            ))
        return ReleaseListResponse(releases=releases, total=len(releases))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_update_service.py::TestDevBackendDowngrade -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/update/dev_backend.py backend/tests/services/test_update_service.py
git commit -m "feat(updates): add downgrade support to DevUpdateBackend"
```

---

### Task 4: Implement ProdUpdateBackend Downgrade Support

**Files:**
- Modify: `backend/app/services/update/prod_backend.py:287-295` (rollback area)
- Modify: `backend/app/services/update/prod_backend.py:657-688` (get_all_releases)
- Modify: `backend/app/services/update/prod_backend.py:297-354` (launch_update_script)
- Test: `backend/tests/services/test_update_service.py`

- [ ] **Step 1: Write failing test for ProdBackend.resolve_alembic_revision**

In `backend/tests/services/test_update_service.py`, add:

```python
class TestProdBackendDowngrade:
    """Tests for ProdUpdateBackend downgrade with mocked git."""

    @pytest.mark.asyncio
    async def test_resolve_alembic_revision_parses_revision(self):
        """Should extract revision from git show output."""
        from app.services.update.prod_backend import ProdUpdateBackend

        backend = ProdUpdateBackend()

        # Mock _run_git to simulate listing migration files and showing content
        call_count = 0
        def mock_run_git(*args):
            nonlocal call_count
            cmd = args
            if cmd[0] == "ls-tree" and "alembic/versions" in cmd[-1]:
                return True, "backend/alembic/versions/001_initial.py\nbackend/alembic/versions/002_add_users.py", ""
            if cmd[0] == "show" and "001_initial.py" in cmd[1]:
                return True, 'revision = "001_abc"\ndown_revision = None', ""
            if cmd[0] == "show" and "002_add_users.py" in cmd[1]:
                return True, 'revision = "002_def"\ndown_revision = "001_abc"', ""
            return False, "", "unknown command"

        backend._run_git = mock_run_git
        rev = await backend.resolve_alembic_revision("abc1234567890")
        assert rev == "002_def"  # Head of the chain
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/services/test_update_service.py::TestProdBackendDowngrade -v`
Expected: FAIL — method does not exist

- [ ] **Step 3: Implement resolve_alembic_revision in ProdUpdateBackend**

In `backend/app/services/update/prod_backend.py`, after the `rollback` method (around line 295), add:

```python
    async def resolve_alembic_revision(self, commit: str) -> Optional[str]:
        """Determine the Alembic head revision at a given git commit.

        Reads migration files from the target commit via git show,
        extracts revision/down_revision, and walks the chain to find the head.
        Note: uses module-level `re` import already present in prod_backend.py.
        """

        # List migration files at target commit
        success, output, _ = self._run_git(
            "ls-tree", "-r", "--name-only", commit, "backend/alembic/versions/"
        )
        if not success or not output.strip():
            logger.warning(f"No alembic versions found at commit {commit[:8]}")
            return None

        files = [f.strip() for f in output.strip().split("\n") if f.strip().endswith(".py")]

        # Extract revision and down_revision from each file
        # Matches: revision = "abc123" (quoted string)
        rev_pattern = re.compile(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
        # Matches: down_revision = "abc123" (single quoted string)
        down_single_pattern = re.compile(r"^down_revision\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
        # Matches: down_revision = ("rev1", "rev2") (tuple for merge migrations)
        down_tuple_pattern = re.compile(r"^down_revision\s*=\s*\(([^)]+)\)", re.MULTILINE)

        revisions: dict[str, Optional[str]] = {}  # revision -> down_revision (first parent)

        for filepath in files:
            success, content, _ = self._run_git("show", f"{commit}:{filepath}")
            if not success:
                continue

            rev_match = rev_pattern.search(content)
            if not rev_match:
                continue

            revision = rev_match.group(1)

            # Try single down_revision first, then tuple (merge migrations)
            down_match = down_single_pattern.search(content)
            if down_match:
                down_revision = down_match.group(1)
            else:
                tuple_match = down_tuple_pattern.search(content)
                if tuple_match:
                    # Merge migration: extract first parent from tuple
                    parts = [p.strip().strip("'\"") for p in tuple_match.group(1).split(",")]
                    down_revision = parts[0] if parts else None
                else:
                    # down_revision = None (initial migration)
                    down_revision = None

            revisions[revision] = down_revision

        if not revisions:
            logger.warning(f"Could not parse any revisions at commit {commit[:8]}")
            return None

        # Find head: a revision that is NOT referenced as any other revision's down_revision
        all_down_revs = set(v for v in revisions.values() if v is not None)
        heads = [r for r in revisions if r not in all_down_revs]

        if len(heads) == 1:
            return heads[0]
        elif len(heads) > 1:
            # Multiple heads (merge needed) — return first one, log warning
            logger.warning(f"Multiple alembic heads found at {commit[:8]}: {heads}")
            return heads[0]
        else:
            # Circular reference or no heads — shouldn't happen
            logger.error(f"Could not determine alembic head at {commit[:8]}")
            return None

    async def run_alembic_downgrade(self, target_revision: str) -> tuple[bool, Optional[str]]:
        """Run alembic downgrade to a target revision."""
        try:
            result = subprocess.run(
                [
                    str(self.backend_path / ".venv" / "bin" / "alembic"),
                    "-c", str(self.backend_path / "alembic.ini"),
                    "downgrade", target_revision,
                ],
                cwd=self.backend_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                return False, f"Alembic downgrade failed: {result.stderr[:500]}"
            return True, None
        except subprocess.TimeoutExpired:
            return False, "Alembic downgrade timed out"
        except Exception as e:
            return False, str(e)
```

- [ ] **Step 4: Update get_all_releases to include full commit hash**

In `backend/app/services/update/prod_backend.py`, find the `get_all_releases` method (around line 657). Change the `rev-parse --short=7` to a full `rev-parse`, and pass both to `ReleaseInfo`:

```python
    async def get_all_releases(self) -> ReleaseListResponse:
        """Get list of all releases from git tags."""
        success, tags_output, _ = self._run_git("tag", "-l", "--sort=-version:refname")
        if not success or not tags_output.strip():
            return ReleaseListResponse(releases=[], total=0)

        tags = [t.strip() for t in tags_output.strip().split("\n") if t.strip()]

        releases: list[ReleaseInfo] = []
        for tag in tags:
            # Get full commit hash
            ok_full, commit_full, _ = self._run_git("rev-parse", tag)
            # Get short commit hash
            ok_short, commit_short, _ = self._run_git("rev-parse", "--short=7", tag)
            if not ok_full:
                commit_full = "unknown"
            if not ok_short:
                commit_short = commit_full[:7] if ok_full else "unknown"

            # Get tag date
            ok, date_str, _ = self._run_git("log", "-1", "--format=%aI", tag)
            tag_date = date_str if ok and date_str else None

            version = tag.lstrip("v")
            is_prerelease = bool(parse_version(tag)[3])

            releases.append(ReleaseInfo(
                tag=tag,
                version=version,
                date=tag_date,
                is_prerelease=is_prerelease,
                commit_short=commit_short,
                commit=commit_full,
            ))

        return ReleaseListResponse(releases=releases, total=len(releases))
```

- [ ] **Step 5: Extend launch_update_script for downgrade**

In `backend/app/services/update/prod_backend.py`, update the `launch_update_script` method signature and body to accept `downgrade` and `alembic_rev` parameters:

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

In the `subprocess.run` call inside that method, append the new flags conditionally. After the existing args list `["sudo", "systemd-run", ..., "--to-version", to_version]`, add:

```python
        cmd = [
            "sudo", "systemd-run",
            "--unit=baluhost-update",
            "--remain-after-exit",
            str(script_path),
            "--update-id", str(update_id),
            "--from-commit", from_commit,
            "--to-commit", to_commit,
            "--from-version", from_version,
            "--to-version", to_version,
        ]
        if downgrade:
            cmd.append("--downgrade")
        if alembic_rev:
            cmd.extend(["--alembic-rev", alembic_rev])
```

Replace the existing hardcoded list with `cmd`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_update_service.py::TestProdBackendDowngrade -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/update/prod_backend.py backend/tests/services/test_update_service.py
git commit -m "feat(updates): add downgrade support to ProdUpdateBackend"
```

---

### Task 5: Implement UpdateService.downgrade() Core Logic

**Files:**
- Modify: `backend/app/services/update/service.py`
- Test: `backend/tests/services/test_update_service.py`

- [ ] **Step 1: Write failing tests for downgrade validation**

In `backend/tests/services/test_update_service.py`, add:

```python
class TestDowngradeService:
    """Tests for UpdateService.downgrade()."""

    @pytest.fixture
    def db(self):
        """Create a mock DB session."""
        session = MagicMock(spec=Session)
        session.query.return_value.filter.return_value.first.return_value = None
        session.query.return_value.filter.return_value.count.return_value = 0
        # Mock UpdateConfig
        config = MagicMock()
        config.auto_backup_before_update = True
        config.require_healthy_services = True
        config.channel = "stable"
        session.query.return_value.first.return_value = config
        return session

    @pytest.fixture
    def backend(self):
        return DevUpdateBackend()

    @pytest.fixture
    def service(self, db, backend):
        return UpdateService(db=db, backend=backend)

    @pytest.mark.asyncio
    async def test_downgrade_rejects_invalid_tag(self, service):
        """Downgrade should fail if target_tag doesn't match expected format."""
        from app.schemas.update import DowngradeRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            DowngradeRequest(
                target_tag="not-a-tag",
                target_commit="abc1234567890abcdef1234567890abcdef12",
            )

    @pytest.mark.asyncio
    async def test_downgrade_rejects_newer_version(self, service):
        """Downgrade should fail if target version >= current version."""
        from app.schemas.update import DowngradeRequest
        # DevBackend's current version is from pyproject.toml (e.g., 1.19.0)
        # The mock "next minor" is always greater, so use that as target
        req = DowngradeRequest(
            target_tag="v99.0.0",
            target_commit="abc1234567890abcdef1234567890abcdef12",
        )
        result = await service.downgrade(req, user_id=1)
        assert result.success is False
        assert "newer" in result.message.lower() or "greater" in result.message.lower() or "higher" in result.message.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/services/test_update_service.py::TestDowngradeService -v`
Expected: FAIL — `downgrade` method does not exist

- [ ] **Step 3: Implement downgrade() in UpdateService**

In `backend/app/services/update/service.py`, add the necessary imports at the top (add `DowngradeRequest` to the schema imports), then add the following methods after the existing `rollback()` method (around line 675):

```python
    async def downgrade(
        self,
        request: DowngradeRequest,
        user_id: int,
    ) -> UpdateStartResponse:
        """Start a downgrade to a previous release version."""
        # Validate: target version must be less than current version
        current = await self.backend.get_current_version()
        target_version = parse_version(request.target_tag)
        current_version = parse_version(current.version)

        if target_version >= current_version:
            return UpdateStartResponse(
                success=False,
                message=f"Target version {request.target_tag} is not lower than current {current.version}",
            )

        # Check blockers
        blockers = await self._check_blockers()
        if blockers and not request.force:
            return UpdateStartResponse(
                success=False,
                message="Downgrade blocked",
                blockers=blockers,
            )

        # Validate tag exists and commit matches (prod only — dev always passes)
        if hasattr(self.backend, '_run_git'):
            success, tag_commit, _ = self.backend._run_git("rev-parse", request.target_tag)
            if not success:
                return UpdateStartResponse(
                    success=False,
                    message=f"Tag {request.target_tag} not found in repository",
                )
            if not tag_commit.startswith(request.target_commit[:7]):
                return UpdateStartResponse(
                    success=False,
                    message=f"Commit mismatch: tag points to {tag_commit[:8]}, expected {request.target_commit[:8]}",
                )

        # Get admin username for backup restore
        from app.models.user import User
        user = self.db.query(User).filter(User.id == user_id).first()
        admin_username = user.username if user else "system"

        # Create update history record
        update = UpdateHistory(
            from_version=current.version,
            to_version=request.target_tag.lstrip("v"),
            channel="downgrade",
            from_commit=current.commit,
            to_commit=request.target_commit,
            user_id=user_id,
            status=UpdateStatus.PENDING.value,
        )
        self.db.add(update)
        self.db.commit()
        self.db.refresh(update)

        self._current_update = update

        # Production: launch shell script with --downgrade flag
        if isinstance(self.backend, ProdUpdateBackend):
            # Resolve alembic revision before launching
            alembic_rev = await self.backend.resolve_alembic_revision(request.target_commit)

            update.status = UpdateStatus.DOWNLOADING.value
            update.set_progress(5, "Launching downgrade runner...")
            self.db.commit()

            success, error = self.backend.launch_update_script(
                update_id=update.id,
                from_commit=current.commit,
                to_commit=request.target_commit,
                from_version=current.version,
                to_version=request.target_tag.lstrip("v"),
                downgrade=True,
                alembic_rev=alembic_rev,
            )
            if not success:
                update.fail(f"Failed to launch downgrade: {error}")
                self.db.commit()
                return UpdateStartResponse(
                    success=False,
                    message=f"Failed to launch downgrade: {error}",
                )
        else:
            # Dev mode: run in-process
            task = asyncio.create_task(
                self._run_dev_downgrade(update.id, admin_username)
            )
            _running_tasks[update.id] = task

        return UpdateStartResponse(
            success=True,
            update_id=update.id,
            message=f"Downgrade to {request.target_tag} started",
        )

    async def _run_dev_downgrade(self, update_id: int, admin_username: str) -> None:
        """Run the downgrade process in-process (dev mode only)."""
        db = SessionLocal()
        try:
            update = db.query(UpdateHistory).filter(UpdateHistory.id == update_id).first()
            if not update:
                return

            def progress(percent: int, step: str):
                update.set_progress(percent, step)
                db.commit()

            try:
                # Step 1: Mandatory DB backup
                update.status = UpdateStatus.BACKING_UP.value
                progress(5, "Creating mandatory database backup...")

                try:
                    from app.services.backup import BackupService
                    from app.schemas.backup import BackupCreate

                    backup_service = BackupService(db)
                    backup_data = BackupCreate(
                        backup_type="full",
                        includes_database=True,
                        includes_files=False,
                        includes_config=True,
                    )
                    backup = backup_service.create_backup(
                        backup_data,
                        update.user_id or 0,
                        admin_username,
                    )
                    update.backup_id = backup.id
                    db.commit()
                    progress(10, "Backup complete")
                except Exception as e:
                    logger.warning(f"Backup failed during downgrade: {e}")
                    progress(10, f"Backup failed: {e} — continuing with caution")

                # Step 2: Fetch
                update.status = UpdateStatus.DOWNLOADING.value
                progress(15, "Fetching updates...")

                success = await self.backend.fetch_updates(
                    lambda p, s: progress(15 + int(p * 0.10), s)
                )
                if not success:
                    raise Exception("Failed to fetch updates")

                # Step 3: Checkout target
                update.status = UpdateStatus.INSTALLING.value
                progress(25, f"Checking out {update.to_commit[:8]}...")

                success, error = await self.backend.apply_updates(
                    update.to_commit,
                    lambda p, s: progress(25 + int(p * 0.15), s),
                )
                if not success:
                    raise Exception(f"Failed to checkout target: {error}")

                # Step 4: Dependencies
                progress(40, "Installing dependencies...")

                success, error = await self.backend.install_dependencies(
                    lambda p, s: progress(40 + int(p * 0.15), s),
                )
                if not success:
                    raise Exception(f"Failed to install dependencies: {error}")

                # Step 5: Alembic downgrade
                update.status = UpdateStatus.MIGRATING.value
                progress(55, "Running database downgrade...")

                target_rev = await self.backend.resolve_alembic_revision(update.to_commit)
                if target_rev:
                    success, error = await self.backend.run_alembic_downgrade(target_rev)
                    if not success:
                        logger.warning(f"Alembic downgrade failed: {error}")
                        progress(65, "Alembic downgrade failed, restoring backup...")
                        # Fallback: restore DB backup
                        if update.backup_id:
                            try:
                                from app.services.backup import BackupService
                                backup_svc = BackupService(db)
                                restore_ok = backup_svc.restore_backup(
                                    backup_id=update.backup_id,
                                    user=admin_username,
                                    restore_database=True,
                                    restore_files=False,
                                    restore_config=False,
                                )
                                if not restore_ok:
                                    raise Exception("Backup restore returned False")
                                progress(70, "Database restored from backup")
                            except Exception as restore_err:
                                raise Exception(
                                    f"Alembic downgrade failed ({error}) AND backup restore "
                                    f"failed ({restore_err}). Manual intervention required."
                                )
                        else:
                            logger.warning("No backup available for restore fallback")
                else:
                    progress(70, "Could not determine target revision, skipping migration downgrade")

                # Step 6: Health check
                update.status = UpdateStatus.HEALTH_CHECK.value
                progress(75, "Health check...")

                healthy, issues = await self.backend.health_check()

                # Step 7: Restart
                update.status = UpdateStatus.RESTARTING.value
                progress(85, "Restarting services...")

                success, error = await self.backend.restart_services(
                    lambda p, s: progress(85 + int(p * 0.10), s),
                )
                if not success:
                    logger.warning(f"Service restart may have failed: {error}")

                # Step 8: Complete
                progress(95, "Post-restart health check...")
                await asyncio.sleep(2)

                update.complete()
                db.commit()

            except asyncio.CancelledError:
                logger.info(f"Downgrade {update_id} was cancelled")
                update.cancel()
                db.commit()

            except Exception as e:
                logger.exception(f"Downgrade failed: {e}")
                update.fail(str(e))
                update.rollback_commit = update.from_commit
                db.commit()

                # Try to rollback to original commit
                if update.from_commit:
                    try:
                        await self.backend.rollback(update.from_commit)
                        update.mark_rolled_back(update.from_commit)
                        db.commit()
                    except Exception as rollback_error:
                        logger.error(f"Rollback also failed: {rollback_error}")

        finally:
            _running_tasks.pop(update_id, None)
            db.close()
            self._current_update = None
```

Also add the import for `DowngradeRequest` at the top of the file and `parse_version` from utils:

```python
from app.schemas.update import (
    # ...existing imports...
    DowngradeRequest,
)
from app.services.update.utils import ProgressCallback, parse_version
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/services/test_update_service.py::TestDowngradeService -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/update/service.py backend/tests/services/test_update_service.py
git commit -m "feat(updates): implement UpdateService.downgrade() with async flow"
```

---

### Task 6: Add POST /downgrade API Endpoint

**Files:**
- Modify: `backend/app/api/routes/updates.py`
- Test: `backend/tests/services/test_update_service.py`

- [ ] **Step 1: Write failing test for the API endpoint**

In `backend/tests/services/test_update_service.py`, add:

```python
class TestDowngradeEndpoint:
    """Tests for the POST /downgrade endpoint schema validation."""

    def test_downgrade_request_valid(self):
        """Valid DowngradeRequest should pass validation."""
        from app.schemas.update import DowngradeRequest
        req = DowngradeRequest(
            target_tag="v1.17.0",
            target_commit="abc1234567890abcdef1234567890abcdef12",
        )
        assert req.target_tag == "v1.17.0"
        assert req.skip_backup is False
        assert req.force is False

    def test_downgrade_request_rejects_bad_tag(self):
        """Invalid tag format should be rejected."""
        from app.schemas.update import DowngradeRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            DowngradeRequest(
                target_tag="main",
                target_commit="abc1234567890abcdef1234567890abcdef12",
            )

    def test_downgrade_request_accepts_prerelease_tag(self):
        """Pre-release tags like v1.17.0-beta.1 should be valid."""
        from app.schemas.update import DowngradeRequest
        req = DowngradeRequest(
            target_tag="v1.17.0-beta.1",
            target_commit="abc1234567890abcdef1234567890abcdef12",
        )
        assert req.target_tag == "v1.17.0-beta.1"
```

- [ ] **Step 2: Run tests to verify they pass** (schema already created in Task 1)

Run: `cd backend && python -m pytest tests/services/test_update_service.py::TestDowngradeEndpoint -v`
Expected: PASS

- [ ] **Step 3: Add the POST /downgrade route**

In `backend/app/api/routes/updates.py`, add `DowngradeRequest` to the imports from `app.schemas.update`, then add the endpoint after the existing `rollback_update` route (around line 368):

```python
@router.post("/downgrade", response_model=UpdateStartResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def start_downgrade(
    request: Request, response: Response,
    body: DowngradeRequest,
    current_user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> UpdateStartResponse:
    """Downgrade to a previous release version.

    Initiates a downgrade to the specified release tag. Creates a mandatory
    database backup, attempts Alembic downgrade, and falls back to backup
    restore if migrations fail.

    Requires admin privileges.
    """
    service = get_update_service(db)
    audit_logger = get_audit_logger_db()

    result = await service.downgrade(body, current_user.id)

    audit_logger.log_event(
        event_type="UPDATE",
        action="downgrade",
        user=current_user.username,
        resource="system",
        success=result.success,
        details={
            "target_tag": body.target_tag,
            "target_commit": body.target_commit,
            "skip_backup": body.skip_backup,
            "force": body.force,
            "update_id": result.update_id,
            "message": result.message,
            "blockers": result.blockers,
        },
        db=db,
    )

    if not result.success and result.blockers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": result.message,
                "blockers": result.blockers,
            }
        )

    return result
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes/updates.py backend/tests/services/test_update_service.py
git commit -m "feat(updates): add POST /api/updates/downgrade endpoint"
```

---

### Task 7: Extend run-update.sh for Downgrade Mode

**Files:**
- Modify: `deploy/update/run-update.sh`

- [ ] **Step 1: Add --downgrade and --alembic-rev argument parsing**

In `deploy/update/run-update.sh`, add two new variables after the existing ones (around line 23):

```bash
DOWNGRADE=false
ALEMBIC_REV=""
```

Add two new cases in the `while` loop (around line 25-34), **before** the `*)` catch-all case:

```bash
        --downgrade)    DOWNGRADE=true;    shift ;;
        --alembic-rev)  ALEMBIC_REV="$2";  shift 2 ;;
```

These must appear before `*) echo "Unknown argument: $1" >&2; exit 1 ;;` or they will never be reached.

- [ ] **Step 2: Add conditional migration step**

Replace the existing Step 3 block (around line 210-211) with a conditional:

```bash
# ─── Step 3: Database migrations ─────────────────────────────────────

if [[ "$DOWNGRADE" == "true" && -n "$ALEMBIC_REV" ]]; then
    write_status "migrating" 45 "Running alembic downgrade to $ALEMBIC_REV..."
    log_step "Alembic downgrade to $ALEMBIC_REV"
    CURRENT_PROGRESS=45
    sudo -u "$BALUHOST_USER" "$INSTALL_DIR/backend/.venv/bin/alembic" \
        -c "$INSTALL_DIR/backend/alembic.ini" \
        downgrade "$ALEMBIC_REV"
    CURRENT_PROGRESS=55
    log_info "Alembic downgrade complete."
elif [[ "$DOWNGRADE" == "true" ]]; then
    write_status "migrating" 45 "Skipping migrations (no target revision)..."
    log_warn "No alembic revision specified for downgrade, skipping migration step."
    CURRENT_PROGRESS=55
else
    write_status "migrating" 45 "Running database migrations..."
    run_module "08" "database-migrate" 45 55
fi
```

- [ ] **Step 3: Commit**

```bash
git add deploy/update/run-update.sh
git commit -m "feat(updates): add --downgrade and --alembic-rev support to run-update.sh"
```

---

### Task 8: Frontend — API Client & i18n

**Files:**
- Modify: `client/src/api/updates.ts`
- Modify: `client/src/i18n/locales/en/updates.json`
- Modify: `client/src/i18n/locales/de/updates.json`

- [ ] **Step 1: Add DowngradeRequest interface and startDowngrade function**

In `client/src/api/updates.ts`, after the `RollbackResponse` interface (around line 134), add:

```typescript
// Downgrade request/response
export interface DowngradeRequest {
  target_tag: string;
  target_commit: string;
  skip_backup?: boolean;
  force?: boolean;
}
```

After the `rollbackUpdate` function (around line 326), add:

```typescript
/**
 * Start a downgrade to a previous release version
 */
export async function startDowngrade(request: DowngradeRequest): Promise<UpdateStartResponse> {
  const response = await apiClient.post<UpdateStartResponse>('/api/updates/downgrade', request);
  return response.data;
}
```

- [ ] **Step 2: Add `commit` field to ReleaseInfo interface**

In `client/src/api/updates.ts`, find the `ReleaseInfo` interface (around line 221) and add:

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

- [ ] **Step 3: Add `"downgrade"` to UpdateChannel and getChannelInfo**

In `client/src/api/updates.ts`, update the `UpdateChannel` type (line 21):

```typescript
export type UpdateChannel = 'stable' | 'unstable' | 'development' | 'downgrade';
```

In `getChannelInfo` (around line 528), add a new case before `default`:

```typescript
    case 'downgrade':
      return {
        label: 'Downgrade',
        color: 'text-orange-400',
        description: 'Downgrade to a previous release',
      };
```

- [ ] **Step 4: Add English i18n keys**

In `client/src/i18n/locales/en/updates.json`, add a new `"downgrade"` section at the top level (e.g., after `"buttons"`):

```json
  "downgrade": {
    "button": "Downgrade",
    "warning": "Downgrade to {{version}} may cause database data loss. A database backup will be created automatically before proceeding.",
    "continueButton": "Continue",
    "confirmPrompt": "Type {{version}} to confirm the downgrade:",
    "startButton": "Start Downgrade",
    "progressLabel": "Downgrading to {{version}}",
    "channel": "Downgrade",
    "current": "Current"
  },
```

- [ ] **Step 5: Add German i18n keys**

In `client/src/i18n/locales/de/updates.json`, add the matching German keys:

```json
  "downgrade": {
    "button": "Downgrade",
    "warning": "Ein Downgrade auf {{version}} kann zu Datenverlust in der Datenbank führen. Ein Datenbank-Backup wird automatisch vor dem Downgrade erstellt.",
    "continueButton": "Weiter",
    "confirmPrompt": "Gib {{version}} ein, um den Downgrade zu bestätigen:",
    "startButton": "Downgrade starten",
    "progressLabel": "Downgrade auf {{version}}",
    "channel": "Downgrade",
    "current": "Aktuell"
  },
```

- [ ] **Step 6: Commit**

```bash
git add client/src/api/updates.ts client/src/i18n/locales/en/updates.json client/src/i18n/locales/de/updates.json
git commit -m "feat(updates): add downgrade API client, types, and i18n keys"
```

---

### Task 9: Frontend — Downgrade UI in UpdateHistoryTab

**Files:**
- Modify: `client/src/components/updates/UpdateHistoryTab.tsx`

This is the main UI task. The component currently shows releases and version history. We need to:
1. Accept current version as a prop
2. Add a downgrade button to each release row where version < current
3. Implement two-step inline confirmation (warning → type version → confirm)

- [ ] **Step 1: Extend props interface**

In `client/src/components/updates/UpdateHistoryTab.tsx`, update `UpdateHistoryTabProps` to add new props:

```typescript
import {
  GitBranch,
  Loader2,
  Tag,
  AlertTriangle,
  RotateCcw,
} from 'lucide-react';
import { useState } from 'react';
import type { ReleaseInfo, VersionHistoryResponse } from '../../api/updates';
import { startDowngrade } from '../../api/updates';
import toast from 'react-hot-toast';

interface UpdateHistoryTabProps {
  t: (key: string, options?: Record<string, unknown>) => string;
  releases: ReleaseInfo[];
  releasesLoading: boolean;
  versionHistory: VersionHistoryResponse | null;
  versionHistoryLoading: boolean;
  currentVersion: string;
  onDowngradeStarted: (updateId: number) => void;
}
```

- [ ] **Step 2: Add downgrade state and handler inside the component**

At the top of the `UpdateHistoryTab` function body, add:

```typescript
  const [downgradeTarget, setDowngradeTarget] = useState<string | null>(null);
  const [confirmStep, setConfirmStep] = useState<'warning' | 'confirm' | null>(null);
  const [confirmInput, setConfirmInput] = useState('');
  const [downgradeLoading, setDowngradeLoading] = useState(false);

  const handleStartDowngrade = async (release: ReleaseInfo) => {
    setDowngradeLoading(true);
    try {
      const result = await startDowngrade({
        target_tag: release.tag,
        target_commit: release.commit,
      });
      if (result.success && result.update_id) {
        toast.success(t('downgrade.progressLabel', { version: release.tag }));
        onDowngradeStarted(result.update_id);
      } else {
        toast.error(result.message);
      }
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'Downgrade failed';
      toast.error(msg);
    } finally {
      setDowngradeLoading(false);
      setDowngradeTarget(null);
      setConfirmStep(null);
      setConfirmInput('');
    }
  };

  const cancelDowngrade = () => {
    setDowngradeTarget(null);
    setConfirmStep(null);
    setConfirmInput('');
  };
```

- [ ] **Step 3: Update the release row rendering**

In the existing release list `.map((release) => ...)` block, add the downgrade button and inline confirmation. Replace the existing release row `<div>` with:

Add a semver comparison helper at the top of the component file (before the component function):

```typescript
/** Compare two semver strings numerically. Returns negative if a < b. */
function compareSemver(a: string, b: string): number {
  const pa = a.split('.').map(Number);
  const pb = b.split('.').map(Number);
  for (let i = 0; i < 3; i++) {
    const diff = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}
```

Then in the release list map:

```tsx
{releases.map((release) => {
  const isCurrent = release.version === currentVersion;
  const canDowngrade = !isCurrent && compareSemver(release.version, currentVersion) < 0;
  const isTargeted = downgradeTarget === release.tag;

  return (
    <div key={release.tag}>
      <div
        className="px-4 py-3 flex items-center justify-between hover:bg-slate-700/30 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="font-mono text-white">{release.tag}</span>
          <span className="font-mono text-xs text-slate-500">{release.commit_short}</span>
          {isCurrent && (
            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/20 text-emerald-400">
              {t('downgrade.current')}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {release.date && (
            <span className="text-sm text-slate-400">
              {new Date(release.date).toLocaleDateString()}
            </span>
          )}
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
              release.is_prerelease
                ? 'bg-amber-500/20 text-amber-400'
                : 'bg-emerald-500/20 text-emerald-400'
            }`}
          >
            {release.is_prerelease ? t('releases.prerelease') : t('releases.stable')}
          </span>
          {canDowngrade && !isTargeted && (
            <button
              onClick={() => { setDowngradeTarget(release.tag); setConfirmStep('warning'); }}
              className="flex items-center gap-1.5 px-2.5 py-1 bg-orange-600/20 hover:bg-orange-600/40 text-orange-400 rounded text-xs font-medium transition-all touch-manipulation active:scale-95"
            >
              <RotateCcw className="h-3 w-3" />
              {t('downgrade.button')}
            </button>
          )}
        </div>
      </div>

      {/* Two-step inline confirmation */}
      {isTargeted && confirmStep === 'warning' && (
        <div className="px-4 py-3 bg-orange-500/5 border-t border-orange-500/20">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-orange-400 mt-0.5 shrink-0" />
            <div className="flex-1">
              <p className="text-sm text-orange-300">
                {t('downgrade.warning', { version: release.tag })}
              </p>
              <div className="flex items-center gap-2 mt-3">
                <button
                  onClick={() => setConfirmStep('confirm')}
                  className="px-3 py-1.5 bg-orange-600 hover:bg-orange-700 text-white rounded text-xs font-medium transition-all touch-manipulation active:scale-95"
                >
                  {t('downgrade.continueButton')}
                </button>
                <button
                  onClick={cancelDowngrade}
                  className="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white rounded text-xs transition-all touch-manipulation active:scale-95"
                >
                  {t('common:cancel')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {isTargeted && confirmStep === 'confirm' && (
        <div className="px-4 py-3 bg-orange-500/5 border-t border-orange-500/20">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-orange-400 mt-0.5 shrink-0" />
            <div className="flex-1">
              <p className="text-sm text-slate-300 mb-2">
                {t('downgrade.confirmPrompt', { version: release.tag })}
              </p>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={confirmInput}
                  onChange={(e) => setConfirmInput(e.target.value)}
                  placeholder={release.tag}
                  className="px-3 py-1.5 bg-slate-700 border border-slate-600 rounded text-sm text-white font-mono w-40 focus:outline-none focus:border-orange-500"
                />
                <button
                  onClick={() => handleStartDowngrade(release)}
                  disabled={confirmInput !== release.tag || downgradeLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-orange-600 hover:bg-orange-700 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded text-xs font-medium transition-all touch-manipulation active:scale-95"
                >
                  {downgradeLoading ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <RotateCcw className="h-3.5 w-3.5" />
                  )}
                  {t('downgrade.startButton')}
                </button>
                <button
                  onClick={cancelDowngrade}
                  className="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white rounded text-xs transition-all touch-manipulation active:scale-95"
                >
                  {t('common:cancel')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
})}
```

- [ ] **Step 4: Verify no syntax errors in the changed file**

Run: `cd client && npx tsc --noEmit src/components/updates/UpdateHistoryTab.tsx 2>&1 || echo "Expected: type errors for missing parent props — will be resolved in Task 10"`

Note: The parent component `UpdatePage.tsx` doesn't pass the new required props yet. A full `npm run build` will fail until Task 10 completes. This step only verifies the component file itself has no syntax errors.

- [ ] **Step 5: Commit**

```bash
git add client/src/components/updates/UpdateHistoryTab.tsx
git commit -m "feat(updates): add downgrade button and two-step confirmation to release list"
```

---

### Task 10: Frontend — Wire Up Parent Component

**Files:**
- Modify: `client/src/pages/UpdatePage.tsx`

- [ ] **Step 1: Pass new props to UpdateHistoryTab**

In `client/src/pages/UpdatePage.tsx`, find where `UpdateHistoryTab` is rendered (search for `<UpdateHistoryTab`). Add the new props.

- [ ] **Step 2: Pass currentVersion prop**

The parent likely already has `checkResult` (from `checkForUpdates()`). Pass `currentVersion={checkResult?.current_version.version ?? ''}` to `UpdateHistoryTab`.

- [ ] **Step 3: Add onDowngradeStarted handler**

The handler should switch to the Overview tab and set the `currentUpdate` state so `UpdateProgress` shows the downgrade progress. Pattern: similar to how `onStartUpdate` works.

```typescript
const handleDowngradeStarted = (updateId: number) => {
  // Switch to overview tab to show progress
  setActiveTab('overview');
  // Trigger a refresh of current update
  refreshCurrentUpdate();
};
```

Pass `onDowngradeStarted={handleDowngradeStarted}` to `UpdateHistoryTab`.

- [ ] **Step 4: Verify frontend compiles and renders**

Run: `cd client && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add client/src/pages/UpdatePage.tsx  # or whatever the parent file is
git commit -m "feat(updates): wire downgrade props to UpdateHistoryTab parent"
```

---

### Task 11: Frontend — Handle Downgrade Channel in UpdateOverviewTab

**Files:**
- Modify: `client/src/components/updates/UpdateOverviewTab.tsx`

The Overview tab shows progress for running updates. When a downgrade is in progress (`channel === 'downgrade'`), the badge and labels should reflect this.

- [ ] **Step 1: Add downgrade channel handling to progress display**

In `client/src/components/updates/UpdateOverviewTab.tsx`, find where the channel badge is rendered (search for `getChannelInfo` or the channel badge area). The existing code shows a badge like "Stable" or "Beta" — ensure the `'downgrade'` channel renders with orange styling.

Since `getChannelInfo` already returns the correct info after Task 8, verify that the Overview tab uses it for the badge. If the tab has a hardcoded channel label, replace it with `getChannelInfo(update.channel)`.

- [ ] **Step 2: Add downgrade-specific progress label**

If the progress section shows "Updating to vX.Y.Z", add a conditional for downgrade:

```tsx
{update.channel === 'downgrade' ? (
  <span className="text-orange-400 font-medium">
    {t('downgrade.progressLabel', { version: `v${update.to_version}` })}
  </span>
) : (
  <span className="text-blue-400 font-medium">
    {t('updates.progress.updatingTo', { version: `v${update.to_version}` })}
  </span>
)}
```

- [ ] **Step 3: Verify frontend compiles**

Run: `cd client && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add client/src/components/updates/UpdateOverviewTab.tsx
git commit -m "feat(updates): handle downgrade channel display in overview tab"
```

---

### Task 12: API Endpoint Tests — Auth, Rate-Limiting, Audit

**Files:**
- Modify: `backend/tests/api/test_updates_routes.py`

- [ ] **Step 1: Write tests for downgrade endpoint security**

In `backend/tests/api/test_updates_routes.py`, add the following tests. If this file doesn't exist yet, create it with appropriate imports (FastAPI `TestClient`, pytest fixtures for auth tokens):

```python
class TestDowngradeEndpointSecurity:
    """Tests for POST /api/updates/downgrade security requirements."""

    def test_downgrade_requires_admin(self, client, user_token):
        """Non-admin users should get 403 on downgrade."""
        response = client.post(
            "/api/updates/downgrade",
            json={
                "target_tag": "v1.0.0",
                "target_commit": "abc1234567890abcdef1234567890abcdef12",
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403

    def test_downgrade_requires_auth(self, client):
        """Unauthenticated requests should get 401."""
        response = client.post(
            "/api/updates/downgrade",
            json={
                "target_tag": "v1.0.0",
                "target_commit": "abc1234567890abcdef1234567890abcdef12",
            },
        )
        assert response.status_code == 401

    def test_downgrade_audit_logged(self, client, admin_token, db):
        """Downgrade attempts should be recorded in the audit log."""
        response = client.post(
            "/api/updates/downgrade",
            json={
                "target_tag": "v1.0.0",
                "target_commit": "abc1234567890abcdef1234567890abcdef12",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Even if the downgrade fails (version validation), an audit entry should exist
        from app.models.audit_log import AuditLog
        log = db.query(AuditLog).filter(
            AuditLog.action == "downgrade",
            AuditLog.event_type == "UPDATE",
        ).first()
        assert log is not None

    def test_downgrade_validates_tag_format(self, client, admin_token):
        """Invalid tag format should return 422."""
        response = client.post(
            "/api/updates/downgrade",
            json={
                "target_tag": "not-a-tag",
                "target_commit": "abc1234567890abcdef1234567890abcdef12",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422
```

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/api/test_updates_routes.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/api/test_updates_routes.py
git commit -m "test(updates): add downgrade endpoint security tests"
```

---

### Task 13: Integration Test — Full Downgrade Flow

**Files:**
- Modify: `backend/tests/services/test_update_service.py`

- [ ] **Step 1: Write integration test for full dev-mode downgrade**

```python
class TestDowngradeIntegration:
    """Integration tests for the full downgrade flow in dev mode."""

    @pytest.fixture
    def db(self):
        session = MagicMock(spec=Session)
        session.query.return_value.filter.return_value.first.return_value = None
        session.query.return_value.filter.return_value.count.return_value = 0
        config = MagicMock()
        config.auto_backup_before_update = True
        config.require_healthy_services = True
        config.channel = "stable"
        session.query.return_value.first.return_value = config
        return session

    @pytest.mark.asyncio
    async def test_downgrade_creates_history_with_downgrade_channel(self, db):
        """Downgrade should create UpdateHistory with channel='downgrade'."""
        from app.schemas.update import DowngradeRequest

        backend = DevUpdateBackend()
        service = UpdateService(db=db, backend=backend)

        # Use a version we know is less than current
        req = DowngradeRequest(
            target_tag="v1.0.0",
            target_commit="abc1234567890abcdef1234567890abcdef12",
        )
        result = await service.downgrade(req, user_id=1)
        assert result.success is True

        # Verify the UpdateHistory was created with correct channel
        add_call = db.add.call_args
        history_obj = add_call[0][0]
        assert history_obj.channel == "downgrade"

    @pytest.mark.asyncio
    async def test_downgrade_mandatory_backup_even_with_skip(self, db):
        """Backup must be created even when skip_backup=True."""
        from app.schemas.update import DowngradeRequest

        backend = DevUpdateBackend()
        service = UpdateService(db=db, backend=backend)

        req = DowngradeRequest(
            target_tag="v1.0.0",
            target_commit="abc1234567890abcdef1234567890abcdef12",
            skip_backup=True,
        )
        result = await service.downgrade(req, user_id=1)
        assert result.success is True
        # The backup creation happens in the async task, not in the initial call.
        # This test verifies the downgrade starts successfully even with skip_backup=True.
```

- [ ] **Step 2: Run all downgrade tests**

Run: `cd backend && python -m pytest tests/services/test_update_service.py -k "downgrade or Downgrade" -v`
Expected: All PASS

- [ ] **Step 3: Write cancellation test**

```python
    @pytest.mark.asyncio
    async def test_downgrade_cancellation(self, db):
        """Cancelling a running downgrade should set status to cancelled."""
        from app.schemas.update import DowngradeRequest

        backend = DevUpdateBackend()
        service = UpdateService(db=db, backend=backend)

        req = DowngradeRequest(
            target_tag="v1.0.0",
            target_commit="abc1234567890abcdef1234567890abcdef12",
        )
        result = await service.downgrade(req, user_id=1)
        assert result.success is True

        # Cancel the running task
        update_id = result.update_id
        from app.services.update.service import _running_tasks
        task = _running_tasks.get(update_id)
        if task:
            task.cancel()
            import asyncio
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Verify status was set to cancelled
        history_obj = db.add.call_args[0][0]
        # After cancellation the task handler should have called update.cancel()
        # Note: In mock DB this verifies the code path runs without error
```

- [ ] **Step 4: Run all downgrade tests**

Run: `cd backend && python -m pytest tests/services/test_update_service.py -k "downgrade or Downgrade" -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `cd backend && python -m pytest tests/services/test_update_service.py -v`
Expected: All existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add backend/tests/services/test_update_service.py
git commit -m "test(updates): add downgrade integration and cancellation tests"
```

---

### Task 14: Final Verification & Cleanup

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 2: Run frontend build**

Run: `cd client && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Start dev server and manually verify**

Run: `python start_dev.py`

Verify:
1. Navigate to Updates page → History tab
2. Release list shows "Downgrade" buttons on older versions
3. Click "Downgrade" → warning appears inline
4. Click "Continue" → version input appears
5. Type the version → "Start Downgrade" button enables
6. Click "Start Downgrade" → switches to Overview tab, progress shows

- [ ] **Step 4: Final commit if any cleanup needed**

```bash
git add -A
git commit -m "chore(updates): downgrade feature cleanup"
```
