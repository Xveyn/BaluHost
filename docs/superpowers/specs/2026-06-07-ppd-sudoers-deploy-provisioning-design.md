# PPD-Sudoers Deploy-Provisioning + Workaround-Cleanup

**Datum:** 2026-06-07
**Issue:** [#126](https://github.com/Xveyn/BaluHost/issues/126) — *deploy: PPD-sudoers automatisch ausspielen + %BALUHOST_USER%-Substitution fixen*
**Scope:** `deploy/` (CODEOWNERS-relevant, CI/CD-Security)

---

## Problem

Das CPU-Power-Authority-Feature (#123) braucht eine sudoers-Regel, damit der Backend-Service
`power-profiles-daemon` stoppen/maskieren darf (`backend/app/services/power/ppd_authority.py`).
Ohne sie → HTTP 500 beim Aktivieren (*"could not stop/mask power-profiles-daemon (check sudoers
provisioning)"*).

Beim Live-Schalten auf der BaluNode sind zwei Deploy-Lücken aufgefallen:

1. **Routine-Deploy spielt die Power-Sudoers-Vorlage nicht aus.** Die vier
   `power-profiles-daemon`-Zeilen stehen in `deploy/install/templates/sudoers-baluhost-power`,
   installiert werden sie aber nur vom Voll-Install-Modul
   `deploy/install/modules/13-power-helpers.sh`. `ci-deploy.sh` zieht das nicht nach — ein reiner
   Code-Deploy bekommt die Regel nie.

2. **`%BALUHOST_USER%` steht wörtlich in `/etc/sudoers.d/baluhost-power`** auf der BaluNode — die
   Datei ist funktionslos, auch die bestehende logind-Helper-Regel. Zusätzlich läuft der Service
   dort als **`sven`**, nicht `baluhost`.

### Korrektur zur Issue-Diagnose (To-Do #2)

Das Issue vermutet einen `process_template`/`%BALUHOST_USER%`-Substitutions-Bug. **Den gibt es im
Code nicht (mehr).** Befund:

- `process_template()` (`deploy/install/lib/common.sh:115`) ersetzt `@@KEY@@`-Tokens und funktioniert.
- Das aktuelle Template `sudoers-baluhost-power` nutzt korrekt `@@BALUHOST_USER@@`.
- Commit `b1cffc10` (*"fix(deploy): use @@BALUHOST_USER@@ token in power sudoers template"*) hat das
  Token bereits gefixt.

Das literale `%BALUHOST_USER%` auf der BaluNode ist eine **veraltete Datei von vor `b1cffc10`**, die
nie neu substituiert wurde (weil Lücke #1: ci-deploy zieht Modul 13 nicht nach). Es ist **kein**
Code-Change an `process_template` nötig — der neue Standalone-Installer rendert die Datei mit dem
echten Service-User neu und behebt damit beide Symptome.

---

## Lösung (Approach A)

Spiegelt das bereits etablierte Muster von `deploy/scripts/install-hardware-sudoers.sh` — ein
eigenständiger, idempotenter Sudoers-Installer, der von `ci-deploy.sh` im `SYNC_PERMISSIONS`-Block
aufgerufen wird.

### Verworfene Alternativen

- **B — Power-Regeln in `baluhost-hardware-sudoers` falten.** `/etc/sudoers.d/baluhost-power` ist
  bewusst getrennt und wird namentlich in `.claude/rules/ci-cd-security.md` (Known Gap #9) und
  `13-power-helpers.sh` referenziert. Bricht Konventionen.
- **C — `process_template` umbauen.** Basiert auf der oben widerlegten Fehldiagnose; kein
  Substitutions-Bug vorhanden.

---

## Komponenten

### 1. Neues Script: `deploy/scripts/install-power-sudoers.sh`

1:1-Adaption von `install-hardware-sudoers.sh`. Verhalten:

| Aspekt | Wert |
|---|---|
| `TEMPLATE` (default) | `/opt/baluhost/deploy/install/templates/sudoers-baluhost-power` |
| `TARGET` | `/etc/sudoers.d/baluhost-power` |
| `SERVICE` (default) | `baluhost-backend.service` |
| User-Ableitung | `BALUHOST_USER` override → `systemctl show -p User --value "$SERVICE"` → sonst Fehler `exit 1` |

Ablauf (Reihenfolge sicherheitsrelevant):

1. `require_root` (EUID-Check).
2. Template-Existenz prüfen.
3. Service-User ableiten (auf BaluNode automatisch `sven`).
4. `sed "s|@@BALUHOST_USER@@|$BALUHOST_USER|g"` → `mktemp` (trap-cleanup).
5. **`visudo -cf "$TMP"` VOR dem Ersetzen** — bei Fehler `exit 1`, Live-Datei unangetastet.
6. Timestamped Backup der bestehenden `$TARGET` (falls vorhanden).
7. `install -m 0440 -o root -g root "$TMP" "$TARGET"`; finaler `visudo -cf "$TARGET"`.
8. **Workaround-Cleanup — erst NACH erfolgreichem Schritt 7:** Falls
   `/etc/sudoers.d/baluhost-ppd` existiert → timestamped sichern (`.bak.<ts>`) + entfernen, mit
   Log-Hinweis. Die Reihenfolge garantiert, dass die gültigen Power-Regeln bereits live sind, bevor
   der Workaround verschwindet — keine Lücke ohne Regeln.

### 2. `deploy/scripts/ci-deploy.sh` — Power-Sudoers-Hook

Im `SYNC_PERMISSIONS`-Block an der Stelle *"Future permission scripts go here following the same
pattern"* (aktuell Z. 461), nach dem Hardware-Sudoers-Block, ein analoger Block:

```bash
# Power sudoers: power-profiles-daemon stop/start/mask/unmask + logind idle +
# sddm toggle grants. Renders @@BALUHOST_USER@@ from the running service user and
# validates with visudo before replacing the live file. This is the path by which
# sudoers-baluhost-power template changes reach an installed box, and it also
# clears the obsolete /etc/sudoers.d/baluhost-ppd workaround once superseded.
POWER_SUDOERS_SCRIPT="$INSTALL_DIR/deploy/scripts/install-power-sudoers.sh"
if [[ -f "$POWER_SUDOERS_SCRIPT" ]]; then
    log_info "Re-applying power sudoers..."
    if sudo bash "$POWER_SUDOERS_SCRIPT"; then
        log_info "Power sudoers sync OK."
    else
        log_warn "Power sudoers sync failed (non-fatal — deploy continues)."
    fi
else
    log_warn "Power sudoers script not found at $POWER_SUDOERS_SCRIPT (skipping)."
fi
```

- Nur unter `SYNC_PERMISSIONS=1` / `true` (wahrt die Invariante *"Routine-Deploy fasst `/etc` nie an"*).
- Kein env-var-Passing (wie der Hardware-Block); der Template-Default matcht den prod `INSTALL_DIR`.
- Fehler ist non-fatal (`log_warn`), bricht keinen gesunden Deploy ab.

### 3. `deploy/install/templates/baluhost-deploy-sudoers` — Whitelist

Zwei Zeilen nach dem Hardware-Block (aktuell Z. 19), beide bash-Pfade gepinnt:

```
@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /bin/bash /opt/baluhost/deploy/scripts/install-power-sudoers.sh
@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /usr/bin/bash /opt/baluhost/deploy/scripts/install-power-sudoers.sh
```

Gepinnter absoluter Pfad auf ein versioniertes Script → der Deploy-User kann kein beliebiges Script
als root ausführen, nur dieses. Erweitert den Blast-Radius nicht über das etablierte Muster hinaus.

---

## Security-Betrachtung (CI/CD)

- **CODEOWNERS:** Alle drei Änderungen liegen unter `/deploy/` → owner-tagged auf `@Xveyn`.
- **Reviewer-Checklist (`ci-cd-security.md`):** Kein neuer `runs-on: self-hosted`, kein neuer
  PR-/`pull_request_target`-Trigger, kein `DEPLOY_PAT`-Gebrauch, keine Workflow-Änderung. Die neue
  Sudoers-Whitelist-Zeile ist auf eine spezifische, versionierte Binary mit explizitem Pfad
  begrenzt — kein `ALL`, keine user-controlled Globs.
- **Known Gap #9 (`ci-cd-security.md`):** Bezieht sich auf genau diese vier
  `systemctl … power-profiles-daemon`-Verben. Dieses Design ändert die Verben nicht, sondern stellt
  nur ihre korrekte Provisionierung sicher. Doku bleibt gültig.

---

## Bootstrap & Verifikation (Live-Box, kein Repo-Change)

Die neuen Whitelist-Zeilen in `baluhost-deploy-sudoers` sind erst dann live, wenn
`/etc/sudoers.d/baluhost-deploy` neu gerendert wird (gleiche Bootstrap-Eigenheit, die Hardware
hatte). Einmalig auf BaluNode als root:

```bash
cd /opt/baluhost && git pull
sudo bash /opt/baluhost/deploy/scripts/install-deploy-sudoers.sh   # erneuert die Whitelist
SYNC_PERMISSIONS=1 ./deploy/scripts/ci-deploy.sh                    # spielt baluhost-power aus
```

Danach verifizieren (To-Do #3 aus dem Issue):

```bash
sudo cat /etc/sudoers.d/baluhost-power     # vier systemctl … power-profiles-daemon-Zeilen, User=sven
sudo visudo -cf /etc/sudoers.d/baluhost-power   # OK
test ! -e /etc/sudoers.d/baluhost-ppd && echo "workaround entfernt"
```

---

## Tests

Reine Shell/Deploy-Änderung, keine pytest-Abdeckung. Verifikation:

- `bash -n deploy/scripts/install-power-sudoers.sh` (Syntaxcheck).
- `bash -n deploy/scripts/ci-deploy.sh` (Syntaxcheck nach Edit).
- Manuelle Review der gepinnten Pfade in `baluhost-deploy-sudoers`.
- (Optional, falls vorhanden) `shellcheck` auf das neue Script.

---

## Out of Scope

- `process_template`-Änderungen (kein Bug, siehe Korrektur oben).
- Unconditional-Provisioning bei jedem Deploy (bewusst verworfen zugunsten der
  `SYNC_PERMISSIONS`-Invariante).
- Manuelles Entfernen von `baluhost-ppd` per Hand — übernimmt jetzt das Script.
