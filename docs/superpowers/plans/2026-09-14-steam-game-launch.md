# Steam-Spiele aus BaluApp starten (Backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nutzer mit dem Recht `can_launch_games` listen über `GET /api/plugins/steam_gaming/games` installierte Steam-Spiele und starten eines über `POST /api/plugins/steam_gaming/games/{app_id}/launch` — Bildschirme an, Entsperren (falls erlaubt), Big Picture, Spiel.

**Architecture:** Neues Power-Recht nach dem Muster `can_manage_bluetooth`. Im bundled Plugin `steam_gaming` kommen `library.py` (manifestbasierte Spieleliste), `launch.py` (aus `run_menu_action` gezogener Gaming-Mode-Ablauf + `launch_game`), `models.py` und `routes.py` dazu; `get_router()` importiert `routes` spät. Die Menüaktion nutzt denselben Helfer. Einzige Frontend-Änderung: der Rechte-Schalter.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, slowapi, pytest; React + TypeScript + Vitest.

**Spec:** `docs/superpowers/specs/2026-09-14-steam-game-launch-design.md` — Abschnitt „PR B".

## Global Constraints

- **Voraussetzung:** Plan A (`2026-09-14-steam-launch-systemd-run.md`) ist gemergt, deployt und an der Box verifiziert. `launcher._dispatch(url, what)` nutzt `systemd-run --user`.
- Branch `feat/steam-game-launch` auf aktuellen `main` rebasen, bevor Task 1 beginnt (`git fetch origin ; git rebase origin/main`).
- `routes.py` und `models.py` **ohne** `from __future__ import annotations` (slowapi-Body-Erkennung, siehe `bluetooth/__init__.py:7-11`).
- App-ID-Prüfung: `re.fullmatch(r"[0-9]{1,10}", app_id)` — kein `\d`, kein `$`.
- Spielname maximal 200 Zeichen.
- Rate-Limits: `steam_games_read` = `60/minute`, `steam_launch` = `6/minute`.
- Fehlermeldungen (englisch, exakt): `"Launching is only allowed from the local network"` (403), `"Game not installed"` (404), `"Game library unavailable"` (503), `"A game is already running"` (409), `"Displays could not be turned on"` (502), `"Steam could not be started"` (502).
- Audit-`details` enthalten nur `app_id` und `failed_step` (bzw. `reason`) — **nie** Spielname oder Launcher-`detail`; `ip_address=client_host`.
- Kein äußeres `asyncio.wait_for` um den Startablauf.
- Migration kettet an `19b0fbf9df31` — vorher `cd backend ; python -m alembic heads` prüfen; weicht der Head ab, den tatsächlichen eintragen.
- Nur die relevanten Tests lokal; die volle Backend-Suite gehört der CI. Frontend vor dem PR: `npx vitest run`, `npx eslint .`, `npm run build`.
- PowerShell 5.1: nie `&&`, Verkettung mit `;`. PR-/Commit-Bodies per Datei (`--body-file`).
- Commits enden mit `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` und `Claude-Session: https://claude.ai/code/session_01ATWS2TMkGeJzKetpRttHtC`.

---

### Task 1: Recht `can_launch_games` im Backend

**Files:**
- Create: `backend/alembic/versions/b4e1d8a2c7f3_add_can_launch_games_permission.py`
- Modify: `backend/app/models/power_permissions.py` (nach der Spalte `can_manage_bluetooth`)
- Modify: `backend/app/schemas/power_permissions.py` (drei Klassen)
- Modify: `backend/app/services/power_permissions.py` (Map, `get_permissions`, Update-Zweig, beide Audit-Dicts, `check_permission`-Docstring)
- Modify: `backend/app/api/deps.py:406` (neue Abhängigkeit)
- Modify: `backend/app/api/routes/sleep.py:360-380` (beide `MyPowerPermissionsResponse`-Konstruktionen)
- Modify: `backend/app/services/CLAUDE.md`, `backend/app/models/CLAUDE.md`, `backend/app/api/CLAUDE.md`
- Test: `backend/tests/test_power_permissions_launch_games.py`

**Interfaces:**
- Produces: Spalte/Feld `can_launch_games: bool` (Model, `UserPowerPermissionsResponse`, `MyPowerPermissionsResponse`), `UserPowerPermissionsUpdate.can_launch_games: Optional[bool]`, `_ACTION_FIELD_MAP["launch_games"]`, `app.api.deps.require_power_launch_games` (FastAPI-Abhängigkeit, liefert `UserPublic`).

- [ ] **Step 1: Test schreiben**

`backend/tests/test_power_permissions_launch_games.py`:

```python
"""Das Spielstart-Recht: Standard aus, Admin implizit, keine Implikation."""
from app.schemas.power_permissions import (
    MyPowerPermissionsResponse,
    UserPowerPermissionsResponse,
    UserPowerPermissionsUpdate,
)
from app.services.power_permissions import _ACTION_FIELD_MAP


class TestWiring:
    def test_the_action_maps_to_the_column(self):
        assert _ACTION_FIELD_MAP["launch_games"] == "can_launch_games"

    def test_the_dependency_exists(self):
        from app.api import deps
        assert hasattr(deps, "require_power_launch_games")

    def test_the_model_has_the_column(self):
        from app.models.power_permissions import UserPowerPermission
        assert hasattr(UserPowerPermission, "can_launch_games")


class TestSchemas:
    def test_it_defaults_to_denied(self):
        assert UserPowerPermissionsResponse(user_id=1).can_launch_games is False
        assert MyPowerPermissionsResponse().can_launch_games is False

    def test_the_update_schema_leaves_it_untouched_by_default(self):
        assert UserPowerPermissionsUpdate().can_launch_games is None


class TestGrantAndRevoke:
    def test_granting_and_revoking_round_trip(self, db_session, test_user, admin_user):
        from app.services.power_permissions import check_permission, update_permissions

        assert check_permission(db_session, test_user.id, "launch_games") is False
        update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_launch_games=True),
            granted_by=admin_user.id,
        )
        assert check_permission(db_session, test_user.id, "launch_games") is True
        update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_launch_games=False),
            granted_by=admin_user.id,
        )
        assert check_permission(db_session, test_user.id, "launch_games") is False

    def test_it_implies_neither_unlock_nor_desktop(self, db_session, test_user, admin_user):
        """A launch right must not silently open the physical desktop."""
        from app.services.power_permissions import get_permissions, update_permissions

        update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_launch_games=True),
            granted_by=admin_user.id,
        )
        perms = get_permissions(db_session, test_user.id)
        assert perms.can_launch_games is True
        assert perms.can_unlock_session is False
        assert perms.can_toggle_desktop is False

    def test_the_audit_values_carry_the_field(self, db_session, test_user, admin_user, monkeypatch):
        import app.services.power_permissions as svc

        captured: list[dict] = []

        class _Recorder:
            def log_security_event(self, **kwargs):
                captured.append(kwargs)

        monkeypatch.setattr(svc, "get_audit_logger_db", lambda: _Recorder())
        svc.update_permissions(
            db_session, test_user.id,
            UserPowerPermissionsUpdate(can_launch_games=True),
            granted_by=admin_user.id,
        )
        assert captured[0]["details"]["old"]["can_launch_games"] is False
        assert captured[0]["details"]["new"]["can_launch_games"] is True


class TestMyPermissions:
    def test_admins_get_it(self, client, admin_headers):
        resp = client.get("/api/system/sleep/my-permissions", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["can_launch_games"] is True
```

> Die Fixtures `db_session`, `test_user`, `admin_user`, `client`, `admin_headers` existieren in `backend/tests/conftest.py`. Heißt eine anders, den vorhandenen Namen nehmen — nichts neu erfinden.

- [ ] **Step 2: Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/test_power_permissions_launch_games.py -v --no-cov`
Expected: FAIL — `KeyError: 'launch_games'` bzw. `AttributeError`.

- [ ] **Step 3: Modell**

In `backend/app/models/power_permissions.py` direkt nach der Zeile mit `can_manage_bluetooth` einfügen:

```python
    can_launch_games: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
```

- [ ] **Step 4: Migration**

Run: `cd backend ; python -m alembic heads`
Expected: genau `19b0fbf9df31 (head)`. Sonst den ausgegebenen Head unten als `down_revision` eintragen.

`backend/alembic/versions/b4e1d8a2c7f3_add_can_launch_games_permission.py`:

```python
"""add can_launch_games permission

Revision ID: b4e1d8a2c7f3
Revises: 19b0fbf9df31
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4e1d8a2c7f3'
down_revision: Union[str, Sequence[str], None] = '19b0fbf9df31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fuegt can_launch_games zu user_power_permissions hinzu (standardmaessig aus)."""
    op.add_column(
        'user_power_permissions',
        sa.Column('can_launch_games', sa.Boolean(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    """Entfernt can_launch_games."""
    op.drop_column('user_power_permissions', 'can_launch_games')
```

Run: `cd backend ; python -m alembic upgrade head ; python -m alembic heads`
Expected: Upgrade läuft durch, `heads` zeigt **genau eine** Revision `b4e1d8a2c7f3 (head)`.

- [ ] **Step 5: Schemas**

In `backend/app/schemas/power_permissions.py`:

In `UserPowerPermissionsResponse` nach `can_manage_bluetooth: bool = False`:
```python
    can_launch_games: bool = False
```

In `UserPowerPermissionsUpdate` nach der `can_manage_bluetooth`-Zeile:
```python
    can_launch_games: Optional[bool] = Field(default=None, description="Allow launching installed Steam games (turns displays on and opens Big Picture; local network only)")
```

In `MyPowerPermissionsResponse` nach `can_manage_bluetooth: bool = False`:
```python
    can_launch_games: bool = False
```

- [ ] **Step 6: Service**

In `backend/app/services/power_permissions.py`:

`_ACTION_FIELD_MAP` nach `"manage_bluetooth": "can_manage_bluetooth",`:
```python
    "launch_games": "can_launch_games",
```

In `get_permissions` nach `can_manage_bluetooth=perm.can_manage_bluetooth,`:
```python
        can_launch_games=perm.can_launch_games,
```

In `update_permissions` in **beiden** Dicts `old_values` und `new_values` jeweils nach `"can_manage_bluetooth": perm.can_manage_bluetooth,`:
```python
        "can_launch_games": perm.can_launch_games,
```

Nach dem Block `if update.can_manage_bluetooth is not None: ...`:
```python
    if update.can_launch_games is not None:
        perm.can_launch_games = update.can_launch_games
```

Im Docstring von `check_permission` die Aufzählung ersetzen durch:
```
        action: One of 'soft_sleep', 'wake', 'suspend', 'wol', 'toggle_desktop',
            'unlock_session', 'control_audio', 'manage_displays', 'manage_bluetooth',
            'launch_games'
```

`_apply_implications` bleibt unberührt.

- [ ] **Step 7: Abhängigkeit und `my-permissions`**

In `backend/app/api/deps.py` nach `require_power_manage_bluetooth = _make_power_dependency("manage_bluetooth")`:
```python
require_power_launch_games = _make_power_dependency("launch_games")
```

In `backend/app/api/routes/sleep.py`, `get_my_power_permissions`: im Admin-Zweig `can_manage_bluetooth=True,` ergänzen um
```python
            can_launch_games=True,
```
und im Nutzer-Zweig nach `can_manage_bluetooth=perms.can_manage_bluetooth,`:
```python
        can_launch_games=perms.can_launch_games,
```

- [ ] **Step 8: Tests laufen lassen, Proben**

Run: `cd backend ; python -m pytest tests/test_power_permissions_launch_games.py tests/test_power_permissions_manage_bluetooth.py -v --no-cov`
Expected: PASS.

Probe 1: die Zeile `"launch_games": "can_launch_games",` testweise entfernen → `test_the_action_maps_to_the_column` und `test_granting_and_revoking_round_trip` werden rot. Zurücksetzen.
Probe 2: den Block `if update.can_launch_games is not None:` testweise entfernen → Round-Trip- und Audit-Test werden rot. Zurücksetzen. Beide Ergebnisse im Report nennen.

- [ ] **Step 9: Doku**

- `backend/app/services/CLAUDE.md`, Zeile `power_permissions.py`: `incl. \`can_toggle_desktop\`` ersetzen durch `incl. \`can_toggle_desktop\` and \`can_launch_games\` (Steam game launch; implies neither unlock nor desktop toggle)`.
- `backend/app/api/CLAUDE.md`, Tabelle „Auth Dependencies": neue Zeile
  `| \`require_power_launch_games\` | \`UserPublic\` | steam_gaming launch routes (admin or \`can_launch_games\`) |`
- `backend/app/models/CLAUDE.md`: in der Beschreibung von `power_permissions` die Rechteliste um `can_launch_games` ergänzen (dort, wo `can_manage_bluetooth` steht).

- [ ] **Step 10: Lint und Commit**

Run: `cd backend ; python -m ruff check app/models/power_permissions.py app/schemas/power_permissions.py app/services/power_permissions.py app/api/deps.py app/api/routes/sleep.py alembic/versions/b4e1d8a2c7f3_add_can_launch_games_permission.py tests/test_power_permissions_launch_games.py`
Expected: `All checks passed!`

```bash
git add backend/alembic/versions/b4e1d8a2c7f3_add_can_launch_games_permission.py backend/app/models/power_permissions.py backend/app/schemas/power_permissions.py backend/app/services/power_permissions.py backend/app/api/deps.py backend/app/api/routes/sleep.py backend/tests/test_power_permissions_launch_games.py backend/app/services/CLAUDE.md backend/app/api/CLAUDE.md backend/app/models/CLAUDE.md
git commit -m "feat(power): Recht can_launch_games" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01ATWS2TMkGeJzKetpRttHtC"
```

---

### Task 2: Rechte-Schalter im Frontend

**Files:**
- Modify: `client/src/api/powerPermissions.ts` (drei Interfaces)
- Modify: `client/src/components/user-management/PowerPermissionsSection.tsx` (Import, `FIELD_TO_I18N`, `PERMISSION_TOGGLES`)
- Modify: `client/src/i18n/locales/de/admin.json`, `client/src/i18n/locales/en/admin.json`
- Modify: `client/src/__tests__/components/user-management/PowerPermissionsSection.bluetooth.test.tsx` (`PERMS` um das Feld ergänzen)
- Test: `client/src/__tests__/components/user-management/PowerPermissionsSection.launchGames.test.tsx`
- Test: `client/src/__tests__/i18n/admin-system-permissions-locale.test.ts`

**Interfaces:**
- Consumes: Feld `can_launch_games` aus Task 1.
- Produces: `UserPowerPermissions.can_launch_games`, `UserPowerPermissionsUpdate.can_launch_games?`, `MyPowerPermissions.can_launch_games`; i18n `admin:users.systemPermissions.items.launchGames.{label,desc}`.

- [ ] **Step 1: Tests schreiben**

`client/src/__tests__/components/user-management/PowerPermissionsSection.launchGames.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: (ns: string) => ({
    t: (key: string) => `${ns}:${key}`,
    i18n: { language: 'de' },
  }),
}));

vi.mock('../../../api/powerPermissions', () => ({
  getUserPowerPermissions: vi.fn(),
  updateUserPowerPermissions: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../../lib/errorHandling', () => ({
  handleApiError: vi.fn(),
}));

import { PowerPermissionsSection } from '../../../components/user-management/PowerPermissionsSection';
import { getUserPowerPermissions } from '../../../api/powerPermissions';

const PERMS = {
  user_id: 7,
  can_soft_sleep: false, can_wake: false, can_suspend: false, can_wol: false,
  can_toggle_desktop: false, can_unlock_session: false, can_control_audio: false,
  can_manage_displays: false, can_manage_bluetooth: false, can_launch_games: false,
  granted_by: null, granted_by_username: null, granted_at: null,
};

beforeEach(() => {
  vi.mocked(getUserPowerPermissions).mockResolvedValue(structuredClone(PERMS) as never);
});

describe('PowerPermissionsSection — Spielstart', () => {
  it('bietet den Schalter fuer can_launch_games an', async () => {
    render(<PowerPermissionsSection userId={7} userRole="user" />);
    await waitFor(() => expect(getUserPowerPermissions).toHaveBeenCalled());
    expect(
      await screen.findByText('admin:users.systemPermissions.items.launchGames.label'),
    ).toBeTruthy();
  });
});
```

`client/src/__tests__/i18n/admin-system-permissions-locale.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import de from '../../i18n/locales/de/admin.json';
import en from '../../i18n/locales/en/admin.json';

// The react-i18next mock in component tests echoes keys, so a key missing
// from the JSON only shows up in a contract test against the file itself.
describe('admin locale — system permission items', () => {
  it.each([['de', de], ['en', en]])('%s hat label und desc fuer launchGames', (_lang, locale) => {
    const item = locale.users.systemPermissions.items.launchGames;
    expect(item.label.length).toBeGreaterThan(0);
    expect(item.desc.length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Fehlschlag bestätigen**

Run: `cd client ; npx vitest run src/__tests__/components/user-management/PowerPermissionsSection.launchGames.test.tsx src/__tests__/i18n/admin-system-permissions-locale.test.ts`
Expected: FAIL — Text nicht gefunden bzw. `Cannot read properties of undefined (reading 'label')`.

- [ ] **Step 3: API-Typen**

In `client/src/api/powerPermissions.ts`:
- in `UserPowerPermissions` nach `can_manage_bluetooth: boolean;` → `  can_launch_games: boolean;`
- in `UserPowerPermissionsUpdate` nach `can_manage_bluetooth?: boolean;` → `  can_launch_games?: boolean;`
- in `MyPowerPermissions` nach `can_manage_bluetooth: boolean;` → `  can_launch_games: boolean;`

- [ ] **Step 4: Komponente**

In `client/src/components/user-management/PowerPermissionsSection.tsx`:

Import-Zeile ersetzen durch:
```tsx
import { Moon, Sun, Power, Wifi, MonitorOff, Monitor, LockOpen, Volume2, Loader2, Bluetooth, Gamepad2 } from 'lucide-react';
```

In `FIELD_TO_I18N` nach `can_manage_bluetooth: 'manageBluetooth',`:
```tsx
  can_launch_games: 'launchGames',
```

In `PERMISSION_TOGGLES` nach der Bluetooth-Zeile:
```tsx
  { key: 'can_launch_games', icon: <Gamepad2 className="h-4 w-4" /> },
```

- [ ] **Step 5: Übersetzungen**

`client/src/i18n/locales/en/admin.json` — die Zeile
```json
        "manageBluetooth": { "label": "Bluetooth", "desc": "Connect and pair Bluetooth devices (pairing on the local network only)" }
```
ersetzen durch:
```json
        "manageBluetooth": { "label": "Bluetooth", "desc": "Connect and pair Bluetooth devices (pairing on the local network only)" },
        "launchGames": { "label": "Launch games", "desc": "Start installed Steam games from the app — turns the displays on and opens Big Picture (home network or VPN only)" }
```

`client/src/i18n/locales/de/admin.json` — die Zeile
```json
        "manageBluetooth": { "label": "Bluetooth", "desc": "Bluetooth-Geräte verbinden und koppeln (Koppeln nur im lokalen Netz)" }
```
ersetzen durch:
```json
        "manageBluetooth": { "label": "Bluetooth", "desc": "Bluetooth-Geräte verbinden und koppeln (Koppeln nur im lokalen Netz)" },
        "launchGames": { "label": "Spiele starten", "desc": "Installierte Steam-Spiele aus der App starten — schaltet die Displays ein und öffnet Big Picture (nur aus dem Heimnetz oder VPN)" }
```

- [ ] **Step 6: Bestehenden Test angleichen**

In `client/src/__tests__/components/user-management/PowerPermissionsSection.bluetooth.test.tsx` die Zeile
```tsx
  can_manage_displays: false, can_manage_bluetooth: false,
```
ersetzen durch:
```tsx
  can_manage_displays: false, can_manage_bluetooth: false, can_launch_games: false,
```

- [ ] **Step 7: Tests, Lint, Build**

Run: `cd client ; npx vitest run src/__tests__/components/user-management src/__tests__/i18n ; npx eslint . ; npm run build`
Expected: Vitest PASS, eslint 0 Fehler, Build erfolgreich (`tsc -b` prüft auch die Testprojekte).

- [ ] **Step 8: Commit**

```bash
git add client/src/api/powerPermissions.ts client/src/components/user-management/PowerPermissionsSection.tsx client/src/i18n/locales/de/admin.json client/src/i18n/locales/en/admin.json client/src/__tests__/components/user-management/PowerPermissionsSection.bluetooth.test.tsx client/src/__tests__/components/user-management/PowerPermissionsSection.launchGames.test.tsx client/src/__tests__/i18n/admin-system-permissions-locale.test.ts
git commit -m "feat(client): Schalter für das Recht can_launch_games" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01ATWS2TMkGeJzKetpRttHtC"
```

---

### Task 3: Erkennung ohne Dev-Stand-in und öffentlicher Tool-Filter

**Files:**
- Modify: `backend/app/plugins/installed/steam_gaming/detection.py:41-54`
- Modify: `backend/app/services/game_libraries/steam.py:35-40`
- Test: `backend/tests/plugins/test_steam_gaming_detection.py` (anhängen)
- Test: `backend/tests/game_libraries/test_games_steam_provider.py` (anhängen)

**Interfaces:**
- Produces: `detection.current_app_id(*, dev_stand_in: bool = True) -> Optional[str]`; `app.services.game_libraries.steam.is_tool_app(name: str) -> bool` (`_is_tool_app` bleibt als Alias).

- [ ] **Step 1: Tests anhängen**

An `backend/tests/plugins/test_steam_gaming_detection.py`:

```python
class TestDevStandIn:
    def test_the_stand_in_is_the_default_in_dev_mode(self, monkeypatch):
        monkeypatch.setattr(detection.settings, "is_dev_mode", True)
        monkeypatch.setattr(detection, "detect_running_app_id", lambda: None)

        assert detection.current_app_id() == detection.DEV_APP_ID

    def test_it_can_be_switched_off(self, monkeypatch):
        """The launch routes must not see a permanently running dev game -
        every launch would be a 409 on the Windows dev box."""
        monkeypatch.setattr(detection.settings, "is_dev_mode", True)
        monkeypatch.setattr(detection, "detect_running_app_id", lambda: None)

        assert detection.current_app_id(dev_stand_in=False) is None

    def test_a_real_game_still_wins_without_the_stand_in(self, monkeypatch):
        monkeypatch.setattr(detection.settings, "is_dev_mode", True)
        monkeypatch.setattr(detection, "detect_running_app_id", lambda: "1449560")

        assert detection.current_app_id(dev_stand_in=False) == "1449560"

    def test_the_length_guard_applies_without_the_stand_in(self, monkeypatch, prod_mode):
        monkeypatch.setattr(detection, "detect_running_app_id", lambda: "9" * 40)

        assert detection.current_app_id(dev_stand_in=False) is None
```

An `backend/tests/game_libraries/test_games_steam_provider.py`:

```python
def test_is_tool_app_is_public_and_matches_the_private_name():
    from app.services.game_libraries.steam import _is_tool_app, is_tool_app

    assert is_tool_app("Proton 10.0") is True
    assert is_tool_app("Steam Linux Runtime 3.0 (sniper)") is True
    assert is_tool_app("Portal") is False
    assert _is_tool_app is is_tool_app
```

- [ ] **Step 2: Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/plugins/test_steam_gaming_detection.py tests/game_libraries/test_games_steam_provider.py -v --no-cov`
Expected: FAIL — `TypeError: current_app_id() got an unexpected keyword argument 'dev_stand_in'`, `ImportError: cannot import name 'is_tool_app'`.

- [ ] **Step 3: Implementieren**

In `backend/app/plugins/installed/steam_gaming/detection.py` `current_app_id` ersetzen:

```python
def current_app_id(*, dev_stand_in: bool = True) -> Optional[str]:
    """AppID of the running game, or None. Blocking - call via asyncio.to_thread.

    ``dev_stand_in=False`` skips the dev-mode placeholder. Pill, ledger and
    panel want it (so the strip renders on a box without /proc); the launch
    routes do not - on the Windows dev box a permanently "running" game would
    turn every launch into a 409.
    """
    app_id = detect_running_app_id()
    if app_id is not None and len(app_id) > _MAX_APP_ID_LENGTH:
        logger.warning(
            "Ignoring detected app_id longer than %d chars (got %d): %r",
            _MAX_APP_ID_LENGTH,
            len(app_id),
            app_id,
        )
        app_id = None
    if app_id is None and dev_stand_in and settings.is_dev_mode:
        return DEV_APP_ID
    return app_id
```

In `backend/app/services/game_libraries/steam.py` `_is_tool_app` ersetzen:

```python
def is_tool_app(name: str) -> bool:
    """True if *name* is a Steam tool/runtime (Proton, Linux Runtime, redist)."""
    n = name.strip().lower()
    if n in _TOOL_NAME_EXACT:
        return True
    return any(n.startswith(prefix) for prefix in _TOOL_NAME_PREFIXES)


# Kept for the existing callers in this module and its tests; the steam_gaming
# plugin imports the public name.
_is_tool_app = is_tool_app
```

- [ ] **Step 4: Tests**

Run: `cd backend ; python -m pytest tests/plugins/test_steam_gaming_detection.py tests/game_libraries/ tests/plugins/test_steam_gaming_plugin.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Lint und Commit**

Run: `cd backend ; python -m ruff check app/plugins/installed/steam_gaming/detection.py app/services/game_libraries/steam.py tests/plugins/test_steam_gaming_detection.py tests/game_libraries/test_games_steam_provider.py`
Expected: `All checks passed!`

```bash
git add backend/app/plugins/installed/steam_gaming/detection.py backend/app/services/game_libraries/steam.py backend/tests/plugins/test_steam_gaming_detection.py backend/tests/game_libraries/test_games_steam_provider.py
git commit -m "refactor(steam-gaming): Erkennung ohne Dev-Stand-in abrufbar, Tool-Filter öffentlich" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01ATWS2TMkGeJzKetpRttHtC"
```

---

### Task 4: Manifestbasierte Spieleliste (`library.py`)

**Files:**
- Create: `backend/app/plugins/installed/steam_gaming/library.py`
- Test: `backend/tests/plugins/test_steam_gaming_library.py`

**Interfaces:**
- Consumes: `app.services.game_libraries.steam.find_steamapps_dirs() -> list[Path]`, `is_tool_app(name) -> bool` (Task 3), `app.services.game_libraries.vdf.parse(text) -> dict`.
- Produces:
  - `@dataclass(frozen=True) class InstalledGame: app_id: str; name: str`
  - `class LibraryUnavailable(Exception)`
  - `is_valid_app_id(app_id: str) -> bool`
  - `list_installed_games() -> list[InstalledGame]` (30-s-Cache pro Worker)
  - `find_installed_game(app_id: str) -> Optional[InstalledGame]` (immer frisch)
  - `reset_cache() -> None` (Tests)
  - `DEV_GAMES: tuple[InstalledGame, ...]`

- [ ] **Step 1: Tests schreiben**

`backend/tests/plugins/test_steam_gaming_library.py`:

```python
"""Installed, launchable games - one manifest per game, nothing else."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.plugins.installed.steam_gaming import library


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    library.reset_cache()
    monkeypatch.setattr(library.settings, "is_dev_mode", False)
    yield
    library.reset_cache()


def _steamapps(root: Path, games: dict[str, str | None]) -> Path:
    """games maps a manifest file id -> name (None writes no name field)."""
    steamapps = root / "steamapps"
    steamapps.mkdir(parents=True)
    for app_id, name in games.items():
        body = f'"AppState"\n{{\n\t"appid"\t\t"{app_id}"\n'
        if name is not None:
            body += f'\t"name"\t\t"{name}"\n'
        body += "}\n"
        (steamapps / f"appmanifest_{app_id}.acf").write_text(body, encoding="utf-8")
    return steamapps


class TestIsValidAppId:
    @pytest.mark.parametrize("value", ["400", "1091500", "1234567890"])
    def test_digits_up_to_ten(self, value):
        assert library.is_valid_app_id(value) is True

    @pytest.mark.parametrize("value", ["", "abc", "400\n", "٤٠٠", "12345678901", "400/1", " 400", "-1"])
    def test_everything_else(self, value):
        assert library.is_valid_app_id(value) is False


class TestListInstalledGames:
    def test_a_manifest_with_a_name_is_a_game(self, tmp_path, monkeypatch):
        steamapps = _steamapps(tmp_path / "lib", {"400": "Portal"})
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [steamapps])

        assert library.list_installed_games() == [library.InstalledGame("400", "Portal")]

    def test_tools_and_nameless_manifests_are_skipped(self, tmp_path, monkeypatch):
        steamapps = _steamapps(tmp_path / "lib", {
            "400": "Portal", "3658110": "Proton 10.0", "55": None,
        })
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [steamapps])

        assert [g.app_id for g in library.list_installed_games()] == ["400"]

    def test_a_game_in_two_libraries_is_listed_once(self, tmp_path, monkeypatch):
        a = _steamapps(tmp_path / "a", {"400": "Portal"})
        b = _steamapps(tmp_path / "b", {"400": "Portal", "620": "Portal 2"})
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [a, b])

        assert [g.app_id for g in library.list_installed_games()] == ["400", "620"]

    def test_sorted_by_name_case_insensitively(self, tmp_path, monkeypatch):
        steamapps = _steamapps(tmp_path / "lib", {"1": "valheim", "2": "Among Us", "3": "BeamNG"})
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [steamapps])

        assert [g.name for g in library.list_installed_games()] == ["Among Us", "BeamNG", "valheim"]

    def test_long_names_are_truncated(self, tmp_path, monkeypatch):
        steamapps = _steamapps(tmp_path / "lib", {"400": "A" * 500})
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [steamapps])

        assert len(library.list_installed_games()[0].name) == 200

    def test_a_file_with_a_non_numeric_id_is_ignored(self, tmp_path, monkeypatch):
        steamapps = _steamapps(tmp_path / "lib", {"400": "Portal"})
        (steamapps / "appmanifest_evil.acf").write_text('"AppState"\n{\n\t"name"\t"x"\n}\n', encoding="utf-8")
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [steamapps])

        assert [g.app_id for g in library.list_installed_games()] == ["400"]

    def test_no_library_at_all_is_unavailable_in_prod(self, monkeypatch):
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [])

        with pytest.raises(library.LibraryUnavailable):
            library.list_installed_games()

    def test_no_library_in_dev_mode_is_the_mock(self, monkeypatch):
        monkeypatch.setattr(library.settings, "is_dev_mode", True)
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [])

        assert library.list_installed_games() == sorted(library.DEV_GAMES, key=lambda g: g.name.casefold())

    def test_the_list_is_cached_within_the_ttl(self, tmp_path, monkeypatch):
        steamapps = _steamapps(tmp_path / "lib", {"400": "Portal"})
        calls: list[int] = []

        def _counting():
            calls.append(1)
            return [steamapps]

        monkeypatch.setattr(library, "find_steamapps_dirs", _counting)
        clock = {"now": 100.0}
        monkeypatch.setattr(library, "_monotonic", lambda: clock["now"])

        library.list_installed_games()
        library.list_installed_games()
        assert len(calls) == 1

        clock["now"] += library._LIST_TTL_SECONDS + 1
        library.list_installed_games()
        assert len(calls) == 2


class TestFindInstalledGame:
    def test_finds_by_reading_one_manifest(self, tmp_path, monkeypatch):
        steamapps = _steamapps(tmp_path / "lib", {"400": "Portal"})
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [steamapps])

        assert library.find_installed_game("400") == library.InstalledGame("400", "Portal")

    def test_unknown_tool_and_invalid_ids_are_none(self, tmp_path, monkeypatch):
        steamapps = _steamapps(tmp_path / "lib", {"3658110": "Proton 10.0"})
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [steamapps])

        assert library.find_installed_game("400") is None
        assert library.find_installed_game("3658110") is None
        assert library.find_installed_game("../400") is None

    def test_it_is_never_served_from_the_list_cache(self, tmp_path, monkeypatch):
        steamapps = _steamapps(tmp_path / "lib", {"400": "Portal"})
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [steamapps])
        library.list_installed_games()

        (steamapps / "appmanifest_400.acf").unlink()

        assert library.find_installed_game("400") is None

    def test_no_library_is_unavailable_in_prod(self, monkeypatch):
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [])

        with pytest.raises(library.LibraryUnavailable):
            library.find_installed_game("400")

    def test_dev_mode_finds_a_mock_game(self, monkeypatch):
        monkeypatch.setattr(library.settings, "is_dev_mode", True)
        monkeypatch.setattr(library, "find_steamapps_dirs", lambda: [])

        assert library.find_installed_game("570") == library.InstalledGame("570", "Dota 2")
```

- [ ] **Step 2: Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/plugins/test_steam_gaming_library.py -v --no-cov`
Expected: FAIL — `ImportError: cannot import name 'library'`.

- [ ] **Step 3: Implementieren**

`backend/app/plugins/installed/steam_gaming/library.py`:

```python
"""Installed, launchable Steam games - one manifest per game, nothing else.

Deliberately NOT built on services/game_libraries/service.get_game_libraries():
that one swallows provider failures (a spun-down mount would read as "nothing
installed" and turn a launch into a 404), takes app ids from
libraryfolders.vdf even when no manifest exists, and reads sizes nobody here
needs.

A game counts as installed when ``appmanifest_<id>.acf`` exists in one of the
steamapps directories, its name is readable, and it is not a Steam tool
(Proton, runtimes, redistributables). The id comes from the file name and is
checked like the id in a launch request, so nothing unvalidated ever reaches a
steam:// URL.

All of this is blocking filesystem I/O - call via asyncio.to_thread.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.services.game_libraries import vdf
from app.services.game_libraries.steam import find_steamapps_dirs, is_tool_app

# fullmatch, not \d (matches Unicode digits) and not $ (matches before "\n").
_APP_ID_RE = re.compile(r"[0-9]{1,10}")
_MANIFEST_RE = re.compile(r"appmanifest_([0-9]{1,10})\.acf")
_NAME_MAX = 200
_LIST_TTL_SECONDS = 30.0
_LIST_CACHE: dict[str, object] = {}


@dataclass(frozen=True)
class InstalledGame:
    app_id: str
    name: str


# The Windows dev box has no Steam library; same titles as the game_libraries mock.
DEV_GAMES: tuple[InstalledGame, ...] = (
    InstalledGame("1091500", "Cyberpunk 2077"),
    InstalledGame("570", "Dota 2"),
    InstalledGame("730", "Counter-Strike 2"),
)


class LibraryUnavailable(Exception):
    """No steamapps directory could be found at all."""


def _monotonic() -> float:
    """Indirection so tests can control the clock."""
    return time.monotonic()


def reset_cache() -> None:
    """Drop the list cache. Intended for tests."""
    _LIST_CACHE.clear()


def is_valid_app_id(app_id: str) -> bool:
    """True for 1-10 ASCII digits and nothing else."""
    return _APP_ID_RE.fullmatch(app_id) is not None


def _read_name(manifest: Path) -> Optional[str]:
    """The launchable display name in *manifest*, or None."""
    try:
        data = vdf.parse(manifest.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        # Missing or corrupt: not launchable, and no reason to break the rest.
        return None
    state = data.get("AppState")
    if not isinstance(state, dict):
        return None
    raw = state.get("name")
    if not isinstance(raw, str) or not raw.strip():
        return None
    name = raw.strip()
    if is_tool_app(name):
        return None
    return name[:_NAME_MAX]


def _scan(dirs: list[Path]) -> list[InstalledGame]:
    found: dict[str, InstalledGame] = {}
    for steamapps in dirs:
        try:
            manifests = sorted(steamapps.glob("appmanifest_*.acf"))
        except OSError:
            continue
        for manifest in manifests:
            match = _MANIFEST_RE.fullmatch(manifest.name)
            if match is None:
                continue
            app_id = match.group(1)
            if app_id in found:
                continue
            name = _read_name(manifest)
            if name is not None:
                found[app_id] = InstalledGame(app_id, name)
    return sorted(found.values(), key=lambda game: game.name.casefold())


def list_installed_games() -> list[InstalledGame]:
    """Every launchable game, sorted by name. Cached per worker for 30 s."""
    now = _monotonic()
    checked_at = _LIST_CACHE.get("checked_at")
    if isinstance(checked_at, float) and now - checked_at < _LIST_TTL_SECONDS:
        return list(_LIST_CACHE["games"])  # type: ignore[arg-type]

    dirs = find_steamapps_dirs()
    if not dirs:
        if not settings.is_dev_mode:
            raise LibraryUnavailable("no steamapps directory found")
        games = sorted(DEV_GAMES, key=lambda game: game.name.casefold())
    else:
        games = _scan(dirs)

    _LIST_CACHE["checked_at"] = now
    _LIST_CACHE["games"] = games
    return list(games)


def find_installed_game(app_id: str) -> Optional[InstalledGame]:
    """The launchable game with *app_id*, read fresh from its manifest, or None."""
    if not is_valid_app_id(app_id):
        return None
    dirs = find_steamapps_dirs()
    if not dirs:
        if not settings.is_dev_mode:
            raise LibraryUnavailable("no steamapps directory found")
        return next((game for game in DEV_GAMES if game.app_id == app_id), None)
    for steamapps in dirs:
        name = _read_name(steamapps / f"appmanifest_{app_id}.acf")
        if name is not None:
            return InstalledGame(app_id, name)
    return None
```

- [ ] **Step 4: Tests**

Run: `cd backend ; python -m pytest tests/plugins/test_steam_gaming_library.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Lint und Commit**

Run: `cd backend ; python -m ruff check app/plugins/installed/steam_gaming/library.py tests/plugins/test_steam_gaming_library.py`
Expected: `All checks passed!`

```bash
git add backend/app/plugins/installed/steam_gaming/library.py backend/tests/plugins/test_steam_gaming_library.py
git commit -m "feat(steam-gaming): manifestbasierte Liste startbarer Spiele" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01ATWS2TMkGeJzKetpRttHtC"
```

---

### Task 5: Gemeinsamer Startablauf (`launch.py`) und `launch_game`

**Files:**
- Create: `backend/app/plugins/installed/steam_gaming/launch.py`
- Modify: `backend/app/plugins/installed/steam_gaming/launcher.py` (neue Funktion `launch_game`)
- Modify: `backend/app/plugins/installed/steam_gaming/__init__.py:33-43` (Imports) und `:248-305` (`run_menu_action`)
- Modify: `backend/tests/plugins/test_steam_gaming_plugin.py` (Patch-Ziele)
- Test: `backend/tests/plugins/test_steam_gaming_launch.py`
- Test: `backend/tests/plugins/test_steam_gaming_launcher.py` (anhängen)

**Interfaces:**
- Consumes: `launcher._dispatch(url, what)` (Plan A), `gaming_state.mark_started()`, `get_desktop_service().enable() -> Awaitable[tuple[bool, str]]`, `unlock_if_permitted(*, user, client_host, db) -> Awaitable[tuple[bool, str]]`.
- Produces:
  - `launcher.launch_game(app_id: str) -> tuple[bool, str]` — URL `steam://rungameid/<app_id>`
  - `launch.GamingModeStart(ok: bool, failed_step: Optional[Literal["displays", "steam"]], detail: str)` (frozen dataclass)
  - `async launch.start_gaming_mode(*, user, client_host: Optional[str], db) -> GamingModeStart`
  - `launch.launch_game` (Re-Export aus `launcher`, damit Routen und Tests es über `launch` erreichen)

- [ ] **Step 1: Launcher-Test anhängen**

An `backend/tests/plugins/test_steam_gaming_launcher.py`:

```python
class TestLaunchGame:
    def test_builds_the_rungameid_url(self, prod):
        from app.plugins.installed.steam_gaming.launcher import launch_game

        with patch("subprocess.run", return_value=_completed()) as run:
            ok, _detail = launch_game("400")

        assert ok is True
        assert run.call_args.args[0][-1] == "steam://rungameid/400"
        assert run.call_args.args[0][:5] == ["systemd-run", "--user", "--collect", "--quiet", "steam"]

    def test_refuses_anything_but_digits(self, prod):
        """Defense in depth: the route validates first, but the launcher is the
        last stop before a command line."""
        from app.plugins.installed.steam_gaming.launcher import launch_game

        with patch("subprocess.run") as run:
            for bad in ("400//-console", "abc", "400\n", ""):
                ok, _detail = launch_game(bad)
                assert ok is False

        run.assert_not_called()
```

- [ ] **Step 2: `launch.py`-Tests schreiben**

`backend/tests/plugins/test_steam_gaming_launch.py`:

```python
"""The gaming-mode start sequence shared by menu action and launch route."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.plugins.installed.steam_gaming import gaming_state, launch

_P = "app.plugins.installed.steam_gaming.launch"


@pytest.fixture(autouse=True)
def _marker_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(gaming_state.settings, "nas_storage_path", str(tmp_path))


def _desktop(ok: bool = True, order: list[str] | None = None):
    service = MagicMock()

    async def _enable():
        if order is not None:
            order.append("displays")
        return ok, "ok" if ok else "kscreen-doctor not found"

    service.enable = AsyncMock(side_effect=_enable)
    return patch(f"{_P}.get_desktop_service", return_value=service)


class TestStartGamingMode:
    async def test_order_is_displays_unlock_bigpicture_marker(self):
        order: list[str] = []

        async def _unlock(**_kwargs):
            order.append("unlock")
            return True, "unlocked"

        with _desktop(order=order), patch(f"{_P}.unlock_if_permitted", _unlock), patch(
            f"{_P}.open_big_picture",
            side_effect=lambda: order.append("bigpicture") or (True, "requested"),
        ), patch(
            f"{_P}.gaming_state.mark_started", side_effect=lambda: order.append("marker"),
        ):
            result = await launch.start_gaming_mode(
                user=MagicMock(role="admin"), client_host="192.168.178.29", db=None
            )

        assert result == launch.GamingModeStart(ok=True, failed_step=None, detail="requested")
        assert order == ["displays", "unlock", "bigpicture", "marker"]

    async def test_dark_displays_stop_everything(self):
        with _desktop(ok=False), patch(f"{_P}.open_big_picture") as bigpicture:
            result = await launch.start_gaming_mode(user=None, client_host=None, db=None)

        bigpicture.assert_not_called()
        assert result.ok is False and result.failed_step == "displays"
        assert gaming_state.is_active() is False

    async def test_a_refused_unlock_is_not_a_failure(self):
        async def _unlock(**_kwargs):
            return False, "permission required: power:unlock_session"

        with _desktop(), patch(f"{_P}.unlock_if_permitted", _unlock), patch(
            f"{_P}.open_big_picture", return_value=(True, "requested")
        ):
            result = await launch.start_gaming_mode(
                user=MagicMock(role="user"), client_host="192.168.178.29", db=None
            )

        assert result.ok is True

    async def test_no_user_means_no_unlock_attempt(self):
        gate = AsyncMock(return_value=(True, "unlocked"))
        with _desktop(), patch(f"{_P}.unlock_if_permitted", gate), patch(
            f"{_P}.open_big_picture", return_value=(True, "requested")
        ):
            await launch.start_gaming_mode(user=None, client_host=None, db=None)

        gate.assert_not_awaited()

    async def test_steam_failure_sets_no_marker(self):
        with _desktop(), patch(f"{_P}.open_big_picture", return_value=(False, "steam could not be started")):
            result = await launch.start_gaming_mode(user=None, client_host=None, db=None)

        assert result.ok is False and result.failed_step == "steam"
        assert gaming_state.is_active() is False

    async def test_an_already_set_marker_does_not_change_the_sequence(self):
        """Big Picture already open: a second open/bigpicture is forwarded to
        the running client (measured M4) - the sequence just runs again."""
        gaming_state.mark_started()
        with _desktop(), patch(f"{_P}.open_big_picture", return_value=(True, "requested")) as bigpicture:
            result = await launch.start_gaming_mode(user=None, client_host=None, db=None)

        bigpicture.assert_called_once()
        assert result.ok is True
        assert gaming_state.is_active() is True
```

- [ ] **Step 3: Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/plugins/test_steam_gaming_launch.py tests/plugins/test_steam_gaming_launcher.py -v --no-cov`
Expected: FAIL — `ImportError: cannot import name 'launch'` bzw. `'launch_game'`.

- [ ] **Step 4: `launch_game` im Launcher**

In `backend/app/plugins/installed/steam_gaming/launcher.py` oben bei den Imports `import re` ergänzen und nach `CLOSE_BIG_PICTURE_URL = ...`:

```python
RUN_GAME_URL_PREFIX = "steam://rungameid/"
_APP_ID_RE = re.compile(r"[0-9]{1,10}")
```

Am Dateiende:

```python
def launch_game(app_id: str) -> tuple[bool, str]:
    """Ask Steam to start the game *app_id*. Blocking - call via asyncio.to_thread.

    Digits only, checked again here although the route already did: this is
    the last stop before a command line. Anything else - ``//`` launch
    arguments, 64-bit shortcut ids - never becomes a URL.

    Returns:
        (ok, detail). ok=True means the unit was started, not that the game
        runs - the steam_gaming detector sees that once Steam's reaper appears.
    """
    if _APP_ID_RE.fullmatch(app_id) is None:
        return False, "invalid app id"
    return _dispatch(f"{RUN_GAME_URL_PREFIX}{app_id}", "game")
```

- [ ] **Step 5: `launch.py`**

`backend/app/plugins/installed/steam_gaming/launch.py`:

```python
"""The gaming-mode start sequence, shared by the power-menu action and the launch route.

Displays on, then the lock screen, then Big Picture, then the marker - in that
order, for the reasons in the plugin's CLAUDE.md ("Gaming Mode"). Pulled out of
SteamGamingPlugin.run_menu_action so the launch route runs exactly the same
steps instead of a second copy that would drift.

No outer timeout here or in the callers' route: asyncio.wait_for only cancels
the await, never the thread behind it, so a cut-off unlock would still unlock -
without its audit entry (#643). Each step bounds itself instead.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Literal, Optional

from app.plugins.installed.steam_gaming import gaming_state
from app.plugins.installed.steam_gaming.launcher import launch_game, open_big_picture
from app.services.power.desktop import get_desktop_service
from app.services.power.session_lock import unlock_if_permitted

logger = logging.getLogger(__name__)

__all__ = ["GamingModeStart", "launch_game", "start_gaming_mode"]


@dataclass(frozen=True)
class GamingModeStart:
    ok: bool
    failed_step: Optional[Literal["displays", "steam"]]
    detail: str  # for the log only - never for a response or the audit trail


async def start_gaming_mode(
    *, user: Optional[Any], client_host: Optional[str], db: Any
) -> GamingModeStart:
    """Run the start sequence. A refused unlock is not a failure."""
    # Displays first: opening Big Picture onto dark screens helps nobody.
    # LinuxDesktopBackend.enable() runs kscreen-doctor in a thread.
    ok, detail = await get_desktop_service().enable()
    if not ok:
        logger.warning("gaming mode: turning the displays on failed: %s", detail)
        return GamingModeStart(ok=False, failed_step="displays", detail=detail)

    # Then the lock screen, under the core's own right + LAN gate and audit.
    # Callers without a user (older menu dispatch) simply do not unlock.
    if user is not None:
        unlocked, unlock_detail = await unlock_if_permitted(
            user=user, client_host=client_host, db=db
        )
        if not unlocked:
            logger.info("gaming mode: session not unlocked: %s", unlock_detail)

    launched, detail = await asyncio.to_thread(open_big_picture)
    if not launched:
        logger.warning("gaming mode: Big Picture did not start: %s", detail)
        return GamingModeStart(ok=False, failed_step="steam", detail=detail)

    # Only now: the marker drives which direction the menu offers, so recording
    # a start that never happened would hide "start" behind a useless "end".
    await asyncio.to_thread(gaming_state.mark_started)
    return GamingModeStart(ok=True, failed_step=None, detail=detail)
```

- [ ] **Step 6: Menüaktion auf den Helfer umstellen**

In `backend/app/plugins/installed/steam_gaming/__init__.py`:

Die Imports
```python
from app.plugins.installed.steam_gaming.launcher import close_big_picture, open_big_picture
```
und
```python
from app.services.power.desktop import get_desktop_service
```
und
```python
from app.services.power.session_lock import unlock_if_permitted
```
ersetzen durch (die zweite und dritte Zeile entfallen ersatzlos):
```python
from app.plugins.installed.steam_gaming.launch import start_gaming_mode
from app.plugins.installed.steam_gaming.launcher import close_big_picture
```

`run_menu_action` (ab `async def run_menu_action(` bis vor `async def _end_gaming_mode`) ersetzen durch:

```python
    async def run_menu_action(
        self,
        action_id: str,
        db: Session,
        *,
        user=None,
        client_host: Optional[str] = None,
    ) -> Optional[MenuActionResult]:
        if action_id == _MENU_END_ACTION_ID:
            return await self._end_gaming_mode()
        if action_id != _MENU_ACTION_ID:
            return None

        # The sequence lives in launch.py so the launch route runs the very
        # same steps. The user only ever sees the translated key; the detail
        # goes into the literal fallback like before.
        started = await start_gaming_mode(user=user, client_host=client_host, db=db)
        if started.failed_step == "displays":
            return MenuActionResult(
                ok=False,
                message_key="menu_displays_failed",
                message_text=f"Displays could not be turned on: {started.detail}",
            )
        if started.failed_step == "steam":
            return MenuActionResult(
                ok=False,
                message_key="menu_steam_failed",
                message_text=f"Displays are on, but Steam did not start: {started.detail}",
            )
        # "started", not "Big Picture is running": nothing past the spawn is
        # observable from here.
        return MenuActionResult(
            ok=True,
            message_key="menu_gaming_mode_started",
            message_text="Gaming mode started",
        )

```

- [ ] **Step 7: Patch-Ziele der bestehenden Plugin-Tests umziehen**

In `backend/tests/plugins/test_steam_gaming_plugin.py` mit Suchen-und-Ersetzen (alle Vorkommen):

| Alt | Neu |
|---|---|
| `"app.plugins.installed.steam_gaming.get_desktop_service"` | `"app.plugins.installed.steam_gaming.launch.get_desktop_service"` |
| `"app.plugins.installed.steam_gaming.open_big_picture"` | `"app.plugins.installed.steam_gaming.launch.open_big_picture"` |
| `"app.plugins.installed.steam_gaming.unlock_if_permitted"` | `"app.plugins.installed.steam_gaming.launch.unlock_if_permitted"` |

**Keine Assertion ändern.** `_patch_end_action` (`close_big_picture`, `show_desktop`, `steam_is_running`, `_current_game`) bleibt unverändert.

- [ ] **Step 8: Tests**

Run: `cd backend ; python -m pytest tests/plugins/test_steam_gaming_launch.py tests/plugins/test_steam_gaming_launcher.py tests/plugins/test_steam_gaming_plugin.py tests/plugins/test_plugin_menu_actions.py -v --no-cov`
Expected: PASS — insbesondere alle bestehenden Gaming-Mode-Tests mit unveränderten Assertions.

Probe: in Step 7 eine Ersetzung testweise rückgängig machen → der betroffene Test wird rot (der Patch greift ins Leere). Zurücksetzen und im Report nennen.

- [ ] **Step 9: Lint und Commit**

Run: `cd backend ; python -m ruff check app/plugins/installed/steam_gaming tests/plugins/test_steam_gaming_launch.py tests/plugins/test_steam_gaming_launcher.py tests/plugins/test_steam_gaming_plugin.py`
Expected: `All checks passed!`

```bash
git add backend/app/plugins/installed/steam_gaming/launch.py backend/app/plugins/installed/steam_gaming/launcher.py backend/app/plugins/installed/steam_gaming/__init__.py backend/tests/plugins/test_steam_gaming_launch.py backend/tests/plugins/test_steam_gaming_launcher.py backend/tests/plugins/test_steam_gaming_plugin.py
git commit -m "refactor(steam-gaming): Gaming-Mode-Start in launch.py, launch_game im Launcher" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01ATWS2TMkGeJzKetpRttHtC"
```

---

### Task 6: Routen, Modelle, Rate-Limits und Plugin-Doku

**Files:**
- Create: `backend/app/plugins/installed/steam_gaming/models.py`
- Create: `backend/app/plugins/installed/steam_gaming/routes.py`
- Modify: `backend/app/plugins/installed/steam_gaming/__init__.py` (neue Methode `get_router`)
- Modify: `backend/app/core/rate_limiter.py` (zwei Kategorien am Ende des Dicts nach `"bluetooth": "120/minute",`)
- Modify: `backend/app/plugins/installed/steam_gaming/CLAUDE.md`, `backend/app/plugins/CLAUDE.md`, `CLAUDE.md` (Root, Quick Reference), `.claude/rules/architecture.md`, `.claude/rules/security-agent.md`
- Test: `backend/tests/plugins/test_steam_gaming_routes.py`

**Interfaces:**
- Consumes: `require_power_launch_games` (Task 1), `detection.current_app_id(dev_stand_in=False)` (Task 3), `library.*` (Task 4), `launch.start_gaming_mode`, `launch.launch_game`, `launch.GamingModeStart` (Task 5), `session_lock.current_lock_state() -> Awaitable[Optional[bool]]`.
- Produces: `GET /api/plugins/steam_gaming/games` → `GameListResponse`; `POST /api/plugins/steam_gaming/games/{app_id}/launch` → `202 LaunchResponse`; `SteamGamingPlugin.get_router() -> APIRouter`.

- [ ] **Step 1: Routen-Tests schreiben**

`backend/tests/plugins/test_steam_gaming_routes.py`:

```python
"""Launch routes: right, LAN gate, validation order, status codes, audit hygiene.

Driven through TestClient on purpose - only a real request exercises FastAPI's
body/param detection behind slowapi, which a future-annotations import breaks.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import require_power_launch_games
from app.core.database import get_db
from app.core.exception_handlers import register_exception_handlers
from app.plugins.installed.steam_gaming import SteamGamingPlugin, routes
from app.plugins.installed.steam_gaming.launch import GamingModeStart
from app.plugins.installed.steam_gaming.library import InstalledGame, LibraryUnavailable

BASE = "/api/plugins/steam_gaming"
PORTAL = InstalledGame("400", "Portal")


class _Admin:
    id = 1
    username = "admin"
    role = "admin"


class _User:
    id = 2
    username = "someone"
    role = "user"


class _State:
    lan = True
    running: object = None
    order: list = []


@pytest.fixture(autouse=True)
def _stubs(monkeypatch):
    _State.lan = True
    _State.running = None
    _State.order = []
    monkeypatch.setattr(routes, "is_private_or_local_ip", lambda host: _State.lan)
    monkeypatch.setattr(routes.library, "list_installed_games", lambda: [PORTAL])
    monkeypatch.setattr(
        routes.library, "find_installed_game", lambda app_id: PORTAL if app_id == "400" else None
    )
    monkeypatch.setattr(
        routes.detection, "current_app_id", lambda *, dev_stand_in=True: _State.running
    )
    monkeypatch.setattr(routes.detection, "resolve_game_name", lambda app_id: "Metro Exodus")
    monkeypatch.setattr(routes, "current_lock_state", AsyncMock(return_value=False))

    async def _start(**kwargs):
        _State.order.append(("start", kwargs["client_host"]))
        return GamingModeStart(ok=True, failed_step=None, detail="requested")

    monkeypatch.setattr(routes.launch, "start_gaming_mode", _start)

    def _launch_game(app_id):
        _State.order.append(("game", app_id))
        return True, "game requested"

    monkeypatch.setattr(routes.launch, "launch_game", _launch_game)


@pytest.fixture
def audit(monkeypatch):
    events: list[dict] = []
    security: list[dict] = []

    class _Recorder:
        def log_event(self, **kwargs):
            events.append(kwargs)

        def log_security_event(self, **kwargs):
            security.append(kwargs)

    monkeypatch.setattr(routes, "get_audit_logger_db", lambda: _Recorder())
    return events, security


def _client(user=_Admin) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(SteamGamingPlugin().get_router(), prefix=BASE)
    app.dependency_overrides[require_power_launch_games] = lambda: user()
    app.dependency_overrides[get_db] = lambda: MagicMock()
    return TestClient(app)


class TestPermission:
    def test_both_routes_are_gated(self):
        app = FastAPI()
        app.include_router(SteamGamingPlugin().get_router(), prefix=BASE)
        client = TestClient(app)
        assert client.get(f"{BASE}/games").status_code in (401, 403)
        assert client.post(f"{BASE}/games/400/launch").status_code in (401, 403)

    def test_a_delegated_user_may_launch(self, audit):
        _events, security = audit
        assert _client(_User).post(f"{BASE}/games/400/launch").status_code == 202
        assert security and security[0]["resource"] == "launch_games"


class TestList:
    def test_lists_games_and_running_state(self):
        _State.running = "1449560"
        body = _client().get(f"{BASE}/games").json()
        assert body["games"] == [{"app_id": "400", "name": "Portal"}]
        assert body["running"] == {"app_id": "1449560", "name": "Metro Exodus"}
        assert body["can_launch_here"] is True

    def test_says_when_launching_is_not_possible_from_here(self):
        _State.lan = False
        assert _client().get(f"{BASE}/games").json()["can_launch_here"] is False

    def test_an_unreadable_library_is_503(self, monkeypatch):
        def _raise():
            raise LibraryUnavailable("gone")

        monkeypatch.setattr(routes.library, "list_installed_games", _raise)
        resp = _client().get(f"{BASE}/games")
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Game library unavailable"


class TestLaunchGates:
    def test_outside_the_lan_is_403_even_for_an_admin_and_audited_with_ip(self, audit):
        events, _ = audit
        _State.lan = False
        resp = _client().post(f"{BASE}/games/400/launch")
        assert resp.status_code == 403
        assert events[-1]["action"] == "steam_game_launch_denied"
        assert events[-1]["success"] is False
        assert events[-1]["ip_address"] == "testclient"
        assert _State.order == []

    @pytest.mark.parametrize("app_id", ["abc", "400%0A", "%D9%A4%D9%A0%D9%A0", "12345678901", "401"])
    def test_invalid_or_unknown_ids_are_404_without_audit(self, app_id, audit):
        events, _ = audit
        resp = _client().post(f"{BASE}/games/{app_id}/launch")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Game not installed"
        assert events == []
        assert _State.order == []

    def test_an_encoded_slash_never_reaches_the_launcher(self):
        assert _client().post(f"{BASE}/games/400%2F1/launch").status_code == 404
        assert _State.order == []

    def test_an_unreadable_library_is_503(self, monkeypatch):
        def _raise(app_id):
            raise LibraryUnavailable("gone")

        monkeypatch.setattr(routes.library, "find_installed_game", _raise)
        assert _client().post(f"{BASE}/games/400/launch").status_code == 503
        assert _State.order == []

    def test_a_running_game_is_409_without_audit(self, audit):
        events, _ = audit
        _State.running = "1449560"
        resp = _client().post(f"{BASE}/games/400/launch")
        assert resp.status_code == 409
        assert resp.json()["detail"] == "A game is already running"
        assert events == []
        assert _State.order == []


class TestLaunchSequence:
    def test_starts_gaming_mode_then_the_library_id(self, audit):
        events, _ = audit
        resp = _client().post(f"{BASE}/games/400/launch")
        assert resp.status_code == 202
        assert resp.json() == {"status": "requested", "session_locked": False}
        assert _State.order == [("start", "testclient"), ("game", "400")]
        assert events[-1]["action"] == "steam_game_launch"
        assert events[-1]["success"] is True
        assert events[-1]["details"] == {"app_id": "400", "failed_step": None}

    def test_uses_the_id_from_the_library_entry(self, monkeypatch):
        monkeypatch.setattr(
            routes.library, "find_installed_game", lambda app_id: InstalledGame("400", "Portal")
        )
        _client().post(f"{BASE}/games/400/launch")
        assert ("game", "400") in _State.order

    @pytest.mark.parametrize("locked", [True, False, None])
    def test_reports_the_lock_state_afterwards(self, monkeypatch, locked):
        monkeypatch.setattr(routes, "current_lock_state", AsyncMock(return_value=locked))
        assert _client().post(f"{BASE}/games/400/launch").json()["session_locked"] is locked

    def test_dark_displays_are_502_and_no_game(self, monkeypatch, audit):
        events, _ = audit

        async def _start(**_kwargs):
            return GamingModeStart(ok=False, failed_step="displays", detail="kscreen-doctor: /secret")

        monkeypatch.setattr(routes.launch, "start_gaming_mode", _start)
        resp = _client().post(f"{BASE}/games/400/launch")
        assert resp.status_code == 502
        assert resp.json()["detail"] == "Displays could not be turned on"
        assert _State.order == []
        assert events[-1]["details"] == {"app_id": "400", "failed_step": "displays"}
        assert "secret" not in repr(events)

    def test_steam_failure_is_502_and_no_game(self, monkeypatch):
        async def _start(**_kwargs):
            return GamingModeStart(ok=False, failed_step="steam", detail="x")

        monkeypatch.setattr(routes.launch, "start_gaming_mode", _start)
        resp = _client().post(f"{BASE}/games/400/launch")
        assert resp.status_code == 502
        assert resp.json()["detail"] == "Steam could not be started"
        assert not any(step == "game" for step, _ in _State.order)

    def test_a_failed_game_start_is_502_and_audited(self, monkeypatch, audit):
        events, _ = audit
        monkeypatch.setattr(routes.launch, "launch_game", lambda app_id: (False, "steam could not be started"))
        resp = _client().post(f"{BASE}/games/400/launch")
        assert resp.status_code == 502
        assert events[-1]["details"] == {"app_id": "400", "failed_step": "game"}
        assert events[-1]["success"] is False

    def test_the_game_name_never_reaches_the_audit_trail(self, audit):
        events, security = audit
        _client(_User).post(f"{BASE}/games/400/launch")
        assert "Portal" not in repr(events) + repr(security)


class TestRouter:
    def test_the_plugin_contributes_one_stable_router(self):
        plugin = SteamGamingPlugin()
        assert plugin.get_router() is plugin.get_router()
```

- [ ] **Step 2: Fehlschlag bestätigen**

Run: `cd backend ; python -m pytest tests/plugins/test_steam_gaming_routes.py -v --no-cov`
Expected: FAIL — `ImportError: cannot import name 'routes'`.

- [ ] **Step 3: Rate-Limits**

In `backend/app/core/rate_limiter.py` die Zeile
```python
    "bluetooth": "120/minute",
}
```
ersetzen durch:
```python
    "bluetooth": "120/minute",

    # Steam-Spielstart (steam_gaming-Plugin) — BaluApp liest die Liste beim
    # Oeffnen und fragt nach einem Start zweimal nach. Getrennt vom Start, damit
    # das Nachfragen nicht das knappe Start-Budget verbraucht; Starts selbst
    # sind selten, 6/Minute haelt Doppeltipps und Skripte klein.
    "steam_games_read": "60/minute",
    "steam_launch": "6/minute",
}
```

- [ ] **Step 4: `models.py`**

`backend/app/plugins/installed/steam_gaming/models.py`:

```python
"""Pydantic models of the steam_gaming routes; field names are the API contract.

NB: no ``from __future__ import annotations`` - see routes.py.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel


class LaunchableGame(BaseModel):
    app_id: str
    name: str


class RunningGame(BaseModel):
    app_id: str
    name: Optional[str]


class GameListResponse(BaseModel):
    games: List[LaunchableGame]
    running: Optional[RunningGame]
    # Information for the client, not a control - the launch route checks itself.
    can_launch_here: bool


class LaunchResponse(BaseModel):
    status: Literal["requested"]
    # Read after the sequence; None when logind cannot tell.
    session_locked: Optional[bool]
```

- [ ] **Step 5: `routes.py`**

`backend/app/plugins/installed/steam_gaming/routes.py`:

```python
"""HTTP routes of the steam_gaming plugin: list and launch installed games.

Design: docs/superpowers/specs/2026-09-14-steam-game-launch-design.md (PR B).
"""
# NB: no ``from __future__ import annotations`` here (cf. bluetooth, audio_control).
# Deferred annotations behind slowapi's ``@user_limiter.limit`` wrapper become
# ForwardRefs FastAPI can no longer resolve - every request would be a 422.
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_power_launch_games
from app.core.database import get_db
from app.core.exceptions import (
    BadGatewayError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.core.network_utils import is_private_or_local_ip
from app.core.rate_limiter import get_limit, user_limiter
from app.plugins.installed.steam_gaming import detection, launch, library
from app.plugins.installed.steam_gaming.models import (
    GameListResponse,
    LaunchableGame,
    LaunchResponse,
    RunningGame,
)
from app.schemas.user import UserPublic
from app.services.audit.logger_db import get_audit_logger_db
from app.services.power.session_lock import current_lock_state

logger = logging.getLogger(__name__)

router = APIRouter()

_READ_LIMIT = get_limit("steam_games_read")
_LAUNCH_LIMIT = get_limit("steam_launch")


def _client_host(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _audit(
    action: str, user: UserPublic, success: bool, details: dict, client_host: Optional[str]
) -> None:
    """Audit launches and refused attempts - never the game name, never a detail.

    The name comes from a manifest the desktop user can write; details carry
    subprocess and kscreen-doctor output.
    """
    audit_logger = get_audit_logger_db()
    audit_logger.log_event(
        event_type="POWER",
        action=action,
        user=user.username,
        resource="steam_gaming",
        success=success,
        details=details,
        ip_address=client_host,
    )
    if getattr(user, "role", None) != "admin":
        audit_logger.log_security_event(
            action="delegated_power_action",
            user=user.username,
            resource="launch_games",
            details={"action": action},
            success=True,
        )


def _running_game() -> Optional[RunningGame]:
    """The running game without the dev stand-in. Blocking - call via to_thread."""
    app_id = detection.current_app_id(dev_stand_in=False)
    if app_id is None:
        return None
    return RunningGame(app_id=app_id, name=detection.resolve_game_name(app_id))


@router.get("/games", response_model=GameListResponse)
@user_limiter.limit(_READ_LIMIT)
async def list_games(
    request: Request,
    response: Response,
    current_user=Depends(require_power_launch_games),
) -> GameListResponse:
    """Installed, launchable games and what is running right now.

    Behind the launch right although it only reads: the library and the
    running game are information about the box owner. No LAN gate - reading
    creates no trust.
    """
    try:
        games = await asyncio.to_thread(library.list_installed_games)
    except library.LibraryUnavailable as exc:
        raise ServiceUnavailableError("Game library unavailable") from exc
    running = await asyncio.to_thread(_running_game)
    return GameListResponse(
        games=[LaunchableGame(app_id=game.app_id, name=game.name) for game in games],
        running=running,
        can_launch_here=is_private_or_local_ip(_client_host(request)),
    )


@router.post(
    "/games/{app_id}/launch",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=LaunchResponse,
)
@user_limiter.limit(_LAUNCH_LIMIT)
async def launch_installed_game(
    app_id: str,
    request: Request,
    response: Response,
    current_user=Depends(require_power_launch_games),
    db: Session = Depends(get_db),
) -> LaunchResponse:
    """Displays on, unlock (if permitted), Big Picture, then the game.

    Every check runs before the first side effect. No outer timeout: wait_for
    would cancel the await but not the thread behind it (#643).
    """
    client_host = _client_host(request)

    # For every role: a stolen account must not light up and drive the TV
    # from the internet. Refusals are exactly the pattern worth auditing.
    if not is_private_or_local_ip(client_host):
        _audit("steam_game_launch_denied", current_user, False, {"reason": "not_local"}, client_host)
        raise ForbiddenError("Launching is only allowed from the local network")

    if not library.is_valid_app_id(app_id):
        raise NotFoundError("Game not installed")
    try:
        game = await asyncio.to_thread(library.find_installed_game, app_id)
    except library.LibraryUnavailable as exc:
        raise ServiceUnavailableError("Game library unavailable") from exc
    if game is None:
        raise NotFoundError("Game not installed")

    # Nobody with the right takes a running game away from someone else.
    running = await asyncio.to_thread(detection.current_app_id, dev_stand_in=False)
    if running is not None:
        raise ConflictError("A game is already running")

    started = await launch.start_gaming_mode(user=current_user, client_host=client_host, db=db)
    if not started.ok:
        _audit(
            "steam_game_launch", current_user, False,
            {"app_id": game.app_id, "failed_step": started.failed_step}, client_host,
        )
        if started.failed_step == "displays":
            raise BadGatewayError("Displays could not be turned on")
        raise BadGatewayError("Steam could not be started")

    # The id from the library entry, not the request string.
    launched, detail = await asyncio.to_thread(launch.launch_game, game.app_id)
    if not launched:
        logger.warning("steam game launch: %s did not start: %s", game.app_id, detail)
        _audit(
            "steam_game_launch", current_user, False,
            {"app_id": game.app_id, "failed_step": "game"}, client_host,
        )
        raise BadGatewayError("Steam could not be started")

    _audit(
        "steam_game_launch", current_user, True,
        {"app_id": game.app_id, "failed_step": None}, client_host,
    )
    return LaunchResponse(status="requested", session_locked=await current_lock_state())
```

- [ ] **Step 6: `get_router` im Plugin**

In `backend/app/plugins/installed/steam_gaming/__init__.py` in `SteamGamingPlugin` direkt nach `get_menu_items` einfügen:

```python
    def get_router(self):
        """The launch routes (routes.py).

        Imported here, not at module level: routes imports detection, launch
        and library from this package, and the package __init__ must finish
        before those resolve. Routers are mounted once at startup, so enabling
        the plugin later needs a backend restart before these routes exist
        (restart_required reports that) - pill, menu and panel still work
        immediately.
        """
        from app.plugins.installed.steam_gaming.routes import router  # noqa: PLC0415

        return router
```

- [ ] **Step 7: Tests**

Run: `cd backend ; python -m pytest tests/plugins/test_steam_gaming_routes.py tests/plugins/ -q --no-cov`
Expected: PASS. Schlägt ein allgemeiner Plugin-Manager-Test fehl, der für `steam_gaming` „kein Router" annahm: den Test auf das neue Verhalten anpassen und im Report nennen — nicht den Router entfernen.

- [ ] **Step 8: Plugin-Doku**

In `backend/app/plugins/installed/steam_gaming/CLAUDE.md`:

1. Den ersten Absatz nach der Überschrift um einen Satz ergänzen: `It also lets holders of \`can_launch_games\` list installed games and launch one (\`GET /games\`, \`POST /games/{app_id}/launch\`), mainly for BaluApp.`
2. Den Absatz `**No router, no \`plugin.json\`.** …` ersetzen durch:

```markdown
**One router, no `plugin.json`.** Pill, menu, panel, notifications and the
background task come from `PluginBase` method overrides and take effect within
seconds across all workers. The launch routes (`routes.py`) are a router, and
routers are mounted once at startup: enabling the plugin after the backend
started needs a `baluhost-backend` restart before `/api/plugins/steam_gaming/*`
exists (`restart_required` reports it; until then requests get
`404 "Plugin not found"` from the catch-all proxy). `get_router()` imports
`routes` lazily to avoid an import cycle. `routes.py` and `models.py` must not
use `from __future__ import annotations` (slowapi body detection).
```

3. In der Layout-Tabelle nach der `launcher.py`-Zeile ergänzen:

```markdown
| `library.py` | Launchable games: `appmanifest_<id>.acf` present, name readable, not a tool; 30 s per-worker list cache; `LibraryUnavailable` when no steamapps dir exists |
| `launch.py` | `start_gaming_mode()` — the displays → unlock → Big Picture → marker sequence shared by the menu action and the launch route; re-exports `launch_game` |
| `models.py` | Pydantic models of the routes; field names are the API contract |
| `routes.py` | `GET /games`, `POST /games/{app_id}/launch`; right, LAN gate, audit |
```

4. Im Abschnitt „Gaming Mode (the menu action)" nach dem Aufzählungspunkt „Start order is displays → unlock …" ergänzen:

```markdown
- The sequence lives in `launch.py:start_gaming_mode()` and is reused by the
  launch route. Tests patch `steam_gaming.launch.*`, not the package names.
  There is no outer timeout around it (wait_for cancels awaits, not threads —
  #643); steps bound themselves. Worst case ≈ 70 s (displays 30 s, unlock ~15 s,
  Big Picture 10 s, game 10 s, lock state ~3 s), typically < 3 s.
```

5. Neuen Abschnitt vor „## Contributions in one place" einfügen:

```markdown
## Game launch (routes)

- Both routes require `require_power_launch_games` (admins implicitly). The
  right lets a user turn the displays on and open Big Picture as part of a
  launch; unlocking still needs `can_unlock_session` via `unlock_if_permitted()`.
- `POST` checks, before any side effect: LAN/VPN for every role (403, audited
  with IP) → `library.is_valid_app_id` + `find_installed_game` (404; 503 when no
  library is readable) → `current_app_id(dev_stand_in=False)` (409).
- The steam:// URL is built from the library entry's id; `launcher.launch_game`
  re-checks digits-only.
- Audit `steam_game_launch` carries only `app_id` and `failed_step` — never the
  manifest name, never subprocess output. 404/409/503 are not audited.
- Rate limits: `steam_games_read` 60/min, `steam_launch` 6/min.
- `running` and the 409 use `current_app_id(dev_stand_in=False)`, so the
  Windows dev box can click through a launch.
```

6. Im Abschnitt „## Tests" die Dateiliste um `launch`, `library`, `routes` ergänzen.

In `backend/app/plugins/CLAUDE.md` die Zeile
```
    ├── steam_gaming/       # Status pill, session ledger, Gaming-Mode menu action
```
ersetzen durch:
```
    ├── steam_gaming/       # Status pill, session ledger, Gaming-Mode menu action, game launch routes
```

- [ ] **Step 9: Projekt-Doku und Regeln**

In `CLAUDE.md` (Repo-Root), Abschnitt „Quick Reference", nach der Zeile `**Bluetooth**: …` einfügen:
```markdown
**Steam-Spielstart**: `backend/app/plugins/installed/steam_gaming/routes.py` (Routen), `launch.py` (gemeinsamer Gaming-Mode-Ablauf), `library.py` (startbare Spiele); Steam startet über `systemd-run --user` (`launcher.py`, #640)
```

In `.claude/rules/architecture.md`, API-Liste, nach der Zeile `- \`/api/plugins/bluetooth/*\` - …` einfügen:
```markdown
- `/api/plugins/steam_gaming/*` - Steam-Spielstart (Spieleliste, Start; Starten nur aus privaten Netzen, Recht `can_launch_games`)
```

In `.claude/rules/security-agent.md`, Abschnitt „Role Model", nach dem Aufzählungspunkt zu `can_manage_bluetooth` einfügen:
```markdown
- `can_launch_games` (power permission) startet installierte Steam-Spiele über
  `/api/plugins/steam_gaming/games/{app_id}/launch` und schaltet dabei **faktisch
  auch die Displays ein und öffnet Big Picture** — ohne `can_toggle_desktop`; das
  ist der Zweck des Rechts. Entsperren bleibt bei `can_unlock_session`. Start nur
  bei `is_private_or_local_ip(request.client.host)` für alle Rollen; abgelehnte
  Versuche werden mit IP auditiert. API-Keys erreichen die Route wie alle
  `require_power_*`-Routen (bewusst akzeptiert). Die App-ID muss
  `re.fullmatch("[0-9]{1,10}")` erfüllen und als Manifest installiert sein; die
  URL wird aus dem Bibliothekseintrag gebaut. Durchgesetzt in
  `plugins/installed/steam_gaming/routes.py`.
```

- [ ] **Step 10: Lint und Commit**

Run: `cd backend ; python -m ruff check app/plugins/installed/steam_gaming app/core/rate_limiter.py tests/plugins/test_steam_gaming_routes.py`
Expected: `All checks passed!`

```bash
git add backend/app/plugins/installed/steam_gaming/models.py backend/app/plugins/installed/steam_gaming/routes.py backend/app/plugins/installed/steam_gaming/__init__.py backend/app/core/rate_limiter.py backend/tests/plugins/test_steam_gaming_routes.py backend/app/plugins/installed/steam_gaming/CLAUDE.md backend/app/plugins/CLAUDE.md CLAUDE.md .claude/rules/architecture.md .claude/rules/security-agent.md
git commit -m "feat(steam-gaming): Spiele aus BaluApp starten" -m "GET /api/plugins/steam_gaming/games und POST .../games/{app_id}/launch hinter can_launch_games; Start nur aus LAN/VPN, 409 bei laufendem Spiel, Gaming-Mode-Ablauf aus launch.py." -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_01ATWS2TMkGeJzKetpRttHtC"
```

---

### Task 7: Abschlussprüfung und PR

**Files:** keine neuen.

- [ ] **Step 1: Backend-Bereich komplett**

Run: `cd backend ; python -m ruff check app tests ; python -m pytest tests/plugins/ tests/game_libraries/ tests/test_power_permissions_launch_games.py tests/test_power_permissions_manage_bluetooth.py tests/services/power/ -q --no-cov`
Expected: `All checks passed!`, alle PASS. Die volle Suite läuft in der CI.

- [ ] **Step 2: Frontend komplett**

Run: `cd client ; npx vitest run ; npx eslint . ; npm run build`
Expected: alle Tests PASS, eslint 0 Fehler, Build erfolgreich.

- [ ] **Step 3: Alembic ein Head**

Run: `cd backend ; python -m alembic heads`
Expected: genau eine Revision.

- [ ] **Step 4: PR**

PR-Body mit dem Write-Tool nach `<scratchpad>/pr-steam-launch.md`: Zusammenfassung, API-Tabelle, Sicherheit (Recht, LAN, ID-Prüfung, Audit), Deploy-Verifikation (Spec, Abschnitt „Deploy & Betrieb", Schritte 1–3 inkl. Mobilfunk ohne VPN), Hinweis auf BaluApp-Vertrag in der Spec, Verweise #640 #641 #642 #643, Abschlusszeile `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

Run: `git push -u origin feat/steam-game-launch ; gh pr create --base main --title "feat(steam-gaming): Steam-Spiele aus BaluApp starten" --body-file <scratchpad>/pr-steam-launch.md`
Expected: PR-URL.
