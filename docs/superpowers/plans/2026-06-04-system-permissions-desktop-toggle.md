# System Permissions: Rename + Desktop-Toggle Permission — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the user-facing "Power Permissions" feature to "System Permissions / Systemberechtigungen", internationalize its UI, and add a new grantable `can_toggle_desktop` permission that delegates the KDE desktop enable/disable endpoints to non-admins (parallel to the existing sleep/suspend/WoL delegation).

**Architecture:** Extend the existing `user_power_permissions` table/service/schemas with one independent boolean column (no implication logic). Broaden the desktop `enable`/`disable` endpoints from admin-only to `admin OR can_toggle_desktop` via the existing `_make_power_dependency` factory. Backend identifiers stay `power_permissions` (UI-only rename); CLAUDE.md notes record the mapping. Frontend: internationalize `PowerPermissionsSection.tsx` and add the 5th toggle.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, pytest — React 18 + TypeScript + i18next + Tailwind.

**Spec:** `docs/superpowers/specs/2026-06-04-system-permissions-desktop-toggle-design.md`

**Coordination note (parallel work):** A parallel worktree (`feat/monitoring-retention-ui`) edits the same two i18n files (`en/admin.json`, `de/admin.json`) but in disjoint key regions (`database.tabs.retention`, `databaseStats.metrics.{uptime,gpu}`, top-level `retentionSettings`) — this plan only adds `users.systemPermissions`, so a 3-way merge is clean. That feature adds **no Alembic migration**, so this plan's migration off head `88a45a963ed9` is the only new one — no multi-head risk. If that changes, re-point this migration's `down_revision` onto whatever lands first.

---

## Task 1: Model column + Alembic migration

**Files:**
- Modify: `backend/app/models/power_permissions.py`
- Create: `backend/alembic/versions/<generated>_add_can_toggle_desktop.py`

- [ ] **Step 1: Add the column to the model**

In `backend/app/models/power_permissions.py`, after the `can_wol` column (line 26), add:
```python
    can_toggle_desktop: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
```

- [ ] **Step 2: Confirm the current Alembic head**

Run (from `backend/`): `python -m alembic heads`
Expected: `88a45a963ed9 (head)` — a single head. If it shows more than one head, STOP and reconcile before continuing (multi-head will break prod deploy).

- [ ] **Step 3: Generate an empty migration chained onto that head**

Run (from `backend/`): `python -m alembic revision -m "add can_toggle_desktop to user_power_permissions"`
Expected: a new file `backend/alembic/versions/<revid>_add_can_toggle_desktop_to_user_power_permissions.py` whose `down_revision = "88a45a963ed9"` was filled in automatically. (Plain `revision`, NOT `--autogenerate` — we hand-write the ops to avoid picking up unrelated dev-DB drift.)

- [ ] **Step 4: Fill in upgrade/downgrade**

In the generated migration, set the `upgrade()` and `downgrade()` bodies to:
```python
def upgrade() -> None:
    op.add_column(
        "user_power_permissions",
        sa.Column("can_toggle_desktop", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    with op.batch_alter_table("user_power_permissions") as batch_op:
        batch_op.drop_column("can_toggle_desktop")
```
Leave the auto-generated `revision`, `down_revision`, and the `import sqlalchemy as sa` / `from alembic import op` header as generated. (`server_default="0"` matches the sibling columns and is a valid boolean default on both SQLite and PostgreSQL; `batch_alter_table` on downgrade keeps the drop portable to SQLite.)

- [ ] **Step 5: Apply the migration to the dev DB**

Run (from `backend/`): `python -m alembic upgrade head`
Expected: completes without error; `python -m alembic heads` again shows the new single head.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/power_permissions.py backend/alembic/versions/*_add_can_toggle_desktop*.py
git commit -m "feat(system-permissions): add can_toggle_desktop column + migration"
```

---

## Task 2: Schemas

**Files:**
- Modify: `backend/app/schemas/power_permissions.py`

- [ ] **Step 1: Add the field to all three schemas**

In `backend/app/schemas/power_permissions.py`:

In `UserPowerPermissionsResponse`, after `can_wol: bool = False` (line 16):
```python
    can_toggle_desktop: bool = False
```

In `UserPowerPermissionsUpdate`, after the `can_wol` field (line 30):
```python
    can_toggle_desktop: Optional[bool] = Field(default=None, description="Allow toggling the desktop (DPMS on/off)")
```

In `MyPowerPermissionsResponse`, after `can_wol: bool = False` (line 39):
```python
    can_toggle_desktop: bool = False
```

- [ ] **Step 2: Sanity-check the module imports**

Run (from `backend/`): `python -c "import app.schemas.power_permissions as m; print(m.UserPowerPermissionsUpdate.model_fields.keys())"`
Expected: the printed keys include `can_toggle_desktop`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/power_permissions.py
git commit -m "feat(system-permissions): add can_toggle_desktop to permission schemas"
```

---

## Task 3: Service layer (get/update + audit, no implication)

**Files:**
- Modify: `backend/app/services/power_permissions.py`
- Test: `backend/tests/api/test_power_permissions_routes.py`

- [ ] **Step 1: Write the failing tests (GET/PUT round-trip + no implication)**

Append to `backend/tests/api/test_power_permissions_routes.py`:
```python
class TestToggleDesktopPermission:
    def test_default_is_false(self, client: TestClient, admin_token: str, regular_user: User):
        resp = client.get(
            f"/api/users/{regular_user.id}/power-permissions",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["can_toggle_desktop"] is False

    def test_grant_does_not_imply_other_permissions(
        self, client: TestClient, admin_token: str, regular_user: User,
    ):
        resp = client.put(
            f"/api/users/{regular_user.id}/power-permissions",
            json={"can_toggle_desktop": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["can_toggle_desktop"] is True
        # independent permission — must NOT pull in any sleep permission
        assert data["can_soft_sleep"] is False
        assert data["can_wake"] is False
        assert data["can_suspend"] is False
        assert data["can_wol"] is False

    def test_my_permissions_includes_toggle_desktop(self, client: TestClient, user_token: str):
        resp = client.get(
            "/api/system/sleep/my-permissions",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["can_toggle_desktop"] is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `backend/`): `python -m pytest tests/api/test_power_permissions_routes.py::TestToggleDesktopPermission -v`
Expected: FAIL — `can_toggle_desktop` missing from responses (KeyError / assertion error). The `my_permissions` one already passes via the schema default but the GET/PUT ones fail until the service writes the field.

- [ ] **Step 3: Update `_ACTION_FIELD_MAP`**

In `backend/app/services/power_permissions.py`, in `_ACTION_FIELD_MAP` (lines 17-22), add:
```python
    "toggle_desktop": "can_toggle_desktop",
```

- [ ] **Step 4: Include the field in `get_permissions`**

In `get_permissions`, in the returned `UserPowerPermissionsResponse(...)` (lines 41-50), after `can_wol=perm.can_wol,` add:
```python
        can_toggle_desktop=perm.can_toggle_desktop,
```

- [ ] **Step 5: Handle the field in `update_permissions` (explicit set + audit)**

In `update_permissions`:

In `old_values` (lines 112-117), add:
```python
        "can_toggle_desktop": perm.can_toggle_desktop,
```

In the explicit-updates block, after the `can_wol` handling (lines 141-144), add:
```python
    if update.can_toggle_desktop is not None:
        perm.can_toggle_desktop = update.can_toggle_desktop
```
(No `explicit_true`/`explicit_false` tracking — `can_toggle_desktop` is independent of the sleep/suspend implication chains, so it must NOT be passed to `_apply_implications`.)

In `new_values` (lines 160-165), add:
```python
        "can_toggle_desktop": perm.can_toggle_desktop,
```

- [ ] **Step 6: Run the tests to verify they pass**

Run (from `backend/`): `python -m pytest tests/api/test_power_permissions_routes.py -v`
Expected: PASS — the whole file (existing tests + `TestToggleDesktopPermission`).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/power_permissions.py backend/tests/api/test_power_permissions_routes.py
git commit -m "feat(system-permissions): persist can_toggle_desktop in service + audit"
```

---

## Task 4: Backend wiring — deps dependency, my-permissions, desktop gating

**Files:**
- Modify: `backend/app/api/deps.py`
- Modify: `backend/app/api/routes/sleep.py`
- Modify: `backend/app/api/routes/desktop.py`
- Test: `backend/tests/api/test_power_permissions_routes.py`

- [ ] **Step 1: Write the failing delegated-desktop tests**

Append to `backend/tests/api/test_power_permissions_routes.py`:
```python
class TestDelegatedDesktopAccess:
    @pytest.fixture(autouse=True)
    def _dev_desktop(self):
        # Force the in-memory dev backend so the endpoint result is
        # deterministic and cross-platform (no kscreen-doctor / os.getuid()).
        import app.services.power.desktop as desktop_mod
        from app.services.power.desktop import DesktopService
        from app.services.power.desktop_backend import DevDesktopBackend
        prev = desktop_mod._service
        desktop_mod._service = DesktopService(backend=DevDesktopBackend())
        yield
        desktop_mod._service = prev

    def test_user_without_permission_gets_403(self, client: TestClient, user_token: str):
        resp = client.post(
            "/api/system/sleep/desktop/disable",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 403

    def test_user_with_permission_can_access(
        self, client: TestClient, admin_token: str, user_token: str, regular_user: User,
    ):
        client.put(
            f"/api/users/{regular_user.id}/power-permissions",
            json={"can_toggle_desktop": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp = client.post(
            "/api/system/sleep/desktop/disable",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_admin_still_works(self, client: TestClient, admin_token: str):
        resp = client.post(
            "/api/system/sleep/desktop/enable",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `backend/`): `python -m pytest tests/api/test_power_permissions_routes.py::TestDelegatedDesktopAccess -v`
Expected: FAIL — `test_user_without_permission_gets_403` currently gets 200/4xx-other because the endpoint is admin-only via `get_current_admin` (a non-admin gets 403 from `get_current_admin` actually — verify) and the granted-user test gets 403 because the permission isn't wired. The key failing assertion is `test_user_with_permission_can_access` (403 instead of 200). Proceed regardless; Step 6 turns the class green.

- [ ] **Step 3: Add the desktop permission dependency in `deps.py`**

In `backend/app/api/deps.py`, immediately after `require_power_wol = _make_power_dependency("wol")`, add:
```python
require_power_toggle_desktop = _make_power_dependency("toggle_desktop")
```

- [ ] **Step 4: Include `can_toggle_desktop` in `/my-permissions`**

In `backend/app/api/routes/sleep.py`, in `get_my_power_permissions`:

In the admin branch (the `MyPowerPermissionsResponse(can_soft_sleep=True, ...)`), add `can_toggle_desktop=True,`:
```python
        return MyPowerPermissionsResponse(
            can_soft_sleep=True, can_wake=True, can_suspend=True, can_wol=True,
            can_toggle_desktop=True,
        )
```

In the non-admin return, add `can_toggle_desktop=perms.can_toggle_desktop,`:
```python
    return MyPowerPermissionsResponse(
        can_soft_sleep=perms.can_soft_sleep,
        can_wake=perms.can_wake,
        can_suspend=perms.can_suspend,
        can_wol=perms.can_wol,
        can_toggle_desktop=perms.can_toggle_desktop,
    )
```

- [ ] **Step 5: Gate the desktop enable/disable endpoints**

In `backend/app/api/routes/desktop.py`:

Change the deps import line:
```python
# from:
from app.api.deps import get_current_user, get_current_admin
# to:
from app.api.deps import get_current_user, require_power_toggle_desktop
```

In `desktop_disable` and `desktop_enable`, change the auth dependency:
```python
# from:
    current_user=Depends(get_current_admin),
# to:
    current_user=Depends(require_power_toggle_desktop),
```
Leave `desktop_status` on `Depends(get_current_user)`. Rate-limiting and audit logging stay unchanged. (The audit `log_event` already records `current_user.username`, so a delegated user's desktop action is attributed correctly.)

- [ ] **Step 6: Run the new tests to verify they pass**

Run (from `backend/`): `python -m pytest tests/api/test_power_permissions_routes.py::TestDelegatedDesktopAccess -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Run the desktop route tests to confirm no regression**

Run (from `backend/`): `python -m pytest tests/test_desktop_routes.py -v`
Expected: PASS (3 tests). These override `get_current_user` to an admin `_User`, so `require_power_toggle_desktop` short-circuits on `role == "admin"` without touching the DB — unchanged behaviour.

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/deps.py backend/app/api/routes/sleep.py backend/app/api/routes/desktop.py backend/tests/api/test_power_permissions_routes.py
git commit -m "feat(system-permissions): delegate desktop enable/disable via can_toggle_desktop"
```

---

## Task 5: Frontend API client types

**Files:**
- Modify: `client/src/api/powerPermissions.ts`

- [ ] **Step 1: Add `can_toggle_desktop` to the three interfaces**

In `client/src/api/powerPermissions.ts`:

In `UserPowerPermissions`, after `can_wol: boolean;` (line 12):
```ts
  can_toggle_desktop: boolean;
```

In `UserPowerPermissionsUpdate`, after `can_wol?: boolean;` (line 22):
```ts
  can_toggle_desktop?: boolean;
```

In `MyPowerPermissions`, after `can_wol: boolean;` (line 29):
```ts
  can_toggle_desktop: boolean;
```

- [ ] **Step 2: Commit**

```bash
git add client/src/api/powerPermissions.ts
git commit -m "feat(system-permissions): add can_toggle_desktop to frontend API types"
```

---

## Task 6: i18n locale strings (en + de)

**Files:**
- Modify: `client/src/i18n/locales/en/admin.json`
- Modify: `client/src/i18n/locales/de/admin.json`

- [ ] **Step 1: Add the `systemPermissions` block to EN**

In `client/src/i18n/locales/en/admin.json`, inside the top-level `"users"` object (as a sibling of the existing `users.*` keys such as `fields`, `roles`, `buttons`, `placeholders`), add the following key. Ensure valid JSON — add a comma after the preceding sibling, and no trailing comma if this becomes the last key in `users`:
```json
    "systemPermissions": {
      "title": "System Permissions",
      "description": "Allows this user to perform system actions via the mobile app.",
      "loading": "Loading system permissions…",
      "saved": "System permissions updated",
      "saveError": "Failed to save",
      "lastChangedBy": "Last changed by {{name}} on {{date}}",
      "impliedBy": "Implied by {{name}}",
      "items": {
        "softSleep": { "label": "Soft Sleep", "desc": "Put the server into soft sleep" },
        "wake": { "label": "Wake", "desc": "Wake the server from soft sleep" },
        "suspend": { "label": "Suspend", "desc": "System suspend (S3 sleep)" },
        "wol": { "label": "Wake-on-LAN", "desc": "Send a WoL magic packet" },
        "toggleDesktop": { "label": "Desktop", "desc": "Enable/disable the desktop (saves GPU power)" }
      }
    }
```

- [ ] **Step 2: Add the `systemPermissions` block to DE**

In `client/src/i18n/locales/de/admin.json`, inside the top-level `"users"` object (same placement rules as Step 1), add:
```json
    "systemPermissions": {
      "title": "Systemberechtigungen",
      "description": "Erlaubt diesem User, System-Aktionen über die Mobile App auszuführen.",
      "loading": "Systemberechtigungen werden geladen…",
      "saved": "Systemberechtigungen aktualisiert",
      "saveError": "Fehler beim Speichern",
      "lastChangedBy": "Zuletzt geändert von {{name}} am {{date}}",
      "impliedBy": "Impliziert durch {{name}}",
      "items": {
        "softSleep": { "label": "Soft Sleep", "desc": "Server in Soft Sleep versetzen" },
        "wake": { "label": "Wake", "desc": "Server aus Soft Sleep aufwecken" },
        "suspend": { "label": "Suspend", "desc": "System Suspend (S3 Sleep)" },
        "wol": { "label": "Wake-on-LAN", "desc": "WoL Magic Packet senden" },
        "toggleDesktop": { "label": "Desktop", "desc": "Desktop aktivieren/deaktivieren (spart GPU-Strom)" }
      }
    }
```

- [ ] **Step 3: Validate both JSON files parse**

Run (from `client/`):
```bash
node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/en/admin.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/locales/de/admin.json','utf8')); console.log('JSON OK')"
```
Expected: `JSON OK` (no trailing-comma / syntax error).

- [ ] **Step 4: Commit**

```bash
git add client/src/i18n/locales/en/admin.json client/src/i18n/locales/de/admin.json
git commit -m "feat(system-permissions): i18n strings for System Permissions (en+de)"
```

---

## Task 7: Frontend component — internationalize + add Desktop toggle

**Files:**
- Modify: `client/src/components/user-management/PowerPermissionsSection.tsx`

- [ ] **Step 1: Replace the component with the i18n + 5-toggle version**

Replace the entire contents of `client/src/components/user-management/PowerPermissionsSection.tsx` with:
```tsx
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Moon, Sun, Power, Wifi, MonitorOff, Loader2 } from 'lucide-react';
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
  icon: React.ReactNode;
  impliedBy?: keyof UserPowerPermissionsUpdate;
  implies?: keyof UserPowerPermissionsUpdate;
}

// Maps an API field name to its i18n item key under
// admin:users.systemPermissions.items.*
const FIELD_TO_I18N: Record<string, string> = {
  can_soft_sleep: 'softSleep',
  can_wake: 'wake',
  can_suspend: 'suspend',
  can_wol: 'wol',
  can_toggle_desktop: 'toggleDesktop',
};

const PERMISSION_TOGGLES: PermissionToggle[] = [
  { key: 'can_soft_sleep', icon: <Moon className="h-4 w-4" />, implies: 'can_wake' },
  { key: 'can_wake', icon: <Sun className="h-4 w-4" />, impliedBy: 'can_soft_sleep' },
  { key: 'can_suspend', icon: <Power className="h-4 w-4" />, implies: 'can_wol' },
  { key: 'can_wol', icon: <Wifi className="h-4 w-4" />, impliedBy: 'can_suspend' },
  { key: 'can_toggle_desktop', icon: <MonitorOff className="h-4 w-4" /> },
];

export function PowerPermissionsSection({ userId, userRole }: PowerPermissionsSectionProps) {
  const { t } = useTranslation('admin');
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
        {t('users.systemPermissions.loading')}
      </div>
    );
  }

  const handleToggle = async (key: keyof UserPowerPermissionsUpdate, newValue: boolean) => {
    setSaving(true);
    try {
      const update: UserPowerPermissionsUpdate = { [key]: newValue };
      const result = await updateUserPowerPermissions(userId, update);
      setPermissions(result);
      toast.success(t('users.systemPermissions.saved'));
    } catch (error) {
      handleApiError(error, t('users.systemPermissions.saveError'));
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
      <h3 className="text-sm font-medium text-slate-300 mb-1">
        {t('users.systemPermissions.title')}
      </h3>
      <p className="text-xs text-slate-500 mb-3">
        {t('users.systemPermissions.description')}
      </p>

      <div className="space-y-2">
        {PERMISSION_TOGGLES.map((toggle) => {
          const value = permissions?.[toggle.key] ?? false;
          const implied = isImplied(toggle);
          const i18nKey = FIELD_TO_I18N[toggle.key];

          return (
            <div key={toggle.key} className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-slate-400">{toggle.icon}</span>
                <div>
                  <span className="text-sm text-slate-200">
                    {t(`users.systemPermissions.items.${i18nKey}.label`)}
                  </span>
                  <span className="text-xs text-slate-500 ml-2">
                    {t(`users.systemPermissions.items.${i18nKey}.desc`)}
                  </span>
                </div>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={value}
                disabled={saving || implied}
                onClick={() => handleToggle(toggle.key, !value)}
                title={
                  implied && toggle.impliedBy
                    ? t('users.systemPermissions.impliedBy', {
                        name: t(`users.systemPermissions.items.${FIELD_TO_I18N[toggle.impliedBy]}.label`),
                      })
                    : undefined
                }
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
          {t('users.systemPermissions.lastChangedBy', {
            name: permissions.granted_by_username,
            date: permissions.granted_at
              ? new Date(permissions.granted_at).toLocaleDateString()
              : '',
          })}
        </p>
      )}
    </div>
  );
}
```
(The component keeps its filename and export name `PowerPermissionsSection` — `UserFormModal.tsx` imports it unchanged. Only the user-visible strings change, plus the new 5th toggle.)

- [ ] **Step 2: Type-check / build the frontend**

Run (from `client/`): `npm run build`
Expected: build succeeds, no TypeScript errors. (A missing `can_toggle_desktop` on the API types from Task 5, or a missing `MonitorOff` import, would surface here.)

- [ ] **Step 3: Commit**

```bash
git add client/src/components/user-management/PowerPermissionsSection.tsx
git commit -m "feat(system-permissions): i18n + Desktop toggle in permissions section"
```

---

## Task 8: CLAUDE.md notes (name mapping)

**Files:**
- Modify: `backend/app/services/CLAUDE.md`
- Modify: `backend/app/schemas/CLAUDE.md`
- Modify: `backend/app/models/CLAUDE.md`

- [ ] **Step 1: services/CLAUDE.md**

In `backend/app/services/CLAUDE.md`, replace the line:
```
| `power_permissions.py` | Per-user power action permissions (get, update, check) |
```
with:
```
| `power_permissions.py` | Per-user power action permissions (get, update, check), incl. `can_toggle_desktop`. UI name: "System Permissions / Systemberechtigungen"; backend identifiers stay `power_permissions` (deliberate — no rename/migration). |
```

- [ ] **Step 2: schemas/CLAUDE.md**

In `backend/app/schemas/CLAUDE.md`, replace the line:
```
**Power Permissions** (`power_permissions.py`): `UserPowerPermissionsResponse`, `UserPowerPermissionsUpdate`, `MyPowerPermissionsResponse` — per-user power action delegation
```
with:
```
**Power Permissions** (`power_permissions.py`): `UserPowerPermissionsResponse`, `UserPowerPermissionsUpdate`, `MyPowerPermissionsResponse` — per-user power action delegation (incl. `can_toggle_desktop`). UI name: "System Permissions / Systemberechtigungen"; backend stays `power_permissions`.
```

- [ ] **Step 3: models/CLAUDE.md**

In `backend/app/models/CLAUDE.md`, in the **Power & Hardware** line, replace the trailing fragment:
```
`sleep.py`, `smart_device.py`, `power_permissions.py`
```
with:
```
`sleep.py`, `smart_device.py`, `power_permissions.py` (UI name: "System Permissions / Systemberechtigungen"; table/columns keep the `power_permissions` name)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/CLAUDE.md backend/app/schemas/CLAUDE.md backend/app/models/CLAUDE.md
git commit -m "docs(system-permissions): note UI rename vs kept backend identifiers"
```

---

## Task 9: Full verification

**Files:** none changed.

- [ ] **Step 1: Backend — run the touched suites**

Run (from `backend/`):
```bash
python -m pytest tests/api/test_power_permissions_routes.py tests/test_desktop_routes.py -v
```
Expected: all PASS.

- [ ] **Step 2: Backend — regression sweep of related areas**

Run (from `backend/`):
```bash
python -m pytest tests/api tests/test_desktop_routes.py tests/test_desktop_service.py tests/test_desktop_backend.py -q
```
Expected: no new failures. (Per repo memory, two auth/permission delete tests can flake only in the full Windows run; if you see exactly those, re-run them standalone to confirm they pass in isolation. Anything else is a real regression.)

- [ ] **Step 3: Frontend — production build**

Run (from `client/`): `npm run build`
Expected: build succeeds, no TypeScript errors.

- [ ] **Step 4: Manual smoke (dev)**

Run `python start_dev.py`. As admin, open User Management → edit a **non-admin** user. Confirm:
- The section heading reads **"System Permissions"** (EN) / **"Systemberechtigungen"** (DE, depending on UI language).
- Five toggles are shown: Soft Sleep, Wake, Suspend, Wake-on-LAN, **Desktop**.
- Toggling **Desktop** shows the success toast and persists across reopening the modal.
- (Optional) `GET /api/system/sleep/my-permissions` (as that user) returns `can_toggle_desktop: true`.

- [ ] **Step 5: Update the vectordb index**

Run the `mcp__vectordb-search__index_update` tool with `projectPath: D:/Programme (x86)/Baluhost` so the new/changed symbols are searchable.

---

## Self-Review notes (already reconciled)

- **Spec coverage:** rename (Tasks 6–8), `can_toggle_desktop` column/schema/service (Tasks 1–3), my-permissions + endpoint gating (Task 4), API client + component + i18n (Tasks 5–7), CLAUDE.md notes (Task 8), tests + verification (Tasks 3/4/9). All spec sections map to a task.
- **Type consistency:** `can_toggle_desktop` (snake_case) is the single field name across model, schemas, service `_ACTION_FIELD_MAP` value, sleep response, API client, and component `FIELD_TO_I18N`. The permission *action* string is `toggle_desktop` (used by `_make_power_dependency("toggle_desktop")` and the `_ACTION_FIELD_MAP` key). i18n item key is `toggleDesktop`.
- **No implication:** `can_toggle_desktop` is deliberately excluded from `_apply_implications` and has no `implies`/`impliedBy` in `PERMISSION_TOGGLES`.
```

