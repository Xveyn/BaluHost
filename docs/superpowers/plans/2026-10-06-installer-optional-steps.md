# Installer: optionale Schritte kippen die Installation nicht — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein Fehler in einem optionalen Installer-Schritt lässt die Installation durchlaufen (Warnung statt Abbruch); Kernmodule brechen weiter hart ab.

**Architecture:** `install.sh` bekommt eine Liste `OPTIONAL_MODULES` (13, 14), deren Fehlschlag gesammelt statt mit `break` quittiert wird. Modul 10 führt Kern (Units, `daemon-reload`, `enable`) vor den optionalen Blöcken aus; jeder optionale Block ist eine Funktion, in der **jedes** Kommando sich selbst absichert. `lib/features.sh` bekommt explizite `|| return 1`. Eine gemeinsame Funktion `install_sudoers_file` in `lib/common.sh` ersetzt vier kopierte Sudoers-Blöcke.

**Tech Stack:** Bash (`set -euo pipefail`), Debian 12/13, Bash-Testskripte unter `deploy/install/tests/` und `deploy/install/verify/`.

**Spec:** `docs/superpowers/specs/2026-10-06-installer-optional-steps-design.md`

## Global Constraints

- Arbeitsverzeichnis: Worktree `.claude/worktrees/installer-optional-683`, Branch `fix/installer-optional-steps-683`. Nicht auf `main` committen.
- Exit-Code von `install.sh` bei „fertig mit Warnungen" ist **0**. `failed` bleibt ausschließlich für Kernmodule.
- Einzelmodul-Modus (`--module`) gibt den Exit-Code des Moduls unverändert durch.
- Kernmodule (01–12) brechen bei Fehler weiter ab; ihr Verhalten darf nicht aufgeweicht werden. Modul 12: nur `baluhost-backend` ist Kern.
- **Errexit-Falle (#683):** Eine Funktion, die in einer `if`-Bedingung oder `||`-Liste aufgerufen wird, läuft mit ausgeschaltetem `errexit`. Jede solche Funktion muss jedes Kommando einzeln mit `|| return 1` (oder `|| { …; return 1; }`) absichern. Niemals `func || log_warn …` auf eine mehrteilige Funktion anwenden und sich auf `errexit` im Rumpf verlassen.
- Kein `shell=True`-Äquivalent: keine Nutzereingabe in Kommandostrings (hier nicht relevant, nur Sudoers-Templates mit festen Platzhaltern).
- `deploy/` ist CODEOWNERS-geschützt (`.github/CODEOWNERS`); Änderungen bleiben auf `deploy/install/` und `docs/`. Keine Änderungen an `.github/`, sudoers-**Templates** oder systemd-Unit-Templates.
- Commit-Trailer: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Nicht Teil dieser Arbeit: #780, #781, #782, Modul-04-Git-Soft-Fails, Health-Timeout, kosmetische Versionsausgaben in 05/06.
- Testlauf-Befehle (alle ohne Root): `bash deploy/install/tests/test-install-orchestration.sh`, `bash deploy/install/tests/test-install-helpers.sh`, `bash deploy/install/tests/test-module-structure.sh`, `bash deploy/install/verify/test-features.sh`.

## Review Focus

- **polkit nicht installiert** (`/etc/polkit-1/rules.d/` fehlt): Modul 10 darf nicht abbrechen, bevor `systemctl enable` lief → Task 4 (Reihenfolge-Test + Helper-Test mit fehlendem Zielverzeichnis).
- **`visudo -cf` lehnt die gerenderte Sudoers-Datei ab**: Datei wird gelöscht, Installation läuft weiter → Task 3 (Test 2).
- **Beide optionalen Module scheitern**: Exit 0, beide im Banner genannt → Task 1.
- **Kernmodul (11-nginx) scheitert**: wie bisher Abbruch, 12–14 laufen nicht → Task 1.
- **`apt-get install` in einem Feature scheitert, obwohl `run_feature` in einer `if`-Bedingung läuft**: Feature gilt als fehlgeschlagen; `_HW_SUDOERS_DONE` bleibt `false` → Task 2.
- **Leeres `warned_modules`-Array unter `set -u`** (sauberer Lauf): bestehender Test 1 (Exit 0) deckt das ab; er bleibt grün → Task 1.

---

## File Structure

- Modify `deploy/install/install.sh` — Registry `OPTIONAL_MODULES`, `is_optional_module()`, Schleife, Banner, `--list-modules`.
- Modify `deploy/install/lib/common.sh` — neue Funktion `install_sudoers_file`.
- Modify `deploy/install/lib/features.sh` — explizite Fehlerpropagation in `run_feature` / `install_hardware_sudoers_once`.
- Modify `deploy/install/modules/10-systemd-services.sh` — Umbau in Kern + optionale Funktionen.
- Modify `deploy/install/modules/12-start-services.sh` — nur Backend ist Kern.
- Modify `deploy/install/modules/13-power-helpers.sh` — Guards mit klaren Meldungen, nutzt `install_sudoers_file`.
- Modify `deploy/install/tests/test-install-orchestration.sh` — neue Fälle.
- Modify `deploy/install/verify/test-features.sh` — Errexit-Fälle (Abweichung von der Spec: kein neues `test-features-errexit.sh`, weil `test-features.sh` bereits Mock-Primitive und Hilfsfunktionen hat).
- Create `deploy/install/tests/test-install-helpers.sh` — Tests für `install_sudoers_file` und `process_template` bei fehlendem Zielverzeichnis.
- Create `deploy/install/tests/test-module-structure.sh` — statische Struktur-Tests (Syntax, Reihenfolge, keine harten Exits im optionalen Teil von Modul 10).

---

### Task 1: `install.sh` — optionale Module

**Files:**
- Modify: `deploy/install/tests/test-install-orchestration.sh` (neue Abschnitte vor „Guard: verify-install.sh", derzeit Zeile 205; Test 1 um eine Assertion ergänzen, Zeile ~116-120)
- Modify: `deploy/install/install.sh:29-44` (Registry), `:67-72` (`list_modules`), `:261-274` (Schleife), `:276-306` (Banner/Exit)

**Interfaces:**
- Produces: `OPTIONAL_MODULES` (readonly array), `is_optional_module <name>` (Rückgabe 0/1), Banner-Zeile `Installation Complete (warnings)`, Warnliste mit `sudo $0 --module <name>`.

- [ ] **Step 1: Failing tests schreiben**

In `deploy/install/tests/test-install-orchestration.sh`, direkt nach dem Block von Test 1 (nach der Zeile `fi` der Assertion „completion banner shown", vor `if grep -q "VERIFY-RAN"`), ergänzen:

```bash
if ! grep -q "Installation Complete (warnings)" <<<"$OUTPUT"; then
    pass "clean run shows no warnings banner"
else
    fail "clean run showed the warnings banner"
fi
```

Vor dem Abschnitt `# ─── Guard: verify-install.sh must not use ((var++))` einfügen:

```bash
# ─── Test 7: failing OPTIONAL module does not stop the run ──────────────────

make_sandbox
CONF="$SANDBOX/install.conf"
cat > "$SANDBOX/modules/13-power-helpers.sh" <<'EOF'
#!/bin/bash
set -euo pipefail
echo "MODULE-RAN: 13-power-helpers"
exit 1
EOF
OUTPUT=$(bash "$SANDBOX/install.sh" --non-interactive --config "$CONF" 2>&1)
RC=$?
if [[ $RC -eq 0 ]]; then pass "optional failure: run exits 0"; else fail "optional failure: run exited $RC"; fi
if grep -q "MODULE-RAN: 14-optional-features" <<<"$OUTPUT"; then
    pass "optional failure: later module still ran"
else
    fail "optional failure: later module skipped"
fi
if grep -q "VERIFY-RAN" <<<"$OUTPUT"; then
    pass "optional failure: verification still ran"
else
    fail "optional failure: verification skipped"
fi
if grep -q "Installation Complete (warnings)" <<<"$OUTPUT"; then
    pass "optional failure: warnings banner shown"
else
    fail "optional failure: warnings banner missing"
fi
if grep -q -- "--module 13-power-helpers" <<<"$OUTPUT"; then
    pass "optional failure: retry hint names the module"
else
    fail "optional failure: retry hint missing"
fi
if ! grep -q "Installation stopped" <<<"$OUTPUT"; then
    pass "optional failure: no 'Installation stopped'"
else
    fail "optional failure: reported as stopped"
fi
cleanup

# ─── Test 8: both optional modules fail ──────────────────────────────────────

make_sandbox
CONF="$SANDBOX/install.conf"
for mod in 13-power-helpers 14-optional-features; do
    cat > "$SANDBOX/modules/$mod.sh" <<EOF
#!/bin/bash
echo "MODULE-RAN: $mod"
exit 1
EOF
done
OUTPUT=$(bash "$SANDBOX/install.sh" --non-interactive --config "$CONF" 2>&1)
RC=$?
if [[ $RC -eq 0 ]]; then pass "two optional failures: run exits 0"; else fail "two optional failures: exited $RC"; fi
if grep -q -- "--module 13-power-helpers" <<<"$OUTPUT" && grep -q -- "--module 14-optional-features" <<<"$OUTPUT"; then
    pass "two optional failures: both modules listed"
else
    fail "two optional failures: list incomplete"
fi
cleanup

# ─── Test 9: failing CORE module (11-nginx) still stops the run ─────────────

make_sandbox
CONF="$SANDBOX/install.conf"
cat > "$SANDBOX/modules/11-nginx.sh" <<'EOF'
#!/bin/bash
echo "MODULE-RAN: 11-nginx"
exit 1
EOF
OUTPUT=$(bash "$SANDBOX/install.sh" --non-interactive --config "$CONF" 2>&1)
RC=$?
if [[ $RC -ne 0 ]]; then pass "core failure: run exits nonzero"; else fail "core failure: exited 0"; fi
if grep -q "Installation stopped at module: 11-nginx" <<<"$OUTPUT"; then
    pass "core failure: stop message shown"
else
    fail "core failure: stop message missing"
fi
for mod in 12-start-services 13-power-helpers 14-optional-features; do
    if ! grep -q "MODULE-RAN: $mod" <<<"$OUTPUT"; then
        pass "core failure: $mod skipped"
    else
        fail "core failure: $mod ran after core failure"
    fi
done
if ! grep -q "Installation Complete" <<<"$OUTPUT"; then
    pass "core failure: no completion banner"
else
    fail "core failure: completion banner shown"
fi
cleanup

# ─── Test 10: --module on an optional module propagates its exit code ───────

make_sandbox
CONF="$SANDBOX/install.conf"
cat > "$SANDBOX/modules/13-power-helpers.sh" <<'EOF'
#!/bin/bash
exit 3
EOF
bash "$SANDBOX/install.sh" --module 13-power-helpers --config "$CONF" >/dev/null 2>&1
RC=$?
if [[ $RC -eq 3 ]]; then
    pass "--module on optional module propagates exit code (3)"
else
    fail "--module on optional module exit code was $RC (expected 3)"
fi
cleanup

# ─── Test 11: --list-modules marks optional modules ─────────────────────────

make_sandbox
LIST=$(bash "$SANDBOX/install.sh" --list-modules 2>&1)
if grep -q "13-power-helpers (optional)" <<<"$LIST" && grep -q "14-optional-features (optional)" <<<"$LIST"; then
    pass "--list-modules marks optional modules"
else
    fail "--list-modules does not mark optional modules: $LIST"
fi
if ! grep -q "12-start-services (optional)" <<<"$LIST"; then
    pass "--list-modules does not mark core modules"
else
    fail "--list-modules marked a core module optional"
fi
cleanup
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag prüfen**

Run: `bash deploy/install/tests/test-install-orchestration.sh`
Expected: FAIL u. a. bei „optional failure: run exits 0" (bisher bricht `13` die Installation ab), „retry hint missing", „--list-modules does not mark optional modules". Bestehende Tests 1–6 bleiben PASS.

- [ ] **Step 3: Implementieren — Registry und Prädikat**

In `deploy/install/install.sh` direkt nach dem schließenden `)` von `MODULES` (Zeile 44) einfügen:

```bash

# Modules whose failure must not stop the installation. The core NAS is fully
# installed and started before these run (11-nginx and 12-start-services come
# first); a failure here is reported as a warning at the end instead of
# aborting the run. A module not listed here is core: its failure stops the run.
readonly -a OPTIONAL_MODULES=(
    "13-power-helpers"
    "14-optional-features"
)

is_optional_module() {
    local candidate="$1" mod
    for mod in "${OPTIONAL_MODULES[@]}"; do
        if [[ "$mod" == "$candidate" ]]; then
            return 0
        fi
    done
    return 1
}
```

`list_modules` ersetzen durch:

```bash
list_modules() {
    echo "Available modules:"
    for mod in "${MODULES[@]}"; do
        if is_optional_module "$mod"; then
            echo "  $mod (optional)"
        else
            echo "  $mod"
        fi
    done
}
```

- [ ] **Step 4: Implementieren — Schleife**

Den Block ab `# Run modules 02-14` ersetzen:

```bash
    # Run modules 02-14
    local failed=0
    local -a warned_modules=()
    for mod in "${MODULES[@]:1}"; do  # Skip 01-preflight (already ran)
        if ! run_module "$mod"; then
            if is_optional_module "$mod"; then
                log_warn "Optional module $mod failed — continuing; the core installation is unaffected."
                warned_modules+=("$mod")
                load_config
                continue
            fi
            failed=1
            log_error "Installation stopped at module: $mod"
            log_error "Fix the issue and re-run: sudo $0 --module $mod"
            log_error "Then resume full install: sudo $0"
            break
        fi
        # Re-load config so values a module persisted (POSTGRES_PASSWORD from
        # 06, secrets from 07) are exported to the next module.
        load_config
    done
```

- [ ] **Step 5: Implementieren — Banner**

Im Erfolgszweig (`if [[ $failed -eq 0 ]]; then`) den Banner-Block (die drei `echo`-Zeilen mit „Installation Complete!") ersetzen:

```bash
        echo ""
        if [[ ${#warned_modules[@]} -eq 0 ]]; then
            echo -e "${GREEN}${BOLD}╔══════════════════════════════════════╗${NC}"
            echo -e "${GREEN}${BOLD}║    Installation Complete!            ║${NC}"
            echo -e "${GREEN}${BOLD}╚══════════════════════════════════════╝${NC}"
        else
            echo -e "${YELLOW}${BOLD}╔══════════════════════════════════════╗${NC}"
            echo -e "${YELLOW}${BOLD}║   Installation Complete (warnings)   ║${NC}"
            echo -e "${YELLOW}${BOLD}╚══════════════════════════════════════╝${NC}"
            echo ""
            echo "  The core installation succeeded. These optional steps failed:"
            for mod in "${warned_modules[@]}"; do
                echo "    - $mod   (retry: sudo $0 --module $mod)"
            done
        fi
        echo ""
```

(Die direkt folgenden `echo "  Web Interface: …"`-Zeilen bleiben unverändert; die dortige leere `echo ""` davor entfällt, weil der neue Block mit `echo ""` endet. Den bisherigen einzelnen `echo ""` vor dem Banner entfernen, damit keine doppelte Leerzeile bleibt.)

- [ ] **Step 6: Tests laufen lassen**

Run: `bash deploy/install/tests/test-install-orchestration.sh`
Expected: alle PASS, letzte Zeile `Results: N passed, 0 failed`.

- [ ] **Step 7: Commit**

```bash
git add deploy/install/install.sh deploy/install/tests/test-install-orchestration.sh
git commit -m "fix(install): optionale Module (13, 14) stoppen die Installation nicht mehr (#683)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `lib/features.sh` — Fehler nicht verschlucken

**Files:**
- Modify: `deploy/install/verify/test-features.sh` (neue Sektion vor der Ergebniszusammenfassung am Dateiende; vorher die letzten Zeilen der Datei lesen)
- Modify: `deploy/install/lib/features.sh:92-98`, `:134-145`

**Interfaces:**
- Consumes: `_apt_install`, `_run_script` (Test-Seams, in `test-features.sh` überschrieben), `reset()` (setzt `_HW_SUDOERS_DONE=false`).
- Produces: `run_feature` liefert ≠ 0, wenn `_apt_install` oder `feature_setup` scheitert — **auch wenn der Aufrufer es in einer `if`-Bedingung aufruft**; `install_hardware_sudoers_once` setzt `_HW_SUDOERS_DONE=true` nur bei Erfolg.

- [ ] **Step 1: Failing tests schreiben**

Zuerst `tail -20 deploy/install/verify/test-features.sh` lesen, um die Ergebniszeilen zu finden. Vor der Zusammenfassung (vor dem Block, der `PASS`/`FAILED` ausgibt) einfügen:

```bash
echo "== run_feature under 'if' (errexit off): failures must propagate =="
# The caller (module 14) runs `if run_feature "$key"` — errexit is OFF inside the
# whole function body. A failing apt install or setup script must still make
# run_feature return non-zero (#683 trap).
reset
_apt_install() { echo "apt:$*" >>"$MOCK_LOG"; return 1; }
if run_feature RAID; then bad "RAID counted as OK although apt install failed"; else ok "failed apt install fails the feature"; fi
_apt_install() { echo "apt:$*" >>"$MOCK_LOG"; }

reset
_run_script() { echo "script:$1" >>"$MOCK_LOG"; return 1; }
if run_feature VPN; then bad "VPN counted as OK although setup script failed"; else ok "failed setup script fails the feature"; fi

reset
if run_feature RAID; then bad "RAID counted as OK although hardware sudoers script failed"; else ok "failed hardware sudoers fails RAID"; fi
[[ "$_HW_SUDOERS_DONE" == "false" ]] && ok "hardware sudoers not marked done after failure" || bad "hardware sudoers marked done despite failure"
# A second feature must retry instead of trusting the failed attempt.
: >"$MOCK_LOG"
run_feature SMART >/dev/null 2>&1 || true
[[ "$(logcount 'install-hardware-sudoers.sh')" == "1" ]] && ok "SMART retries hardware sudoers after RAID failure" || bad "SMART did not retry hardware sudoers"
_run_script()  { echo "script:$1 SERVICE_USER=${SERVICE_USER:-} STORAGE_GROUP=${STORAGE_GROUP:-} ARG1=${2:-}" >>"$MOCK_LOG"; }
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `bash deploy/install/verify/test-features.sh`
Expected: BAD bei „RAID counted as OK although apt install failed" (heute wird `_apt_install` im `if`-Kontext ignoriert) und bei „hardware sudoers marked done despite failure".

- [ ] **Step 3: Implementieren**

In `deploy/install/lib/features.sh`:

```bash
install_hardware_sudoers_once() {
    [[ "$_HW_SUDOERS_DONE" == "true" ]] && return 0
    # Explicit `|| return 1`: callers run this inside `if`, where errexit is off.
    BALUHOST_USER="$BALUHOST_USER" \
    TEMPLATE="$FEATURES_DEPLOY_DIR/install/templates/baluhost-hardware-sudoers" \
        _run_script "$FEATURES_DEPLOY_DIR/scripts/install-hardware-sudoers.sh" || return 1
    _HW_SUDOERS_DONE=true
}
```

```bash
# Install + configure one feature. Returns non-zero if any step fails.
# Callers run this as `if run_feature …`, which switches errexit OFF for the
# whole body — so every step propagates its failure explicitly.
run_feature() {
    local key="$1"
    feature_precheck "$key" || true
    local pkgs
    pkgs="$(feature_packages "$key")"
    if [[ -n "$pkgs" ]]; then
        log_info "Installing packages: $pkgs"
        # shellcheck disable=SC2086
        _apt_install $pkgs || return 1
    fi
    feature_setup "$key" || return 1
}
```

Zusätzlich in `feature_setup` den `SAMBA|NFS`-Zweig prüfen: die Subshell `( … _run_script … )` ist letztes Kommando des Zweigs, ihr Status wird propagiert — keine Änderung nötig.

- [ ] **Step 4: Tests laufen lassen**

Run: `bash deploy/install/verify/test-features.sh`
Expected: keine `BAD`-Zeilen, bestehende Cases weiterhin `ok`.

- [ ] **Step 5: Commit**

```bash
git add deploy/install/lib/features.sh deploy/install/verify/test-features.sh
git commit -m "fix(install): run_feature verschluckt Fehler nicht mehr unter if-Kontext (#683)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `install_sudoers_file` in `lib/common.sh`

**Files:**
- Create: `deploy/install/tests/test-install-helpers.sh`
- Modify: `deploy/install/lib/common.sh` (nach `process_template`, Zeile ~149)

**Interfaces:**
- Consumes: `process_template <template> <output> KEY=VAL…`, `log_info/log_warn/log_error`.
- Produces: `install_sudoers_file <template> <dest> [KEY=VAL…]` → Rückgabe 0 bei Erfolg **oder** fehlender Vorlage (Warnung, überspringen); Rückgabe 1 bei Schreib-, `chmod`- oder `visudo`-Fehler (die Zieldatei wird dann entfernt). Jedes Kommando intern abgesichert — sicher in `if`-Kontext.

- [ ] **Step 1: Failing tests schreiben**

`deploy/install/tests/test-install-helpers.sh` anlegen:

```bash
#!/bin/bash
# Tests for lib/common.sh helpers used by the installer modules (issue #683):
# install_sudoers_file must be safe to call from an `if` condition (errexit is
# OFF there), so it has to propagate every failure itself.
#
# Usage: bash deploy/install/tests/test-install-helpers.sh
set -uo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_SRC="$(cd "$TESTS_DIR/.." && pwd)"

PASS=0
FAIL=0
pass() { echo "PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $*" >&2; FAIL=$((FAIL + 1)); }

source "$INSTALL_SRC/lib/common.sh"
set +e  # common.sh enables errexit; the assertions below must run to the end

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Fake visudo: exit code controlled by FAKE_VISUDO_RC.
mkdir -p "$TMP/bin"
cat > "$TMP/bin/visudo" <<'EOF'
#!/bin/bash
exit "${FAKE_VISUDO_RC:-0}"
EOF
chmod +x "$TMP/bin/visudo"
PATH="$TMP/bin:$PATH"

TPL="$TMP/sudoers.tpl"
echo '@@BALUHOST_USER@@ ALL=(root) NOPASSWD: /usr/bin/true' > "$TPL"

# 1. Success: rendered, mode 440, rc 0.
DEST="$TMP/ok-sudoers"
FAKE_VISUDO_RC=0 install_sudoers_file "$TPL" "$DEST" "BALUHOST_USER=baluhost" >/dev/null 2>&1
RC=$?
if [[ $RC -eq 0 ]]; then pass "success returns 0"; else fail "success returned $RC"; fi
if [[ "$(stat -c %a "$DEST" 2>/dev/null)" == "440" ]]; then pass "file mode is 440"; else fail "file mode is not 440"; fi
if grep -q '^baluhost ALL=' "$DEST" 2>/dev/null; then pass "template rendered"; else fail "template not rendered"; fi

# 2. visudo rejects the file: rc 1, file removed.
DEST="$TMP/bad-sudoers"
FAKE_VISUDO_RC=1 install_sudoers_file "$TPL" "$DEST" "BALUHOST_USER=baluhost" >/dev/null 2>&1
RC=$?
if [[ $RC -eq 1 ]]; then pass "visudo failure returns 1"; else fail "visudo failure returned $RC"; fi
if [[ ! -e "$DEST" ]]; then pass "rejected sudoers file removed"; else fail "rejected sudoers file left behind"; fi

# 3. Destination directory missing (the polkit/udev shape): rc 1, no 'Installed'.
OUT=$(if install_sudoers_file "$TPL" "$TMP/no-such-dir/sudoers" "BALUHOST_USER=baluhost"; then echo IF-TRUE; else echo IF-FALSE; fi 2>&1)
if grep -q 'IF-FALSE' <<<"$OUT"; then pass "missing dest dir fails in if-context"; else fail "missing dest dir did not fail: $OUT"; fi
if ! grep -q 'Installed sudoers rule' <<<"$OUT"; then
    pass "no false success message after a failed write"
else
    fail "reported success after a failed write (errexit trap): $OUT"
fi

# 4. Template missing: warn and skip with rc 0 (matches the old 'skipping' branch).
install_sudoers_file "$TMP/missing.tpl" "$TMP/never" "BALUHOST_USER=x" >/dev/null 2>&1
RC=$?
if [[ $RC -eq 0 && ! -e "$TMP/never" ]]; then pass "missing template skipped with rc 0"; else fail "missing template: rc=$RC"; fi

# 5. process_template into a missing directory returns non-zero (documents the
# behavior the optional blocks rely on).
process_template "$TPL" "$TMP/no-such-dir/x" "BALUHOST_USER=x" >/dev/null 2>&1
RC=$?
if [[ $RC -ne 0 ]]; then pass "process_template fails for missing target dir"; else fail "process_template returned 0 for missing target dir"; fi

echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `bash deploy/install/tests/test-install-helpers.sh`
Expected: FAIL — `install_sudoers_file: command not found` (rc 127) bei den Tests 1–4; Test 5 PASS.

- [ ] **Step 3: Implementieren**

In `deploy/install/lib/common.sh` direkt nach `process_template` einfügen:

```bash
install_sudoers_file() {
    # Render a sudoers template to <dest>, set 0440 and validate with visudo.
    # A file that fails any step is removed so a broken rule never stays live.
    # Usage: install_sudoers_file <template> <dest> [KEY=VALUE ...]
    # Returns 0 on success or when the template is absent (warns and skips),
    # 1 when writing, chmod or validation fails.
    #
    # Callers invoke this inside `if`, where errexit is OFF — so every command
    # below guards itself instead of relying on `set -e` (#683).
    local template="$1"
    local dest="$2"
    shift 2

    if [[ ! -f "$template" ]]; then
        log_warn "Sudoers template not found: $template (skipping)"
        return 0
    fi

    if ! process_template "$template" "$dest" "$@"; then
        log_error "Could not write sudoers file: $dest"
        rm -f "$dest"
        return 1
    fi
    if ! chmod 440 "$dest"; then
        log_error "Could not set permissions on $dest"
        rm -f "$dest"
        return 1
    fi
    if ! visudo -cf "$dest" &>/dev/null; then
        log_error "Sudoers syntax check failed! Removing $dest"
        rm -f "$dest"
        return 1
    fi
    log_info "Installed sudoers rule: $dest"
}
```

- [ ] **Step 4: Tests laufen lassen**

Run: `bash deploy/install/tests/test-install-helpers.sh`
Expected: `Results: 9 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add deploy/install/lib/common.sh deploy/install/tests/test-install-helpers.sh
git commit -m "feat(install): install_sudoers_file mit Fehlerpropagation für if-Kontext (#683)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Modul 10 — Kern zuerst, optionale Blöcke isoliert

**Files:**
- Create: `deploy/install/tests/test-module-structure.sh`
- Modify: `deploy/install/modules/10-systemd-services.sh` (Umbau Zeilen 46-340; Verifikations- und Summary-Abschnitt bleiben inhaltlich, wandern aber hinter die Kern-`enable`-Schleife)

**Interfaces:**
- Consumes: `install_sudoers_file` (Task 3), `process_template`, `$TEMPLATE_DIR`, `$SCRIPT_DIR`, `$BALUHOST_USER`, `$INSTALL_DIR`, bestehende `install_tray_user_unit` (unverändert).
- Produces: Reihenfolge in Modul 10: Units rendern → `daemon-reload` → `enable` → Verifikation (Kern, darf `exit 1`) → Marker `# --- Optional extras ---` → optionale Funktionen via `run_optional` → Summary → `exit 0`. Nach dem Marker kein `exit 1`.

- [ ] **Step 1: Failing test schreiben**

`deploy/install/tests/test-module-structure.sh` anlegen:

```bash
#!/bin/bash
# Static structure tests for the installer modules (issue #683).
# Modules need root and absolute system paths, so ordering and error-handling
# invariants are asserted on the source instead of by running them.
#
# Usage: bash deploy/install/tests/test-module-structure.sh
set -uo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_SRC="$(cd "$TESTS_DIR/.." && pwd)"

PASS=0
FAIL=0
pass() { echo "PASS: $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $*" >&2; FAIL=$((FAIL + 1)); }

# ─── Syntax of everything the installer executes ─────────────────────────────
for f in "$INSTALL_SRC"/install.sh "$INSTALL_SRC"/lib/*.sh "$INSTALL_SRC"/modules/*.sh; do
    if bash -n "$f" 2>/dev/null; then pass "syntax ok: ${f#"$INSTALL_SRC"/}"; else fail "syntax error: ${f#"$INSTALL_SRC"/}"; fi
done

# ─── Module 10: core (enable) before optional extras, no hard exit after ─────
M10="$INSTALL_SRC/modules/10-systemd-services.sh"
ENABLE_LINE=$(awk '/systemctl enable "\$service"/ {print NR; exit}' "$M10")
MARKER_LINE=$(awk '/^# --- Optional extras ---/ {print NR; exit}' "$M10")
FIRST_OPT_LINE=$(awk '/^run_optional / {print NR; exit}' "$M10")

if [[ -n "$ENABLE_LINE" && -n "$MARKER_LINE" && -n "$FIRST_OPT_LINE" ]]; then
    pass "module 10: enable loop, optional marker and run_optional calls found"
else
    fail "module 10: missing enable loop ($ENABLE_LINE), marker ($MARKER_LINE) or run_optional ($FIRST_OPT_LINE)"
fi
if [[ -n "$ENABLE_LINE" && -n "$MARKER_LINE" && "$ENABLE_LINE" -lt "$MARKER_LINE" && "$MARKER_LINE" -lt "${FIRST_OPT_LINE:-0}" ]]; then
    pass "module 10: systemctl enable runs before the optional extras"
else
    fail "module 10: optional extras are not strictly after systemctl enable"
fi
BAD_EXITS=$(awk -v m="${MARKER_LINE:-999999}" 'NR > m && /exit 1/ {print NR": "$0}' "$M10")
if [[ -z "$BAD_EXITS" ]]; then
    pass "module 10: no 'exit 1' after the optional marker"
else
    fail "module 10: hard exit in optional section: $BAD_EXITS"
fi

# ─── Results ─────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `bash deploy/install/tests/test-module-structure.sh`
Expected: FAIL bei „module 10: enable loop, optional marker and run_optional calls found" und den beiden folgenden (Marker und `run_optional` existieren noch nicht). Syntax-Tests PASS.

- [ ] **Step 3: Modul 10 umbauen**

In `deploy/install/modules/10-systemd-services.sh` die Abschnitte wie folgt neu anordnen. Der Abschnitt „Generate service files from templates" (Zeilen 26-44) bleibt unverändert. Danach folgen — in dieser Reihenfolge:

```bash
# --- Reload systemd ---
log_step "Reloading Systemd"

systemctl daemon-reload
log_info "systemd daemon reloaded."

# --- Enable services ---
log_step "Enabling Services"

for service in "${SERVICES[@]}"; do
    if systemctl is-enabled "$service" &>/dev/null; then
        log_info "$service is already enabled."
    else
        systemctl enable "$service"
        log_info "$service enabled."
    fi
done

# --- Verify (core) ---
log_step "Service Verification"

ALL_OK=true
for service in "${SERVICES[@]}"; do
    if [[ -f "$SYSTEMD_DIR/${service}.service" ]]; then
        ENABLED_STATE=$(systemctl is-enabled "$service" 2>/dev/null || echo "unknown")
        log_info "$service: installed, enabled=$ENABLED_STATE"
    else
        log_error "$service: service file missing!"
        ALL_OK=false
    fi
done

if [[ "$ALL_OK" != "true" ]]; then
    log_error "One or more service files are missing."
    exit 1
fi
```

(dies ist der bestehende Inhalt der Zeilen 222-235 und 342-359, nur neu angeordnet, ohne den Tray-Block dazwischen.)

Danach den Marker und die optionalen Funktionen. Die bestehende Funktion `install_tray_user_unit` (Zeilen 228-323) wird **unverändert** hierher verschoben. Davor:

```bash
# --- Optional extras ---
# Everything below is best-effort: the four core services are already installed
# and enabled above. A failure here is reported as a warning and never stops the
# module (#683). `run_optional` calls each step inside an `if`, which switches
# errexit OFF for the step's whole body — so every command in the functions below
# guards itself with `|| return 1` / `|| { …; return 1; }`. Do not drop those
# guards and do not add `exit 1` in this section (test-module-structure.sh
# checks the latter).
run_optional() {
    local label="$1"
    shift
    if "$@"; then
        return 0
    fi
    log_warn "$label: not installed — the core installation is unaffected."
    return 0
}

install_plugin_wrapper() {
    local src="$SCRIPT_DIR/bin/spawn-plugin-worker.sh"
    local dst="/usr/local/sbin/baluhost-spawn-plugin-worker.sh"

    if [[ ! -f "$src" ]]; then
        log_warn "Spawn wrapper source not found: $src (skipping; external plugins fail closed)"
        return 0
    fi
    if ! bash -n "$src"; then
        log_error "Spawn wrapper source failed syntax check: $src — live binary untouched"
        return 1
    fi
    if ! install -o root -g root -m 0755 "$src" "$dst"; then
        log_error "Could not install spawn wrapper to $dst"
        return 1
    fi
    if ! bash -n "$dst"; then
        log_error "Spawn wrapper failed post-install syntax check! Removing $dst"
        rm -f "$dst"
        return 1
    fi
    log_info "Installed plugin spawn wrapper: $dst (root:root 0755)"

    install_sudoers_file "$TEMPLATE_DIR/baluhost-plugin-sudoers" /etc/sudoers.d/baluhost-plugin \
        "BALUHOST_USER=$BALUHOST_USER"
}

install_polkit_rule() {
    local tpl="$TEMPLATE_DIR/50-baluhost-inhibit-sleep.rules"
    local out="/etc/polkit-1/rules.d/50-baluhost-inhibit-sleep.rules"

    if [[ ! -f "$tpl" ]]; then
        log_warn "Polkit rule template not found: $tpl (skipping)"
        log_warn "Core uptime inhibitor will degrade to BaluHost-internal guards only."
        return 0
    fi
    if [[ ! -d "$(dirname "$out")" ]]; then
        log_warn "polkit is not installed ($(dirname "$out") missing) — rule skipped."
        log_warn "Core uptime inhibitor will degrade to BaluHost-internal guards only."
        return 0
    fi
    process_template "$tpl" "$out" "BALUHOST_USER=$BALUHOST_USER" || return 1
    chmod 644 "$out" || return 1
    log_info "Installed polkit rule: $out"
    # polkit reloads rules.d files on next request — no daemon-reload needed.
}

install_udev_rule() {
    local tpl="$TEMPLATE_DIR/70-baluhost-amd-gpu.rules"
    local out="/etc/udev/rules.d/70-baluhost-amd-gpu.rules"

    if [[ ! -f "$tpl" ]]; then
        log_warn "Udev rule template not found: $tpl (skipping)"
        log_warn "GPU Power Management will report 'WRITE PERMISSION: missing' until applied manually."
        return 0
    fi
    if [[ ! -d "$(dirname "$out")" ]]; then
        log_warn "$(dirname "$out") missing — udev rule skipped."
        return 0
    fi
    process_template "$tpl" "$out" "BALUHOST_USER=$BALUHOST_USER" || return 1
    chmod 644 "$out" || return 1
    log_info "Installed udev rule: $out"

    # Ensure the service user is in the video group so the rule's
    # chgrp + g+w bit actually grants access.
    if id -nG "$BALUHOST_USER" | tr ' ' '\n' | grep -qx video; then
        log_info "$BALUHOST_USER already in 'video' group."
    elif usermod -aG video "$BALUHOST_USER"; then
        log_info "Added $BALUHOST_USER to 'video' group."
    else
        log_warn "Could not add $BALUHOST_USER to 'video' group — GPU power sysfs may stay read-only."
    fi

    udevadm control --reload-rules || log_warn "udevadm reload-rules failed (non-fatal)"
    udevadm trigger --subsystem-match=drm || log_warn "udevadm trigger drm failed (non-fatal)"
    log_info "Udev rules reloaded and drm subsystem re-triggered."
}

install_bluetooth_group() {
    # The BlueZ D-Bus policy grants org.bluez to the 'bluetooth' group. Only act
    # when BlueZ is installed (the group exists); without it the plugin reports
    # available=false and nothing else breaks.
    if ! getent group bluetooth &>/dev/null; then
        log_warn "Group 'bluetooth' not found (BlueZ not installed) — bluetooth plugin will be unavailable."
        return 0
    fi
    if id -nG "$BALUHOST_USER" | tr ' ' '\n' | grep -qx bluetooth; then
        log_info "$BALUHOST_USER already in 'bluetooth' group."
    elif usermod -aG bluetooth "$BALUHOST_USER"; then
        log_info "Added $BALUHOST_USER to 'bluetooth' group (takes effect on next service start)."
    else
        log_warn "Could not add $BALUHOST_USER to 'bluetooth' group — bluetooth plugin may be unavailable."
    fi
}

log_step "Optional Extras"

run_optional "Update sudoers" install_sudoers_file \
    "$TEMPLATE_DIR/baluhost-update-sudoers" /etc/sudoers.d/baluhost-update \
    "BALUHOST_USER=$BALUHOST_USER" "INSTALL_DIR=$INSTALL_DIR"
run_optional "Deploy sudoers" install_sudoers_file \
    "$TEMPLATE_DIR/baluhost-deploy-sudoers" /etc/sudoers.d/baluhost-deploy \
    "BALUHOST_USER=$BALUHOST_USER" "INSTALL_DIR=$INSTALL_DIR"
run_optional "Hardware sudoers" install_sudoers_file \
    "$TEMPLATE_DIR/baluhost-hardware-sudoers" /etc/sudoers.d/baluhost-hardware \
    "BALUHOST_USER=$BALUHOST_USER"
run_optional "Plugin sandbox spawn wrapper" install_plugin_wrapper
run_optional "Polkit rule" install_polkit_rule
run_optional "Udev rule" install_udev_rule
run_optional "Bluetooth group" install_bluetooth_group

# --- Desktop Tray ---
# install_tray_user_unit guards each command itself (see its body); it is called
# plainly, not through run_optional.
log_step "Desktop Tray Unit"

install_tray_user_unit
```

Danach bleibt der bestehende `# --- Summary ---`-Block (Zeilen 361-368) unverändert am Ende. Wichtig: Die ursprünglichen Blöcke „Update Sudoers" … „Bluetooth Group" (Zeilen 46-220) werden **ersetzt**, nicht zusätzlich beibehalten; ebenso entfallen die alten Positionen von Reload, Enable, Tray-Aufruf und Verify.

Den `log_step`-Titeln der alten Blöcke („Update Sudoers", …) entsprechen jetzt die `run_optional`-Labels; die Schritt-Überschrift „Optional Extras" ersetzt sie.

- [ ] **Step 4: Tests laufen lassen**

Run: `bash deploy/install/tests/test-module-structure.sh`
Expected: alle PASS inkl. „enable runs before the optional extras" und „no 'exit 1' after the optional marker".

Zusätzlich: `bash -n deploy/install/modules/10-systemd-services.sh` (Exit 0) und, falls installiert, `shellcheck -x deploy/install/modules/10-systemd-services.sh` — neue Findings außer SC1091 (source) prüfen.

- [ ] **Step 5: Commit**

```bash
git add deploy/install/modules/10-systemd-services.sh deploy/install/tests/test-module-structure.sh
git commit -m "fix(install): Modul 10 aktiviert Kerndienste vor den optionalen Extras (#683)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Module 12 und 13

**Files:**
- Modify: `deploy/install/tests/test-module-structure.sh` (zwei Abschnitte vor „Results")
- Modify: `deploy/install/modules/12-start-services.sh:23-34`
- Modify: `deploy/install/modules/13-power-helpers.sh:14-39`

**Interfaces:**
- Consumes: `install_sudoers_file` (Task 3).
- Produces: Modul 12 — `baluhost-backend`-Startfehler ⇒ `exit 1`; andere Units ⇒ Warnung. Modul 13 — jeder Schritt meldet seinen Fehler mit eigener Meldung und `exit 1` (der Orchestrator behandelt 13 als optional).

- [ ] **Step 1: Failing tests schreiben**

Vor dem Abschnitt `# ─── Results` in `test-module-structure.sh` einfügen:

```bash
# ─── Module 12: only the backend start is fatal ──────────────────────────────
M12="$INSTALL_SRC/modules/12-start-services.sh"
# A bare `systemctl start|restart …` line would abort the module under set -e
# for scheduler/webdav too. Starting must happen inside an `if`.
BARE_START=$(awk '/^[[:space:]]*systemctl[[:space:]]+(start|restart)[[:space:]]/ {print NR": "$0}' "$M12")
if [[ -z "$BARE_START" ]]; then
    pass "module 12: no unguarded systemctl start/restart"
else
    fail "module 12: unguarded start: $BARE_START"
fi
if awk '/== "baluhost-backend"/ {b=1} /exit 1/ && b {found=1} END {exit !found}' "$M12"; then
    pass "module 12: backend start failure is handled explicitly"
else
    fail "module 12: no explicit backend failure handling"
fi

# ─── Module 13: every single-line system command is guarded ──────────────────
M13="$INSTALL_SRC/modules/13-power-helpers.sh"
UNGUARDED=$(awk '/^(mkdir|cp|chmod|chown)[[:space:]]/ && !/\|\|/ {print NR": "$0}' "$M13")
if [[ -z "$UNGUARDED" ]]; then
    pass "module 13: mkdir/cp/chmod/chown are guarded"
else
    fail "module 13: unguarded command: $UNGUARDED"
fi
```

- [ ] **Step 2: Fehlschlag prüfen**

Run: `bash deploy/install/tests/test-module-structure.sh`
Expected: FAIL bei „module 12: no unguarded systemctl start/restart" (Zeilen 27 und 30), „module 12: no explicit backend failure handling" und „module 13: unguarded command" (Zeilen 20-23).

- [ ] **Step 3: Modul 12 implementieren**

Die Schleife `# --- Start all services ---` bis einschließlich `log_info "All services started."` ersetzen:

```bash
# --- Start all services ---
# Only the backend is required for the installation to be usable. Scheduler and
# WebDAV are secondary: a failure there (e.g. a WebDAV port conflict) is a
# warning, so the health check below and modules 13/14 still run. The backend
# is listed first. The status report further down shows any unit that is down.
for service in "${SERVICES[@]}"; do
    if systemctl is-active "$service" &>/dev/null; then
        log_info "$service is already running, restarting..."
        verb=restart
    else
        log_info "Starting $service..."
        verb=start
    fi

    if systemctl "$verb" "$service"; then
        continue
    fi
    if [[ "$service" == "baluhost-backend" ]]; then
        log_error "$service failed to $verb — cannot continue."
        log_error "Check: sudo journalctl -u $service -n 50 --no-pager"
        exit 1
    fi
    log_warn "$service failed to $verb — continuing; check: sudo journalctl -u $service -n 50 --no-pager"
done

log_info "Service start commands issued."
```

- [ ] **Step 4: Modul 13 implementieren**

Den Abschnitt ab `log_step "Power Helpers"` bis zum Dateiende ersetzen:

```bash
log_step "Power Helpers"

require_root

# This module is optional from install.sh's point of view: a failure here is
# reported as a warning, not as a failed installation. It still exits non-zero
# so `--module 13-power-helpers` tells the operator the truth.
abort_module() {
    log_error "$1"
    exit 1
}

# Install helper
log_info "Installing $HELPER_DEST..."
[[ -f "$HELPER_SRC" ]] || abort_module "Helper script not found: $HELPER_SRC"
mkdir -p "$HELPER_DEST_DIR" || abort_module "Could not create $HELPER_DEST_DIR"
cp "$HELPER_SRC" "$HELPER_DEST" || abort_module "Could not copy $HELPER_SRC to $HELPER_DEST"
chmod 0755 "$HELPER_DEST" || abort_module "Could not chmod $HELPER_DEST"
chown root:root "$HELPER_DEST" || abort_module "Could not chown $HELPER_DEST"

# Install sudoers (template-substituted, validated, removed again if invalid)
log_info "Installing $SUDOERS_DEST..."
[[ -f "$SUDOERS_TEMPLATE" ]] || abort_module "Sudoers template not found: $SUDOERS_TEMPLATE"
install_sudoers_file "$SUDOERS_TEMPLATE" "$SUDOERS_DEST" "BALUHOST_USER=$BALUHOST_USER" \
    || abort_module "Power sudoers not installed: $SUDOERS_DEST"
chown root:root "$SUDOERS_DEST" || abort_module "Could not chown $SUDOERS_DEST"

log_info "Power helpers installed successfully."
```

- [ ] **Step 5: Tests laufen lassen**

Run: `bash deploy/install/tests/test-module-structure.sh`
Expected: alle PASS.
Run: `bash -n deploy/install/modules/12-start-services.sh && bash -n deploy/install/modules/13-power-helpers.sh` → kein Output, Exit 0.

- [ ] **Step 6: Commit**

```bash
git add deploy/install/modules/12-start-services.sh deploy/install/modules/13-power-helpers.sh deploy/install/tests/test-module-structure.sh
git commit -m "fix(install): Modul 12 startet nur das Backend hart, Modul 13 meldet Fehler sauber (#683)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Dokumentation, Gesamtlauf, Abschluss

**Files:**
- Modify: ggf. eine Doku-Stelle unter `docs/` (nur wenn vorhanden)

- [ ] **Step 1: Doku-Stelle suchen**

Mit `mcp__vectorgrep__search_files` (Fallback: Glob/Grep) nach Dokumentation des Installers suchen: Begriffe „install.sh", „Installation stopped", „Module 13", „optional features" unter `docs/` und `deploy/`. Existiert eine Stelle, die den Abbruch bei Modulfehler beschreibt, einen Absatz ergänzen: „Module 13 (Power Helpers) und 14 (Optional Features) sind optional: ein Fehler dort wird als Warnung im Abschlussbanner gemeldet (Exit-Code 0); alle anderen Module brechen die Installation bei einem Fehler ab." Gibt es keine, nichts anlegen.

- [ ] **Step 2: Gesamtlauf aller Tests**

Run:
```bash
bash deploy/install/tests/test-install-orchestration.sh \
 && bash deploy/install/tests/test-install-helpers.sh \
 && bash deploy/install/tests/test-module-structure.sh \
 && bash deploy/install/verify/test-features.sh
```
Expected: jeder Lauf endet mit `0 failed` bzw. ohne `BAD`; Gesamt-Exit 0.

- [ ] **Step 3: Spec gegenlesen**

Jeden Abschnitt der Spec (1–6, Tests) gegen den Diff halten (`git diff main --stat`, `git diff main -- deploy/install`): Ist `OPTIONAL_MODULES` genau `13`, `14`? Steht kein `exit 1` im optionalen Teil von Modul 10? Hat `run_feature` beide `|| return 1`? Abweichungen beheben.

- [ ] **Step 4: Commit (falls Doku geändert)**

```bash
git add docs
git commit -m "docs(install): Kern- und optionale Module im Installer beschrieben (#683)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: PR vorbereiten — nicht ohne Rückfrage pushen**

Mit `superpowers:finishing-a-development-branch` abschließen. Vor `git push` und `gh pr create` den Nutzer fragen (außenwirksam). PR-Beschreibung: bezieht sich auf #683 (`Refs #683`, nicht `Closes`, falls der Nutzer das Issue für die Nacharbeit offenlassen will — Nutzer fragen), nennt #780–#782 als ausgegliederte Folgefunde und endet mit
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
