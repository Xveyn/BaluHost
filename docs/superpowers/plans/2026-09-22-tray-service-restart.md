# Dienste-Neustart aus dem Desktop-Tray — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein Menüpunkt im Tray startet alle fünf BaluHost-Units neu — über die API mit BaluHost-Step-up, und bei totem Backend über `systemctl` mit polkit-Abfrage.

**Architecture:** Zwei Wege, ein Menüpunkt. Das Tray probt beim Klick `/api/health`. Antwortet die API, fragt ein Dialog Passwort bzw. TOTP und `POST /api/system/restart-all` erledigt den Rest im Backend (vier Units synchron, `baluhost-backend` zuletzt per Timer). Antwortet sie nicht, ruft das Tray **einen** `systemctl restart` für alle Units auf; systemd fragt polkit, KDE zeigt den Dialog. Alles Entscheidbare im Tray liegt in `restart.py` und ist ohne Qt, ohne systemd und ohne Backend prüfbar.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy, pytest; Tray: PyQt6, httpx über `baluhost_tui.client.BackendClient`.

**Spec:** `docs/superpowers/specs/2026-09-22-tray-service-restart-design.md`

## Global Constraints

- **Unit-Liste, wörtlich:** `("baluhost-scheduler", "baluhost-monitoring", "baluhost-webdav", "baluhost-backend-local", "baluhost-backend")`. `baluhost-backend` steht zuletzt, weil sein Neustart auf dem API-Weg den Prozess beendet, der die Sequenz ausführt.
- **Eine sudoers-Zeile kommt dazu** (`baluhost-backend-local`), gleiche Form wie die vier bestehenden. Sonst keine Rechteerweiterung: kein polkit-Policy-File, kein neues Recht für den Desktop-Nutzer, `NoNewPrivileges=yes` in `baluhost-tray.service` bleibt.
- **Der Notweg startet einen kurzlebigen `systemctl`-Prozess je Aufruf.** Nie `org.freedesktop.systemd1.Manager.RestartUnit` aus dem langlebigen Tray-Prozess über D-Bus — das erzeugt ein Fünf-Minuten-Fenster, in dem derselbe Prozess `manage-units` (und damit `StartTransientUnit` = root-Codeausführung) ohne Abfrage nutzen darf.
- **Kein SIGINT-Fallback im Prod-Zweig.** Bei `--workers 4` trifft `os.kill(os.getpid(), SIGINT)` einen Kindprozess, den uvicorn sofort neu startet (Issue #695). Fehlschlag wird protokolliert, nicht kaschiert.
- **`subprocess` immer mit Argumentliste**, nie `shell=True`.
- **Pydantic-Schemas für Request-Bodies**, nie rohes `dict`.
- **Rate-Limit auf jedem neuen Endpunkt** — es gibt keinen globalen Fallback.
- **Deutsch** für alle Texte, die ein Mensch im Tray sieht; Code und Docstrings wie im umgebenden Modul (Tray-Docstrings englisch, Kommentare gemischt).
- **`/api/system/restart` bleibt unangetastet** — `localApi.ts:313` und die Companion-App hängen daran. Die Step-up-Lücke dort ist Issue #699 und wird dokumentiert, nicht stillschweigend gelassen.
- **Testlauf:** `cd backend && ./.venv/bin/python -m pytest <pfad> -v`. **Nicht** `python -m pytest` — `python` existiert auf dieser Maschine nicht. Baseline vor Task 1 gemessen: **2 failed, 5758 passed, 18 skipped** (beide Fehlschläge in `tests/plugins/sandbox/test_phase3_e2e.py`, vorbestehend).
- **PyQt6 fehlt im venv** (`backend/.venv`), liegt aber im System-Python. Qt-Tests deshalb mit `pytest.importorskip("PyQt6")`; sie laufen auf dieser Maschine über `QT_QPA_PLATFORM=offscreen python3 -m pytest … -o addopts=""` und im Produktions-venv mit dem Extra `[tray]`.
- **Commit nach jeder Task.**

---

## File Structure

**Neu:**

| Datei | Verantwortung |
|---|---|
| `backend/app/services/system_restart.py` | Unit-Liste und `systemctl`-Aufruf im Backend. Einzige Stelle, die im Backend `sudo systemctl restart` kennt. |
| `backend/app/services/step_up.py` | Zweiter Nachweis (Passwort oder TOTP/Backup-Code) für eine Aktion, die ein gültiges Token allein nicht decken soll. |
| `backend/baluhost_tray/restart.py` | Alles Entscheidbare des Tray-Neustarts: Probe, Kontodaten, Pfadwahl, API-Aufruf, `systemctl`-Aufruf, Fehlerabbildung, Sichtbarkeitsregel. |
| `backend/tests/services/test_system_restart.py` | Task 1 |
| `backend/tests/test_deploy_sudoers_units.py` | Task 1 (sudoers-Vorlage gegen die Unit-Liste) |
| `backend/tests/services/test_step_up.py` | Task 2 |
| `backend/tests/schemas/test_system_restart_schemas.py` | Task 3 |
| `backend/tests/api/test_system_restart_all.py` | Task 4 |
| `backend/tests/tray/test_restart.py` | Task 5–7 |
| `backend/tests/tray/test_restart_flow.py` | Task 8 |
| `backend/tests/tray/test_tray_wiring.py` | Task 9 (Qt-Rauchtest, `importorskip`) |

**Geändert:** `backend/app/schemas/system.py`, `backend/app/core/rate_limiter.py`, `backend/tests/test_rate_limit_values.py`, `backend/app/api/routes/system.py`, `backend/baluhost_tray/tray.py`, `deploy/install/templates/baluhost-deploy-sudoers`, `deploy/install/templates/baluhost-tray.service`, `docs/features/desktop-tray.{de,en}.md`, `docs/superpowers/specs/2026-09-21-desktop-tray-design.md`, `.claude/rules/{security-agent,architecture}.md`

---

## Task 1: Backend — Unit-Liste, `systemctl`-Helfer, sudoers-Zeile

**Files:**
- Create: `backend/app/services/system_restart.py`
- Modify: `deploy/install/templates/baluhost-deploy-sudoers`
- Test: `backend/tests/services/test_system_restart.py`, `backend/tests/test_deploy_sudoers_units.py`

**Interfaces:**
- Produces:
  - `BALUHOST_UNITS: tuple[str, ...]` (5 Einträge, Backend zuletzt)
  - `SUPPORT_UNITS: tuple[str, ...]` (die ersten vier), `BACKEND_UNIT: str`
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


def test_local_channel_unit_is_included():
    """Sie ist socket-aktiviert, läuft danach aber dauerhaft weiter.

    Ohne sie liefe der Companion-Kanal nach dem Neustart mit altem Code.
    """
    assert "baluhost-backend-local" in system_restart.SUPPORT_UNITS


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

    assert seen == [
        "baluhost-scheduler",
        "baluhost-monitoring",
        "baluhost-webdav",
        "baluhost-backend-local",
    ]
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
        ("baluhost-backend-local", True),
    ]
```

```python
# backend/tests/test_deploy_sudoers_units.py
"""Die sudoers-Vorlage deckt genau die Units ab, die der Code neu startet.

Ohne diese Prüfung fällt eine neue Unit erst in Produktion auf — als
`sudo: no entry`, gemeldet als fehlgeschlagener Neustart, den niemand erklärt.
Und eine übrig gebliebene Zeile erweitert den Radius, ohne dass sie jemand
benutzt.
"""
import re
from pathlib import Path

from app.services.system_restart import BALUHOST_UNITS

TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "deploy" / "install" / "templates" / "baluhost-deploy-sudoers"
)


def _restart_units() -> set[str]:
    lines = [
        line
        for line in TEMPLATE.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    return set(re.findall(r"/usr/bin/systemctl restart (\S+)", "\n".join(lines)))


def test_sudoers_covers_exactly_the_units_we_restart():
    assert _restart_units() == set(BALUHOST_UNITS)


def test_no_wildcard_in_the_restart_entries():
    """Ein Platzhalter im Unit-Namen wäre ein viel längerer Hebel."""
    assert not [unit for unit in _restart_units() if "*" in unit or "?" in unit]
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && ./.venv/bin/python -m pytest tests/services/test_system_restart.py tests/test_deploy_sudoers_units.py -v`
Erwartet: FAIL — `ModuleNotFoundError: No module named 'app.services.system_restart'`

- [ ] **Step 3: Implementierung schreiben**

```python
# backend/app/services/system_restart.py
"""Neustart der BaluHost-systemd-Units.

Die Reihenfolge ist Teil des Vertrags: ``baluhost-backend`` steht zuletzt, weil
sein Neustart den Prozess beendet, der diese Funktion ausführt. Alles, was
danach käme, liefe nie.

``baluhost-backend-local`` ist dabei, obwohl sie socket-aktiviert ist: sie ist
``Type=simple`` mit ``Restart=on-failure`` und läuft nach dem ersten
Verbindungsaufbau dauerhaft weiter. Ohne sie liefe der Companion-Kanal nach
einem "Neustart" mit altem Code.
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
    "baluhost-backend-local",
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

In `deploy/install/templates/baluhost-deploy-sudoers` nach der `baluhost-webdav`-Zeile einfügen:

```
@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /usr/bin/systemctl restart baluhost-backend-local
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && ./.venv/bin/python -m pytest tests/services/test_system_restart.py tests/test_deploy_sudoers_units.py -v`
Erwartet: PASS (12 Tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/system_restart.py backend/tests/services/test_system_restart.py \
        backend/tests/test_deploy_sudoers_units.py deploy/install/templates/baluhost-deploy-sudoers
git commit -m "feat(system): Helfer fuer den Neustart der BaluHost-Units

Fuenf Units, Backend zuletzt. baluhost-backend-local ist dabei, weil sie
socket-aktiviert startet, danach aber dauerhaft laeuft -- dafuer kommt eine
fuenfte sudoers-Zeile derselben Form dazu. Ein Test haelt Vorlage und
Unit-Liste zusammen.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: Backend — Step-up-Nachweis

**Files:**
- Create: `backend/app/services/step_up.py`
- Test: `backend/tests/services/test_step_up.py`

**Interfaces:**
- Produces: `verify_step_up(db: Session, user_record, current_password: str | None, code: str | None) -> bool`

**Hinweis für den Umsetzer:** `auth.py:_verify_fresh_totp` macht fast dasselbe und wird **nicht** umgebaut — ein Refactoring der 2FA-Routen gehört nicht in diese Änderung. Der Name dort verspricht mehr, als der Code hält (keine Frischeprüfung, Issue #697); das neue Modul übernimmt das Verhalten und benennt es im Docstring ehrlich.

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
    """Mit 2FA zählt nur der Code — ein Passwort öffnet nichts."""
    monkeypatch.setattr(
        "app.services.auth.authenticate_user",
        lambda username, password, db=None: totp_user,
    )
    assert step_up.verify_step_up(None, totp_user, "richtig", None) is False


def test_totp_code_accepted(monkeypatch, totp_user):
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

Run: `cd backend && ./.venv/bin/python -m pytest tests/services/test_step_up.py -v`
Erwartet: FAIL — `ModuleNotFoundError: No module named 'app.services.step_up'`

- [ ] **Step 3: Implementierung schreiben**

```python
# backend/app/services/step_up.py
"""Zweiter Nachweis vor einer Aktion, die ein gültiges Token allein nicht decken soll.

Ein gekoppeltes Gerät hält sein Token tagelang. Für eine Aktion, die den Dienst
unterbricht, ist "dieses Gerät war einmal angemeldet" zu wenig — verlangt wird
derselbe Nachweis wie bei einer Anmeldung.

Was tatsächlich akzeptiert wird, und zwar genau so wie in den 2FA-Routen: bei
aktivem 2FA ein Code im aktuellen ±1-Zeitfenster (~90 s, **ohne**
Frischeprüfung — derselbe Code geht mehrfach, Issue #697) oder ein Backup-Code;
sonst das Passwort. Der Name "Step-up" beschreibt den Zweck, nicht eine
Einmaligkeitsgarantie, die es hier nicht gibt.
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
        # Mit 2FA zählt ausschließlich der Code. Ein Passwort würde den zweiten
        # Faktor aushebeln, den der Nutzer gerade eingeschaltet hat.
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

Run: `cd backend && ./.venv/bin/python -m pytest tests/services/test_step_up.py -v`
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
- Modify: `backend/app/schemas/system.py` (anhängen), `backend/app/core/rate_limiter.py`
- Test: `backend/tests/schemas/test_system_restart_schemas.py`, `backend/tests/test_rate_limit_values.py`

**Interfaces:**
- Produces: `SystemRestartAllRequest`, `UnitRestartResult`, `SystemRestartAllResponse`, `RATE_LIMITS["system_restart"] == "5/minute"`

- [ ] **Step 1: Test schreiben**

```python
# an backend/tests/test_rate_limit_values.py anhängen

def test_system_restart_is_strict():
    """/api/system/restart-all nimmt ein Passwort entgegen.

    admin_operations (30/minute) wäre dafür zu locker. Was dieser Wert NICHT
    ist: derselbe Schutz wie auth_password_change — jene Route liegt zusätzlich
    hinter nginx' auth_limit (5 r/m), diese nicht. Und der Limiter lebt im
    Prozessspeicher, den der Endpunkt selbst neu startet. Siehe security-agent.md.
    """
    assert RATE_LIMITS["system_restart"] == "5/minute"
```

```python
# backend/tests/schemas/test_system_restart_schemas.py
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

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_rate_limit_values.py tests/schemas/test_system_restart_schemas.py -v`
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

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_rate_limit_values.py tests/schemas/test_system_restart_schemas.py -v`
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
- Consumes: `system_restart` (Task 1), `step_up` (Task 2), die Schemas und `get_limit("system_restart")` (Task 3)
- Produces: `POST /api/system/restart-all`, `_schedule_backend_restart(eta: float = 1.0) -> None`

**Drei Gates, in dieser Reihenfolge:** Admin → LAN → Step-up. Und API-Keys fliegen raus, bevor irgendetwas passiert.

- [ ] **Step 1: Test schreiben**

```python
# backend/tests/api/test_system_restart_all.py
"""Tests für POST /api/system/restart-all (Admin + LAN + Step-up)."""
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
    """Alle Support-Units melden Erfolg, ohne systemctl anzufassen."""
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


def test_non_local_client_is_rejected(client, admin_headers, fake_units, monkeypatch):
    """:8000 lauscht auf 0.0.0.0 ohne Paketfilter (#698) — das Gate ist real."""
    monkeypatch.setattr(
        "app.api.routes.system.is_private_or_local_ip", lambda ip: False
    )

    r = client.post(
        PATH, json={"current_password": settings.admin_password}, headers=admin_headers
    )

    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "local_network_required"
    assert fake_units == []


def test_api_key_is_rejected(client, admin_headers, fake_units, monkeypatch):
    """Ein Step-up soll Anwesenheit belegen; ein Schlüssel kann das nicht.

    Nebenbei: ein Key-Aufrufer fiele in get_user_identifier auf den
    IP-Schlüssel zurück und könnte das Rate-Limit aufweichen.
    """
    from app.api.routes import system as system_module

    # deps.get_current_user setzt request.state.auth_method = "api_key";
    # hier wird der Leser dieses Markers ersetzt, nicht die halbe Auth-Kette.
    monkeypatch.setattr(system_module, "_is_api_key_request", lambda request: True)

    r = client.post(
        PATH, json={"current_password": settings.admin_password}, headers=admin_headers
    )

    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "api_key_not_allowed"
    assert fake_units == []


def test_wrong_password_returns_structured_401(client, admin_headers, fake_units):
    r = client.post(PATH, json={"current_password": "falsch"}, headers=admin_headers)

    assert r.status_code == 401
    detail = r.json()["detail"]
    assert detail["error"] == "step_up_failed"
    assert detail["totp_required"] is False
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
            system_restart.UnitResult("baluhost-backend-local", True),
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


def test_totp_account_needs_a_code_and_the_body_says_so(
    client, admin_headers, fake_units, monkeypatch
):
    """Mit 2FA öffnet das Passwort nichts — und der 401 sagt dem Client, warum."""
    from app.api.routes import system as system_module

    monkeypatch.setattr(system_module, "_totp_enabled_for", lambda user_record: True)
    monkeypatch.setattr(
        "app.services.step_up.verify_step_up",
        lambda db, user_record, current_password, code: code == "123456",
    )

    rejected = client.post(
        PATH, json={"current_password": settings.admin_password}, headers=admin_headers
    )
    assert rejected.status_code == 401
    assert rejected.json()["detail"]["totp_required"] is True

    assert client.post(
        PATH, json={"code": "123456"}, headers=admin_headers
    ).status_code == 200


def test_rate_limit_decorator_is_actually_attached():
    """Der Wert in RATE_LIMITS nützt nichts, wenn der Dekorator fehlt.

    Im Testmodus liefert get_limit() für diesen Schlüssel ein sehr hohes Limit,
    der Dekorator bremst hier also nichts — geprüft wird nur, dass er dranhängt.
    """
    from app.main import app

    route = next(
        r for r in app.routes if getattr(r, "path", "").endswith("/system/restart-all")
    )
    assert getattr(route.endpoint, "_rate_limit_marker", None) or hasattr(
        route.endpoint, "__wrapped__"
    ), "keine Rate-Limit-Umhüllung an der Route"
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && ./.venv/bin/python -m pytest tests/api/test_system_restart_all.py -v`
Erwartet: FAIL — 404 auf allen Routen, plus `AttributeError` beim Patchen von `_schedule_backend_restart`

- [ ] **Step 3: Implementierung schreiben**

Importe oben in `backend/app/api/routes/system.py` ergänzen:

```python
import asyncio

from app.core.network_utils import is_private_or_local_ip
from app.models.user import User as UserModel
from app.services import step_up, system_restart
from app.schemas.system import (
    SystemRestartAllRequest,
    SystemRestartAllResponse,
    UnitRestartResult,
)
```

**Module importieren, nicht die Funktionen.** `from app.services.step_up import verify_step_up` bindet den Namen hier fest; ein `monkeypatch.setattr` auf `app.services.step_up.verify_step_up` ginge dann ins Leere, und der 2FA-Test wäre ein stiller Blindgänger.

**Bereits vorhanden und nicht erneut zu importieren:** `logging`, `os`, `signal`, `threading`, `status`, `HTTPException`, `Depends`, `Request`, `Response`, `Session` (aus `sqlalchemy.orm`), `deps` (die DB-Session kommt als `Depends(deps.get_db)`), `user_limiter`, `get_limit`, `UserPublic`, `get_audit_logger_db`.

Dann, nach der bestehenden `restart_system`-Route:

```python
def _is_api_key_request(request: Request) -> bool:
    """deps.get_current_user setzt diesen Marker für den API-Key-Pfad."""
    return getattr(request.state, "auth_method", None) == "api_key"


def _totp_enabled_for(user_record) -> bool:
    """Eigene Funktion, damit Tests die 2FA-Variante ohne Secret erreichen."""
    return bool(getattr(user_record, "totp_enabled", False))


def _schedule_backend_restart(eta: float = 1.0) -> None:
    """Das Backend zuletzt neu starten, nachdem die Antwort draußen ist.

    Bewusst als eigener Helfer und nicht im Route-Körper: Tests müssen ihn
    ersetzen können, sonst beendet der Timer den Testlauf.

    **Kein SIGINT-Fallback.** Das bestehende `/api/system/restart` fällt bei
    einem Fehlschlag auf `os.kill(os.getpid(), SIGINT)` zurück; bei
    `uvicorn --workers 4` trifft das einen Kindprozess, den uvicorn binnen
    einer halben Sekunde neu startet, während drei Worker unverändert
    weiterlaufen — und der Aufrufer hat "Neustart geplant" gelesen. Issue #695.
    Hier wird ein Fehlschlag protokolliert und sonst nichts getan.
    `/api/system/restart` bleibt unangetastet, weil die Companion-App und
    `localApi.ts` daran hängen.
    """
    from app.core.config import settings

    def _perform() -> None:
        logger = logging.getLogger(__name__)
        if settings.is_dev_mode:
            # Dort läuft ein einzelner Prozess — dort stimmt SIGINT.
            logger.info("Dev mode: sending SIGINT to trigger restart")
            os.kill(os.getpid(), signal.SIGINT)
            return
        result = system_restart.restart_unit(system_restart.BACKEND_UNIT)
        if not result.success:
            logger.error(
                "restart of %s failed: %s — the service is still running the "
                "old process",
                result.name,
                result.message,
            )

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
    """Alle BaluHost-Units neu starten (Admin + lokales Netz + Step-up).

    Die vier Nebendienste laufen synchron, damit ihr Ergebnis in die Antwort
    passt. `baluhost-backend` kommt zuletzt und per Timer — die Antwort muss
    raus sein, bevor der Prozess stirbt.
    """
    # settings lokal, wie in den übrigen Routen dieser Datei;
    # get_audit_logger_db steht bereits oben im Modul.
    from app.core.config import settings

    audit = get_audit_logger_db()
    ip_address = request.client.host if request.client else None

    if _is_api_key_request(request):
        audit.log_security_event(
            action="restart_all_api_key_denied",
            user=user.username,
            details={"ip_address": ip_address},
            success=False,
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "api_key_not_allowed",
                "message": (
                    "Dieser Vorgang verlangt eine erneute Anmeldung und ist "
                    "mit einem API-Schlüssel nicht möglich."
                ),
            },
        )

    # LAN-Gate (echte Client-IP über --proxy-headers), Muster wie
    # /api/auth/recovery-reset. Grund: :8000 lauscht auf 0.0.0.0 und es läuft
    # kein Paketfilter (#698) — ohne dieses Gate wäre der Endpunkt aus LAN und
    # VPN an nginx und dessen Rate-Limits vorbei erreichbar.
    if not is_private_or_local_ip(ip_address):
        audit.log_security_event(
            action="restart_all_denied",
            user=user.username,
            details={"ip_address": ip_address, "reason": "non_local"},
            success=False,
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "local_network_required",
                "message": (
                    "Der Sammelneustart ist nur aus dem lokalen Netz möglich."
                ),
            },
        )

    user_record = db.query(UserModel).filter(UserModel.id == user.id).first()
    if not user_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    totp_required = _totp_enabled_for(user_record)
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
                # Sagt dem Client, welches Feld die Route erwartet. Zuverlässiger
                # als ein vorher abgefragter 2FA-Status, der bei abgelaufenem
                # Token leer zurückkommt.
                "totp_required": totp_required,
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

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && ./.venv/bin/python -m pytest tests/api/test_system_restart_all.py -v`
Erwartet: PASS (13 Tests)

- [ ] **Step 5: Regression prüfen**

Run: `cd backend && ./.venv/bin/python -m pytest tests/api tests/services tests/schemas -q`
Erwartet: keine neuen Fehlschläge

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/system.py backend/tests/api/test_system_restart_all.py
git commit -m "feat(system): POST /api/system/restart-all mit Step-up und LAN-Gate

Drei Gates: Admin, lokales Netz, zweiter Nachweis. API-Keys werden
abgelehnt -- ein Step-up soll Anwesenheit belegen, und ein Key-Aufrufer
wuerde nebenbei den Rate-Limit-Schluessel auf die IP verschieben.
Kein SIGINT-Fallback (#695).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: Tray — Grundlagen von `restart.py`

**Files:**
- Create: `backend/baluhost_tray/restart.py`
- Test: `backend/tests/tray/test_restart.py`

**Interfaces:**
- Produces:
  - `UNITS: tuple[str, ...]`, `HEALTH_PATH`, `ME_PATH`, `TOTP_STATUS_PATH`, `RESTART_ALL_PATH`, `PROBE_TIMEOUT`, `API_TIMEOUT`
  - `@dataclass(frozen=True) RestartOutcome(ok, message, retry_secret=False, offer_local=False)`
  - `@dataclass(frozen=True) AccountFacts(is_admin: bool | None, totp_enabled: bool)`
  - `probe_api(client) -> bool`
  - `fetch_account_facts(client, on_auth_expired=None) -> AccountFacts`
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
    assert client.get.call_args.kwargs["timeout"] == restart.PROBE_TIMEOUT


def test_probe_false_on_error_status():
    assert restart.probe_api(_client(get=_response(502))) is False


def test_probe_false_on_transport_error():
    """Kein Statuscode, gar keine Antwort — genau der Notfall."""
    assert restart.probe_api(_client(get=httpx.ConnectError("refused"))) is False


def test_probe_false_on_timeout():
    assert restart.probe_api(_client(get=httpx.ReadTimeout("slow"))) is False


# --- Kontodaten ----------------------------------------------------------

def test_facts_report_admin_and_totp():
    client = MagicMock()
    client.get.side_effect = [
        _response(200, {"role": "admin"}),
        _response(200, {"enabled": True}),
    ]

    assert restart.fetch_account_facts(client) == restart.AccountFacts(
        is_admin=True, totp_enabled=True
    )


def test_facts_report_non_admin():
    client = MagicMock()
    client.get.side_effect = [
        _response(200, {"role": "user"}),
        _response(200, {"enabled": False}),
    ]
    assert restart.fetch_account_facts(client).is_admin is False


def test_facts_unknown_when_me_is_unreachable():
    """Unbekannt ist nicht dasselbe wie 'kein Admin' — siehe menu_visible."""
    client = _client(get=httpx.ConnectError("down"))

    facts = restart.fetch_account_facts(client)

    assert facts.is_admin is None
    assert facts.totp_enabled is False


def test_facts_refresh_once_on_401_and_retry():
    """Der Normalfall beim Tray-Start ist ein abgelaufener Access-Token (#692).

    Ohne Refresh liefe ein 2FA-Konto in drei Passwortabfragen, die die Route
    gar nicht akzeptiert.
    """
    client = MagicMock()
    client.get.side_effect = [
        _response(401),                              # /me, Token abgelaufen
        _response(200, {"role": "admin"}),           # /me nach dem Refresh
        _response(200, {"enabled": True}),           # /2fa/status
    ]
    refreshed = []

    facts = restart.fetch_account_facts(
        client, on_auth_expired=lambda: refreshed.append(True)
    )

    assert refreshed == [True]
    assert facts == restart.AccountFacts(is_admin=True, totp_enabled=True)


def test_facts_give_up_after_one_refresh():
    client = MagicMock()
    client.get.side_effect = [_response(401), _response(401)]

    facts = restart.fetch_account_facts(client, on_auth_expired=lambda: None)

    assert facts.is_admin is None


def test_facts_survive_a_failing_refresh():
    """refresh_access wirft PairingLost/TemporaryFailure — das darf nicht durch."""
    client = MagicMock()
    client.get.side_effect = [_response(401)]

    def boom():
        raise RuntimeError("refresh kaputt")

    facts = restart.fetch_account_facts(client, on_auth_expired=boom)

    assert facts.is_admin is None


def test_facts_totp_defaults_to_false_when_status_fails():
    client = MagicMock()
    client.get.side_effect = [_response(200, {"role": "admin"}), _response(500)]

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

Run: `cd backend && ./.venv/bin/python -m pytest tests/tray/test_restart.py -v`
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

import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Sequence

import httpx

HEALTH_PATH = "/api/health"
ME_PATH = "/api/auth/me"
TOTP_STATUS_PATH = "/api/auth/2fa/status"
RESTART_ALL_PATH = "/api/system/restart-all"

# Long enough that a busy backend still counts as alive, short enough that the
# dialog does not feel stuck in the case this feature exists for.
PROBE_TIMEOUT = 2.0
# The API path restarts four units synchronously (20 s each in the worst case)
# before it answers. Below that, a slow restart would look like a dead backend.
API_TIMEOUT = 120.0
LOCAL_TIMEOUT = 120.0

UNITS: tuple[str, ...] = (
    "baluhost-scheduler",
    "baluhost-monitoring",
    "baluhost-webdav",
    "baluhost-backend-local",
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


_UNKNOWN = AccountFacts(is_admin=None, totp_enabled=False)


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


def fetch_account_facts(
    client,
    on_auth_expired: Callable[[], None] | None = None,
) -> AccountFacts:
    """Role and 2FA state of the paired account. Never raises.

    Refreshes once on a 401: an expired access token is the normal state at
    tray start (#692), and without the retry a 2FA account would be asked three
    times for a password the route does not accept.
    """
    refreshed = False
    while True:
        try:
            response = client.get(ME_PATH, timeout=PROBE_TIMEOUT)
        except httpx.HTTPError:
            return _UNKNOWN

        if response.status_code == 401 and on_auth_expired is not None and not refreshed:
            try:
                on_auth_expired()
            except Exception:       # noqa: BLE001 — PairingLost, network, anything
                return _UNKNOWN
            refreshed = True
            continue

        if response.status_code != 200:
            return _UNKNOWN

        try:
            is_admin = response.json().get("role") == "admin"
        except (ValueError, AttributeError):
            return _UNKNOWN
        break

    totp_enabled = False
    try:
        status_response = client.get(TOTP_STATUS_PATH, timeout=PROBE_TIMEOUT)
        if status_response.status_code == 200:
            totp_enabled = bool(status_response.json().get("enabled"))
    except (httpx.HTTPError, ValueError, AttributeError):
        # A missing 2FA state only mislabels the dialog, and the route's 401
        # carries `totp_required` anyway.
        pass

    return AccountFacts(is_admin=is_admin, totp_enabled=totp_enabled)


def menu_visible(is_admin: bool | None, api_reachable: bool) -> bool:
    """Show the entry for admins — and for anyone when we could not ask.

    The middle case is the point: without it the button would be missing in
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

Run: `cd backend && ./.venv/bin/python -m pytest tests/tray/test_restart.py -v`
Erwartet: PASS (18 Tests)

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
- Produces: `restart_via_systemctl(runner=subprocess.run, units=UNITS, timeout=LOCAL_TIMEOUT) -> RestartOutcome`

**Der springende Punkt: ein einziger Aufruf.** polkit bindet die temporäre Autorisierung an die PID des Anfragenden (`polkit_unix_process_equal` verlangt PID-Gleichheit). Fünf einzelne `systemctl`-Aufrufe wären fünf Prozesse und damit **fünf Dialoge**. Ein Aufruf mit allen fünf Units ist ein Prozess, fünf D-Bus-Aufrufe, ein Dialog. Der Zustand je Unit kommt danach aus `systemctl is-active` — lesend, ohne Abfrage.

- [ ] **Step 1: Test schreiben**

```python
# an backend/tests/tray/test_restart.py anhängen
import subprocess


class _Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _runner_script(*responses):
    """Ein Runner, der die vorbereiteten Antworten der Reihe nach liefert."""
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        return responses[len(calls) - 1]

    runner.calls = calls
    return runner


def test_systemctl_restarts_all_units_in_one_call():
    """Ein Prozess, ein polkit-Dialog. Fünf Aufrufe wären fünf Dialoge."""
    runner = _runner_script(
        _Completed(),
        _Completed(stdout="active\n" * len(restart.UNITS)),
    )

    outcome = restart.restart_via_systemctl(runner=runner)

    assert outcome.ok is True
    assert runner.calls[0] == ["systemctl", "restart", *restart.UNITS]


def test_systemctl_is_called_without_sudo_and_without_shell():
    """polkit macht die Rechtefrage — sudo wäre eine zweite, andere Antwort."""
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        return _Completed(stdout="active\n" * len(restart.UNITS))

    restart.restart_via_systemctl(runner=runner)

    args, kwargs = calls[0]
    assert "sudo" not in args
    assert "shell" not in kwargs


def test_systemctl_checks_state_with_is_active_afterwards():
    runner = _runner_script(
        _Completed(),
        _Completed(stdout="active\n" * len(restart.UNITS)),
    )

    restart.restart_via_systemctl(runner=runner)

    assert runner.calls[1] == ["systemctl", "is-active", *restart.UNITS]


def test_cancelled_dialog_reports_which_units_are_running():
    """Wer den Dialog abbricht, will wissen, was jetzt läuft und was nicht."""
    states = ["active", "active", "failed", "active", "active"]
    runner = _runner_script(
        _Completed(returncode=1, stderr="Interactive authentication required."),
        _Completed(returncode=1, stdout="\n".join(states) + "\n"),
    )

    outcome = restart.restart_via_systemctl(runner=runner)

    assert outcome.ok is False
    assert "Interactive authentication required." in outcome.message
    assert "baluhost-webdav" in outcome.message      # die nicht aktive Unit


def test_systemctl_handles_timeout():
    def runner(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=120.0)

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


def test_failed_is_active_lookup_does_not_hide_the_failure():
    """Der Neustart ist gescheitert; die Nachschau auch — sag trotzdem etwas."""
    def runner(args, **kwargs):
        if args[1] == "is-active":
            raise OSError("systemctl weg")
        return _Completed(returncode=1, stderr="Interactive authentication required.")

    outcome = restart.restart_via_systemctl(runner=runner)

    assert outcome.ok is False
    assert "Interactive authentication required." in outcome.message


def test_success_message_names_the_count():
    runner = _runner_script(
        _Completed(), _Completed(stdout="active\n" * len(restart.UNITS))
    )

    outcome = restart.restart_via_systemctl(runner=runner)

    assert str(len(restart.UNITS)) in outcome.message
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && ./.venv/bin/python -m pytest tests/tray/test_restart.py -k systemctl -v`
Erwartet: FAIL — `AttributeError: module 'baluhost_tray.restart' has no attribute 'restart_via_systemctl'`

- [ ] **Step 3: Implementierung schreiben**

```python
# ans Ende von backend/baluhost_tray/restart.py

def _unit_states(
    runner: Callable[..., Any], units: Sequence[str], timeout: float
) -> dict[str, str]:
    """`systemctl is-active` für alle Units. Lesend — kein polkit, kein Dialog.

    Returns an empty mapping when the query itself fails; the caller must not
    turn a successful restart into a failure just because the follow-up look
    did not work.
    """
    try:
        completed = runner(
            ["systemctl", "is-active", *units],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.SubprocessError, OSError):
        return {}
    lines = (completed.stdout or "").splitlines()
    return {unit: (lines[i].strip() if i < len(lines) else "") for i, unit in enumerate(units)}


def restart_via_systemctl(
    runner: Callable[..., Any] = subprocess.run,
    units: Sequence[str] = UNITS,
    timeout: float = LOCAL_TIMEOUT,
) -> RestartOutcome:
    """The fallback: ask systemd directly, let polkit ask the user.

    No sudo. systemd checks the caller against
    ``org.freedesktop.systemd1.manage-units`` (auth_admin_keep), so KDE's own
    agent prompts.

    **One call for all units, on purpose.** polkit binds the temporary
    authorisation to the requesting *process* — five separate systemctl calls
    would be five processes and five password prompts. One call is one process
    making five D-Bus requests, so the agent asks once.

    **And it stays a short-lived subprocess.** Calling
    org.freedesktop.systemd1.Manager.RestartUnit over D-Bus from this
    long-lived tray process would keep that authorisation alive for five
    minutes — and `manage-units` also covers StartTransientUnit, i.e. running
    anything as root. The process boundary is what keeps the radius small.
    """
    try:
        completed = runner(
            ["systemctl", "restart", *units],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return RestartOutcome(
            False,
            "Zeitüberschreitung beim Neustart. Die Dienste können trotzdem "
            "gerade hochfahren — bitte den Zustand prüfen.",
        )
    except OSError as exc:
        return RestartOutcome(
            False, f"systemctl konnte nicht ausgeführt werden: {exc}"
        )

    if completed.returncode == 0:
        return RestartOutcome(True, f"{len(units)} Dienste neu gestartet.")

    detail = (completed.stderr or completed.stdout or "").strip()
    detail = detail or f"exit {completed.returncode}"
    states = _unit_states(runner, units, timeout)
    inactive = [unit for unit, state in states.items() if state != "active"]
    tail = (
        "\n\nNicht aktiv: " + ", ".join(inactive)
        if inactive
        else "\n\nAlle Dienste laufen trotzdem."
    )
    return RestartOutcome(
        False,
        f"Neustart fehlgeschlagen — abgebrochen oder keine Berechtigung.\n\n"
        f"{detail}{tail}",
    )
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && ./.venv/bin/python -m pytest tests/tray/test_restart.py -v`
Erwartet: PASS (26 Tests)

- [ ] **Step 5: Commit**

```bash
git add backend/baluhost_tray/restart.py backend/tests/tray/test_restart.py
git commit -m "feat(tray): Notweg ueber einen systemctl-Aufruf mit polkit-Abfrage

Ein Aufruf fuer alle Units, weil polkit die temporaere Autorisierung an die
PID bindet -- fuenf Aufrufe waeren fuenf Passwortdialoge. Der Zustand je Unit
kommt danach aus is-active, das keine Abfrage braucht.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: Tray — Normalweg über die API

**Files:**
- Modify: `backend/baluhost_tray/restart.py` (anhängen)
- Test: `backend/tests/tray/test_restart.py` (anhängen)

**Interfaces:**
- Produces: `restart_via_api(client, secret: str, totp: bool, on_auth_expired=None) -> RestartOutcome`

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
    outcome = restart.restart_via_api(
        _client(post=_response(200, _ok_payload())), "geheim", totp=False
    )
    assert "Backend" in outcome.message


def test_api_reports_a_failed_unit_by_name():
    client = _client(post=_response(200, _ok_payload(failed=["baluhost-webdav"])))

    outcome = restart.restart_via_api(client, "geheim", totp=False)

    assert outcome.ok is False
    assert "baluhost-webdav" in outcome.message


def test_step_up_failure_asks_again():
    client = _client(
        post=_response(401, {"detail": {"error": "step_up_failed", "totp_required": False}})
    )

    outcome = restart.restart_via_api(client, "falsch", totp=False)

    assert outcome.ok is False
    assert outcome.retry_secret is True


def test_step_up_failure_switches_to_totp_when_the_body_says_so():
    """Der 401 ist die zuverlässigere Quelle als ein vorher geholter Status."""
    client = _client(
        post=_response(401, {"detail": {"error": "step_up_failed", "totp_required": True}})
    )

    outcome = restart.restart_via_api(client, "geheim", totp=False)

    assert outcome.retry_secret is True
    assert outcome.totp_required is True


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


def test_a_failing_refresh_does_not_escape():
    """session.refresh_access wirft PairingLost — das darf den Klick nicht sprengen."""
    client = MagicMock()
    client.post.side_effect = [_response(401, {"detail": "Not authenticated"})]

    def boom():
        raise RuntimeError("pairing lost")

    outcome = restart.restart_via_api(
        client, "geheim", totp=False, on_auth_expired=boom
    )

    assert outcome.ok is False


def test_step_up_failure_is_not_retried_as_an_expired_token():
    client = MagicMock()
    client.post.side_effect = [
        _response(401, {"detail": {"error": "step_up_failed", "totp_required": False}})
    ]
    refreshed = []

    restart.restart_via_api(
        client, "falsch", totp=False, on_auth_expired=lambda: refreshed.append(True)
    )

    assert refreshed == []
    assert client.post.call_count == 1


def test_403_local_network_is_named():
    client = _client(post=_response(403, {"detail": {"error": "local_network_required"}}))

    outcome = restart.restart_via_api(client, "geheim", totp=False)

    assert outcome.ok is False
    assert "lokalen Netz" in outcome.message


def test_403_admin_is_named():
    client = _client(post=_response(403, {"detail": "Insufficient permissions"}))

    outcome = restart.restart_via_api(client, "geheim", totp=False)

    assert "Admin" in outcome.message


def test_429_names_the_wait():
    outcome = restart.restart_via_api(_client(post=_response(429)), "geheim", totp=False)
    assert outcome.ok is False
    assert "Minute" in outcome.message


def test_5xx_is_reported_as_a_server_error():
    outcome = restart.restart_via_api(_client(post=_response(500)), "geheim", totp=False)
    assert outcome.ok is False
    assert outcome.offer_local is False


def test_timeout_does_not_offer_the_fallback():
    """Sonst startet der Nutzer alles ein zweites Mal, während es gerade läuft."""
    client = _client(post=httpx.ReadTimeout("too slow"))

    outcome = restart.restart_via_api(client, "geheim", totp=False)

    assert outcome.ok is False
    assert outcome.offer_local is False
    assert "länger" in outcome.message


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

Run: `cd backend && ./.venv/bin/python -m pytest tests/tray/test_restart.py -k api -v`
Erwartet: FAIL — `AttributeError: module 'baluhost_tray.restart' has no attribute 'restart_via_api'`

- [ ] **Step 3: Implementierung schreiben**

Zuerst `RestartOutcome` um ein Feld erweitern (oben in der Datei):

```python
@dataclass(frozen=True)
class RestartOutcome:
    ok: bool
    message: str
    retry_secret: bool = False   # wrong password/code — ask again
    offer_local: bool = False    # API died mid-flight — offer the fallback
    totp_required: bool = False  # the route wants a code, not a password
```

```python
# ans Ende von backend/baluhost_tray/restart.py

def _detail(response) -> Any:
    try:
        return response.json().get("detail")
    except (ValueError, AttributeError):
        return None


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
            response = client.post(RESTART_ALL_PATH, json=body, timeout=API_TIMEOUT)
        except httpx.TimeoutException:
            # Nicht als "Backend tot" behandeln: die Route startet vier Units
            # synchron. Wer hier den Notweg anböte, liesse den Nutzer alles ein
            # zweites Mal starten, waehrend es gerade ordentlich laeuft.
            return RestartOutcome(
                False,
                "Der Neustart dauert länger als erwartet. Er läuft "
                "wahrscheinlich noch — bitte den Zustand prüfen, bevor du es "
                "erneut versuchst.",
            )
        except httpx.HTTPError as exc:
            return RestartOutcome(
                False,
                f"Das Backend hat die Verbindung abgebrochen ({exc}).",
                offer_local=True,
            )

        code = response.status_code
        detail = _detail(response)

        if code == 401:
            if isinstance(detail, dict) and detail.get("error") == "step_up_failed":
                return RestartOutcome(
                    False,
                    "Passwort bzw. 2FA-Code stimmt nicht.",
                    retry_secret=True,
                    totp_required=bool(detail.get("totp_required")),
                )
            if on_auth_expired is not None and not refreshed:
                try:
                    on_auth_expired()
                except Exception as exc:        # noqa: BLE001 — PairingLost u.a.
                    return RestartOutcome(
                        False, f"Anmeldung konnte nicht erneuert werden: {exc}"
                    )
                refreshed = True
                continue
            return RestartOutcome(
                False,
                "Die Kopplung ist abgelaufen. Einmalig ausführen: "
                "baluhost-tray --pair",
            )

        if code == 403:
            if isinstance(detail, dict) and detail.get("error") == "local_network_required":
                return RestartOutcome(
                    False, "Der Neustart ist nur aus dem lokalen Netz möglich."
                )
            return RestartOutcome(False, "Dieses Konto ist kein BaluHost-Admin.")
        if code == 429:
            return RestartOutcome(
                False, "Zu viele Versuche. In einer Minute erneut probieren."
            )
        if code != 200:
            return RestartOutcome(
                False, f"Das Backend hat den Neustart abgelehnt ({code})."
            )

        try:
            units = response.json()["units"]
            failed = [u["name"] for u in units if not u.get("success")]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            return RestartOutcome(
                False, f"Unerwartete Antwort des Backends ({exc})."
            )

        if failed:
            return RestartOutcome(False, "Nicht neu gestartet: " + ", ".join(failed))
        return RestartOutcome(
            True,
            "Dienste neu gestartet. Das Backend startet gleich ebenfalls neu — "
            "das Symbol wird kurz grau.",
        )
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && ./.venv/bin/python -m pytest tests/tray/test_restart.py -v`
Erwartet: PASS (43 Tests)

- [ ] **Step 5: Commit**

```bash
git add backend/baluhost_tray/restart.py backend/tests/tray/test_restart.py
git commit -m "feat(tray): Normalweg ueber /api/system/restart-all

Timeout wird von Verbindungsabbruch unterschieden -- sonst boete das Tray
den Notweg an, waehrend das Backend die Units gerade ordentlich neu startet.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: Tray — der Ablauf (`restart_flow`)

**Files:**
- Modify: `backend/baluhost_tray/restart.py` (anhängen)
- Test: `backend/tests/tray/test_restart_flow.py`

**Interfaces:**
- Produces: `restart_flow(client, prompt, probe=probe_api, facts=fetch_account_facts, api=restart_via_api, local=restart_via_systemctl, on_auth_expired=None) -> RestartOutcome`
  - `prompt` ist ein Callback `(mode: str) -> str | None`; Modi: `"password"`, `"password_retry"`, `"totp"`, `"totp_retry"`, `"local"`.

**Warum der Ablauf in `restart.py` und nicht in `tray.py` liegt:** „proben → Kontodaten → Dialog → Weg wählen → bis zu drei Versuche" ist die eigentliche Logik. In `tray.py` wäre sie nur mit laufendem Qt prüfbar.

- [ ] **Step 1: Test schreiben**

```python
# backend/tests/tray/test_restart_flow.py
"""Tests für den Ablauf: proben, fragen, Weg wählen, wiederholen."""
from unittest.mock import MagicMock

from baluhost_tray import restart


def _facts(is_admin=True, totp=False):
    return lambda client, on_auth_expired=None: restart.AccountFacts(
        is_admin=is_admin, totp_enabled=totp
    )


def _prompts(*answers):
    seen = []

    def prompt(mode):
        seen.append(mode)
        return answers[len(seen) - 1]

    prompt.seen = seen
    return prompt


def _never_local(**kwargs):
    raise AssertionError("der Notweg darf hier nicht laufen")


def test_reachable_api_asks_for_a_password_and_calls_the_api():
    prompt = _prompts("geheim")
    called = {}

    def api(client, secret, totp, on_auth_expired=None):
        called.update(secret=secret, totp=totp)
        return restart.RestartOutcome(True, "ok")

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(), api=api, local=_never_local,
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
        local=_never_local,
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
        probe=lambda c: True, facts=_facts(), api=api, local=_never_local,
    )

    assert attempts == ["falsch1", "falsch2", "falsch3"]
    assert prompt.seen == ["password", "password_retry", "password_retry"]
    assert outcome.ok is False


def test_backend_can_switch_the_flow_to_a_code():
    """Der 401 weiss besser als wir, was die Route will."""
    prompt = _prompts("geheim", "123456")
    seen_totp = []

    def api(client, secret, totp, on_auth_expired=None):
        seen_totp.append(totp)
        if len(seen_totp) == 1:
            return restart.RestartOutcome(
                False, "nope", retry_secret=True, totp_required=True
            )
        return restart.RestartOutcome(True, "ok")

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(), api=api, local=_never_local,
    )

    assert prompt.seen == ["password", "totp_retry"]
    assert seen_totp == [False, True]
    assert outcome.ok is True


def test_cancelled_dialog_stops_without_calling_anything():
    prompt = _prompts(None)

    def api(client, secret, totp, on_auth_expired=None):
        raise AssertionError("darf nicht gerufen werden")

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(), api=api, local=_never_local,
    )

    assert outcome.ok is False
    assert "Abgebrochen" in outcome.message


def test_non_admin_is_told_without_being_asked_for_a_password():
    prompt = _prompts()

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(is_admin=False),
        api=lambda **kw: restart.RestartOutcome(True, "ok"), local=_never_local,
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
        api=lambda **kw: restart.RestartOutcome(False, "nein"), local=_never_local,
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


def test_timeout_does_not_switch_to_the_fallback():
    prompt = _prompts("geheim")

    outcome = restart.restart_flow(
        MagicMock(), prompt,
        probe=lambda c: True, facts=_facts(),
        api=lambda client, secret, totp, on_auth_expired=None: restart.RestartOutcome(
            False, "dauert länger"
        ),
        local=_never_local,
    )

    assert prompt.seen == ["password"]
    assert outcome.ok is False
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && ./.venv/bin/python -m pytest tests/tray/test_restart_flow.py -v`
Erwartet: FAIL — `AttributeError: module 'baluhost_tray.restart' has no attribute 'restart_flow'`

- [ ] **Step 3: Implementierung schreiben**

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
    Every collaborator is injected so the whole sequence is testable without a
    backend, without systemd and without a display.
    """
    if not probe(client):
        return _local_flow(prompt, local)

    account = facts(client, on_auth_expired=on_auth_expired)
    if account.is_admin is False:
        return RestartOutcome(
            False,
            "Dieses Konto ist kein BaluHost-Admin. Neustart nicht möglich.",
        )

    totp = account.totp_enabled
    for attempt in range(MAX_SECRET_ATTEMPTS):
        mode = "totp" if totp else "password"
        secret = prompt(mode if attempt == 0 else f"{mode}_retry")
        if secret is None:
            return RestartOutcome(False, "Abgebrochen.")

        outcome = api(client, secret, totp, on_auth_expired=on_auth_expired)
        if outcome.offer_local:
            return _local_flow(prompt, local)
        if not outcome.retry_secret:
            return outcome
        # Die Route weiss besser als der vorher geholte 2FA-Status, was sie
        # erwartet — beim naechsten Versuch danach fragen.
        totp = outcome.totp_required or totp

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

Run: `cd backend && ./.venv/bin/python -m pytest tests/tray/test_restart_flow.py -v`
Erwartet: PASS (10 Tests)

- [ ] **Step 5: Commit**

```bash
git add backend/baluhost_tray/restart.py backend/tests/tray/test_restart_flow.py
git commit -m "feat(tray): Ablauf des Dienste-Neustarts ohne Qt

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9: Tray — Menüpunkt, Dialoge, Arbeitsthread

**Files:**
- Modify: `backend/baluhost_tray/tray.py`
- Test: `backend/tests/tray/test_tray_wiring.py`

**Interfaces:**
- Consumes: `restart_flow`, `fetch_account_facts`, `menu_visible`, `RestartOutcome` (Task 5–8)
- Produces: `MENU_RESTART` sowie die Bridge-Signale `restart_prompt`, `restart_finished`, `restart_visible`

### Drei Fallstricke, die beim Review aufgefallen sind

1. **`queue` ist in `run_tray()` schon vergeben.** `tray.py:87` hat `queue = PopupQueue()`; ein zusätzliches `import queue` würde beim Aufruf von `queue.Queue(...)` auf die `PopupQueue`-Instanz auflösen und `run_tray` mit `AttributeError` sterben lassen — noch vor `tray_icon.show()`. Deshalb `from queue import Empty, Queue` und **kein** Modulimport.
2. **Der Menüpunkt darf nicht dauerhaft grau bleiben.** `setEnabled(False)` beim Start, reaktiviert nur über `restart_finished` — also muss der Worker das Signal **garantiert** senden, auch wenn schon der Client-Aufbau scheitert. Ganzer Rumpf in `try`, `emit` in `finally`.
3. **Die neuen Zeilen in `_main()` gehören in den bestehenden zweiten `try:`-Block.** `tray.py:159-168` erklärt warum: jede Anweisung nach `notifier.connect()`, die daneben liegt, beendet bei einem Fehler den Worker still — Icon für immer grau, Exit 0, systemd sieht einen sauberen Abschluss.

- [ ] **Step 1: Test schreiben**

```python
# backend/tests/tray/test_tray_wiring.py
"""Rauchtest für die Qt-Verdrahtung.

Läuft nur, wo das Extra [tray] installiert ist — im venv dieses Repos ist
PyQt6 nicht dabei, im Produktions-venv und im System-Python schon:

    QT_QPA_PLATFORM=offscreen python3 -m pytest tests/tray/test_tray_wiring.py \
        -o addopts="" -p no:cacheprovider

Ohne diesen Test importiert **kein** Test `tray.py`, und ein Namensfehler auf
Funktionsebene fällt erst auf BaluNode auf.
"""
import os

import pytest

pytest.importorskip("PyQt6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _NoThread:
    """Der Worker-Thread wird nicht gestartet — kein Bus, kein Netzwerk."""

    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass


def test_run_tray_builds_the_menu(monkeypatch):
    """Läuft run_tray bis zum Ende durch, ohne dass ein Name kollidiert.

    Genau hier wäre `queue = PopupQueue()` gegen ein `import queue` gelaufen:
    ein AttributeError zur Laufzeit, den weder ast.parse noch ein Modulimport
    findet.
    """
    from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

    from baluhost_tray import tray as tray_module

    monkeypatch.setattr(
        QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True)
    )
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    monkeypatch.setattr(tray_module.threading, "Thread", _NoThread)

    assert tray_module.run_tray("http://localhost:8000", "http://localhost") == 0


def test_restart_menu_label_exists():
    from baluhost_tray import tray as tray_module

    assert tray_module.MENU_RESTART.startswith("BaluHost neu starten")
```

**Zwei Hinweise für den Umsetzer:** `run_tray` legt selbst ein `QApplication`
an — der Test darf keines vorher erzeugen, sonst kollidieren zwei Instanzen.
Und aus demselben Grund ruft nur **ein** Test in dieser Datei `run_tray` auf.
Lässt sich `run_tray` in dieser Umgebung nicht vollständig durchtreiben, den
Test auf `import baluhost_tray.tray` plus `MENU_RESTART` reduzieren und im
Docstring festhalten, was damit nicht mehr abgedeckt ist.

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `cd backend && QT_QPA_PLATFORM=offscreen python3 -m pytest tests/tray/test_tray_wiring.py -o addopts="" -p no:cacheprovider -v`
Erwartet: FAIL — `AttributeError: module 'baluhost_tray.tray' has no attribute 'MENU_RESTART'`

- [ ] **Step 3: `tray.py` verdrahten**

Importe:

```python
from queue import Empty, Queue          # NICHT `import queue` — siehe Fallstrick 1

from PyQt6.QtWidgets import (
    QApplication, QInputDialog, QLineEdit, QMenu, QMessageBox, QSystemTrayIcon,
)

from baluhost_tray import config as tray_config
from baluhost_tray.restart import (
    RestartOutcome,
    fetch_account_facts,
    menu_visible,
    restart_flow,
)
from baluhost_tui.client import BackendClient
```

Konstanten:

```python
MENU_RESTART = "BaluHost neu starten…"
PROMPT_TIMEOUT = 300.0      # der Worker wartet nicht ewig auf einen Dialog
```

In `_Bridge`:

```python
    restart_prompt = pyqtSignal(str)
    restart_finished = pyqtSignal(bool, str)
    restart_visible = pyqtSignal(bool)
```

In `run_tray()`, nach dem Menüpunkt `MENU_DEVICES` und vor dem Separator:

```python
    restart_action = menu.addAction(MENU_RESTART)
    # Bis die Rolle bekannt ist sichtbar: unbekannt heisst, dass die API gerade
    # nicht antwortet — genau der Fall, fuer den der Notweg da ist. Das Gate
    # ist polkit bzw. das Backend, nicht diese Zeile.
    restart_action.setVisible(True)
    bridge.restart_visible.connect(restart_action.setVisible)

    # Die Antwort des Dialogs geht ueber eine Queue zurueck in den
    # Arbeitsthread. Dialoge gehoeren in den GUI-Thread, Netzwerk nicht.
    answers: Queue = Queue(maxsize=1)

    def _show_prompt(mode: str) -> None:
        # Jeder Pfad legt genau eine Antwort ab. Ohne das finally bliebe der
        # Worker fuer immer in answers.get() haengen.
        value = None
        try:
            if mode == "local":
                choice = QMessageBox.question(
                    None,
                    "BaluHost neu starten",
                    "Das Backend antwortet nicht.\n\nDienste direkt über das "
                    "System neu starten? Das System fragt gleich nach dem "
                    "Passwort.\n\nLaufende Aufträge und Uploads werden dabei "
                    "abgebrochen.",
                )
                value = "ja" if choice == QMessageBox.StandardButton.Yes else None
                return
            is_totp = mode.startswith("totp")
            label = "2FA-Code" if is_totp else "Passwort"
            text = (
                f"{label} stimmt nicht. Noch einmal:"
                if mode.endswith("_retry")
                else f"{label} für BaluHost:\n\nLaufende Aufträge und Uploads "
                     f"werden abgebrochen."
            )
            typed, ok = QInputDialog.getText(
                None, "BaluHost neu starten", text, QLineEdit.EchoMode.Password
            )
            value = typed if ok and typed else None
        finally:
            answers.put(value)

    bridge.restart_prompt.connect(_show_prompt)

    def _restart_done(ok: bool, message: str) -> None:
        restart_action.setEnabled(True)
        box = QMessageBox.information if ok else QMessageBox.warning
        box(None, "BaluHost neu starten", message)

    bridge.restart_finished.connect(_restart_done)

    def _prompt_from_worker(mode: str) -> str | None:
        bridge.restart_prompt.emit(mode)
        try:
            return answers.get(timeout=PROMPT_TIMEOUT)
        except Empty:
            return None

    def _refresh_into(client: BackendClient) -> None:
        """Token erneuern und dem Neustart-Client mitgeben.

        Der Refresh-Token rotiert serverseitig nicht (siehe session.py), ein
        paralleler Refresh im Worker ist also inhaltlich harmlos. Alles, was
        dabei schiefgeht, faengt restart.py ab — hier darf nichts durch.
        """
        session.refresh_access()
        tokens = tray_config.load_tokens()
        if tokens:
            client.set_token(tokens.access)

    def _restart_worker() -> None:
        outcome = RestartOutcome(False, "Unerwarteter Fehler.")
        client = None
        try:
            # Eigener Client: der Worker-Thread wechselt beim Refresh das Token
            # des gemeinsamen Clients, und zwei Threads auf demselben Objekt
            # sind eine Verabredung zum Rennen.
            tokens = tray_config.load_tokens()
            client = BackendClient(
                server=base_url, token=tokens.access if tokens else None
            )
            outcome = restart_flow(
                client,
                _prompt_from_worker,
                on_auth_expired=lambda: _refresh_into(client),
            )
        except Exception as exc:                     # noqa: BLE001
            logger.exception("restart flow failed")
            outcome = RestartOutcome(False, f"Unerwarteter Fehler: {exc}")
        finally:
            if client is not None:
                client.close()
            # Muss feuern: nur dieses Signal macht den Menuepunkt wieder
            # anklickbar.
            bridge.restart_finished.emit(outcome.ok, outcome.message)

    def _start_restart() -> None:
        restart_action.setEnabled(False)
        threading.Thread(target=_restart_worker, daemon=True).start()

    restart_action.triggered.connect(_start_restart)
```

In `_main()` — **innerhalb** des bestehenden zweiten `try:`-Blocks, direkt vor `ctx = LoopContext(...)`:

```python
            # Sichtbarkeit einmal beim Start bestimmen. Eine Rollenaenderung
            # braucht danach einen Neustart des Trays — das ist selten genug.
            account = await asyncio.to_thread(
                fetch_account_facts, session.client(), session.refresh_access
            )
            bridge.restart_visible.emit(
                menu_visible(account.is_admin, account.is_admin is not None)
            )
```

- [ ] **Step 4: Tests laufen lassen**

Run: `cd backend && QT_QPA_PLATFORM=offscreen python3 -m pytest tests/tray/test_tray_wiring.py -o addopts="" -p no:cacheprovider -v`
Erwartet: PASS

Run: `cd backend && ./.venv/bin/python -m pytest tests/tray/ -v`
Erwartet: PASS, der Qt-Test als SKIPPED (kein PyQt6 im venv)

- [ ] **Step 5: Zusätzlich der Importcheck mit dem Interpreter, der PyQt6 hat**

Run: `cd backend && QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 -c "import baluhost_tray.tray; print('import ok')"`
Erwartet: `import ok`

- [ ] **Step 6: Commit**

```bash
git add backend/baluhost_tray/tray.py backend/tests/tray/test_tray_wiring.py
git commit -m "feat(tray): Menuepunkt und Dialoge fuer den Dienste-Neustart

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 10: Dokumentation und Regeln

**Files:**
- Modify: `docs/superpowers/specs/2026-09-21-desktop-tray-design.md`, `docs/features/desktop-tray.de.md`, `docs/features/desktop-tray.en.md`, `.claude/rules/security-agent.md`, `.claude/rules/architecture.md`, `deploy/install/templates/baluhost-tray.service`

- [ ] **Step 1: Beide überholten Stellen im Tray-Entwurf markieren**

In `docs/superpowers/specs/2026-09-21-desktop-tray-design.md` **zwei** Stellen, nicht eine:

Im Abschnitt „Nicht-Ziele" (ca. Zeile 45) den ersten Punkt ersetzen:

```markdown
- ~~**Service-Steuerung.** Neustarten oder Beenden von Diensten bleibt der
  Companion-App und der Web-UI vorbehalten. Das Tray fasst nichts
  Privilegiertes an und braucht keine sudoers-Erweiterung.~~
  **Überholt am 2026-09-22** durch
  `2026-09-22-tray-service-restart-design.md`: Das Tray kann Dienste neu
  starten. Der Notweg läuft über polkit statt über sudo; auf dem API-Weg kommt
  eine fünfte sudoers-Zeile für `baluhost-backend-local` dazu.
```

Und im Abschnitt „Architektur" (ca. Zeile 164) den Absatz über Menü und
ausgehenden Pfad:

```markdown
> **Überholt am 2026-09-22:** Das Menü hat einen fünften Eintrag („BaluHost neu
> starten…"), und damit hat das Tray sehr wohl einen ausgehenden Pfad. Siehe
> `2026-09-22-tray-service-restart-design.md`. Die Aussage zur Meldungsliste
> gilt weiter.
```

- [ ] **Step 2: Feature-Doku in beiden Sprachen**

In `docs/features/desktop-tray.de.md`, Abschnitt „Menue und Klick" (ab Zeile 91),
die Tabelle um eine Zeile **vor** „Beenden" erweitern:

```markdown
| **BaluHost neu starten…** | Startet alle BaluHost-Dienste neu — fragt vorher nach |
```

Und nach dem Absatz über *„Geraete in der Web-UI"* einen neuen Abschnitt:

```markdown
## Dienste neu starten

Der Menuepunkt *„BaluHost neu starten…"* startet alle fuenf Units neu:
`baluhost-scheduler`, `baluhost-monitoring`, `baluhost-webdav`,
`baluhost-backend-local` und zuletzt `baluhost-backend`.

**Laufende Auftraege werden dabei abgebrochen.** Der Scheduler markiert beim
Start jede noch laufende Ausfuehrung als abgebrochen, laufende Uploads sterben
mit dem Prozess. Der Dialog sagt das vorher.

**Wenn das Backend antwortet** fragt ein Dialog nach dem BaluHost-Passwort des
gekoppelten Kontos — bei aktivem 2FA nach einem Code. Das gekoppelte Token
allein reicht fuer diesen Vorgang nicht: es liegt tagelang auf der Platte, und
wer vor einem entsperrten Desktop sitzt, soll damit nicht den Dienst
unterbrechen koennen. Danach startet das Backend die Units selbst; das Symbol
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

Ist das gekoppelte Konto nachweislich kein Admin, erscheint der Menuepunkt
nicht. Konnte die Rolle nicht abgefragt werden — weil das Backend nicht
antwortet —, ist er da; dann entscheidet ohnehin polkit.

Der Neustart ueber das Backend steht im Audit-Log. Der Notweg nicht: dort
schreibt niemand mehr in die Datenbank. Die Spur liegt im Journal, wo polkitd
die Freigabe samt Nutzer protokolliert. Die systemd-Zeile nennt keinen Urheber,
und ein abgebrochener Dialog hinterlaesst gar nichts.
```

Dieselben Änderungen sinngemäß in `docs/features/desktop-tray.en.md` (Abschnitt
„Menu and click", ab Zeile 88). Die englische Fassung behält die deutschen
Menü-Beschriftungen in der Tabelle bei — so steht es dort bereits.

- [ ] **Step 3: Sicherheitsregeln ergänzen**

In `.claude/rules/security-agent.md`, am Ende des Abschnitts „Role Model" (nach
dem Absatz über `GET /api/plugins/steam_gaming/session-state`):

```markdown
- `POST /api/system/restart-all` startet alle fünf BaluHost-Units neu. Dreifach
  gegated: `get_current_admin`, `is_private_or_local_ip(request.client.host)`
  und ein Step-up (`services/step_up.verify_step_up`) — Code bei aktivem 2FA,
  sonst Passwort. **API-Keys werden abgelehnt** (`auth_method == "api_key"` →
  403): ein Step-up soll Anwesenheit belegen, und ein Key-Aufrufer fiele in
  `get_user_identifier` auf den IP-Schlüssel zurück und könnte das Rate-Limit
  über beliebige Quell-IPs aufweichen. Ein gescheiterter Step-up antwortet 401
  mit `{"error": "step_up_failed", "totp_required": …}`; die Unterscheidung zum
  abgelaufenen Token ist Teil des Vertrags, der Client reagiert auf beides
  anders. Rate-Limit `system_restart` (5/minute). Durchgesetzt in
  `api/routes/system.py`.

  **Was der Step-up nicht deckt:** `POST /api/system/restart` startet
  `baluhost-backend` weiterhin allein mit dem Admin-Token, ohne zweiten
  Nachweis und ohne LAN-Gate (Issue #699). Wer ein Tray-Token hat, erreicht die
  Fähigkeit „Backend neu starten" also auch ohne Step-up. Geschützt ist der
  *Sammel*neustart, nicht die Fähigkeit als solche.
```

Unter „Known Gaps & Accepted Risks" als Punkt **10** anhängen — die Liste endet
heute bei 9, und der Hinweis darunter (über den 2026-07-21 entfernten Eintrag 10)
bekommt einen Halbsatz, sonst zeigen zwei Dinge auf dieselbe Nummer:

```markdown
10. **Der Tray-Notweg schreibt keinen Audit-Eintrag, und sein Rate-Limit ist
    zurücksetzbar** — Zwei getrennte Einschränkungen desselben Features
    (`docs/superpowers/specs/2026-09-22-tray-service-restart-design.md`):

    *Audit:* Antwortet das Backend nicht, startet `baluhost_tray/restart.py`
    die Units selbst über einen einzigen `systemctl restart`-Aufruf; systemd
    fragt polkit (`org.freedesktop.systemd1.manage-units`, `auth_admin_keep`),
    KDE zeigt den Dialog. Ein App-Audit ist dann unmöglich — die Datenbank ist
    so unerreichbar wie die API. Im Journal steht die polkitd-Zeile mit Nutzer,
    Aktion und Zeit; die systemd-Zeile nennt **keinen** Urheber, und ein
    abgebrochener Dialog hinterlässt **gar nichts**. Ein Nachtrag-Endpunkt
    wurde verworfen: ein vom Client behaupteter Audit-Eintrag ist schwächeres
    Beweismaterial als die Zeile, die polkitd selbst geschrieben hat.

    *Rate-Limit:* `system_restart` (5/minute) liegt im Prozessspeicher, gilt
    also pro uvicorn-Worker (vier, ohne `ip_hash` im nginx-Upstream) — und der
    Endpunkt startet genau diese Prozesse neu. Ein Angreifer mit Admin-Token
    kann seine Zähler über `/api/system/restart` zurücksetzen und den Step-up
    damit schneller raten, als die Zahl vermuten lässt. Belastbar wäre ein
    persistenter Fehlversuchszähler am Konto (wie `pin_failed_attempts`); das
    ist bewusst nicht gebaut.

    Der Notweg braucht **kein** neues Recht: kein polkit-Policy-File, keine
    sudoers-Zeile für den Desktop-Nutzer, `NoNewPrivileges=yes` bleibt.
    `systemctl` eskaliert nichts im eigenen Prozess. **Wichtig:** Er muss ein
    kurzlebiger Subprozess bleiben. Ein D-Bus-Aufruf von
    `Manager.RestartUnit` aus dem langlebigen Tray-Prozess würde die
    Autorisierung fünf Minuten an diesem Prozess halten, und `manage-units`
    deckt auch `StartTransientUnit` ab — also beliebige Codeausführung als root.
    Der API-Weg nutzt die bestehenden NOPASSWD-Einträge aus
    `baluhost-deploy-sudoers` (jetzt fünf statt vier Units).
```

- [ ] **Step 4: API-Liste ergänzen**

In `.claude/rules/architecture.md`, unter „API Structure":

```markdown
- `/api/system/restart-all` - Sammelneustart aller BaluHost-Units (Admin, lokales Netz **und** Step-up, keine API-Keys — siehe `security-agent.md`)
```

- [ ] **Step 5: Kommentar in der Tray-Unit nachziehen**

In `deploy/install/templates/baluhost-tray.service`:

```
# Kein root, keine Rechteerweiterung. Der Neustart-Notweg laeuft ueber
# systemd/polkit — systemctl eskaliert nichts im eigenen Prozess, deshalb
# bleibt NoNewPrivileges hier richtig.
NoNewPrivileges=yes
```

`backend/tests/tray/test_unit_template.py` parst nur Direktiven, Kommentare
fallen weg — die Änderung bricht nichts. Trotzdem laufen lassen.

- [ ] **Step 6: Prüfen, dass keine dritte Stelle die alte Zusage wiederholt**

Run:
```bash
cd /home/sven/projects/BaluHost && python3 - <<'PY'
import os, re
pat = re.compile(r"fasst nichts Privilegiertes an|keine Service-Steuerung|"
                 r"keinen ausgehenden Pfad|es bedient nicht|liest nur")
for dp, dn, fn in os.walk("."):
    dn[:] = [d for d in dn if d not in {".git", "node_modules", "__pycache__", "worktrees"}]
    for f in fn:
        if not f.endswith((".md", ".py", ".service")):
            continue
        p = os.path.join(dp, f)
        for i, line in enumerate(open(p, errors="ignore"), 1):
            if pat.search(line):
                print(f"{p}:{i}: {line.strip()[:110]}")
PY
```

Erwartet: nur Treffer in den beiden nun als überholt markierten Absätzen des
Entwurfs vom 2026-09-21 und im aktualisierten Unit-Kommentar. `.claude/worktrees/`
ist ausgeschlossen, sonst kommt jeder Treffer fünffach.

- [ ] **Step 7: Tests laufen lassen**

Run: `cd backend && ./.venv/bin/python -m pytest tests/tray/ -v`
Erwartet: PASS

- [ ] **Step 8: Commit**

```bash
git add docs/ .claude/rules/ deploy/install/templates/baluhost-tray.service
git commit -m "docs(tray): Dienste-Neustart in Doku und Regeln nachziehen

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Abschluss

- [ ] **Gesamtlauf:** `cd backend && ./.venv/bin/python -m pytest -q`
      Erwartet: 2 failed (die vorbestehenden in `tests/plugins/sandbox/test_phase3_e2e.py`), sonst grün.
- [ ] **Qt-Rauchtest mit dem Interpreter, der PyQt6 hat:**
      `cd backend && QT_QPA_PLATFORM=offscreen python3 -m pytest tests/tray/ -o addopts="" -p no:cacheprovider -q`
- [ ] **Manuelle Probe auf BaluNode** (erst nach dem Deploy, und der Deploy muss
      die neue sudoers-Zeile mitbringen — `SYNC_PERMISSIONS=1`, sonst scheitert
      der Neustart von `baluhost-backend-local` mit `sudo: no entry`):
  1. `baluhost-tray` neu starten, Menüpunkt „BaluHost neu starten…" ist da.
  2. Normalweg: Passwort eingeben → Erfolgsmeldung, Icon kurz grau, kommt zurück.
  3. Falsches Passwort → „Passwort bzw. 2FA-Code stimmt nicht.", erneute Abfrage.
  4. Notweg: `sudo systemctl stop baluhost-backend`, dann Menüpunkt → Bestätigung
     → **ein** KDE-Passwortdialog → `systemctl status 'baluhost-*'` zeigt alle
     fünf Units frisch gestartet.
  5. Im Journal nachsehen, dass die polkitd-Zeile den Nutzer nennt:
     `journalctl -t polkitd --since "-5 min"`.
- [ ] **Branch abschließen** mit superpowers:finishing-a-development-branch.
