# CPU Power Authority — Durchgesetzter Cap mit Allowlist-Boost

**Datum:** 2026-05-30
**Status:** Design / Spec
**Branch:** `feat/cpu-power-authority`

---

## 1. Problem & Root Cause

In *System Control → Hardware → Energy* setzen Presets pro Service-Intensität CPU-Taktwerte
(z. B. IDLE = 400 MHz). In der Praxis taktet die CPU jedoch deutlich höher, und externe
Prozesse überschreiben die Logik.

**Belegte Root Cause (Code-Untersuchung):**

1. **Write-once, kein Re-Assert.** `PowerManagerService._apply_profile_internal`
   (`backend/app/services/power/manager.py:625-626`) bricht sofort ab, wenn das logische
   Profil sich nicht ändert:
   ```python
   if profile == self._current_profile:
       return True, None   # kein Hardware-Write
   ```
   Der 5-s-`_monitor_loop` ruft nur diese Methode auf → `scaling_max_freq` wird **genau
   einmal** beim Profilwechsel geschrieben und danach nie wieder durchgesetzt.

2. **Keine Drift-Erkennung.** Schreibt ein externer Akteur in
   `/sys/.../cpufreq/scaling_*`, gewinnt er dauerhaft. BaluHosts `_current_profile` bleibt
   auf IDLE; die UI zeigt weiter „400 MHz".

3. **Kein Read-back.** `LinuxCpuPowerBackend._write_sysfs` wertet einen Write als Erfolg,
   sobald `open().write()` nicht wirft — der Kernel kann den Wert aber clampen/ignorieren.

4. **Anzeige zeigt Soll statt Ist.** `get_power_status` (`manager.py:913-916`) leitet den
   angezeigten `freq_range` aus `self._profiles` (Default-Profile) ab, nicht aus dem
   aktiven Preset und nicht aus der Hardware.

**Externer Überschreiber (auf der Prod-Box BaluNode bestätigt):**

```
scaling_driver        = amd-pstate-epp   (status: active)
verfügbare governors  = performance powersave        # kein schedutil
scaling_governor      = performance                  # von PPD gesetzt
scaling_max (alle CPUs) = 4668000 = cpuinfo_max       # KEIN Cap aktiv
scaling_cur           = 3955761  (~3,96 GHz idle)
power-profiles-daemon = active   (powerprofilesctl get → performance)
cgroup.controllers    = … cpu …  (cgroup v2)
boost                 = 1
```

→ `power-profiles-daemon` (von KDE PowerDevil gesteuert) hält den Governor auf
`performance`, niemand setzt `scaling_max_freq`. Die CPU läuft idle bei ~3,96 GHz, während
die UI „400 MHz" anzeigt. Symptom vollständig erklärt.

Weil der Treiber `amd-pstate-epp` im **active**-Modus läuft (nur `performance`/`powersave`,
kein `schedutil`), ist echte **pro-Prozess-Frequenz via uclamp nicht möglich** ohne
Treiber-Umbau. Deshalb der Allowlist-Presence-Ansatz statt uclamp.

---

## 2. Ziel & Nicht-Ziele

**Ziel:** BaluHost wird **alleinige Autorität** über den CPU-Takt der BaluNode. Der
konfigurierte Cap wird *durchgesetzt* (Re-Assert + Drift-Korrektur). Ein global gehaltener
Cap wird **angehoben, sobald ein Allowlist-Programm bzw. eine Spielsitzung läuft**, und
danach wieder gesenkt.

**Nicht-Ziele:**
- Keine echte pro-Prozess-Frequenz (uclamp) — Hardware/Treiber gibt das nicht her.
- Keine cgroup-Drosselung (Option B) in dieser Iteration.
- Keine Änderung am globalen `boost`-Flag.
- Kein Remote-Zugriff auf die sensiblen Steuerungen (nur lokale Tauri-Schiene).

---

## 3. Getroffene Entscheidungen

| Thema | Entscheidung |
|---|---|
| Verhalten | **C** — globaler Cap durchgesetzt, Anwesenheit eines Allowlist-Programms hebt ihn. |
| Hoheit | **① Volle Hoheit** — `power-profiles-daemon` wird gestoppt + `mask`ed; BaluHost steuert Governor/EPP/Cap allein. |
| Privileg-Weg | **(i) Eng begrenzte sudoers-Regel** (NOPASSWD, exakte Args) für `power-profiles-daemon`. |
| Lokal-only | Alle mutierenden Endpoints via `Depends(deps.require_local_admin)` (bestehende Tauri/UDS-Schiene). |
| Allowlist | **Spielsitzungs-Erkennung** (Wrapper-Prozesse) + explizite Prozess-Globs + manueller „Boost jetzt". |
| Integration | Wiederverwendung des bestehenden **Demand-Systems** (`register_demand`/`unregister_demand`, „höchste Anforderung gewinnt"). |

---

## 4. Architektur & Komponenten

Fünf Bausteine, integriert in den bestehenden `PowerManagerService` und sein Demand-System.

### 4.1 CPU-Enforcement-Loop (Root-Cause-Fix)

Läuft in einem **eigenen 2-s-Tick** (`_enforcement_loop`, primary-only) gemeinsam mit dem
Game-Session-Watcher. Der bestehende `_monitor_loop` (5 s) bleibt unverändert für
Demand-Expiry / Auto-Scaling / SHM-Write. Pro 2-s-Tick **wenn das Feature aktiv ist**:

1. Soll-Config des aktuellen Profils ermitteln (aus Preset, wie heute via
   `_get_profile_config_from_preset`, Fallback `_profiles`). **Der Halten-Cap kommt immer
   aus dem aktiven Preset** (Wert der aktuellen Service-Property), mit hartem **400-MHz-Floor**
   (`scaling_max = max(preset_clock, 400)`). Ändert sich das aktive Preset, übernimmt der
   nächste Tick den neuen Cap automatisch — kein separater `idle_cap`-Wert wird gehalten.
2. Pro Kern `scaling_governor` + `scaling_max_freq` zurücklesen (`_read_sysfs`).
3. Bei Abweichung vom Soll: **neu schreiben** (Governor, EPP, `scaling_min`, `scaling_max`)
   und **WARNING loggen** inkl. des extern vorgefundenen Werts (Drift sichtbar machen).
4. Letztes Drift-Ereignis im Service-State halten → für UI-Badge & Status.

Der `profile == self._current_profile`-Shortcut in `_apply_profile_internal` bleibt für die
*logische* Profilumschaltung bestehen; das Re-Assert läuft über einen **neuen, separaten
Pfad** (`_enforce_current_profile()`), der direkt `backend.apply_profile(config)` aufruft
und den Shortcut nicht durchläuft. Damit bleibt die History/Logging-Logik der
Profilwechsel unberührt, und das Re-Assert erzeugt keine Profilwechsel-Logs.

**Read-back-Verifikation:** Nach jedem Enforce-Write optional ein Verifikations-Read; bei
weiterhin abweichendem Wert (Kernel-Clamp) wird das als eigener Statuszustand
(`cap_unenforceable`) geführt statt endlos zu schreiben.

### 4.2 PPD-Ownership

Neuer kleiner Service `ppd_authority.py` (in `services/power/`):

- `acquire()` — Vorzustand erfassen (`systemctl is-enabled/is-active power-profiles-daemon`),
  dann `sudo -n systemctl stop power-profiles-daemon` + `sudo -n systemctl mask power-profiles-daemon`.
  Vorzustand in der Power-Config persistieren.
- `release()` — `sudo -n systemctl unmask power-profiles-daemon` und, falls vorher aktiv,
  `start`. Stellt den ursprünglichen Zustand wieder her.
- `status()` — aktueller Mask-/Active-Zustand für UI/Status.

Aufgerufen beim Setzen von `external_authority_enabled` true/false über den lokalen Endpoint.
Alle `subprocess.run`-Aufrufe mit **expliziten Argumentlisten**, kein `shell=True`.

### 4.3 Game-Session-Watcher

Im **eigenen 2-s-Tick** (zusammen mit 4.1), psutil-basiert:

- **`process_glob`-Regeln:** `fnmatch.fnmatchcase(name.lower(), pattern.lower())` gegen
  `proc.name()`/`comm`. Wegen der 15-Zeichen-`comm`-Kürzung zusätzlich Prefix-Match.
- **`game_session`-Regel (eingebaut):** Treffer, wenn ein Wrapper-Prozess läuft:
  - `reaper` mit `SteamLaunch` in `cmdline`, **oder**
  - `pressure-vessel` / `pv-bwrap` / `proton` / `wine`,`wine64`,`wineserver`,`wine64-preloader`.
  - Diese existieren **nur während aktiven Spielens** → Steam-im-Tray triggert nicht.
    Deckt nebenbei Lutris/Heroic-Proton ab.
- **Hysterese:** Demand wird registriert beim ersten Treffer; **freigegeben erst, wenn der
  Trigger 2 aufeinanderfolgende Ticks weg ist** (Anti-Flacker). Zusätzlich greift der
  bestehende `cooldown_seconds`-Mechanismus beim Runterstufen.
- **Pro-Regel-Ziel:** Jede Regel hat ein eigenes `target_max_mhz` (null = voller Boost =
  `cpuinfo_max`). Matchen mehrere Regeln gleichzeitig, gilt das **höchste** Ziel (null
  schlägt alles, da voller Boost). Dieses effektive Ziel wird als `max_freq`-Override mit dem
  Demand mitgeführt.
- Bei Treffer → `register_demand("game-session", PowerProfile.SURGE, max_freq_override=<eff. target>,
  description=<rule label>)`; bei Wegfall → `unregister_demand("game-session")`. Der Manager
  wendet eine SURGE-Config an, deren `scaling_max` = effektives Ziel ist (statt fix `cpuinfo_max`).

### 4.4 Allowlist + Feature-Config

**Neue Tabelle `power_boost_rules`:**

| Spalte | Typ | Beschreibung |
|---|---|---|
| `id` | int PK | |
| `kind` | str | `process_glob` \| `game_session` |
| `pattern` | str nullable | nur bei `process_glob` (z. B. `lutris*`, `*.x86_64`) |
| `label` | str | Anzeigename |
| `target_max_mhz` | int nullable | Boost-Ziel dieser Regel; **null = voller Boost** (`cpuinfo_max`) |
| `enabled` | bool | |
| `created_at` | datetime | |

Seed: eine `game_session`-Regel (enabled, `target_max_mhz=null`, Label „Steam/Proton-Spielsitzung").

**Feature-Config** (in bestehender Power-Runtime-State/-Config, `config_store.py`):
- `external_authority_enabled: bool` — PPD gemaskt, BaluHost = alleinige Autorität.
- `boost_rules_enabled: bool` — Allowlist-Watcher aktiv.

Der **Halten-Cap** ist *kein* eigener Config-Wert, sondern wird pro Tick aus dem aktiven
Preset abgeleitet (Floor 400 MHz, siehe 4.1).

### 4.5 UI (System Control → Hardware → Energy)

- **Live-Frequenz** prominent: `scaling_cur_freq` (aus `get_current_frequency_mhz`) statt
  Soll-Fiktion.
- **`freq_range`-Fix:** aus dem **aktiven Preset** ableiten statt aus `_profiles`
  (heutiger Anzeige-Bug).
- **Drift-/Override-Badge:** zeigt letztes Drift-Ereignis bzw. `cap_unenforceable`.
- **Authority-Schalter:** „BaluHost steuert CPU allein (PPD stilllegen)" — lokal-only.
- **Allowlist-Editor:** CRUD der Regeln; bei `channel=remote` ausgegraut mit Companion-Hinweis
  (`useChannelStatus`-Hook existiert).
- **„Boost jetzt"-Override:** registriert `manual-boost`-Demand mit wählbarer Dauer.

---

## 5. Datenfluss

```
Watcher erkennt Spiel/Allowlist-Prozess (2-s-Tick)
   → register_demand("game-session", SURGE, max_freq_override=eff. Regel-Ziel)
      → Manager: highest demand = SURGE
         → backend.apply_profile(governor=performance, EPP=performance, max=eff. Ziel|cpuinfo_max)
Spiel endet (2 Ticks weg)
   → unregister_demand("game-session")
      → Manager: highest demand = IDLE
         → backend.apply_profile(governor=powersave, EPP=power, max=max(preset_clock,400))
Jeder 2-s-Tick (Feature aktiv)
   → _enforce_current_profile(): read-back governor+max; bei Drift → re-write + WARNING
```

---

## 6. Cap-Enforcement-Werte (amd-pstate-epp, active)

| Zustand | governor | EPP | scaling_min | scaling_max | boost |
|---|---|---|---|---|---|
| Halten (idle/low/medium) | `powersave` | `power` | ≈ Cap·0,85 | `max(preset_clock, 400)` | unverändert (1) |
| Heben (SURGE/Spiel) | `performance` | `performance` | hoch | effektives Regel-Ziel (null → `cpuinfo_max`) | unverändert (1) |

Governor/EPP-Werte stammen aus den **bestehenden** Presets (`get_governor_for_property`,
`get_epp_for_property`). Der **Halten-Cap** = Wert des aktiven Presets für die aktuelle
Property, hart auf 400 MHz gefloort; folgt Preset-Änderungen pro 2-s-Tick. Der **Heben-Cap**
= effektives Ziel der matchenden Boost-Regel(n). Das globale `boost`-Flag wird nicht
angefasst — `scaling_max` unter dem Boost-Bereich deckelt ohnehin, `boost=0` wäre ein
systemweiter Nebeneffekt.

---

## 7. API-Endpoints (alle mutierenden → `require_local_admin`)

| Methode | Pfad | Gate | Zweck |
|---|---|---|---|
| GET | `/api/power/authority` | admin | Authority-/PPD-/Drift-Status |
| PUT | `/api/power/authority` | **local** | `external_authority_enabled` setzen → PPD acquire/release |
| GET | `/api/power/boost-rules` | admin | Regeln listen |
| POST | `/api/power/boost-rules` | **local** | Regel anlegen |
| PUT | `/api/power/boost-rules/{id}` | **local** | Regel ändern/aktivieren |
| DELETE | `/api/power/boost-rules/{id}` | **local** | Regel löschen |
| POST | `/api/power/boost-now` | **local** | manueller Boost-Demand mit Dauer |

Alle mit Pydantic-Schemas (kein raw `dict`), `@user_limiter.limit(get_limit("admin_operations"))`,
und Audit-Logging via `get_audit_logger_db()` für Authority-Toggle und Regeländerungen.

---

## 8. Privileg-Modell (sudoers)

Erweiterung der bestehenden sudoers-Vorlage unter `deploy/install/templates/`. Neue,
exakt gescopte Zeilen für den `baluhost`-User (NOPASSWD, feste Args, keine Globs):

```
baluhost ALL=(root) NOPASSWD: /usr/bin/systemctl stop power-profiles-daemon
baluhost ALL=(root) NOPASSWD: /usr/bin/systemctl start power-profiles-daemon
baluhost ALL=(root) NOPASSWD: /usr/bin/systemctl mask power-profiles-daemon
baluhost ALL=(root) NOPASSWD: /usr/bin/systemctl unmask power-profiles-daemon
```

Die cpufreq-Writes (Governor/EPP/`scaling_*`) laufen über das **bestehende** Modell
(`cpufreq`-Gruppe bzw. `sudo -n tee`, siehe `LinuxCpuPowerBackend._check_sudo_available`).
Keine neue Schreib-Berechtigung über das schon Vorhandene hinaus nötig.

---

## 9. Security-Quervergleich (`.claude/rules/security-agent.md`)

- **NEVER** eingehalten: kein `shell=True` (subprocess mit Arg-Listen), keine raw SQL
  (ORM), keine Secrets geloggt, kein Auth-Bypass.
- **ALWAYS** erfüllt: neue Endpoints mit Auth-Dependency (`get_current_admin`-Kette bzw.
  `require_local_admin`), Rate-Limit, Pydantic-Schemas, Audit-Logging.
- Neue sudoers-Zeilen sind auf **vier feste Befehle mit exakten Args** begrenzt (Reviewer-
  Checklist `ci-cd-security.md`: keine `ALL`, keine user-kontrollierten Globs).
- PPD-Mask/Unmask berührt keine produktiven Secrets/Pfade.

---

## 10. Tests

- **Enforcement:** Mock-Backend liefert beim Read-back einen abweichenden Governor/max →
  erwartet Re-Write + WARNING; kein Re-Write wenn Soll == Ist (kein Write-Spam).
- **`cap_unenforceable`:** Read-back bleibt nach Write abweichend → Statuszustand gesetzt,
  kein Endlos-Schreiben.
- **Spielerkennung:** Fake-Prozesslisten (Steam-Tray ohne Wrapper → kein Demand; mit
  `reaper SteamLaunch` / `pressure-vessel` → Demand SURGE; Wegfall erst nach 2 Ticks).
- **PPD-Ownership:** `subprocess.run` gemockt → `stop`+`mask` mit exakten Args bei acquire,
  `unmask`(+`start`) bei release; Vorzustand korrekt restauriert.
- **Endpoints:** Allowlist-CRUD / Authority-Toggle / Boost-now über `remote_client` → 403
  `local_channel_required`; über lokalen Channel → 200.
- **Anzeige:** `get_power_status` liefert Live-Frequenz und `freq_range` aus aktivem Preset.

---

## 11. Risiken / Trade-offs

1. **KDEs Energieprofil-Schalter wird wirkungslos**, solange `external_authority_enabled`.
   Bewusst gewählt (Hoheit ①). `release()` stellt PPD vollständig wieder her.
2. **Spielsitzungs-Heuristik** kann exotische Launcher verpassen → manueller „Boost jetzt"
   als Fallback; explizite `process_glob`-Regeln für Sonderfälle.
3. **psutil-Scan alle 5 s** über alle Prozesse — auf der Box vernachlässigbar; bei Bedarf
   nur `name`/`cmdline` lesen, nicht den ganzen Prozessbaum materialisieren.
4. **sudoers-Erweiterung** vergrößert die Angriffsfläche minimal (vier feste systemctl-
   Befehle, nur für eine Unit). Akzeptiert, gescoped.
5. **Doppel-Backend (local/remote)**: Authority-/Boost-State liegt in DB/Config, also über
   beide Uvicorn-Prozesse konsistent. Der Enforcement-Loop läuft nur auf dem **primary**
   Worker (wie das bestehende Demand-Recalc).

---

## 12. Berührte Dateien (Erstschätzung)

**Neu:**
- `backend/app/services/power/ppd_authority.py`
- `backend/app/services/power/process_watcher.py` (Game-Session-Watcher)
- `backend/app/models/power.py` → `PowerBoostRule` (oder neue Migration)
- `backend/alembic/versions/<rev>_power_boost_rules.py`
- `backend/app/schemas/power.py` → Boost-Rule-/Authority-/Boost-now-Schemas
- Tests: `backend/tests/services/test_power_enforcement.py`,
  `test_process_watcher.py`, `test_ppd_authority.py`,
  `backend/tests/api/test_power_authority_routes.py`
- `deploy/install/templates/` → sudoers-Snippet-Erweiterung
- Frontend: Allowlist-Editor-Komponente, Authority-Schalter, Boost-now-Control

**Geändert:**
- `backend/app/services/power/manager.py` (Enforcement-Pfad `_enforce_current_profile`,
  Drift-State, Watcher-Anbindung)
- `backend/app/services/power/cpu_linux_backend.py` (Read-back-Helfer für Drift-Vergleich)
- `backend/app/services/power/config_store.py` (neue Config-Keys)
- `backend/app/services/power/presets.py` (falls EPP/Governor-Mapping erweitert wird)
- `backend/app/api/routes/power.py` (neue Endpoints)
- `backend/app/services/power/__init__.py` (Exporte)
- `client/src/pages/` bzw. `client/src/components/power/` (UI), i18n de/en
- `.claude/rules/ci-cd-security.md` (sudoers-Inventar), `.claude/rules/architecture.md`
  (Power-Tabellen: `power_boost_rules`)

---

## 13. Offene Punkte für die Implementierung

- Exakter Migrations-Stil (Modell in `models/power.py` + Alembic autogenerate).
- Genauer UI-Ort/Komponentenname (während Implementierung lokalisieren).
- Mechanik des `max_freq_override` am Demand: entweder neues optionales Feld am
  `PowerDemandInfo`/`power_demands`-Row, oder der Watcher hält das effektive Ziel im
  Service-State und der Manager liest es beim SURGE-Apply. Während Implementierung festlegen.

**Entschieden (vormals offen):**
- Tick = **2 s** (eigener Task, getrennt vom 5-s-`_monitor_loop`).
- Halten-Cap = **aktives Preset**, Floor **400 MHz**, kein eigener Config-Wert.
- Boost-Ziel **pro Regel** (`target_max_mhz`, null = voller Boost).
