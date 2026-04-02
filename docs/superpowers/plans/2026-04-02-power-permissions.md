# Power Permissions Delegation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow admins to grant normal users granular power permissions (soft sleep, wake, suspend, WoL) that they can use via the mobile app.

**Architecture:** New `user_power_permissions` table with per-user boolean permissions. A new FastAPI dependency `get_power_authorized_user` replaces `get_current_admin` on sleep endpoints, allowing authorized non-admin users through. Admin configures permissions via the user edit form in SettingsPage. Implication logic (soft_sleep implies wake, suspend implies wol) enforced in the service layer.

**Tech Stack:** Python/FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, React/TypeScript, Tailwind CSS

---

### Task 1: Model + Schema + Migration

**Files:**
- Create: `backend/app/models/power_permissions.py`
- Create: `backend/app/schemas/power_permissions.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create the SQLAlchemy model**

Create `backend/app/models/power_permissions.py`:

```python
"""Database model for user power permissions."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class UserPowerPermission(Base):
    """Per-user power action permissions, granted by an admin."""

    __tablename__ = "user_power_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    can_soft_sleep: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    can_wake: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    can_suspend: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    can_wol: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")

    granted_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    granted_by_user = relationship("User", foreign_keys=[granted_by])
```

- [ ] **Step 2: Create the Pydantic schemas**

Create `backend/app/schemas/power_permissions.py`:

```python
"""Pydantic schemas for user power permissions."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserPowerPermissionsResponse(BaseModel):
    """Response schema for power permissions."""

    user_id: int
    can_soft_sleep: bool = False
    can_wake: bool = False
    can_suspend: bool = False
    can_wol: bool = False
    granted_by: Optional[int] = None
    granted_by_username: Optional[str] = None
    granted_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserPowerPermissionsUpdate(BaseModel):
    """Request schema for updating power permissions."""

    can_soft_sleep: Optional[bool] = Field(default=None, description="Allow entering soft sleep")
    can_wake: Optional[bool] = Field(default=None, description="Allow waking from soft sleep")
    can_suspend: Optional[bool] = Field(default=None, description="Allow system suspend")
    can_wol: Optional[bool] = Field(default=None, description="Allow sending Wake-on-LAN")


class MyPowerPermissionsResponse(BaseModel):
    """Response for the user's own power permissions (used by mobile app)."""

    can_soft_sleep: bool = False
    can_wake: bool = False
    can_suspend: bool = False
    can_wol: bool = False
```

- [ ] **Step 3: Register the model in `__init__.py`**

In `backend/app/models/__init__.py`, add the import and `__all__` entry:

```python
# Add import after the existing FritzBoxConfig import:
from app.models.power_permissions import UserPowerPermission

# Add to __all__ list:
"UserPowerPermission",
```

- [ ] **Step 4: Create the Alembic migration**

Run:
```bash
cd backend && alembic revision --autogenerate -m "add user_power_permissions table"
```

Expected: A new migration file in `alembic/versions/` that creates the `user_power_permissions` table.

- [ ] **Step 5: Apply the migration**

Run:
```bash
cd backend && alembic upgrade head
```

Expected: Migration applies successfully.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/power_permissions.py backend/app/schemas/power_permissions.py backend/app/models/__init__.py backend/alembic/versions/*_add_user_power_permissions_table.py
git commit -m "feat(power): add UserPowerPermission model, schemas, and migration"
```

---

### Task 2: Service Layer

**Files:**
- Create: `backend/app/services/power_permissions.py`

- [ ] **Step 1: Write the test file**

Create `backend/tests/services/test_power_permissions.py`:

```python
"""Tests for power permissions service."""

import pytest
from sqlalchemy.orm import Session

from app.models.power_permissions import UserPowerPermission
from app.models.user import User
from app.schemas.power_permissions import UserPowerPermissionsUpdate
from app.services.power_permissions import (
    get_permissions,
    update_permissions,
    check_permission,
)


@pytest.fixture
def regular_user(db_session: Session) -> User:
    """Create a regular user for testing."""
    from app.services import users as user_service
    from app.schemas.user import UserCreate

    existing = user_service.get_user_by_username("testuser", db=db_session)
    if existing:
        return existing
    return user_service.create_user(
        UserCreate(username="testuser", email="test@test.com", password="Test1234", role="user"),
        db=db_session,
    )


@pytest.fixture
def admin_user(db_session: Session) -> User:
    """Create an admin user for testing."""
    from app.services import users as user_service
    from app.schemas.user import UserCreate
    from app.core.config import settings

    existing = user_service.get_user_by_username(settings.admin_username, db=db_session)
    if existing:
        return existing
    return user_service.create_user(
        UserCreate(
            username=settings.admin_username,
            email=settings.admin_email,
            password=settings.admin_password,
            role="admin",
        ),
        db=db_session,
    )


class TestGetPermissions:
    def test_returns_defaults_when_no_entry(self, db_session: Session, regular_user: User):
        result = get_permissions(db_session, regular_user.id)
        assert result.user_id == regular_user.id
        assert result.can_soft_sleep is False
        assert result.can_wake is False
        assert result.can_suspend is False
        assert result.can_wol is False
        assert result.granted_by is None

    def test_returns_existing_permissions(self, db_session: Session, regular_user: User):
        perm = UserPowerPermission(
            user_id=regular_user.id,
            can_soft_sleep=True,
            can_wake=True,
            can_suspend=False,
            can_wol=False,
            granted_by=None,
        )
        db_session.add(perm)
        db_session.commit()

        result = get_permissions(db_session, regular_user.id)
        assert result.can_soft_sleep is True
        assert result.can_wake is True
        assert result.can_suspend is False


class TestUpdatePermissions:
    def test_creates_entry_if_none_exists(self, db_session: Session, regular_user: User, admin_user: User):
        update = UserPowerPermissionsUpdate(can_soft_sleep=True)
        result = update_permissions(db_session, regular_user.id, update, granted_by=admin_user.id)

        assert result.can_soft_sleep is True
        assert result.can_wake is True  # implied by soft_sleep
        assert result.granted_by == admin_user.id

    def test_soft_sleep_implies_wake(self, db_session: Session, regular_user: User, admin_user: User):
        update = UserPowerPermissionsUpdate(can_soft_sleep=True, can_wake=False)
        result = update_permissions(db_session, regular_user.id, update, granted_by=admin_user.id)

        assert result.can_soft_sleep is True
        assert result.can_wake is True  # implication overrides explicit False

    def test_suspend_implies_wol(self, db_session: Session, regular_user: User, admin_user: User):
        update = UserPowerPermissionsUpdate(can_suspend=True)
        result = update_permissions(db_session, regular_user.id, update, granted_by=admin_user.id)

        assert result.can_suspend is True
        assert result.can_wol is True  # implied by suspend

    def test_disable_wake_disables_soft_sleep(self, db_session: Session, regular_user: User, admin_user: User):
        # First grant both
        update_permissions(
            db_session, regular_user.id,
            UserPowerPermissionsUpdate(can_soft_sleep=True),
            granted_by=admin_user.id,
        )
        # Now disable wake
        result = update_permissions(
            db_session, regular_user.id,
            UserPowerPermissionsUpdate(can_wake=False),
            granted_by=admin_user.id,
        )
        assert result.can_wake is False
        assert result.can_soft_sleep is False  # reverse implication

    def test_disable_wol_disables_suspend(self, db_session: Session, regular_user: User, admin_user: User):
        update_permissions(
            db_session, regular_user.id,
            UserPowerPermissionsUpdate(can_suspend=True),
            granted_by=admin_user.id,
        )
        result = update_permissions(
            db_session, regular_user.id,
            UserPowerPermissionsUpdate(can_wol=False),
            granted_by=admin_user.id,
        )
        assert result.can_wol is False
        assert result.can_suspend is False

    def test_updates_existing_entry(self, db_session: Session, regular_user: User, admin_user: User):
        update_permissions(
            db_session, regular_user.id,
            UserPowerPermissionsUpdate(can_soft_sleep=True),
            granted_by=admin_user.id,
        )
        result = update_permissions(
            db_session, regular_user.id,
            UserPowerPermissionsUpdate(can_suspend=True),
            granted_by=admin_user.id,
        )
        assert result.can_soft_sleep is True
        assert result.can_suspend is True
        assert result.can_wake is True
        assert result.can_wol is True


class TestCheckPermission:
    def test_returns_false_when_no_entry(self, db_session: Session, regular_user: User):
        assert check_permission(db_session, regular_user.id, "soft_sleep") is False

    def test_returns_true_when_granted(self, db_session: Session, regular_user: User, admin_user: User):
        update_permissions(
            db_session, regular_user.id,
            UserPowerPermissionsUpdate(can_soft_sleep=True),
            granted_by=admin_user.id,
        )
        assert check_permission(db_session, regular_user.id, "soft_sleep") is True
        assert check_permission(db_session, regular_user.id, "wake") is True
        assert check_permission(db_session, regular_user.id, "suspend") is False

    def test_returns_false_for_unknown_action(self, db_session: Session, regular_user: User):
        assert check_permission(db_session, regular_user.id, "reboot") is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd backend && python -m pytest tests/services/test_power_permissions.py -v
```

Expected: ImportError — `power_permissions` module does not exist yet.

- [ ] **Step 3: Implement the service**

Create `backend/app/services/power_permissions.py`:

```python
"""Service for managing per-user power permissions."""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.power_permissions import UserPowerPermission
from app.schemas.power_permissions import (
    UserPowerPermissionsResponse,
    UserPowerPermissionsUpdate,
)
from app.services.audit.logger_db import get_audit_logger_db

logger = logging.getLogger(__name__)

_ACTION_FIELD_MAP = {
    "soft_sleep": "can_soft_sleep",
    "wake": "can_wake",
    "suspend": "can_suspend",
    "wol": "can_wol",
}


def get_permissions(db: Session, user_id: int) -> UserPowerPermissionsResponse:
    """Get power permissions for a user. Returns defaults if no entry exists."""
    perm = db.query(UserPowerPermission).filter(
        UserPowerPermission.user_id == user_id
    ).first()

    if not perm:
        return UserPowerPermissionsResponse(user_id=user_id)

    granted_by_username = None
    if perm.granted_by:
        from app.models.user import User
        admin = db.query(User).filter(User.id == perm.granted_by).first()
        if admin:
            granted_by_username = admin.username

    return UserPowerPermissionsResponse(
        user_id=perm.user_id,
        can_soft_sleep=perm.can_soft_sleep,
        can_wake=perm.can_wake,
        can_suspend=perm.can_suspend,
        can_wol=perm.can_wol,
        granted_by=perm.granted_by,
        granted_by_username=granted_by_username,
        granted_at=perm.granted_at,
    )


def _apply_implications(
    can_soft_sleep: bool,
    can_wake: bool,
    can_suspend: bool,
    can_wol: bool,
) -> tuple[bool, bool, bool, bool]:
    """Apply implication rules to permissions.

    Forward: soft_sleep → wake, suspend → wol
    Reverse: !wake → !soft_sleep, !wol → !suspend
    """
    if can_soft_sleep:
        can_wake = True
    if can_suspend:
        can_wol = True
    if not can_wake:
        can_soft_sleep = False
    if not can_wol:
        can_suspend = False
    return can_soft_sleep, can_wake, can_suspend, can_wol


def update_permissions(
    db: Session,
    user_id: int,
    update: UserPowerPermissionsUpdate,
    granted_by: int,
) -> UserPowerPermissionsResponse:
    """Create or update power permissions for a user."""
    audit_logger = get_audit_logger_db()

    perm = db.query(UserPowerPermission).filter(
        UserPowerPermission.user_id == user_id
    ).first()

    if not perm:
        perm = UserPowerPermission(user_id=user_id, granted_by=granted_by)
        db.add(perm)

    old_values = {
        "can_soft_sleep": perm.can_soft_sleep,
        "can_wake": perm.can_wake,
        "can_suspend": perm.can_suspend,
        "can_wol": perm.can_wol,
    }

    # Apply explicit updates
    if update.can_soft_sleep is not None:
        perm.can_soft_sleep = update.can_soft_sleep
    if update.can_wake is not None:
        perm.can_wake = update.can_wake
    if update.can_suspend is not None:
        perm.can_suspend = update.can_suspend
    if update.can_wol is not None:
        perm.can_wol = update.can_wol

    # Apply implication rules
    perm.can_soft_sleep, perm.can_wake, perm.can_suspend, perm.can_wol = (
        _apply_implications(perm.can_soft_sleep, perm.can_wake, perm.can_suspend, perm.can_wol)
    )

    perm.granted_by = granted_by

    db.commit()
    db.refresh(perm)

    new_values = {
        "can_soft_sleep": perm.can_soft_sleep,
        "can_wake": perm.can_wake,
        "can_suspend": perm.can_suspend,
        "can_wol": perm.can_wol,
    }

    # Audit log
    from app.models.user import User
    admin = db.query(User).filter(User.id == granted_by).first()
    target = db.query(User).filter(User.id == user_id).first()

    audit_logger.log_security_event(
        action="power_permission_changed",
        user=admin.username if admin else str(granted_by),
        resource=f"user:{target.username if target else user_id}",
        details={"old": old_values, "new": new_values},
        success=True,
        db=db,
    )

    return get_permissions(db, user_id)


def check_permission(db: Session, user_id: int, action: str) -> bool:
    """Check if a user has a specific power permission.

    Args:
        db: Database session
        user_id: User ID to check
        action: One of 'soft_sleep', 'wake', 'suspend', 'wol'

    Returns:
        True if the user has the permission, False otherwise.
    """
    field = _ACTION_FIELD_MAP.get(action)
    if not field:
        return False

    perm = db.query(UserPowerPermission).filter(
        UserPowerPermission.user_id == user_id
    ).first()

    if not perm:
        return False

    return bool(getattr(perm, field, False))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd backend && python -m pytest tests/services/test_power_permissions.py -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/power_permissions.py backend/tests/services/test_power_permissions.py
git commit -m "feat(power): add power permissions service with implication logic"
```

---

### Task 3: API Dependency + Sleep Route Changes

**Files:**
- Modify: `backend/app/api/deps.py`
- Modify: `backend/app/api/routes/sleep.py`

- [ ] **Step 1: Write the test file**

Create `backend/tests/api/test_power_permissions_routes.py`:

```python
"""Tests for power permissions API endpoints and delegated sleep access."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import users as user_service


@pytest.fixture
def admin_token(client: TestClient) -> str:
    resp = client.post("/api/auth/login", data={
        "username": settings.admin_username,
        "password": settings.admin_password,
    })
    return resp.json()["access_token"]


@pytest.fixture
def regular_user(db_session: Session) -> User:
    existing = user_service.get_user_by_username("poweruser", db=db_session)
    if existing:
        return existing
    return user_service.create_user(
        UserCreate(username="poweruser", email="power@test.com", password="Test1234", role="user"),
        db=db_session,
    )


@pytest.fixture
def user_token(client: TestClient, regular_user: User) -> str:
    resp = client.post("/api/auth/login", data={
        "username": "poweruser",
        "password": "Test1234",
    })
    return resp.json()["access_token"]


class TestGetPowerPermissions:
    def test_admin_can_get_permissions(self, client: TestClient, admin_token: str, regular_user: User):
        resp = client.get(
            f"/api/users/{regular_user.id}/power-permissions",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["can_soft_sleep"] is False
        assert data["can_wake"] is False

    def test_non_admin_cannot_get_permissions(self, client: TestClient, user_token: str, regular_user: User):
        resp = client.get(
            f"/api/users/{regular_user.id}/power-permissions",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 403


class TestUpdatePowerPermissions:
    def test_admin_can_set_permissions(self, client: TestClient, admin_token: str, regular_user: User):
        resp = client.put(
            f"/api/users/{regular_user.id}/power-permissions",
            json={"can_soft_sleep": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["can_soft_sleep"] is True
        assert data["can_wake"] is True  # implied

    def test_non_admin_cannot_set_permissions(self, client: TestClient, user_token: str, regular_user: User):
        resp = client.put(
            f"/api/users/{regular_user.id}/power-permissions",
            json={"can_soft_sleep": True},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 403


class TestMyPermissions:
    def test_user_can_see_own_permissions(self, client: TestClient, user_token: str):
        resp = client.get(
            "/api/system/sleep/my-permissions",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["can_soft_sleep"] is False

    def test_unauthenticated_rejected(self, client: TestClient):
        resp = client.get("/api/system/sleep/my-permissions")
        assert resp.status_code == 401


class TestDelegatedSleepAccess:
    def test_user_without_permission_gets_403(self, client: TestClient, user_token: str):
        resp = client.post(
            "/api/system/sleep/soft",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 403

    def test_user_with_permission_can_access(
        self, client: TestClient, admin_token: str, user_token: str, regular_user: User,
    ):
        # Grant permission
        client.put(
            f"/api/users/{regular_user.id}/power-permissions",
            json={"can_soft_sleep": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # User can now access (will get 503 because sleep manager isn't running in test, but not 403)
        resp = client.post(
            "/api/system/sleep/soft",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code != 403  # 503 expected (service not running), not 403

    def test_admin_still_works(self, client: TestClient, admin_token: str):
        resp = client.post(
            "/api/system/sleep/soft",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code != 403  # 503 expected (service not running), not 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && python -m pytest tests/api/test_power_permissions_routes.py -v
```

Expected: Failures — endpoints don't exist yet.

- [ ] **Step 3: Add `get_power_authorized_user` dependency to `deps.py`**

Add the following at the end of `backend/app/api/deps.py`:

```python
def _make_power_dependency(action: str):
    """Factory for power-action-specific auth dependencies."""

    async def get_power_authorized_user(
        request: Request,
        user: UserPublic = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> UserPublic:
        """Allow admins or users with the specific power permission."""
        if user.role == "admin":
            return user

        from app.services.power_permissions import check_permission

        if check_permission(db, user.id, action):
            return user

        audit_logger = get_audit_logger_db()
        audit_logger.log_authorization_failure(
            user=user.username,
            action=f"power_{action}_denied",
            required_permission=f"power:{action}",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions: power:{action} required",
        )

    return get_power_authorized_user


require_power_soft_sleep = _make_power_dependency("soft_sleep")
require_power_wake = _make_power_dependency("wake")
require_power_suspend = _make_power_dependency("suspend")
require_power_wol = _make_power_dependency("wol")
```

- [ ] **Step 4: Update sleep route endpoints**

Replace the dependency in each endpoint in `backend/app/api/routes/sleep.py`:

1. Update imports at the top:

```python
# Replace:
from app.api.deps import get_current_user, get_current_admin
# With:
from app.api.deps import (
    get_current_user,
    get_current_admin,
    require_power_soft_sleep,
    require_power_wake,
    require_power_suspend,
    require_power_wol,
)
```

2. Change `enter_soft_sleep` (line 52): `Depends(get_current_admin)` → `Depends(require_power_soft_sleep)`

3. Change `wake_from_sleep` (line 68): `Depends(get_current_admin)` → `Depends(require_power_wake)`

4. Change `enter_suspend` (line 84): `Depends(get_current_admin)` → `Depends(require_power_suspend)`

5. Change `send_wol` (line 103): `Depends(get_current_admin)` → `Depends(require_power_wol)`

6. Add audit logging for delegated actions in each of the 4 endpoints. After the `logger.info(...)` line in each endpoint, add (using the corresponding action name):

In `enter_soft_sleep`:
```python
    if current_user.role != "admin":
        audit_logger = get_audit_logger_db()
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=current_user.username,
            resource="soft_sleep",
            details={"action": "soft_sleep"},
            success=True,
            db=db,
        )
```

In `wake_from_sleep`:
```python
    if current_user.role != "admin":
        audit_logger = get_audit_logger_db()
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=current_user.username,
            resource="wake",
            details={"action": "wake"},
            success=True,
            db=db,
        )
```

In `enter_suspend`:
```python
    if current_user.role != "admin":
        audit_logger = get_audit_logger_db()
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=current_user.username,
            resource="suspend",
            details={"action": "suspend"},
            success=True,
            db=db,
        )
```

In `send_wol`:
```python
    if current_user.role != "admin":
        audit_logger = get_audit_logger_db()
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=current_user.username,
            resource="wol",
            details={"action": "wol"},
            success=True,
            db=db,
        )
```

Note: The endpoints currently don't have a `db` parameter. Add `db: Session = Depends(get_db)` to the 4 action endpoints, and add the import `from app.core.database import get_db` and `from app.services.audit.logger_db import get_audit_logger_db`.

7. Add the `/my-permissions` endpoint at the end of the file:

```python
@router.get("/my-permissions", response_model=MyPowerPermissionsResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_my_power_permissions(
    request: Request, response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MyPowerPermissionsResponse:
    """Get the current user's power permissions (for mobile app)."""
    if current_user.role == "admin":
        return MyPowerPermissionsResponse(
            can_soft_sleep=True, can_wake=True, can_suspend=True, can_wol=True,
        )
    from app.services.power_permissions import get_permissions
    perms = get_permissions(db, current_user.id)
    return MyPowerPermissionsResponse(
        can_soft_sleep=perms.can_soft_sleep,
        can_wake=perms.can_wake,
        can_suspend=perms.can_suspend,
        can_wol=perms.can_wol,
    )
```

Add the import at the top of the file:
```python
from app.schemas.power_permissions import MyPowerPermissionsResponse
from app.core.database import get_db
from sqlalchemy.orm import Session
from app.services.audit.logger_db import get_audit_logger_db
```

- [ ] **Step 5: Add admin endpoints to users route**

Add to the end of `backend/app/api/routes/users.py`:

```python
from app.schemas.power_permissions import UserPowerPermissionsResponse, UserPowerPermissionsUpdate


@router.get("/{user_id}/power-permissions", response_model=UserPowerPermissionsResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def get_user_power_permissions(
    request: Request,
    response: Response,
    user_id: int,
    current_admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> UserPowerPermissionsResponse:
    """Get power permissions for a user (admin only)."""
    from app.services.power_permissions import get_permissions

    user = user_service.get_user(user_id, db=db)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return get_permissions(db, user_id)


@router.put("/{user_id}/power-permissions", response_model=UserPowerPermissionsResponse)
@user_limiter.limit(get_limit("admin_operations"))
async def update_user_power_permissions(
    request: Request,
    response: Response,
    user_id: int,
    body: UserPowerPermissionsUpdate,
    current_admin: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(get_db),
) -> UserPowerPermissionsResponse:
    """Update power permissions for a user (admin only)."""
    from app.services.power_permissions import update_permissions

    user = user_service.get_user(user_id, db=db)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return update_permissions(db, user_id, body, granted_by=current_admin.id)
```

- [ ] **Step 6: Run the tests**

Run:
```bash
cd backend && python -m pytest tests/api/test_power_permissions_routes.py -v
```

Expected: All tests pass.

- [ ] **Step 7: Run full test suite to check for regressions**

Run:
```bash
cd backend && python -m pytest tests/ -x --timeout=30 -q
```

Expected: No regressions.

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/deps.py backend/app/api/routes/sleep.py backend/app/api/routes/users.py backend/tests/api/test_power_permissions_routes.py
git commit -m "feat(power): add power permission dependency, update sleep routes, add admin endpoints"
```

---

### Task 4: Frontend API Module

**Files:**
- Create: `client/src/api/powerPermissions.ts`

- [ ] **Step 1: Create the API client module**

Create `client/src/api/powerPermissions.ts`:

```typescript
/**
 * API client for user power permissions management.
 */

import { apiClient } from '../lib/api';

export interface UserPowerPermissions {
  user_id: number;
  can_soft_sleep: boolean;
  can_wake: boolean;
  can_suspend: boolean;
  can_wol: boolean;
  granted_by: number | null;
  granted_by_username: string | null;
  granted_at: string | null;
}

export interface UserPowerPermissionsUpdate {
  can_soft_sleep?: boolean;
  can_wake?: boolean;
  can_suspend?: boolean;
  can_wol?: boolean;
}

export interface MyPowerPermissions {
  can_soft_sleep: boolean;
  can_wake: boolean;
  can_suspend: boolean;
  can_wol: boolean;
}

/**
 * Get power permissions for a user (admin only).
 */
export async function getUserPowerPermissions(userId: number): Promise<UserPowerPermissions> {
  const { data } = await apiClient.get<UserPowerPermissions>(
    `/api/users/${userId}/power-permissions`,
  );
  return data;
}

/**
 * Update power permissions for a user (admin only).
 */
export async function updateUserPowerPermissions(
  userId: number,
  update: UserPowerPermissionsUpdate,
): Promise<UserPowerPermissions> {
  const { data } = await apiClient.put<UserPowerPermissions>(
    `/api/users/${userId}/power-permissions`,
    update,
  );
  return data;
}

/**
 * Get own power permissions (for mobile app / client apps).
 */
export async function getMyPowerPermissions(): Promise<MyPowerPermissions> {
  const { data } = await apiClient.get<MyPowerPermissions>(
    '/api/system/sleep/my-permissions',
  );
  return data;
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/api/powerPermissions.ts
git commit -m "feat(power): add frontend API client for power permissions"
```

---

### Task 5: Frontend Power Permissions UI in User Edit

**Files:**
- Create: `client/src/components/user-management/PowerPermissionsSection.tsx`
- Modify: `client/src/components/user-management/UserFormModal.tsx`

- [ ] **Step 1: Create the PowerPermissionsSection component**

Create `client/src/components/user-management/PowerPermissionsSection.tsx`:

```tsx
import { useState, useEffect } from 'react';
import { Moon, Sun, Power, Wifi, Loader2 } from 'lucide-react';
import {
  getUserPowerPermissions,
  updateUserPowerPermissions,
  type UserPowerPermissions,
  type UserPowerPermissionsUpdate,
} from '../../api/powerPermissions';
import { handleApiError } from '../../lib/errorHandling';
import toast from 'react-hot-toast';

interface PowerPermissionsSectionProps {
  userId: number;
  userRole: string;
}

interface PermissionToggle {
  key: keyof UserPowerPermissionsUpdate;
  label: string;
  description: string;
  icon: React.ReactNode;
  impliedBy?: keyof UserPowerPermissionsUpdate;
  implies?: keyof UserPowerPermissionsUpdate;
}

const PERMISSION_TOGGLES: PermissionToggle[] = [
  {
    key: 'can_soft_sleep',
    label: 'Soft Sleep',
    description: 'Server in Soft Sleep versetzen',
    icon: <Moon className="h-4 w-4" />,
    implies: 'can_wake',
  },
  {
    key: 'can_wake',
    label: 'Wake',
    description: 'Server aus Soft Sleep aufwecken',
    icon: <Sun className="h-4 w-4" />,
    impliedBy: 'can_soft_sleep',
  },
  {
    key: 'can_suspend',
    label: 'Suspend',
    description: 'System Suspend (S3 Sleep)',
    icon: <Power className="h-4 w-4" />,
    implies: 'can_wol',
  },
  {
    key: 'can_wol',
    label: 'Wake-on-LAN',
    description: 'WoL Magic Packet senden',
    icon: <Wifi className="h-4 w-4" />,
    impliedBy: 'can_suspend',
  },
];

export function PowerPermissionsSection({ userId, userRole }: PowerPermissionsSectionProps) {
  const [permissions, setPermissions] = useState<UserPowerPermissions | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (userRole === 'admin') return;
    setLoading(true);
    getUserPowerPermissions(userId)
      .then(setPermissions)
      .catch(() => setPermissions(null))
      .finally(() => setLoading(false));
  }, [userId, userRole]);

  if (userRole === 'admin') return null;

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-3 text-sm text-slate-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        Lade Power Permissions...
      </div>
    );
  }

  const handleToggle = async (key: keyof UserPowerPermissionsUpdate, newValue: boolean) => {
    setSaving(true);
    try {
      const update: UserPowerPermissionsUpdate = { [key]: newValue };
      const result = await updateUserPowerPermissions(userId, update);
      setPermissions(result);
      toast.success('Power Permissions aktualisiert');
    } catch (error) {
      handleApiError(error, 'Fehler beim Speichern');
    } finally {
      setSaving(false);
    }
  };

  const isImplied = (toggle: PermissionToggle): boolean => {
    if (!toggle.impliedBy || !permissions) return false;
    return permissions[toggle.impliedBy] === true;
  };

  return (
    <div className="border-t border-slate-800 pt-3 mt-3">
      <h3 className="text-sm font-medium text-slate-300 mb-1">Power Permissions</h3>
      <p className="text-xs text-slate-500 mb-3">
        Erlaubt diesem User, Power-Aktionen ueber die Mobile App auszufuehren.
      </p>

      <div className="space-y-2">
        {PERMISSION_TOGGLES.map((toggle) => {
          const value = permissions?.[toggle.key] ?? false;
          const implied = isImplied(toggle);

          return (
            <div key={toggle.key} className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-slate-400">{toggle.icon}</span>
                <div>
                  <span className="text-sm text-slate-200">{toggle.label}</span>
                  <span className="text-xs text-slate-500 ml-2">{toggle.description}</span>
                </div>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={value}
                disabled={saving || implied}
                onClick={() => handleToggle(toggle.key, !value)}
                title={implied ? `Impliziert durch ${toggle.impliedBy === 'can_soft_sleep' ? 'Soft Sleep' : 'Suspend'}` : undefined}
                className={`relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors
                  ${value ? 'bg-sky-500' : 'bg-slate-700'}
                  ${implied ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}
                  ${saving ? 'opacity-50' : ''}
                `}
              >
                <span
                  className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform
                    ${value ? 'translate-x-4' : 'translate-x-0.5'}
                  `}
                />
              </button>
            </div>
          );
        })}
      </div>

      {permissions?.granted_by_username && (
        <p className="text-xs text-slate-500 mt-2">
          Zuletzt geaendert von {permissions.granted_by_username}
          {permissions.granted_at && ` am ${new Date(permissions.granted_at).toLocaleDateString('de-DE')}`}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Integrate into UserFormModal**

In `client/src/components/user-management/UserFormModal.tsx`:

1. Add import at the top:
```tsx
import { PowerPermissionsSection } from './PowerPermissionsSection';
```

2. Add the section in the modal body, after the "is_active" checkbox `<div>` block (after line 124) and before the button row:

```tsx
          {editingUser && (
            <PowerPermissionsSection
              userId={editingUser.id}
              userRole={editingUser.role}
            />
          )}
```

- [ ] **Step 3: Verify frontend builds**

Run:
```bash
cd client && npm run build
```

Expected: Build succeeds without errors.

- [ ] **Step 4: Commit**

```bash
git add client/src/components/user-management/PowerPermissionsSection.tsx client/src/components/user-management/UserFormModal.tsx
git commit -m "feat(power): add Power Permissions UI section in user edit modal"
```

---

### Task 6: Update Directory CLAUDE.md Files

**Files:**
- Modify: `backend/app/models/CLAUDE.md`
- Modify: `backend/app/services/CLAUDE.md`
- Modify: `backend/app/schemas/CLAUDE.md`

- [ ] **Step 1: Update models CLAUDE.md**

In `backend/app/models/CLAUDE.md`, add `power_permissions.py` to the **Power & Hardware** line:

```
**Power & Hardware**: `power.py` (profiles, demands, auto-scaling), `power_preset.py`, `fans.py` (config, samples, schedules, curve profiles), `sleep.py`, `smart_device.py`, `power_permissions.py`
```

- [ ] **Step 2: Update services CLAUDE.md**

In `backend/app/services/CLAUDE.md`, add to the **Top-level Services** table:

```
| `power_permissions.py` | Per-user power action permissions (get, update, check) |
```

- [ ] **Step 3: Update schemas CLAUDE.md**

In `backend/app/schemas/CLAUDE.md`, add to the **Key Schemas** section:

```
**Power Permissions** (`power_permissions.py`): `UserPowerPermissionsResponse`, `UserPowerPermissionsUpdate`, `MyPowerPermissionsResponse` — per-user power action delegation
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/CLAUDE.md backend/app/services/CLAUDE.md backend/app/schemas/CLAUDE.md
git commit -m "docs: update directory CLAUDE.md files for power permissions"
```
