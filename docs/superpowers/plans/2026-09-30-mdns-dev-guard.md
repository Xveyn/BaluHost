# mDNS Dev-Guard Implementation Plan (#678)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eine Dev-Instanz (`NAS_MODE=dev`) annonciert `baluhost.local` nicht mehr per mDNS, solange nicht ausdrücklich `MDNS_FORCE_ENABLED=true` gesetzt ist.

**Architecture:** Der Guard sitzt am Anfang von `NetworkDiscoveryService.start()` — nicht in `lifespan.py` und nicht in `start_dev.py`. Dann deckt er jeden Startweg ab (`start_dev.py`, direktes `uvicorn`, Tests), und `get_status()` meldet weiter ehrlich `is_running: false`, weil `self.zeroconf` `None` bleibt. Ein neues Setting `mdns_force_enabled` (Default `False`) erlaubt gezieltes Testen der Discovery im Dev-Mode.

**Tech Stack:** Python 3.11, zeroconf, pydantic-settings, pytest.

**Spec:** Issue #678 (https://github.com/Xveyn/BaluHost/issues/678), Fix-Vorschlag Variante 1. Kein separates Spec-Dokument — der Umfang ist ein Guard und ein Setting.

## Global Constraints

- Kein Verhalten in Produktion ändern: `NAS_MODE=prod` registriert exakt wie bisher.
- Setting-Name `mdns_force_enabled`, Env-Variable `MDNS_FORCE_ENABLED` (pydantic-settings ohne Prefix, wie `mdns_hostname`).
- Default `False`.
- `start()` bleibt exception-sicher: der Guard wirft nie.
- Nebenbefunde nicht mitfixen (siehe „Out of Scope").
- Commit-Nachrichten enden mit `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Branch: `fix/mdns-dev-guard-678`, Basis `main` (25977613). PR geht direkt nach `main`.

## Review Focus

- **`NAS_MODE=dev` ohne Flag:** kein `Zeroconf()`-Objekt, keine `register_service`-Aufrufe, `get_status()["is_running"] is False`. → Task 1.
- **`NAS_MODE=dev` mit `MDNS_FORCE_ENABLED=true`:** registriert alle drei Services wie in Prod. → Task 1.
- **`NAS_MODE=prod` mit `MDNS_FORCE_ENABLED=true`:** Flag ändert nichts, registriert weiterhin. → Task 1.
- **`stop()` nach übersprungenem `start()`:** darf nicht werfen (`self.zeroconf` ist `None`). → Task 1.
- **Env-Parsing:** `MDNS_FORCE_ENABLED=true` in der Umgebung ergibt `settings.mdns_force_enabled is True`; leer/ungesetzt ergibt `False`. → Task 2.

---

### Task 1: Guard in `NetworkDiscoveryService.start()`

**Files:**
- Modify: `backend/app/services/network_discovery.py:42-44` (Guard), `:115-119` (irreführender Kommentar/Log)
- Test: `backend/tests/services/test_network_discovery_dev_guard.py` (neu)

**Interfaces:**
- Consumes: `settings.is_dev_mode: bool` (existiert, `config.py:293` synchronisiert es mit `nas_mode`), `settings.mdns_force_enabled: bool` (entsteht in Task 2 — die Tests dieses Tasks ersetzen `settings` per Stub und brauchen es noch nicht).
- Produces: unverändert `NetworkDiscoveryService.start() -> None`; neues Verhalten: im Dev-Mode ohne Force kehrt `start()` sofort zurück, `self.zeroconf` bleibt `None`.

- [ ] **Step 1: Failing Tests schreiben**

`backend/tests/services/test_network_discovery_dev_guard.py`:

```python
"""Dev instances must not announce baluhost.local over mDNS (#678).

start_dev.py runs NAS_MODE=dev and the process becomes primary worker, so
without a guard every dev start on the LAN announces the production hostname.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import network_discovery as nd


def _settings(*, dev: bool, force: bool = False) -> SimpleNamespace:
    return SimpleNamespace(is_dev_mode=dev, mdns_force_enabled=force)


@pytest.fixture
def fake_zeroconf(monkeypatch):
    """Replace Zeroconf so no socket is ever opened, and pin the local IP."""
    zc_class = MagicMock(name="Zeroconf")
    monkeypatch.setattr(nd, "Zeroconf", zc_class)
    monkeypatch.setattr(nd.NetworkDiscoveryService, "get_local_ip", lambda self: "192.0.2.10")
    return zc_class


def test_dev_mode_does_not_register(monkeypatch, fake_zeroconf):
    monkeypatch.setattr(nd, "settings", _settings(dev=True))
    service = nd.NetworkDiscoveryService(hostname="baluhost")

    service.start()

    fake_zeroconf.assert_not_called()
    assert service.zeroconf is None
    assert service.get_status()["is_running"] is False


def test_dev_mode_with_force_registers_all_three_services(monkeypatch, fake_zeroconf):
    monkeypatch.setattr(nd, "settings", _settings(dev=True, force=True))
    service = nd.NetworkDiscoveryService(hostname="baluhost")

    service.start()

    fake_zeroconf.assert_called_once()
    assert fake_zeroconf.return_value.register_service.call_count == 3
    assert service.get_status()["is_running"] is True


def test_prod_mode_registers_all_three_services(monkeypatch, fake_zeroconf):
    monkeypatch.setattr(nd, "settings", _settings(dev=False))
    service = nd.NetworkDiscoveryService(hostname="baluhost")

    service.start()

    assert fake_zeroconf.return_value.register_service.call_count == 3


def test_prod_mode_ignores_the_force_flag(monkeypatch, fake_zeroconf):
    monkeypatch.setattr(nd, "settings", _settings(dev=False, force=True))
    service = nd.NetworkDiscoveryService(hostname="baluhost")

    service.start()

    assert fake_zeroconf.return_value.register_service.call_count == 3


def test_stop_after_skipped_start_is_a_noop(monkeypatch, fake_zeroconf):
    monkeypatch.setattr(nd, "settings", _settings(dev=True))
    service = nd.NetworkDiscoveryService(hostname="baluhost")
    service.start()

    service.stop()  # must not raise with zeroconf is None

    fake_zeroconf.assert_not_called()
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run (aus `backend/`): `python -m pytest tests/services/test_network_discovery_dev_guard.py -v`
Expected: `test_dev_mode_does_not_register` FAIL (`Zeroconf` wurde aufgerufen), `test_stop_after_skipped_start_is_a_noop` FAIL (`assert_not_called`); die drei übrigen PASS (sie beschreiben das heutige Verhalten und sichern es gegen Regression).

- [ ] **Step 3: Guard implementieren**

In `network_discovery.py` am Anfang von `start()` vor dem `try:` einfügen:

```python
    def start(self):
        """Start broadcasting the service via mDNS.

        In dev mode nothing is announced unless MDNS_FORCE_ENABLED is set: a dev
        instance would otherwise publish the same ``baluhost.local`` as the
        production box on the same LAN (#678).
        """
        if settings.is_dev_mode and not settings.mdns_force_enabled:
            logger.info("mDNS registration skipped (dev mode; set MDNS_FORCE_ENABLED=true to enable)")
            return

        try:
```

Den `except`-Zweig vereinfachen — der Dev-Sonderfall ist jetzt unerreichbar bzw. irreführend („expected in dev mode"). Ersetzen durch:

```python
        except Exception as e:
            logger.error(f"Failed to start mDNS service: {e}")
            logger.warning("Network discovery will not be available")
```

Hinweis: Wer im Dev-Mode mit Force startet und keine Netzwerkschnittstelle hat, bekommt jetzt bewusst einen `error` — er hat mDNS ausdrücklich verlangt.

- [ ] **Step 4: Tests laufen lassen**

Run: `python -m pytest tests/services/test_network_discovery_dev_guard.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/network_discovery.py backend/tests/services/test_network_discovery_dev_guard.py
git commit -m "fix(discovery): mDNS-Registrierung im Dev-Mode ueberspringen (#678)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Setting `mdns_force_enabled`, `.env.example`, Doku

**Files:**
- Modify: `backend/app/core/config.py:92-93`
- Modify: `backend/.env.example` (neuer Block am Ende)
- Modify: `backend/app/services/CLAUDE.md` (Zeile `network_discovery.py` in der Top-level-Tabelle)
- Test: `backend/tests/core/test_mdns_settings.py` (neu)

**Interfaces:**
- Consumes: nichts aus Task 1 zur Compile-Zeit.
- Produces: `Settings.mdns_force_enabled: bool = False` — das Attribut, das Task 1 liest.

- [ ] **Step 1: Failing Test schreiben**

`backend/tests/core/test_mdns_settings.py`:

```python
"""MDNS_FORCE_ENABLED is read from the environment like MDNS_HOSTNAME (#678)."""
import pytest

from app.core.config import Settings


def test_force_flag_defaults_to_false(monkeypatch):
    monkeypatch.delenv("MDNS_FORCE_ENABLED", raising=False)
    assert Settings().mdns_force_enabled is False


@pytest.mark.parametrize("raw", ["true", "1", "True"])
def test_force_flag_reads_env(monkeypatch, raw):
    monkeypatch.setenv("MDNS_FORCE_ENABLED", raw)
    assert Settings().mdns_force_enabled is True
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `python -m pytest tests/core/test_mdns_settings.py -v`
Expected: FAIL mit `AttributeError: 'Settings' object has no attribute 'mdns_force_enabled'`.

- [ ] **Step 3: Setting anlegen**

In `config.py` unter `mdns_hostname`:

```python
    mdns_force_enabled: bool = False  # env: MDNS_FORCE_ENABLED — announce over mDNS even in dev mode (default: dev stays silent, #678)
```

- [ ] **Step 4: Tests laufen lassen**

Run: `python -m pytest tests/core/test_mdns_settings.py tests/services/test_network_discovery_dev_guard.py -v`
Expected: 8 passed. Falls `Settings()` im Test wegen Prod-Validatoren scheitert (SECRET_KEY o. ä.), im Test `monkeypatch.setenv("NAS_MODE", "dev")` ergänzen — nicht die Validatoren anfassen.

- [ ] **Step 5: `.env.example` und `services/CLAUDE.md` nachziehen**

Ans Ende von `backend/.env.example`:

```
# mDNS/Bonjour — a dev instance (NAS_MODE=dev) announces nothing by default, so it
# cannot shadow the production hostname on the same LAN (#678). Set to `true` only
# to test discovery itself, and pick a distinct MDNS_HOSTNAME when you do.
MDNS_FORCE_ENABLED=false
```

In `backend/app/services/CLAUDE.md` die Zeile `network_discovery.py` ersetzen durch:

```
| `network_discovery.py` | mDNS/Bonjour local network discovery. Skipped in dev mode unless `MDNS_FORCE_ENABLED=true` (#678) — a dev instance would otherwise announce the production hostname |
```

- [ ] **Step 6: Gesamtlauf und Commit**

Run: `python -m pytest tests/services/test_network_discovery_dev_guard.py tests/core/test_mdns_settings.py -v` und `ruff check app/services/network_discovery.py app/core/config.py` (CI erzwingt ruff, #184).
Expected: 8 passed, ruff ohne Befund.

```bash
git add backend/app/core/config.py backend/.env.example backend/app/services/CLAUDE.md backend/tests/core/test_mdns_settings.py
git commit -m "feat(config): MDNS_FORCE_ENABLED fuer mDNS im Dev-Mode (#678)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Verifikation und PR

**Files:** keine Änderungen.

- [ ] **Step 1: Betroffene Test-Gruppen laufen lassen**

Run: `python -m pytest tests/services tests/core -q`
Expected: keine neuen Fehler gegenüber `main`. Falls etwas rot ist, zuerst auf `main` gegenprüfen (`git stash; git checkout main; …`), bevor es dieser Änderung zugeschrieben wird.

- [ ] **Step 2: Handprobe im Dev-Start** (nur auf einer Box **ohne** laufende Produktion oder nach Klärung des `pkill`-Nebenbefunds — siehe unten)

Run: `python start_dev.py`, im Log nach `mDNS registration skipped (dev mode` suchen; parallel `avahi-browse -art | head` zeigt keinen zweiten `_baluhost._tcp`-Eintrag. Danach mit `MDNS_FORCE_ENABLED=true` gegenprüfen, dass `mDNS service started:` erscheint.

- [ ] **Step 3: Push und PR nach `main`**

```bash
git push -u origin fix/mdns-dev-guard-678
gh pr create --base main --title "fix(discovery): mDNS im Dev-Mode nicht annoncieren (#678)" --body "$(cat <<'EOF'
Fixes #678.

- `NetworkDiscoveryService.start()` kehrt im Dev-Mode sofort zurück, sofern nicht `MDNS_FORCE_ENABLED=true` gesetzt ist.
- Neues Setting `mdns_force_enabled` (Default `false`), dokumentiert in `.env.example` und `services/CLAUDE.md`.
- Der irreführende „expected in dev mode"-Zweig im `except` entfällt.
- Prod-Verhalten unverändert (Test deckt das ab).

Nicht Teil dieses PR: annoncierter Port (`settings.port` statt tatsächlichem Listen-Port).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Nach dem Merge: Worktree/Branch aufräumen (`git branch -d fix/mdns-dev-guard-678`), siehe `production.md`.

---

## Out of Scope (bewusst nicht in diesem PR)

- **`start_dev.py:360-362` killt Produktionsprozesse** (`pkill -f uvicorn|scheduler_worker|monitoring_worker|…` ohne Nutzer-/Pfadbindung). Eigener Befund → eigenes Issue, sobald freigegeben.
- **Annoncierter Port** (`settings.port` statt tatsächlichem Listen-Port, Issue-Absatz 3): betrifft nur Dev mit Force, eigener Fix.
- **Alternativer Hostname im Dev** (`baluhost-dev.local`): nur relevant, wenn Force-Betrieb Alltag wird.

## Self-Review

- **Spec-Abdeckung:** Guard (Task 1), Override-Schalter (Task 2), irreführender Kommentar (Task 1 Step 3), Tests für alle vier Modus-Kombinationen plus `stop()` (Task 1), Env-Parsing (Task 2). Der Port-Punkt und der Hostname-Alternativvorschlag sind bewusst ausgeklammert.
- **Platzhalter:** keine.
- **Typkonsistenz:** `mdns_force_enabled` heißt in Config, Guard, Test-Stub und `.env.example` (`MDNS_FORCE_ENABLED`) gleich.
