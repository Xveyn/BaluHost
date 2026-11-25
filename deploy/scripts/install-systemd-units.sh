#!/bin/bash
# Gleicht die systemd-Units von BaluHost mit ihren Repo-Templates ab (#689).
#
# Warum: ci-deploy.sh hat Unit-Dateien nie geschrieben -- das tat nur
# Installer-Modul 10, und das laeuft nur von Hand. Eine Template-Aenderung
# blieb deshalb unter <install-dir>/deploy/ liegen: --proxy-headers fehlte der
# laufenden Unit monatelang, und alle LAN-Gates waren wirkungslos. Jetzt ruft
# ci-deploy.sh dieses Skript bei jedem Deploy auf (Schritt 6b) und im Rollback
# noch einmal, dann mit den alten Templates.
#
# Ablauf:
#   1. rendern mit process_template aus deploy/install/lib/common.sh -- Byte
#      fuer Byte wie Modul 10, mit denselben drei Werten;
#   2. systemd-analyze verify ueber ALLE Units, bevor irgendetwas geschrieben
#      wird (gemessen auf BaluNode 2026-09-27: korrekte Units exit=0, relativer
#      ExecStart exit=1);
#   3. nur abweichende Dateien ersetzen: Backup, install in eine Temp-Datei im
#      Zielverzeichnis, atomarer mv;
#   4. daemon-reload nur, wenn sich etwas geaendert hat.
#
# Exit 0: alles im Takt oder erfolgreich ersetzt. Jeder andere Exit: ci-deploy
# rollt zurueck. Scheitert Schritt 1 oder 2, ist nichts geschrieben.
#
# Test-Naehte: SYSTEMD_DIR, UNIT_BACKUP_DIR und BALUHOST_UNITS_ALLOW_NONROOT
# sind aus der Umgebung ueberschreibbar. Ueber den Deploy erreicht keine davon
# das Skript: die sudoers-Zeile pinnt die Kommandozeile ohne SETENV, und sudo
# verwirft die Umgebung (env_reset). Wer die Umgebung eines root-Aufrufs
# kontrolliert, braucht diese Naehte nicht.
#
# Der Local-Channel (#717) besteht aus zwei Dateien, Service und Socket, und
# ist optional: Modul 10 legt sie an, nicht jede Box hat sie. Abgeglichen
# werden sie nur, wenn mindestens eine der beiden schon installiert ist --
# dann beide, damit das Paar zusammenpasst. Ein Deploy fuehrt nie eine Unit
# ein, die es auf der Box nicht gab, und aktiviert nichts.
#
# Nicht verwaltet: die Tray-User-Unit.
# UNITS muss mit Modul 10, ci-deploy.sh und unit_drift.MANAGED_UNITS
# uebereinstimmen, OPTIONAL_UNIT_FILES mit Modul 10 und
# unit_drift.OPTIONAL_UNIT_FILES --
# backend/tests/test_deploy_install_systemd_units.py prueft das.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEMPLATE_DIR="$INSTALL_DIR/deploy/install/templates"
VENV_BIN="$INSTALL_DIR/backend/.venv/bin"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
UNIT_BACKUP_DIR="${UNIT_BACKUP_DIR:-/var/backups/baluhost/units}"
BACKUP_KEEP=10

UNITS=(baluhost-backend baluhost-scheduler baluhost-webdav baluhost-monitoring)
OPTIONAL_UNIT_FILES=(baluhost-backend-local.service baluhost-backend-local.socket)

# Die Dateien, um die es in diesem Lauf geht: die vier Kern-Units immer, das
# optionale Paar nur, wenn es auf der Box schon existiert.
UNIT_FILES=()
for unit in "${UNITS[@]}"; do
    UNIT_FILES+=("$unit.service")
done
for file in "${OPTIONAL_UNIT_FILES[@]}"; do
    if [[ -f "$SYSTEMD_DIR/$file" ]]; then
        UNIT_FILES+=("${OPTIONAL_UNIT_FILES[@]}")
        break
    fi
done

# shellcheck source=../install/lib/common.sh
source "$INSTALL_DIR/deploy/install/lib/common.sh"

fail() {
    log_error "$*"
    exit 1
}

prune_backups() {
    local file="$1" i excess
    local -a old
    shopt -s nullglob
    old=("$UNIT_BACKUP_DIR/$file".*)
    shopt -u nullglob
    # Der Zeitstempel im Namen ist fest breit, die Glob-Sortierung ist also
    # chronologisch: vorne stehen die aeltesten.
    excess=$(( ${#old[@]} - BACKUP_KEEP ))
    for (( i = 0; i < excess; i++ )); do
        rm -f -- "${old[$i]}"
    done
}

if [[ "$EUID" -ne 0 && "${BALUHOST_UNITS_ALLOW_NONROOT:-}" != "1" ]]; then
    fail "must run as root (use sudo)."
fi

# ─── Dienstbenutzer ─────────────────────────────────────────────────
# Explizit > User= des laufenden Dienstes > Abbruch -- dasselbe Muster wie
# install-power-sudoers.sh, festgenagelt in test_deploy_service_user_resolution.
# BALUHOST_USER gilt nur fuer den manuellen Aufruf (siehe Test-Naehte oben).
SERVICE_USER="$(systemctl show -p User --value baluhost-backend.service 2>/dev/null || true)"
BALUHOST_USER="${BALUHOST_USER:-${SERVICE_USER:-}}"
if [[ -z "$BALUHOST_USER" ]]; then
    log_error "could not determine the service user from baluhost-backend.service (User=)"
    log_error "and BALUHOST_USER is unset. Set BALUHOST_USER explicitly."
    exit 1
fi
id -u "$BALUHOST_USER" >/dev/null 2>&1 \
    || fail "service user '$BALUHOST_USER' does not exist on this host."

# ─── 1. Rendern ─────────────────────────────────────────────────────
RENDER_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "$RENDER_DIR"
    rm -f "$SYSTEMD_DIR"/.baluhost-*.service.new "$SYSTEMD_DIR"/.baluhost-*.socket.new
}
trap cleanup EXIT

rendered=()
for file in "${UNIT_FILES[@]}"; do
    out="$RENDER_DIR/$file"
    process_template "$TEMPLATE_DIR/$file" "$out" \
        "BALUHOST_USER=$BALUHOST_USER" \
        "INSTALL_DIR=$INSTALL_DIR" \
        "VENV_BIN=$VENV_BIN" \
        || fail "cannot render $file"
    if leftover="$(grep -oE '@@[A-Z_]+@@' "$out" | sort -u | tr '\n' ' ')" && [[ -n "$leftover" ]]; then
        fail "$file: unrendered placeholder(s) left: $leftover-- nothing installed."
    fi
    rendered+=("$out")
done

# ─── 2. Pruefen, alles oder nichts ──────────────────────────────────
# --recursive-errors=no: seit systemd 250 zaehlt verify sonst auch Fehler in
# geladenen Abhaengigkeiten (postgresql.service ueber Wants=, network.target).
# Ein Distro-Update an einer fremden Unit liesse dann jeden Deploy
# zurueckrollen -- geprueft werden nur unsere eigenen Units.
if ! verify_out="$(systemd-analyze verify --recursive-errors=no "${rendered[@]}" 2>&1)"; then
    echo "$verify_out" >&2
    fail "systemd-analyze verify rejected the rendered units -- nothing installed."
fi
# Nicht-fatale Hinweise von verify gehoeren trotzdem ins Deploy-Log.
if [[ -n "$verify_out" ]]; then
    echo "$verify_out" >&2
fi

# ─── 3. Vergleichen und ersetzen ────────────────────────────────────
install_args=(-m 0644)
if [[ "$EUID" -eq 0 ]]; then
    install_args+=(-o root -g root)
fi
stamp="$(date +%Y%m%d-%H%M%S-%N)"
changed=0

for file in "${UNIT_FILES[@]}"; do
    src="$RENDER_DIR/$file"
    dst="$SYSTEMD_DIR/$file"
    if [[ -f "$dst" ]] && cmp -s "$src" "$dst"; then
        continue
    fi
    if [[ -f "$dst" ]]; then
        mkdir -p "$UNIT_BACKUP_DIR"
        cp -p "$dst" "$UNIT_BACKUP_DIR/$file.$stamp"
        prune_backups "$file"
    fi
    # Temp-Datei im Zielverzeichnis, damit mv ein atomarer Rename auf demselben
    # Dateisystem ist: systemd sieht nie eine halb geschriebene Unit. Der
    # Punkt-Praefix und die Endung .new halten sie aus systemds Unit-Suche.
    tmp="$SYSTEMD_DIR/.$file.new"
    install "${install_args[@]}" "$src" "$tmp"
    mv -f "$tmp" "$dst"
    # Services heissen im Log wie bisher ohne Endung; ein Socket mit.
    echo "CHANGED: ${file%.service}"
    changed=$(( changed + 1 ))
done

# ─── 4. Neu laden ───────────────────────────────────────────────────
# Auch ohne eigene Aenderung, wenn systemd eine Unit als veraltet meldet: nach
# einem gescheiterten daemon-reload stimmen die Dateien bereits, systemd faehrt
# aber die alte Fassung. Ein erneuter Aufruf -- den der Drift-Check als
# Reparatur empfiehlt -- muss genau diesen Fall beheben.
stale=0
for file in "${UNIT_FILES[@]}"; do
    if [[ "$(systemctl show -p NeedDaemonReload --value "$file" 2>/dev/null || true)" == "yes" ]]; then
        stale=1
    fi
done

if [[ "$changed" -eq 0 && "$stale" -eq 0 ]]; then
    echo "OK: all ${#UNIT_FILES[@]} units up to date"
    exit 0
fi

systemctl daemon-reload \
    || fail "systemctl daemon-reload failed -- unit files are written, systemd still runs the old ones."
if [[ "$changed" -eq 0 ]]; then
    echo "OK: all ${#UNIT_FILES[@]} units up to date, stale systemd state fixed by daemon-reload"
else
    echo "OK: $changed unit(s) replaced"
fi
