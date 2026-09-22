# Dienste-Neustart aus dem Desktop-Tray — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein Menüpunkt im Tray startet alle BaluHost-Units neu — über die API mit BaluHost-Step-up, und bei totem Backend über `systemctl` mit polkit-Abfrage.

**Architecture:** Zwei Wege, ein Menüpunkt. Das Tray probt beim Klick `/api/health`. Antwortet die API, fragt ein Dialog Passwort bzw. TOTP und `POST /api/system/restart-all` erledigt den Rest im Backend (drei Units synchron, `baluhost-backend` zuletzt per Timer). Antwortet sie nicht, ruft das Tray `systemctl restart` selbst; systemd fragt polkit, KDE zeigt den Dialog. Alles Entscheidbare im Tray liegt in `restart.py` und ist ohne Qt, ohne systemd und ohne Backend prüfbar.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy, pytest; Tray: PyQt6, httpx über `baluhost_tui.client.BackendClient`.

**Spec:** `docs/superpowers/specs/2026-09-22-tray-service-restart-design.md`

## Global Constraints

- **Unit-Reihenfolge, wörtlich:** `("baluhost-scheduler", "baluhost-monitoring", "baluhost-webdav", "baluhost-backend")`. `baluhost-backend` steht zuletzt, weil sein Neustart den Prozess beendet, der die Sequenz ausführt. `baluhost-backend-local` gehört **nicht** dazu (socket-aktiviert).
- **Keine neue Rechteregel:** keine sudoers-Zeile, kein polkit-Policy-File, `NoNewPrivileges=yes` in `baluhost-tray.service` bleibt unverändert. Wer im Plan eine Rechteerweiterung braucht, hat sich verlaufen.
- **`subprocess` immer mit Argumentliste**, nie `shell=True` (`.claude/rules/security-agent.md`).
- **Pydantic-Schemas für Request-Bodies**, nie rohes `dict`.
- **Rate-Limit auf jedem neuen Endpunkt** — es gibt keinen globalen Fallback.
- **Deutsch** für alle Texte, die ein Mensch im Tray sieht; Code, Bezeichner und Docstrings wie im umgebenden Modul (Tray-Docstrings sind englisch, Kommentare gemischt).
- **Bestehendes `/api/system/restart` bleibt unangetastet** — `localApi.ts:313` und die Companion-App hängen daran.
- **Testlauf:** `cd backend && python -m pytest <pfad> -v`. Commit nach jeder Task.

---

## File Structure

**Neu:**

| Datei | Verantwortung |
|---|---|
| `backend/app/services/system_restart.py` | Unit-Liste und `systemctl`-Aufruf im Backend. Einzige Stelle, die im Backend `sudo systemctl restart` kennt. |
| `backend/app/services/step_up.py` | Zweiter Nachweis (Passwort oder frisches TOTP) für eine Aktion, die ein gültiges Token allein nicht decken soll. |
| `backend/baluhost_tray/restart.py` | Alles Entscheidbare des Tray-Neustarts: Probe, Pfadwahl, API-Aufruf, `systemctl`-Aufruf, Fehlerabbildung, Sichtbarkeitsregel. |
| `backend/tests/services/test_system_restart.py` | Tests zu Task 1 |
| `backend/tests/services/test_step_up.py` | Tests zu Task 2 |
| `backend/tests/api/test_system_restart_all.py` | Tests zu Task 4 |
| `backend/tests/tray/test_restart.py` | Tests zu Task 5–7 |

**Geändert:**

| Datei | Änderung |
|---|---|
| `backend/app/schemas/system.py` | drei neue Schemas |
| `backend/app/core/rate_limiter.py` | Schlüssel `system_restart` |
| `backend/tests/test_rate_limit_values.py` | Test für den neuen Schlüssel |
| `backend/app/api/routes/system.py` | neue Route `/restart-all` + Helfer `_schedule_backend_restart` |
| `backend/baluhost_tray/tray.py` | Menüpunkt, zwei Bridge-Signale, Dialoge, Arbeitsthread |
| `docs/superpowers/specs/2026-09-21-desktop-tray-design.md` | Nicht-Ziel als überholt markieren |
| `.claude/rules/security-agent.md`, `.claude/rules/architecture.md` | neuer Endpunkt, neue Gap |

---

## Task 1: Backend — Unit-Liste und `systemctl`-Helfer

**Files:**
- Create: `backend/app/services/system_restart.py`
- Test: `backend/tests/services/test_system_restart.py`

**Interfaces:**
- Consumes: nichts
- Produces:
  - `BALUHOST_UNITS: tuple[str, ...]` (4 Einträge, Backend zuletzt)
  - `SUPPORT_UNITS: tuple[str, ...]` (die ersten drei)
  - `BACKEND_UNIT: str`
  - `@dataclass(frozen=True) UnitResult(name: str, success: bool, message: str | None = None)`
  - `restart_unit(unit: str, runner=subprocess.run, timeout: float = 20.0) -> UnitResult`
  - `restart_support_units(runner=subprocess.run) -> list[UnitResult]`

- [ ] **Step 1: Test schreiben**

```python
# backend/tests/services/test_system_restart.py
"""Tests für den systemctl-Helfer des Sammelneustarts."""
import subprocess

from app.services import system_restart


class _Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_backend_unit_is_last():
    """Der Backend-Neustart beendet den Prozess, der die Sequenz ausführt.

    Stünde er nicht am Ende, liefe alles danach nie."""
    assert system_restart.BALUHOST_UNITS[-1] == "baluhost-backend"
    assert system_restart.BACKEND_UNIT == "baluhost-backend"
    assert system_restart.SUPPORT_UNITS == system_restart.BALUHOST_UNITS[:-1]


def test_backend_local_is_not_in_the_list():
    """Socket-aktiviert — die Socket-Unit startet sie bei Bedarf selbst."""
    assert "baluhost-backend-local" not in system_restart.BALUHOST_UNITS


def test_restart_unit_uses_argument_list_without_shell():
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        return _Completed()

    result = system_restart.restart_unit("baluhost-webdav", runner=runner)

    assert result == system_restart.UnitResult("baluhost-webdav", True, None)
    args, kwargs = calls[0]
    assert args == ["sudo", "systemctl", "restart", "baluhost-webdav"]
    assert "shell" not in kwargs
    assert kwargs["timeout"] == 20.0


def test_restart_unit_reports_failure_with_stderr():
    def runner(args, **kwargs):
        return _Completed(returncode=1, stderr="Unit baluhost-webdav.service not found.\n")

    result = system_restart.restart_unit("baluhost-webdav", runner=runner)

    assert result.success is False
    assert "not found" in result.message


def test_restart_unit_falls_back_to_exit_code_when_output_is_empty():
    def runner(args, **kwargs):
        return _Completed(returncode=5)

    result = system_restart.restart_unit("baluhost-webdav", runner=runner)

    assert result.success is False
    assert "5" in result.message


def test_restart_unit_truncates_long_output():
    """Die Meldung landet in einer API-Antwort — sie bleibt kurz."""
    def runner(args, **kwargs):
        return _Completed(returncode=1, stderr="x" * 1000)

    result = system_restart.restart_unit("baluhost-webdav", runner=runner)

    assert len(result.message) <= 200


def test_restart_unit_handles_timeout():
    def runner(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=20.0)

    result = system_restart.restart_unit("baluhost-webdav", runner=runner)

    assert result.success is False
    assert "Zeit" in result.message


def test_restart_unit_handles_missing_binary():
    def runner(args, **kwargs):
        raise FileNotFoundError("sudo")

    result = system_restart.restart_unit("baluhost-webdav", runner=runner)

    assert result.success is False
    assert result.message


def test_restart_support_units_keeps_order_and_skips_backend():
    seen = []

    def runner(args, **kwargs):
        seen.append(args[-1])
        return _Completed()

    results = system_restart.restart_support_units(runner=runner)

    assert seen == ["baluhost-scheduler", "baluhost-monitoring", "baluhost-webdav"]
    assert [r.name for r in results] == seen
    assert all(r.success for r in results)


def test_restart_support_units_continues_after_a_failure():
    """Eine kaputte Unit darf die übrigen nicht verhindern."""
    def runner(args, **kwargs):
        if args[-1] == "baluhost-monitoring":
            return _Completed(returncode=1, stderr="boom")
        return _Completed()

    results = system_restart.restart_support_units(runner=runner)

    assert [(r.name, r.success) for r in results] == [
        ("baluhost-scheduler", True),
        ("baluhost-monitoring", False),
        ("baluhost-webdav", True),
    ]
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && python -m pytest tests/services/test_system_restart.py -v`
Erwartet: FAIL — `ModuleNotFoundError: No module named 'app.services.system_restart'`

- [ ] **Step 3: Implementierung schreiben**

```python
# backend/app/services/system_restart.py
"""Neustart der BaluHost-systemd-Units.

Die Reihenfolge ist Teil des Vertrags: ``baluhost-backend`` steht zuletzt, weil
sein Neustart den Prozess beendet, der diese Funktion ausführt. Alles, was
danach käme, liefe nie. ``baluhost-backend-local`` fehlt bewusst — sie ist
socket-aktiviert, die Socket-Unit startet sie bei Bedarf selbst.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

BALUHOST_UNITS: tuple[str, ...] = (
    "baluhost-scheduler",
    "baluhost-monitoring",
    "baluhost-webdav",
    "baluhost-backend",
)
SUPPORT_UNITS: tuple[str, ...] = BALUHOST_UNITS[:-1]
BACKEND_UNIT: str = BALUHOST_UNITS[-1]

RESTART_TIMEOUT = 20.0
# Die Meldung geht in eine API-Antwort. Sie ist nur für Admins sichtbar und
# hinter dem Step-up, aber ein ungekürztes systemctl-Protokoll gehört trotzdem
# nicht in einen Response-Body.
MAX_MESSAGE = 200


@dataclass(frozen=True)
class UnitResult:
    name: str
    success: bool
    message: str | None = None


def restart_unit(
    unit: str,
    runner: Callable[..., Any] = subprocess.run,
    timeout: float = RESTART_TIMEOUT,
) -> UnitResult:
    """Eine Unit neu starten. Wirft nie — jeder Fehlschlag ist ein Ergebnis."""
    try:
        completed = runner(
            ["sudo", "systemctl", "restart", unit],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.warning("restart of %s timed out after %.0fs", unit, timeout)
        return UnitResult(unit, False, f"Zeitüberschreitung nach {timeout:.0f}s")
    except OSError as exc:
        logger.warning("restart of %s failed to start: %s", unit, exc)
        return UnitResult(unit, False, str(exc)[:MAX_MESSAGE])

    if completed.returncode == 0:
        return UnitResult(unit, True)

    output = (completed.stderr or completed.stdout or "").strip()
    message = output[:MAX_MESSAGE] if output else f"exit {completed.returncode}"
    logger.warning("restart of %s failed: %s", unit, message)
    return UnitResult(unit, False, message)


def restart_support_units(
    runner: Callable[..., Any] = subprocess.run,
) -> list[UnitResult]:
    """Alle Units außer dem Backend, in der Reihenfolge von BALUHOST_UNITS.

    Ein Fehlschlag bricht nicht ab: eine kaputte Unit darf die übrigen nicht
    verhindern, und der Aufrufer bekommt jedes Ergebnis einzeln.
    """
    return [restart_unit(unit, runner=runner) for unit in SUPPORT_UNITS]
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && python -m pytest tests/services/test_system_restart.py -v`
Erwartet: PASS (10 Tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/system_restart.py backend/tests/services/test_system_restart.py
git commit -m "feat(system): Helfer fuer den Neustart der BaluHost-Units

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: Backend — Step-up-Nachweis

**Files:**
- Create: `backend/app/services/step_up.py`
- Test: `backend/tests/services/test_step_up.py`

**Interfaces:**
- Consumes: nichts aus Task 1
- Produces: `verify_step_up(db: Session, user_record, current_password: str | None, code: str | None) -> bool`

**Hinweis für den Umsetzer:** `auth.py:_verify_fresh_totp` macht fast dasselbe. Es wird **nicht** umgebaut — ein Refactoring der 2FA-Routen gehört nicht in diese Änderung. Das neue Modul ist die gemeinsame Stelle für künftige Step-ups; `auth.py` kann später nachziehen.

- [ ] **Step 1: Test schreiben**

```python
# backend/tests/services/test_step_up.py
"""Tests für den zweiten Nachweis vor privilegierten Aktionen."""
from types import SimpleNamespace

import pytest

from app.services import step_up


@pytest.fixture
def password_user():
    return SimpleNamespace(id=1, username="admin", totp_enabled=False)


@pytest.fixture
def totp_user():
    return SimpleNamespace(id=2, username="admin2fa", totp_enabled=True)


def test_password_accepted(monkeypatch, password_user):
    monkeypatch.setattr(
        "app.services.auth.authenticate_user",
        lambda username, password, db=None: password_user if password == "richtig" else None,
    )
    assert step_up.verify_step_up(None, password_user, "richtig", None) is True


def test_wrong_password_rejected(monkeypatch, password_user):
    monkeypatch.setattr(
        "app.services.auth.authenticate_user",
        lambda username, password, db=None: None,
    )
    assert step_up.verify_step_up(None, password_user, "falsch", None) is False


def test_missing_password_rejected(password_user):
    """Kein Feld gesetzt ist ein gescheiterter Nachweis, kein Sonderfall."""
    assert step_up.verify_step_up(None, password_user, None, None) is False


def test_totp_user_ignores_password(monkeypatch, totp_user):
    """Mit 2FA zählt nur ein frischer Code — ein Passwort öffnet nichts."""
    monkeypatch.setattr(
        "app.services.auth.authenticate_user",
        lambda username, password, db=None: totp_user,
    )
    assert step_up.verify_step_up(None, totp_user, "richtig", None) is False


def test_fresh_totp_accepted(monkeypatch, totp_user):
    monkeypatch.setattr(
        "app.services.totp_service.verify_code",
        lambda db, user_id, code: code == "123456",
    )
    assert step_up.verify_step_up(None, totp_user, None, "123456") is True


def test_backup_code_accepted_when_totp_fails(monkeypatch, totp_user):
    monkeypatch.setattr(
        "app.services.totp_service.verify_code",
        lambda db, user_id, code: False,
    )
    monkeypatch.setattr(
        "app.services.totp_service.verify_backup_code",
        lambda db, user_id, code: code == "backup-1",
    )
    assert step_up.verify_step_up(None, totp_user, None, "backup-1") is True


def test_value_error_from_totp_is_a_rejection(monkeypatch, totp_user):
    """verify_code wirft ValueError, wenn kein Secret hinterlegt ist."""
    def boom(db, user_id, code):
        raise ValueError("no secret")

    monkeypatch.setattr("app.services.totp_service.verify_code", boom)
    monkeypatch.setattr("app.services.totp_service.verify_backup_code", boom)
    assert step_up.verify_step_up(None, totp_user, None, "123456") is False
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && python -m pytest tests/services/test_step_up.py -v`
Erwartet: FAIL — `ModuleNotFoundError: No module named 'app.services.step_up'`

- [ ] **Step 3: Implementierung schreiben**

```python
# backend/app/services/step_up.py
"""Zweiter Nachweis vor einer Aktion, die ein gültiges Token allein nicht decken soll.

Ein gekoppeltes Gerät hält sein Token tagelang. Für eine Aktion, die den Dienst
unterbricht, ist "dieses Gerät war einmal angemeldet" zu wenig — verlangt wird
derselbe Nachweis wie bei einer Anmeldung: frisches TOTP, wenn 2FA aktiv ist,
sonst das Passwort.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.services import auth as auth_service
from app.services import totp_service


def verify_step_up(
    db: Optional[Session],
    user_record: Any,
    current_password: str | None,
    code: str | None,
) -> bool:
    """True, wenn der zweite Nachweis erbracht ist. Wirft nie."""
    if user_record.totp_enabled:
        # Mit 2FA zählt ausschließlich ein frischer Code. Ein Passwort würde
        # den zweiten Faktor aushebeln, den der Nutzer gerade eingeschaltet hat.
        if not code:
            return False
        try:
            if totp_service.verify_code(db, user_record.id, code):
                return True
        except ValueError:
            pass
        try:
            return bool(totp_service.verify_backup_code(db, user_record.id, code))
        except ValueError:
            return False

    if not current_password:
        return False
    return bool(
        auth_service.authenticate_user(user_record.username, current_password, db=db)
    )
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && python -m pytest tests/services/test_step_up.py -v`
Erwartet: PASS (7 Tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/step_up.py backend/tests/services/test_step_up.py
git commit -m "feat(auth): Step-up-Nachweis als eigener Dienst

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: Backend — Schemas und Rate-Limit-Schlüssel

**Files:**
- Modify: `backend/app/schemas/system.py` (anhängen)
- Modify: `backend/app/core/rate_limiter.py` (`RATE_LIMITS`)
- Test: `backend/tests/test_rate_limit_values.py` (anhängen)

**Interfaces:**
- Consumes: nichts
- Produces:
  - `SystemRestartAllRequest(current_password: str | None = None, code: str | None = None)`
  - `UnitRestartResult(name: str, success: bool, message: str | None = None)`
  - `SystemRestartAllResponse(units: list[UnitRestartResult], backend_restart_scheduled: bool, eta_seconds: int, initiated_by: str)`
  - `RATE_LIMITS["system_restart"] == "5/minute"`

- [ ] **Step 1: Test schreiben**

```python
# an backend/tests/test_rate_limit_values.py anhängen

def test_system_restart_is_as_strict_as_a_password_endpoint():
    """/api/system/restart-all nimmt ein Passwort entgegen.

    admin_operations wäre dafür zu locker; der Wert folgt auth_password_change.
    """
    assert RATE_LIMITS["system_restart"] == "5/minute"
    assert RATE_LIMITS["system_restart"] == RATE_LIMITS["auth_password_change"]
```

```python
# backend/tests/schemas/test_system_restart_schemas.py (neu)
"""Tests für die Schemas des Sammelneustarts."""
from app.schemas.system import (
    SystemRestartAllRequest,
    SystemRestartAllResponse,
    UnitRestartResult,
)


def test_request_accepts_password_only():
    assert SystemRestartAllRequest(current_password="geheim").code is None


def test_request_accepts_code_only():
    assert SystemRestartAllRequest(code="123456").current_password is None


def test_request_accepts_neither():
    """Ein leerer Body ist kein 422, sondern ein gescheiterter Step-up (401).

    Ein Validierungsfehler wäre ein zweiter Fehlerpfad für dieselbe Sache.
    """
    payload = SystemRestartAllRequest()
    assert payload.current_password is None and payload.code is None


def test_response_carries_per_unit_results():
    response = SystemRestartAllResponse(
        units=[UnitRestartResult(name="baluhost-webdav", success=False, message="boom")],
        backend_restart_scheduled=True,
        eta_seconds=1,
        initiated_by="admin",
    )
    assert response.units[0].success is False
    assert response.backend_restart_scheduled is True
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && python -m pytest tests/test_rate_limit_values.py tests/schemas/test_system_restart_schemas.py -v`
Erwartet: FAIL — `KeyError: 'system_restart'` bzw. `ImportError: cannot import name 'SystemRestartAllRequest'`

- [ ] **Step 3: Implementierung schreiben**

```python
# an backend/app/schemas/system.py anhängen

class SystemRestartAllRequest(BaseModel):
    """Step-up für den Sammelneustart.

    Beide Felder sind optional: welches gilt, entscheidet `totp_enabled` am
    Konto. Ein leerer Body ist deshalb kein Validierungsfehler, sondern ein
    gescheiterter Nachweis — ein Fehlerpfad statt zwei.
    """

    current_password: str | None = None
    code: str | None = None


class UnitRestartResult(BaseModel):
    name: str
    success: bool
    message: str | None = None


class SystemRestartAllResponse(BaseModel):
    """`baluhost-backend` fehlt in `units` mit Absicht.

    Sein Ergebnis ist zum Antwortzeitpunkt noch nicht bekannt — die Antwort
    muss raus, bevor der Prozess stirbt. Ein Eintrag, der immer "geplant"
    bedeutet, gehört nicht in dieselbe Liste wie echte Ergebnisse.
    """

    units: list[UnitRestartResult]
    backend_restart_scheduled: bool
    eta_seconds: int
    initiated_by: str
```

```python
# backend/app/core/rate_limiter.py — in RATE_LIMITS, bei den Admin-Einträgen
    "system_restart": "5/minute",  # nimmt ein Passwort entgegen (Step-up)
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && python -m pytest tests/test_rate_limit_values.py tests/schemas/test_system_restart_schemas.py -v`
Erwartet: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/system.py backend/app/core/rate_limiter.py \
        backend/tests/test_rate_limit_values.py backend/tests/schemas/test_system_restart_schemas.py
git commit -m "feat(system): Schemas und Rate-Limit fuer den Sammelneustart

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: Backend — Route `POST /api/system/restart-all`

**Files:**
- Modify: `backend/app/api/routes/system.py` (nach `restart_system`, ca. Zeile 310)
- Test: `backend/tests/api/test_system_restart_all.py`

**Interfaces:**
- Consumes: `system_restart.restart_support_units`, `system_restart.BACKEND_UNIT` (Task 1); `step_up.verify_step_up` (Task 2); die drei Schemas und `get_limit("system_restart")` (Task 3)
- Produces: `POST /api/system/restart-all` und `_schedule_backend_restart(eta: float = 1.0) -> None` in `system.py`

- [ ] **Step 1: Test schreiben**

```python
# backend/tests/api/test_system_restart_all.py
"""Tests für POST /api/system/restart-all (Admin + Step-up)."""
import pytest

from app.core.config import settings
from app.services import system_restart

PATH = "/api/system/restart-all"


@pytest.fixture(autouse=True)
def no_real_restart(monkeypatch):
    """Ohne das würde der Timer den Testlauf selbst per SIGINT beenden."""
    scheduled = []
    monkeypatch.setattr(
        "app.api.routes.system._schedule_backend_restart",
        lambda eta=1.0: scheduled.append(eta),
    )
    return scheduled


@pytest.fixture
def fake_units(monkeypatch):
    """Alle drei Support-Units melden Erfolg, ohne systemctl anzufassen."""
    calls = []

    def fake_restart_support_units(runner=None):
        calls.append(True)
        return [
            system_restart.UnitResult(name, True)
            for name in system_restart.SUPPORT_UNITS
        ]

    monkeypatch.setattr(
        system_restart, "restart_support_units", fake_restart_support_units
    )
    monkeypatch.setattr(settings, "is_dev_mode", False)
    return calls


def test_requires_authentication(client):
    assert client.post(PATH, json={"current_password": "x"}).status_code == 401


def test_regular_user_is_rejected(client, user_headers):
    r = client.post(PATH, json={"current_password": "Testpass123!"}, headers=user_headers)
    assert r.status_code == 403


def test_wrong_password_returns_structured_401(client, admin_headers, fake_units):
    r = client.post(PATH, json={"current_password": "falsch"}, headers=admin_headers)

    assert r.status_code == 401
    assert r.json()["detail"]["error"] == "step_up_failed"
    assert fake_units == []          # ohne Nachweis wird nichts neu gestartet


def test_empty_body_is_a_failed_step_up_not_a_422(client, admin_headers, fake_units):
    r = client.post(PATH, json={}, headers=admin_headers)

    assert r.status_code == 401
    assert r.json()["detail"]["error"] == "step_up_failed"


def test_failed_step_up_is_audited(client, admin_headers, fake_units, monkeypatch):
    events = []
    from app.services.audit import logger_db

    real = logger_db.AuditLoggerDB.log_security_event

    def spy(self, *args, **kwargs):
        events.append(kwargs.get("action") or (args[0] if args else None))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(logger_db.AuditLoggerDB, "log_security_event", spy)

    client.post(PATH, json={"current_password": "falsch"}, headers=admin_headers)

    assert "restart_all_step_up_failed" in events


def test_correct_password_restarts_support_units(client, admin_headers, fake_units, no_real_restart):
    r = client.post(
        PATH, json={"current_password": settings.admin_password}, headers=admin_headers
    )

    assert r.status_code == 200
    body = r.json()
    assert [u["name"] for u in body["units"]] == list(system_restart.SUPPORT_UNITS)
    assert all(u["success"] for u in body["units"])
    assert body["backend_restart_scheduled"] is True
    assert body["initiated_by"] == settings.admin_username
    assert fake_units == [True]
    assert no_real_restart == [1.0]          # Backend zuletzt, per Timer


def test_backend_unit_is_not_in_the_result_list(client, admin_headers, fake_units):
    r = client.post(
        PATH, json={"current_password": settings.admin_password}, headers=admin_headers
    )
    assert "baluhost-backend" not in [u["name"] for u in r.json()["units"]]


def test_failing_unit_is_reported_without_blocking_the_rest(
    client, admin_headers, monkeypatch, no_real_restart
):
    monkeypatch.setattr(settings, "is_dev_mode", False)
    monkeypatch.setattr(
        system_restart,
        "restart_support_units",
        lambda runner=None: [
            system_restart.UnitResult("baluhost-scheduler", True),
            system_restart.UnitResult("baluhost-monitoring", False, "boom"),
            system_restart.UnitResult("baluhost-webdav", True),
        ],
    )

    r = client.post(
        PATH, json={"current_password": settings.admin_password}, headers=admin_headers
    )

    assert r.status_code == 200
    failed = [u for u in r.json()["units"] if not u["success"]]
    assert [u["name"] for u in failed] == ["baluhost-monitoring"]
    assert r.json()["backend_restart_scheduled"] is True   # trotzdem
    assert no_real_restart == [1.0]


def test_dev_mode_touches_no_units(client, admin_headers, monkeypatch, no_real_restart):
    monkeypatch.setattr(settings, "is_dev_mode", True)

    def explode(runner=None):
        raise AssertionError("systemctl darf im Dev-Mode nicht laufen")

    monkeypatch.setattr(system_restart, "restart_support_units", explode)

    r = client.post(
        PATH, json={"current_password": settings.admin_password}, headers=admin_headers
    )

    assert r.status_code == 200
    assert r.json()["units"] == []
    assert no_real_restart == [1.0]


def test_totp_account_needs_a_code(client, admin_headers, fake_units, monkeypatch):
    """Mit 2FA öffnet das Passwort nichts mehr."""
    monkeypatch.setattr(
        "app.services.step_up.verify_step_up",
        lambda db, user_record, current_password, code: code == "123456",
    )

    assert client.post(
        PATH, json={"current_password": settings.admin_password}, headers=admin_headers
    ).status_code == 401
    assert client.post(
        PATH, json={"code": "123456"}, headers=admin_headers
    ).status_code == 200
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && python -m pytest tests/api/test_system_restart_all.py -v`
Erwartet: FAIL — 404 auf allen Routen, plus `AttributeError` beim Patchen von `_schedule_backend_restart`

- [ ] **Step 3: Implementierung schreiben**

Zuerst die Importe oben in `backend/app/api/routes/system.py` ergänzen:

```python
import asyncio

from app.models.user import User as UserModel
from app.services import step_up, system_restart
from app.schemas.system import (
    SystemRestartAllRequest,
    SystemRestartAllResponse,
    UnitRestartResult,
)
```

**Modul importieren, nicht die Funktion.** `from app.services.step_up import
verify_step_up` bindet den Namen hier fest; ein `monkeypatch.setattr` auf
`app.services.step_up.verify_step_up` ginge dann ins Leere, und der
2FA-Test wäre ein stiller Blindgänger. Deshalb `step_up.verify_step_up(...)`
am Aufrufort — wie bei `system_restart` auch.

Dann, direkt nach `restart_system` (der bestehenden Route), Helfer und Route:

```python
def _schedule_backend_restart(eta: float = 1.0) -> None:
    """Das Backend zuletzt neu starten, nachdem die Antwort draußen ist.

    Bewusst als eigener Helfer und nicht im Route-Körper: Tests müssen ihn
    ersetzen können, sonst beendet der Timer den Testlauf.

    `/api/system/restart` behält seinen eigenen, wortgleichen Ablauf. Diese
    Änderung fasst die Route nicht an, weil die Companion-App und
    `localApi.ts` daran hängen; das Zusammenlegen ist eine eigene Aufgabe.
    """
    from app.core.config import settings

    def _perform() -> None:
        logger = logging.getLogger(__name__)
        if settings.is_dev_mode:
            logger.info("Dev mode: sending SIGINT to trigger restart")
            os.kill(os.getpid(), signal.SIGINT)
            return
        result = system_restart.restart_unit(system_restart.BACKEND_UNIT)
        if not result.success:
            logger.warning(
                "restart of %s failed: %s — falling back to SIGINT",
                result.name,
                result.message,
            )
            os.kill(os.getpid(), signal.SIGINT)

    timer = threading.Timer(float(eta), _perform)
    timer.daemon = True
    timer.start()


@router.post("/restart-all", response_model=SystemRestartAllResponse)
@user_limiter.limit(get_limit("system_restart"))
async def restart_all_services(
    payload: SystemRestartAllRequest,
    request: Request,
    response: Response,
    user: UserPublic = Depends(deps.get_current_admin),
    db: Session = Depends(deps.get_db),
) -> SystemRestartAllResponse:
    """Alle BaluHost-Units neu starten (Admin + Step-up).

    Die drei Nebendienste laufen synchron, damit ihr Ergebnis in die Antwort
    passt. `baluhost-backend` kommt zuletzt und per Timer — die Antwort muss
    raus sein, bevor der Prozess stirbt.
    """
    # settings lokal, wie in den übrigen Routen dieser Datei;
    # get_audit_logger_db steht bereits oben im Modul.
    from app.core.config import settings

    audit = get_audit_logger_db()
    ip_address = request.client.host if request.client else None

    user_record = db.query(UserModel).filter(UserModel.id == user.id).first()
    if not user_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if not step_up.verify_step_up(
        db, user_record, payload.current_password, payload.code
    ):
        audit.log_security_event(
            action="restart_all_step_up_failed",
            user=user.username,
            details={"ip_address": ip_address},
            success=False,
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "step_up_failed",
                "message": (
                    "Erneute Anmeldung fehlgeschlagen. Passwort bzw. "
                    "2FA-Code prüfen."
                ),
            },
        )

    if settings.is_dev_mode:
        # Kein systemctl: die übrigen Units gibt es im Dev-Mode nicht.
        results: list[system_restart.UnitResult] = []
    else:
        results = await asyncio.to_thread(system_restart.restart_support_units)

    audit.log_system_event(
        action="restart_all_initiated",
        user=user.username,
        details={
            "units": [r.name for r in results],
            "failed": [r.name for r in results if not r.success],
            "dev_mode": settings.is_dev_mode,
            "ip_address": ip_address,
        },
        success=all(r.success for r in results),
        db=db,
    )
    logging.getLogger(__name__).info(
        "Restart-all requested via API by user %s", user.username
    )

    _schedule_backend_restart()

    return SystemRestartAllResponse(
        units=[
            UnitRestartResult(name=r.name, success=r.success, message=r.message)
            for r in results
        ],
        backend_restart_scheduled=True,
        eta_seconds=1,
        initiated_by=user.username,
    )
```

**Hinweis:** Bereits in `system.py` importiert und **nicht** erneut hinzuzufügen: `logging`, `os`, `signal`, `threading`, `status`, `HTTPException`, `Depends`, `Request`, `Response`, `Session` (aus `sqlalchemy.orm`), `deps` (die DB-Session kommt als `Depends(deps.get_db)`, es gibt kein freistehendes `get_db`), `user_limiter`, `get_limit`, `UserPublic` und `get_audit_logger_db`. Neu sind nur `asyncio`, `UserModel`, `step_up`, `system_restart` und die drei Schemas.

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && python -m pytest tests/api/test_system_restart_all.py -v`
Erwartet: PASS (10 Tests)

- [ ] **Step 5: Regression prüfen**

Run: `cd backend && python -m pytest tests/api tests/services/test_system_restart.py tests/services/test_step_up.py -q`
Erwartet: keine neuen Fehlschläge gegenüber dem Stand vor der Task (vorher einmal messen und die Zahl notieren)

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/system.py backend/tests/api/test_system_restart_all.py
git commit -m "feat(system): POST /api/system/restart-all mit Step-up

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: Tray — Grundlagen von `restart.py`

**Files:**
- Create: `backend/baluhost_tray/restart.py`
- Test: `backend/tests/tray/test_restart.py`

**Interfaces:**
- Consumes: `app.services.system_restart.BALUHOST_UNITS` (nur im Test, für den Gleichheitsvergleich)
- Produces:
  - `UNITS: tuple[str, ...]`, `HEALTH_PATH`, `RESTART_ALL_PATH`, `PROBE_TIMEOUT`
  - `@dataclass(frozen=True) RestartOutcome(ok: bool, message: str, retry_secret: bool = False, offer_local: bool = False)`
  - `@dataclass(frozen=True) AccountFacts(is_admin: bool | None, totp_enabled: bool)`
  - `probe_api(client) -> bool`
  - `fetch_account_facts(client) -> AccountFacts`
  - `menu_visible(is_admin: bool | None, api_reachable: bool) -> bool`

- [ ] **Step 1: Test schreiben**

```python
# backend/tests/tray/test_restart.py
"""Tests für den ausgehenden Pfad des Trays.

Alles hier läuft ohne Qt, ohne systemd und ohne Backend.
"""
from unittest.mock import MagicMock

import httpx
import pytest

from baluhost_tray import restart


def _response(status_code: int, payload: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload or {}
    return response


def _client(**behaviour) -> MagicMock:
    client = MagicMock()
    for name, value in behaviour.items():
        if isinstance(value, Exception):
            getattr(client, name).side_effect = value
        else:
            getattr(client, name).return_value = value
    return client


# --- Unit-Liste ----------------------------------------------------------

def test_units_match_the_backend():
    """Zwei Listen im Repo, eine Wahrheit.

    Das Tray kann die Liste nicht vom Backend holen — auf dem Notweg ist es
    tot. Also diese Prüfung, damit sie nicht auseinanderlaufen.
    """
    from app.services.system_restart import BALUHOST_UNITS

    assert restart.UNITS == BALUHOST_UNITS


# --- Probe ---------------------------------------------------------------

def test_probe_true_on_200():
    client = _client(get=_response(200))
    assert restart.probe_api(client) is True
    client.get.assert_called_once()
    assert client.get.call_args.kwargs["timeout"] == restart.PROBE_TIMEOUT


def test_probe_false_on_error_status():
    assert restart.probe_api(_client(get=_response(502))) is False


def test_probe_false_on_transport_error():
    """Kein Statuscode, gar keine Antwort — genau der Notfall."""
    client = _client(get=httpx.ConnectError("connection refused"))
    assert restart.probe_api(client) is False


def test_probe_false_on_timeout():
    client = _client(get=httpx.ReadTimeout("too slow"))
    assert restart.probe_api(client) is False


# --- Kontodaten ----------------------------------------------------------

def test_facts_report_admin_and_totp():
    client = MagicMock()
    client.get.side_effect = [
        _response(200, {"role": "admin"}),
        _response(200, {"enabled": True}),
    ]

    facts = restart.fetch_account_facts(client)

    assert facts == restart.AccountFacts(is_admin=True, totp_enabled=True)


def test_facts_report_non_admin():
    client = MagicMock()
    client.get.side_effect = [
        _response(200, {"role": "user"}),
        _response(200, {"enabled": False}),
    ]
    assert restart.fetch_account_facts(client).is_admin is False


def test_facts_unknown_when_me_is_unreachable():
    """Unbekannt ist nicht dasselbe wie 'kein Admin' — siehe menu_visible."""
    client = MagicMock()
    client.get.side_effect = httpx.ConnectError("down")

    facts = restart.fetch_account_facts(client)

    assert facts.is_admin is None
    assert facts.totp_enabled is False


def test_facts_totp_defaults_to_false_when_status_fails():
    client = MagicMock()
    client.get.side_effect = [
        _response(200, {"role": "admin"}),
        _response(500),
    ]
    facts = restart.fetch_account_facts(client)
    assert facts.is_admin is True
    assert facts.totp_enabled is False


# --- Sichtbarkeit --------------------------------------------------------

@pytest.mark.parametrize(
    "is_admin,reachable,expected",
    [
        (True, True, True),
        (True, False, True),
        (None, True, True),     # Rolle nie erfahren
        (None, False, True),
        (False, True, False),   # bekannt: kein Admin
        (False, False, True),   # ... aber die API ist tot, polkit entscheidet
    ],
)
def test_menu_visible(is_admin, reachable, expected):
    assert restart.menu_visible(is_admin, reachable) is expected
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && python -m pytest tests/tray/test_restart.py -v`
Erwartet: FAIL — `ModuleNotFoundError: No module named 'baluhost_tray.restart'`

- [ ] **Step 3: Implementierung schreiben**

```python
# backend/baluhost_tray/restart.py
"""The tray's outgoing path: restarting the BaluHost services.

Everything decidable lives here so it can be tested without Qt, without
systemd and without a running backend. tray.py only shows dialogs.

Two routes, deliberately: while the API answers, the backend restarts its own
units after a BaluHost step-up. When it does not answer, nobody can verify a
BaluHost password any more — then systemd does the work and polkit asks the
question that still has an honest answer.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

HEALTH_PATH = "/api/health"
ME_PATH = "/api/auth/me"
TOTP_STATUS_PATH = "/api/auth/2fa/status"
RESTART_ALL_PATH = "/api/system/restart-all"

# Long enough that a busy backend still counts as alive, short enough that the
# dialog does not feel stuck in the case this feature exists for.
PROBE_TIMEOUT = 2.0
# The API path restarts three units synchronously before it answers.
API_TIMEOUT = 60.0

UNITS: tuple[str, ...] = (
    "baluhost-scheduler",
    "baluhost-monitoring",
    "baluhost-webdav",
    "baluhost-backend",
)


@dataclass(frozen=True)
class RestartOutcome:
    """What happened, and what the dialog should do next."""

    ok: bool
    message: str
    retry_secret: bool = False   # wrong password/code — ask again
    offer_local: bool = False    # API died mid-flight — offer the fallback


@dataclass(frozen=True)
class AccountFacts:
    """``is_admin is None`` means "could not ask", not "not an admin"."""

    is_admin: bool | None
    totp_enabled: bool


def probe_api(client) -> bool:
    """Does the API answer right now?

    Deliberately not derived from the icon colour: that one tracks the
    websocket, and a stale ws-token paints the icon grey while /api/health is
    perfectly fine.
    """
    try:
        return client.get(HEALTH_PATH, timeout=PROBE_TIMEOUT).status_code == 200
    except httpx.HTTPError:
        return False


def fetch_account_facts(client) -> AccountFacts:
    """Role and 2FA state of the paired account. Never raises."""
    try:
        response = client.get(ME_PATH, timeout=PROBE_TIMEOUT)
        if response.status_code != 200:
            return AccountFacts(is_admin=None, totp_enabled=False)
        is_admin = response.json().get("role") == "admin"
    except (httpx.HTTPError, ValueError, KeyError):
        return AccountFacts(is_admin=None, totp_enabled=False)

    totp_enabled = False
    try:
        status_response = client.get(TOTP_STATUS_PATH, timeout=PROBE_TIMEOUT)
        if status_response.status_code == 200:
            totp_enabled = bool(status_response.json().get("enabled"))
    except (httpx.HTTPError, ValueError):
        # A missing 2FA state only mislabels the dialog; the backend decides
        # what it accepts either way.
        pass

    return AccountFacts(is_admin=is_admin, totp_enabled=totp_enabled)


def menu_visible(is_admin: bool | None, api_reachable: bool) -> bool:
    """Show the entry for admins — and for anyone when the API is unreachable.

    The second half is the point: without it the button would be missing in
    exactly the situation it exists for, where the backend has been dead since
    login and the role was never learned. It weakens nothing, because on that
    route polkit decides, not the visibility of a menu entry.
    """
    if is_admin:
        return True
    if is_admin is None:
        return True
    return not api_reachable
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && python -m pytest tests/tray/test_restart.py -v`
Erwartet: PASS (15 Tests)

- [ ] **Step 5: Commit**

```bash
git add backend/baluhost_tray/restart.py backend/tests/tray/test_restart.py
git commit -m "feat(tray): Probe, Kontodaten und Sichtbarkeitsregel fuer den Neustart

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: Tray — Notweg über `systemctl`

**Files:**
- Modify: `backend/baluhost_tray/restart.py` (anhängen)
- Test: `backend/tests/tray/test_restart.py` (anhängen)

**Interfaces:**
- Consumes: `UNITS`, `RestartOutcome` (Task 5)
- Produces: `restart_via_systemctl(runner=subprocess.run, units=UNITS, timeout: float = 30.0) -> RestartOutcome`

- [ ] **Step 1: Test schreiben**

```python
# an backend/tests/tray/test_restart.py anhängen
import subprocess


class _Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_systemctl_restarts_every_unit_in_order():
    seen = []

    def runner(args, **kwargs):
        seen.append(args)
        return _Completed()

    outcome = restart.restart_via_systemctl(runner=runner)

    assert outcome.ok is True
    assert seen == [
        ["systemctl", "restart", unit] for unit in restart.UNITS
    ]


def test_systemctl_is_called_without_sudo_and_without_shell():
    """polkit macht die Rechtefrage — sudo wäre eine zweite, andere Antwort."""
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        return _Completed()

    restart.restart_via_systemctl(runner=runner)

    args, kwargs = calls[0]
    assert "sudo" not in args
    assert "shell" not in kwargs


def test_systemctl_stops_at_the_first_failure():
    """Abgebrochene polkit-Abfrage: die restlichen Dialoge erspart man sich."""
    seen = []

    def runner(args, **kwargs):
        seen.append(args[-1])
        return _Completed(returncode=1, stderr="Interactive authentication required.")

    outcome = restart.restart_via_systemctl(runner=runner)

    assert outcome.ok is False
    assert seen == ["baluhost-scheduler"]
    assert "baluhost-scheduler" in outcome.message


def test_systemctl_failure_message_mentions_authentication():
    def runner(args, **kwargs):
        return _Completed(returncode=1, stderr="Interactive authentication required.")

    outcome = restart.restart_via_systemctl(runner=runner)

    assert "Interactive authentication required." in outcome.message


def test_systemctl_handles_timeout():
    def runner(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=30.0)

    outcome = restart.restart_via_systemctl(runner=runner)

    assert outcome.ok is False
    assert "Zeit" in outcome.message


def test_systemctl_handles_missing_binary():
    """Kein systemctl heißt: dieser Weg existiert hier nicht — sag es."""
    def runner(args, **kwargs):
        raise FileNotFoundError("systemctl")

    outcome = restart.restart_via_systemctl(runner=runner)

    assert outcome.ok is False
    assert "systemctl" in outcome.message


def test_systemctl_success_message_names_the_count():
    def runner(args, **kwargs):
        return _Completed()

    outcome = restart.restart_via_systemctl(runner=runner)

    assert str(len(restart.UNITS)) in outcome.message
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && python -m pytest tests/tray/test_restart.py -k systemctl -v`
Erwartet: FAIL — `AttributeError: module 'baluhost_tray.restart' has no attribute 'restart_via_systemctl'`

- [ ] **Step 3: Implementierung schreiben**

```python
# oben in backend/baluhost_tray/restart.py ergänzen
import subprocess
from typing import Any, Callable, Sequence

LOCAL_TIMEOUT = 30.0
```

```python
# ans Ende von backend/baluhost_tray/restart.py

def restart_via_systemctl(
    runner: Callable[..., Any] = subprocess.run,
    units: Sequence[str] = UNITS,
    timeout: float = LOCAL_TIMEOUT,
) -> RestartOutcome:
    """The fallback: ask systemd directly, let polkit ask the user.

    No sudo. systemd checks the caller against
    ``org.freedesktop.systemd1.manage-units`` (auth_admin_keep), so KDE's own
    agent prompts once and that authorisation covers the remaining units. A
    sudo call would be a second, different answer to the same question — and
    would need a sudoers line this design does not want.

    Stops at the first failure: once a prompt was cancelled or denied, three
    more dialogs help nobody.
    """
    for unit in units:
        try:
            completed = runner(
                ["systemctl", "restart", unit],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return RestartOutcome(
                False, f"Zeitüberschreitung beim Neustart von {unit}."
            )
        except OSError as exc:
            return RestartOutcome(
                False, f"systemctl konnte nicht ausgeführt werden: {exc}"
            )

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            detail = detail or f"exit {completed.returncode}"
            return RestartOutcome(
                False,
                f"Neustart von {unit} fehlgeschlagen — abgebrochen oder keine "
                f"Berechtigung.\n\n{detail}",
            )

    return RestartOutcome(True, f"{len(units)} Dienste neu gestartet.")
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && python -m pytest tests/tray/test_restart.py -v`
Erwartet: PASS (22 Tests)

- [ ] **Step 5: Commit**

```bash
git add backend/baluhost_tray/restart.py backend/tests/tray/test_restart.py
git commit -m "feat(tray): Notweg ueber systemctl mit polkit-Abfrage

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: Tray — Normalweg über die API

**Files:**
- Modify: `backend/baluhost_tray/restart.py` (anhängen)
- Test: `backend/tests/tray/test_restart.py` (anhängen)

**Interfaces:**
- Consumes: `RESTART_ALL_PATH`, `RestartOutcome`, `API_TIMEOUT` (Task 5)
- Produces: `restart_via_api(client, secret: str, totp: bool, on_auth_expired=None) -> RestartOutcome`
  - `secret` ist Passwort **oder** TOTP-Code; `totp` entscheidet, in welches Feld er geht.
  - `on_auth_expired` ist ein Callback ohne Argumente (im Betrieb `Session.refresh_access`). Gibt es ihn und kommt ein einfaches 401, wird er einmal gerufen und der Aufruf wiederholt.

- [ ] **Step 1: Test schreiben**

```python
# an backend/tests/tray/test_restart.py anhängen

def _ok_payload(failed: list[str] | None = None) -> dict:
    units = [
        {"name": name, "success": name not in (failed or []), "message": None}
        for name in restart.UNITS[:-1]
    ]
    return {
        "units": units,
        "backend_restart_scheduled": True,
        "eta_seconds": 1,
        "initiated_by": "admin",
    }


def test_api_sends_the_password_in_the_password_field():
    client = _client(post=_response(200, _ok_payload()))

    outcome = restart.restart_via_api(client, "geheim", totp=False)

    assert outcome.ok is True
    assert client.post.call_args.args[0] == restart.RESTART_ALL_PATH
    assert client.post.call_args.kwargs["json"] == {"current_password": "geheim"}


def test_api_sends_the_code_in_the_code_field():
    client = _client(post=_response(200, _ok_payload()))

    restart.restart_via_api(client, "123456", totp=True)

    assert client.post.call_args.kwargs["json"] == {"code": "123456"}


def test_api_success_message_mentions_the_backend_coming_back():
    client = _client(post=_response(200, _ok_payload()))
    outcome = restart.restart_via_api(client, "geheim", totp=False)
    assert "Backend" in outcome.message


def test_api_reports_a_failed_unit_by_name():
    client = _client(post=_response(200, _ok_payload(failed=["baluhost-webdav"])))

    outcome = restart.restart_via_api(client, "geheim", totp=False)

    assert outcome.ok is False
    assert "baluhost-webdav" in outcome.message


def test_step_up_failure_asks_again():
    client = _client(
        post=_response(401, {"detail": {"error": "step_up_failed", "message": "nope"}})
    )

    outcome = restart.restart_via_api(client, "falsch", totp=False)

    assert outcome.ok is False
    assert outcome.retry_secret is True


def test_plain_401_refreshes_once_and_retries():
    """Abgelaufenes Token ist auch 401 — aber etwas völlig anderes."""
    client = MagicMock()
    client.post.side_effect = [
        _response(401, {"detail": "Not authenticated"}),
        _response(200, _ok_payload()),
    ]
    refreshed = []

    outcome = restart.restart_via_api(
        client, "geheim", totp=False, on_auth_expired=lambda: refreshed.append(True)
    )

    assert outcome.ok is True
    assert refreshed == [True]
    assert client.post.call_count == 2


def test_plain_401_gives_up_after_one_refresh():
    client = MagicMock()
    client.post.side_effect = [
        _response(401, {"detail": "Not authenticated"}),
        _response(401, {"detail": "Not authenticated"}),
    ]

    outcome = restart.restart_via_api(
        client, "geheim", totp=False, on_auth_expired=lambda: None
    )

    assert outcome.ok is False
    assert outcome.retry_secret is False
    assert "--pair" in outcome.message


def test_step_up_failure_is_not_retried_as_an_expired_token():
    client = MagicMock()
    client.post.side_effect = [
        _response(401, {"detail": {"error": "step_up_failed", "message": "nope"}})
    ]
    refreshed = []

    restart.restart_via_api(
        client, "falsch", totp=False, on_auth_expired=lambda: refreshed.append(True)
    )

    assert refreshed == []
    assert client.post.call_count == 1


def test_403_says_the_account_may_not():
    client = _client(post=_response(403, {"detail": "Insufficient permissions"}))

    outcome = restart.restart_via_api(client, "geheim", totp=False)

    assert outcome.ok is False
    assert outcome.retry_secret is False
    assert "Admin" in outcome.message


def test_429_names_the_wait():
    outcome = restart.restart_via_api(_client(post=_response(429)), "geheim", totp=False)
    assert outcome.ok is False
    assert "Minute" in outcome.message


def test_5xx_is_reported_as_a_server_error():
    outcome = restart.restart_via_api(_client(post=_response(500)), "geheim", totp=False)
    assert outcome.ok is False
    assert outcome.offer_local is False


def test_transport_error_offers_the_fallback():
    """Die Probe war gerade noch grün — dazwischen ist das Backend gestorben."""
    client = _client(post=httpx.ConnectError("connection refused"))

    outcome = restart.restart_via_api(client, "geheim", totp=False)

    assert outcome.ok is False
    assert outcome.offer_local is True


def test_unparsable_body_does_not_crash():
    response = MagicMock()
    response.status_code = 200
    response.json.side_effect = ValueError("not json")

    outcome = restart.restart_via_api(_client(post=response), "geheim", totp=False)

    assert outcome.ok is False
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && python -m pytest tests/tray/test_restart.py -k api -v`
Erwartet: FAIL — `AttributeError: module 'baluhost_tray.restart' has no attribute 'restart_via_api'`

- [ ] **Step 3: Implementierung schreiben**

```python
# ans Ende von backend/baluhost_tray/restart.py

def _is_step_up_failure(response) -> bool:
    """A failed step-up and an expired token are both 401 and mean opposites.

    The route answers a failed step-up with a structured detail; anything else
    with a 401 is the token, which a refresh can fix.
    """
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return False
    return isinstance(detail, dict) and detail.get("error") == "step_up_failed"


def restart_via_api(
    client,
    secret: str,
    totp: bool,
    on_auth_expired: Callable[[], None] | None = None,
) -> RestartOutcome:
    """The normal route: the backend restarts its own units after the step-up.

    ``secret`` is a password or a TOTP code; ``totp`` decides which field it
    goes into. ``on_auth_expired`` is called at most once, for a plain 401.
    """
    body = {"code": secret} if totp else {"current_password": secret}
    refreshed = False

    while True:
        try:
            response = client.post(
                RESTART_ALL_PATH, json=body, timeout=API_TIMEOUT
            )
        except httpx.HTTPError as exc:
            # The probe was green moments ago, so this is the backend dying
            # mid-flight — exactly what the fallback is for.
            return RestartOutcome(
                False,
                f"Das Backend hat die Verbindung abgebrochen ({exc}).",
                offer_local=True,
            )

        code = response.status_code

        if code == 401:
            if _is_step_up_failure(response):
                return RestartOutcome(
                    False,
                    "Passwort bzw. 2FA-Code stimmt nicht.",
                    retry_secret=True,
                )
            if on_auth_expired is not None and not refreshed:
                on_auth_expired()
                refreshed = True
                continue
            return RestartOutcome(
                False,
                "Die Kopplung ist abgelaufen. Einmalig ausführen: "
                "baluhost-tray --pair",
            )

        if code == 403:
            return RestartOutcome(
                False, "Dieses Konto ist kein BaluHost-Admin."
            )
        if code == 429:
            return RestartOutcome(
                False, "Zu viele Versuche. In einer Minute erneut probieren."
            )
        if code != 200:
            return RestartOutcome(
                False, f"Das Backend hat den Neustart abgelehnt ({code})."
            )

        try:
            payload = response.json()
            units = payload["units"]
        except (ValueError, KeyError, TypeError) as exc:
            return RestartOutcome(
                False, f"Unerwartete Antwort des Backends ({exc})."
            )

        failed = [u["name"] for u in units if not u.get("success")]
        if failed:
            return RestartOutcome(
                False, "Nicht neu gestartet: " + ", ".join(failed)
            )
        return RestartOutcome(
            True,
            "Dienste neu gestartet. Das Backend startet gleich ebenfalls neu — "
            "das Symbol wird kurz grau.",
        )
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && python -m pytest tests/tray/test_restart.py -v`
Erwartet: PASS (35 Tests)

- [ ] **Step 5: Commit**

```bash
git add backend/baluhost_tray/restart.py backend/tests/tray/test_restart.py
git commit -m "feat(tray): Normalweg ueber /api/system/restart-all

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: Tray — Menüpunkt, Dialoge, Arbeitsthread

**Files:**
- Modify: `backend/baluhost_tray/tray.py`
- Test: `backend/tests/tray/test_restart_flow.py` (neu)

**Interfaces:**
- Consumes: alles aus `baluhost_tray.restart` (Task 5–7), `Session` (vorhanden), `tray_config.load_tokens` (vorhanden)
- Produces:
  - `restart_flow(client, prompt, probe=probe_api, facts=fetch_account_facts, api=restart_via_api, local=restart_via_systemctl, on_auth_expired=None) -> RestartOutcome` in `restart.py`
  - in `tray.py`: `MENU_RESTART`, Bridge-Signale `restart_prompt`, `restart_finished`, `restart_visible`

**Warum der Ablauf noch einmal in `restart.py` landet:** Die Abfolge „proben → Kontodaten → Dialog → Weg wählen → bis zu drei Versuche" ist die eigentliche Logik. In `tray.py` wäre sie nur mit laufendem Qt prüfbar. `prompt` ist ein Callback `(mode: str) -> str | None`; im Betrieb reicht `tray.py` darüber die Dialogantwort durch, im Test ist es eine Liste vorbereiteter Antworten.

- [ ] **Step 1: Test schreiben**

```python
# backend/tests/tray/test_restart_flow.py
"""Tests für den Ablauf: proben, fragen, Weg wählen, wiederholen."""
from unittest.mock import MagicMock

from baluhost_tray import restart


def _facts(is_admin=True, totp=False):
    return lambda client: restart.AccountFacts(is_admin=is_admin, totp_enabled=totp)


def _prompts(*answers):
    seen = []

    def prompt(mode):
        seen.append(mode)
        return answers[len(seen) - 1]

    prompt.seen = seen
    return prompt


def test_reachable_api_asks_for_a_password_and_calls_the_api():
    prompt = _prompts("geheim")
    called = {}

    def api(client, secret, totp, on_auth_expired=None):
        called["secret"] = secret
        called["totp"] = totp
        return restart.RestartOutcome(True, "ok")

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(), api=api,
        local=lambda **kw: restart.RestartOutcome(False, "darf nicht laufen"),
    )

    assert outcome.ok is True
    assert prompt.seen == ["password"]
    assert called == {"secret": "geheim", "totp": False}


def test_totp_account_is_asked_for_a_code():
    prompt = _prompts("123456")

    restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(totp=True),
        api=lambda client, secret, totp, on_auth_expired=None: restart.RestartOutcome(True, "ok"),
        local=lambda **kw: restart.RestartOutcome(False, "nein"),
    )

    assert prompt.seen == ["totp"]


def test_wrong_password_is_asked_again_up_to_three_times():
    prompt = _prompts("falsch1", "falsch2", "falsch3")
    attempts = []

    def api(client, secret, totp, on_auth_expired=None):
        attempts.append(secret)
        return restart.RestartOutcome(False, "nope", retry_secret=True)

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(), api=api,
        local=lambda **kw: restart.RestartOutcome(False, "nein"),
    )

    assert attempts == ["falsch1", "falsch2", "falsch3"]
    assert prompt.seen == ["password", "password_retry", "password_retry"]
    assert outcome.ok is False


def test_cancelled_dialog_stops_without_calling_anything():
    prompt = _prompts(None)

    def api(client, secret, totp, on_auth_expired=None):
        raise AssertionError("darf nicht gerufen werden")

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(), api=api,
        local=lambda **kw: restart.RestartOutcome(False, "nein"),
    )

    assert outcome.ok is False
    assert "Abgebrochen" in outcome.message


def test_non_admin_is_told_without_being_asked_for_a_password():
    prompt = _prompts()

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(is_admin=False),
        api=lambda **kw: restart.RestartOutcome(True, "ok"),
        local=lambda **kw: restart.RestartOutcome(True, "ok"),
    )

    assert outcome.ok is False
    assert prompt.seen == []
    assert "Admin" in outcome.message


def test_dead_api_confirms_and_uses_systemctl():
    prompt = _prompts("ja")
    ran = []

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: False, facts=_facts(),
        api=lambda **kw: restart.RestartOutcome(False, "darf nicht laufen"),
        local=lambda: ran.append(True) or restart.RestartOutcome(True, "ok"),
    )

    assert prompt.seen == ["local"]
    assert ran == [True]
    assert outcome.ok is True


def test_declined_confirmation_does_not_restart_anything():
    prompt = _prompts(None)

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: False, facts=_facts(),
        api=lambda **kw: restart.RestartOutcome(False, "nein"),
        local=lambda: (_ for _ in ()).throw(AssertionError("darf nicht laufen")),
    )

    assert outcome.ok is False


def test_api_dying_mid_flight_switches_to_the_fallback():
    prompt = _prompts("geheim", "ja")
    ran = []

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(),
        api=lambda client, secret, totp, on_auth_expired=None: restart.RestartOutcome(
            False, "weg", offer_local=True
        ),
        local=lambda: ran.append(True) or restart.RestartOutcome(True, "ok"),
    )

    assert prompt.seen == ["password", "local"]
    assert ran == [True]
    assert outcome.ok is True
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && python -m pytest tests/tray/test_restart_flow.py -v`
Erwartet: FAIL — `AttributeError: module 'baluhost_tray.restart' has no attribute 'restart_flow'`

- [ ] **Step 3: `restart_flow` implementieren**

```python
# ans Ende von backend/baluhost_tray/restart.py

MAX_SECRET_ATTEMPTS = 3


def restart_flow(
    client,
    prompt: Callable[[str], str | None],
    probe: Callable[..., bool] = probe_api,
    facts: Callable[..., AccountFacts] = fetch_account_facts,
    api: Callable[..., RestartOutcome] = restart_via_api,
    local: Callable[..., RestartOutcome] = restart_via_systemctl,
    on_auth_expired: Callable[[], None] | None = None,
) -> RestartOutcome:
    """One click, start to finish. No Qt in here.

    ``prompt(mode)`` returns what the user typed, or None if they cancelled.
    Modes: "password", "password_retry", "totp", "totp_retry", "local".
    Every collaborator is injected so the whole sequence is testable without a
    backend, without systemd and without a display.
    """
    if not probe(client):
        return _local_flow(prompt, local)

    account = facts(client)
    if account.is_admin is False:
        return RestartOutcome(
            False,
            "Dieses Konto ist kein BaluHost-Admin. Neustart nicht möglich.",
        )

    mode = "totp" if account.totp_enabled else "password"
    for attempt in range(MAX_SECRET_ATTEMPTS):
        secret = prompt(mode if attempt == 0 else f"{mode}_retry")
        if secret is None:
            return RestartOutcome(False, "Abgebrochen.")

        outcome = api(client, secret, account.totp_enabled, on_auth_expired=on_auth_expired)
        if outcome.offer_local:
            return _local_flow(prompt, local)
        if not outcome.retry_secret:
            return outcome

    return RestartOutcome(False, "Passwort bzw. 2FA-Code dreimal falsch.")


def _local_flow(
    prompt: Callable[[str], str | None],
    local: Callable[..., RestartOutcome],
) -> RestartOutcome:
    """Confirm, then hand over to systemd — polkit does the asking."""
    if prompt("local") is None:
        return RestartOutcome(False, "Abgebrochen.")
    return local()
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && python -m pytest tests/tray/test_restart_flow.py -v`
Erwartet: PASS (8 Tests)

- [ ] **Step 5: `tray.py` verdrahten**

In `backend/baluhost_tray/tray.py`:

```python
# bei den Importen
import queue

from baluhost_tray import config as tray_config
from baluhost_tray.restart import (
    RestartOutcome,
    fetch_account_facts,
    menu_visible,
    restart_flow,
)
from baluhost_tui.client import BackendClient
```

```python
# bei den Menü-Konstanten
MENU_RESTART = "BaluHost neu starten…"
```

```python
# in _Bridge ergänzen
    restart_prompt = pyqtSignal(str)    # "password" | "password_retry" | "totp" | "totp_retry" | "local"
    restart_finished = pyqtSignal(bool, str)
    restart_visible = pyqtSignal(bool)
```

```python
# in run_tray(), nach dem Menüpunkt MENU_DEVICES und vor dem Separator

    restart_action = menu.addAction(MENU_RESTART)
    # Bis die Rolle bekannt ist, bleibt der Eintrag sichtbar: unbekannt heisst,
    # dass die API gerade nicht antwortet — genau der Fall, fuer den der Notweg
    # da ist. Das Gate ist polkit bzw. das Backend, nicht diese Zeile.
    restart_action.setVisible(True)
    bridge.restart_visible.connect(restart_action.setVisible)

    # Die Antwort des Dialogs geht ueber eine Queue zurueck in den
    # Arbeitsthread. Dialoge gehoeren in den GUI-Thread, Netzwerk nicht.
    answers: queue.Queue = queue.Queue(maxsize=1)

    def _show_prompt(mode: str) -> None:
        if mode == "local":
            choice = QMessageBox.question(
                None,
                "BaluHost neu starten",
                "Das Backend antwortet nicht.\n\nDienste direkt über das "
                "System neu starten? Das System fragt gleich nach dem "
                "Passwort.",
            )
            answers.put("ja" if choice == QMessageBox.StandardButton.Yes else None)
            return

        retry = mode.endswith("_retry")
        is_totp = mode.startswith("totp")
        label = "2FA-Code" if is_totp else "Passwort"
        text = f"{label} für BaluHost:"
        if retry:
            text = f"{label} stimmt nicht. Noch einmal:"
        value, ok = QInputDialog.getText(
            None, "BaluHost neu starten", text, QLineEdit.EchoMode.Password
        )
        answers.put(value if ok and value else None)

    bridge.restart_prompt.connect(_show_prompt)

    def _restart_done(ok: bool, message: str) -> None:
        restart_action.setEnabled(True)
        box = QMessageBox.information if ok else QMessageBox.warning
        box(None, "BaluHost neu starten", message)

    bridge.restart_finished.connect(_restart_done)

    def _prompt_from_worker(mode: str) -> str | None:
        bridge.restart_prompt.emit(mode)
        return answers.get()

    def _restart_worker() -> None:
        # Eigener Client: der Worker-Thread wechselt beim Refresh das Token
        # des gemeinsamen Clients, und zwei Threads auf demselben Objekt sind
        # eine Verabredung zum Rennen.
        tokens = tray_config.load_tokens()
        client = BackendClient(
            server=base_url, token=tokens.access if tokens else None
        )
        try:
            outcome = restart_flow(
                client,
                _prompt_from_worker,
                on_auth_expired=lambda: _refresh_into(client),
            )
        except Exception as exc:                     # noqa: BLE001
            logger.exception("restart flow failed")
            outcome = RestartOutcome(False, f"Unerwarteter Fehler: {exc}")
        finally:
            client.close()
        bridge.restart_finished.emit(outcome.ok, outcome.message)

    def _refresh_into(client: BackendClient) -> None:
        """Token erneuern und dem Neustart-Client mitgeben.

        Der Refresh-Token rotiert serverseitig nicht (siehe session.py), ein
        paralleler Refresh im Worker ist also harmlos.
        """
        session.refresh_access()
        tokens = tray_config.load_tokens()
        if tokens:
            client.set_token(tokens.access)

    def _start_restart() -> None:
        restart_action.setEnabled(False)
        threading.Thread(target=_restart_worker, daemon=True).start()

    restart_action.triggered.connect(_start_restart)
```

In `_main()` (im Worker), direkt nach `await notifier.connect()`:

```python
        # Sichtbarkeit einmal beim Start bestimmen. Eine Rollenaenderung
        # braucht danach einen Neustart des Trays — das ist selten genug.
        account = await asyncio.to_thread(fetch_account_facts, session.client())
        reachable = account.is_admin is not None
        bridge.restart_visible.emit(menu_visible(account.is_admin, reachable))
```

Und die Qt-Importe oben erweitern:

```python
from PyQt6.QtWidgets import (
    QApplication, QInputDialog, QLineEdit, QMenu, QMessageBox, QSystemTrayIcon,
)
```

- [ ] **Step 6: Verdrahtung prüfen**

Run: `cd backend && python -m pytest tests/tray/ -v`
Erwartet: PASS (alle Tray-Tests, inkl. der bestehenden)

Run: `cd backend && python -c "import ast,sys; ast.parse(open('baluhost_tray/tray.py').read())"`
Erwartet: keine Ausgabe (Syntax in Ordnung; PyQt6 ist in der Testumgebung womöglich nicht installiert, deshalb kein Import)

- [ ] **Step 7: Commit**

```bash
git add backend/baluhost_tray/restart.py backend/baluhost_tray/tray.py \
        backend/tests/tray/test_restart_flow.py
git commit -m "feat(tray): Menuepunkt und Ablauf fuer den Dienste-Neustart

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9: Dokumentation und Regeln

**Files:**
- Modify: `docs/superpowers/specs/2026-09-21-desktop-tray-design.md`
- Modify: `.claude/rules/security-agent.md`
- Modify: `.claude/rules/architecture.md`
- Modify: `docs/features/desktop-tray.de.md` **und** `docs/features/desktop-tray.en.md` (beide Sprachfassungen werden gepflegt und müssen gleich bleiben)

- [ ] **Step 1: Nicht-Ziel im Tray-Entwurf als überholt markieren**

In `docs/superpowers/specs/2026-09-21-desktop-tray-design.md`, im Abschnitt „Nicht-Ziele", den ersten Punkt ersetzen durch:

```markdown
- ~~**Service-Steuerung.** Neustarten oder Beenden von Diensten bleibt der
  Companion-App und der Web-UI vorbehalten. Das Tray fasst nichts
  Privilegiertes an und braucht keine sudoers-Erweiterung.~~
  **Überholt am 2026-09-22** durch
  `2026-09-22-tray-service-restart-design.md`: Das Tray kann Dienste neu
  starten. Die Zusage „keine sudoers-Erweiterung" gilt weiterhin — der Notweg
  läuft über polkit, nicht über sudo.
```

- [ ] **Step 2: Sicherheitsregeln ergänzen**

In `.claude/rules/security-agent.md`, am Ende des Abschnitts „Role Model" (also nach dem Absatz über `GET /api/plugins/steam_gaming/session-state`) einfügen:

```markdown
- `POST /api/system/restart-all` startet alle BaluHost-Units neu. Doppelt
  gegated: `get_current_admin` **und** ein Step-up
  (`services/step_up.verify_step_up`) — frisches TOTP, wenn 2FA aktiv ist,
  sonst das Passwort. Der Grund für den zweiten Nachweis ist das Tray: ein
  gekoppeltes Gerät hält sein Token tagelang, und „dieses Gerät war einmal
  angemeldet" ist für eine Dienstunterbrechung zu wenig. Ein gescheiterter
  Step-up antwortet 401 mit `{"error": "step_up_failed"}` — die
  Unterscheidung zum abgelaufenen Token ist Teil des Vertrags, der Client
  reagiert auf beides anders. Rate-Limit `system_restart` (5/minute), weil
  der Endpunkt ein Passwort entgegennimmt. Durchgesetzt in
  `api/routes/system.py`.
```

In demselben File, unter „Known Gaps & Accepted Risks", als neuen Punkt **10** anhängen — die Liste endet heute bei 9. Direkt darunter steht der Hinweis, dass ein früherer Eintrag 10 am 2026-07-21 entfernt wurde; diesen Satz um einen Halbsatz ergänzen, sonst zeigen zwei Dinge auf dieselbe Nummer:

```markdown
Entry 10 ("SECURITY.md outdated") was removed on 2026-07-21: … Die Nummer 10
ist seit dem 2026-09-22 neu vergeben (Tray-Notweg, siehe oben).
```

Der neue Eintrag:

```markdown
10. **Der Notweg des Trays schreibt keinen Audit-Eintrag** — Kann das Backend
    nicht mehr antworten, startet `baluhost_tray/restart.py` die Units selbst
    über `systemctl`; systemd fragt polkit
    (`org.freedesktop.systemd1.manage-units`, `auth_admin_keep`), KDE zeigt den
    Dialog. Ein App-Audit ist in dem Moment unmöglich — die Datenbank ist
    genau so unerreichbar wie die API. Die Spur liegt im Journal: polkitd
    protokolliert die Autorisierung, systemd den Neustart. Ein
    Nachtrag-Endpunkt wurde bewusst verworfen: ein vom Client behaupteter
    Audit-Eintrag ist schwächeres Beweismaterial als die Zeile, die systemd
    selbst geschrieben hat. Kein neues Recht für den `baluhost`-Nutzer, keine
    sudoers-Zeile, kein eigener polkit-Policy-File —
    `NoNewPrivileges=yes` in `baluhost-tray.service` bleibt, weil `systemctl`
    nichts im eigenen Prozess eskaliert, sondern über D-Bus fragt. Entwurf:
    `docs/superpowers/specs/2026-09-22-tray-service-restart-design.md`.
```

- [ ] **Step 3: API-Liste ergänzen**

In `.claude/rules/architecture.md`, in der Liste unter „API Structure", bei `/api/system/*` ergänzen bzw. als eigene Zeile:

```markdown
- `/api/system/restart-all` - Sammelneustart aller BaluHost-Units (Admin **und** Step-up, siehe `security-agent.md`)
```

- [ ] **Step 4: Feature-Doku in beiden Sprachen**

In `docs/features/desktop-tray.de.md`, Abschnitt „Menue und Klick" (ab Zeile 91),
die Tabelle um eine Zeile **vor** „Beenden" erweitern:

```markdown
| **BaluHost neu starten…** | Startet alle BaluHost-Dienste neu — fragt vorher nach |
```

Und direkt nach dem Absatz über *„Geraete in der Web-UI"* einen neuen Abschnitt
einfügen:

```markdown
## Dienste neu starten

Der Menuepunkt *„BaluHost neu starten…"* startet alle vier Units neu:
`baluhost-scheduler`, `baluhost-monitoring`, `baluhost-webdav` und zuletzt
`baluhost-backend`. Welchen Weg das Tray nimmt, entscheidet es beim Klick.

**Wenn das Backend antwortet** fragt ein Dialog nach dem BaluHost-Passwort des
gekoppelten Kontos — bei aktivem 2FA nach einem frischen Code. Das gekoppelte
Token allein reicht ausdruecklich nicht: es liegt tagelang auf der Platte, und
wer vor einem entsperrten Desktop sitzt, soll damit nicht den Dienst
unterbrechen koennen. Danach startet das Backend die Units selbst. Das Symbol
wird kurz grau, waehrend das Backend selbst neu startet.

**Wenn das Backend nicht mehr antwortet** — genau der Fall, fuer den es den
Menuepunkt gibt — fragt das Tray kurz nach und ruft dann `systemctl` direkt.
Die Rechtefrage stellt dann das System: KDE zeigt seinen eigenen
polkit-Dialog und will das **Linux-Passwort**. Ein BaluHost-Passwort waere in
dem Moment ohnehin nicht pruefbar, die Datenbank ist mit dem Backend weg.

**Voraussetzung dafuer:** Der Desktop-Nutzer muss in der Gruppe `sudo` sein —
polkit nimmt sie laut `/usr/share/polkit-1/rules.d/50-default.rules` als
Admin-Identitaet. Ist er es nicht, fragt der Dialog nach dem Passwort eines
*anderen* Admins. Das ist kein Fehler, nur unerwartet.

Ist das gekoppelte Konto kein Admin, erscheint der Menuepunkt nicht — ausser
das Backend ist gerade nicht erreichbar, dann entscheidet ohnehin polkit.

Der Neustart ueber das Backend steht im Audit-Log. Der Notweg nicht: dort
schreibt niemand mehr in die Datenbank. Die Spur liegt im Journal, polkitd
protokolliert die Freigabe und systemd den Neustart.
```

Dieselben beiden Änderungen sinngemäß in `docs/features/desktop-tray.en.md`
(Abschnitt „Menu and click", ab Zeile 88). Die englische Fassung behält die
deutschen Menü-Beschriftungen in der Tabelle bei — so steht es dort bereits.

- [ ] **Step 5: Prüfen, dass nichts anderes die alte Zusage wiederholt**

Run: `cd /home/sven/projects/BaluHost && python3 - <<'PY'
import os, re
pat = re.compile(r"fasst nichts Privilegiertes an|keine Service-Steuerung|liest nur")
for dp, dn, fn in os.walk("."):
    dn[:] = [d for d in dn if d not in {".git", "node_modules", "__pycache__"}]
    for f in fn:
        if not f.endswith((".md", ".py", ".service")):
            continue
        p = os.path.join(dp, f)
        for i, line in enumerate(open(p, errors="ignore"), 1):
            if pat.search(line):
                print(f"{p}:{i}: {line.strip()[:120]}")
PY`

Erwartet: Treffer im Tray-Entwurf (jetzt als überholt markiert) und der Kommentar
in `deploy/install/templates/baluhost-tray.service` („Kein root, keine
Rechteerweiterung: das Tray liest nur"). Den Kommentar in der Unit auf den
neuen Stand bringen:

```
# Kein root, keine Rechteerweiterung. Der Neustart-Notweg laeuft ueber
# systemd/polkit — systemctl eskaliert nichts im eigenen Prozess, deshalb
# bleibt NoNewPrivileges hier richtig.
NoNewPrivileges=yes
```

Achtung: `backend/tests/tray/test_unit_template.py` prüft diese Datei — nach der
Änderung laufen lassen.

- [ ] **Step 6: Tests laufen lassen**

Run: `cd backend && python -m pytest tests/tray/ -v`
Erwartet: PASS

- [ ] **Step 7: Commit**

```bash
git add docs/ .claude/rules/ deploy/install/templates/baluhost-tray.service
git commit -m "docs(tray): Dienste-Neustart in Doku und Regeln nachziehen

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Abschluss

- [ ] **Gesamtlauf:** `cd backend && python -m pytest -q` — keine neuen Fehlschläge gegenüber dem Stand vor Task 1 (Zahl vorher messen; die Suite hat bekannte, vorbestehende Fehlschläge).
- [ ] **Manuelle Probe auf BaluNode** (erst nach dem Deploy sinnvoll, weil das Tray dort läuft):
  1. `baluhost-tray` neu starten, Menüpunkt „BaluHost neu starten…" ist da.
  2. Normalweg: Passwort eingeben → Dialog meldet Erfolg, Icon wird kurz grau, kommt zurück.
  3. Falsches Passwort → „Passwort bzw. 2FA-Code stimmt nicht.", erneute Abfrage.
  4. Notweg: `sudo systemctl stop baluhost-backend`, dann Menüpunkt → Bestätigung → KDE fragt nach dem Passwort → alle vier Units laufen wieder (`systemctl status 'baluhost-*'`).
- [ ] **Branch abschließen** mit superpowers:finishing-a-development-branch.
