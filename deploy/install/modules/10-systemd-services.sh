#!/bin/bash
# BaluHost Install - Module 10: Systemd Services
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

# ─── Variables ──────────────────────────────────────────────────────

VENV_BIN="${VENV_BIN:-$INSTALL_DIR/backend/.venv/bin}"
TEMPLATE_DIR="$SCRIPT_DIR/templates"
SYSTEMD_DIR="/etc/systemd/system"

SERVICES=(
    "baluhost-backend"
    "baluhost-scheduler"
    "baluhost-webdav"
    "baluhost-monitoring"
)

# ─── Main ───────────────────────────────────────────────────────────

log_step "Systemd Services"

require_root

# --- Generate service files from templates ---
for service in "${SERVICES[@]}"; do
    TEMPLATE="$TEMPLATE_DIR/${service}.service"
    OUTPUT="$SYSTEMD_DIR/${service}.service"

    if [[ ! -f "$TEMPLATE" ]]; then
        log_error "Template not found: $TEMPLATE"
        exit 1
    fi

    log_info "Generating $OUTPUT..."
    process_template "$TEMPLATE" "$OUTPUT" \
        "BALUHOST_USER=$BALUHOST_USER" \
        "INSTALL_DIR=$INSTALL_DIR" \
        "VENV_BIN=$VENV_BIN"

    chmod 644 "$OUTPUT"
    log_info "Created $OUTPUT"
done

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

# --- Optional extras ---
# Everything below is best-effort: the four core services are already installed
# and enabled above. A failure here is reported as a warning and never stops the
# module (#683). `run_optional` calls each step inside an `if`, which switches
# errexit OFF for the step's whole body — so every command in the functions below
# guards itself with `|| return 1` / `|| { …; return 1; }`. Do not drop those
# guards and do not add a hard module exit in this section
# (test-module-structure.sh checks the latter).
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

# --- Desktop tray user unit (KDE Plasma) ---
# Als Funktion, damit der Sonderfall "kein Desktop-Benutzer" an einer Stelle
# endet statt als verschachtelter Block zwischen den System-Units zu stehen.
install_tray_user_unit() {
    # BALUHOST_USER ist das Dienstkonto, nicht zwingend der Mensch an der
    # Tastatur. Eine User-Unit im Home des Dienstkontos startet in keiner
    # Desktop-Sitzung, deshalb wird der Desktop-Benutzer getrennt bestimmt.
    local target_user="${TRAY_DESKTOP_USER:-${SUDO_USER:-}}"
    if [ -z "$target_user" ]; then
        log_warn "Kein Desktop-Benutzer bekannt — Tray-Unit nicht installiert."
        log_warn "Nachtraeglich: TRAY_DESKTOP_USER=<name> erneut ausfuehren."
        return 0
    fi

    local user_home
    # `|| true`, weil getent fuer einen unbekannten Benutzer 2 liefert. Ohne
    # das risse die Zuweisung unter `set -euo pipefail` den ganzen Installer
    # ab, statt die Warnung eine Zeile weiter unten zu erreichen.
    user_home="$(getent passwd "$target_user" | cut -d: -f6 || true)"
    if [ -z "$user_home" ] || [ ! -d "$user_home" ]; then
        log_warn "Kein Home fuer $target_user — Tray-Unit uebersprungen."
        return 0
    fi

    # Ab hier faengt jedes Kommando seinen eigenen Fehlschlag ab. Unter
    # `set -euo pipefail` risse sonst ein einziges davon nicht nur diese
    # Funktion ab, sondern das ganze Modul — und install.sh bricht die
    # Modulschleife daraufhin mit `break` ab, sodass 11-nginx bis
    # 14-optional-features nie laufen. Ein optionaler Desktop-Komfortschritt
    # darf keine Kern-Installation kippen.
    #
    # Nicht stattdessen `install_tray_user_unit || log_warn ...` am Aufrufort:
    # ein Funktionsaufruf in einer ||-Liste schaltet errexit im *gesamten*
    # Rumpf ab, die Funktion liefe nach einem Fehlschlag einfach weiter.
    local unit_dir="$user_home/.config/systemd/user"
    # Als Zielbenutzer anlegen statt als root mit -o/-g: `install -d` setzt
    # Eigentuemer und Gruppe nur auf die *letzte* Komponente. Fehlen
    # ~/.config oder ~/.config/systemd noch — und genau so sieht das Home
    # eines Kontos aus, das sich noch nie angemeldet hat, also der Fall, fuer
    # den der else-Zweig unten ueberhaupt geschrieben ist —, gehoerten sie
    # danach root, und die erste Plasma-Sitzung koennte nicht in ~/.config
    # schreiben.
    sudo -u "$target_user" mkdir -p "$unit_dir" || {
        log_warn "Konnte $unit_dir nicht als $target_user anlegen — Tray-Unit uebersprungen."
        return 0
    }
    process_template \
        "$TEMPLATE_DIR/baluhost-tray.service" \
        "$unit_dir/baluhost-tray.service" \
        "VENV_BIN=$VENV_BIN" \
        "WEB_URL=${TRAY_WEB_URL:-https://baluhost.local}" || {
        log_warn "Vorlage baluhost-tray.service nicht verarbeitbar — Tray-Unit uebersprungen."
        return 0
    }
    # process_template schreibt als root, die Datei gehoert also root. Ohne
    # das chown koennte der Benutzer seine eigene Unit nicht mehr aendern.
    chown "$target_user:$target_user" "$unit_dir/baluhost-tray.service" || {
        log_warn "Konnte Tray-Unit nicht $target_user zuschreiben — uebersprungen."
        return 0
    }

    # Das Extra [tray] steckt bewusst nicht im Standard-venv: Qt gehoert nicht
    # auf eine kopflose Serverinstallation. Deshalb hier nur ein Hinweis, kein
    # Abbruch und keine Warnung — der kopflose Server ist der Normalfall.
    if [ ! -x "$VENV_BIN/baluhost-tray" ]; then
        log_info "Extra [tray] fehlt — einmalig nachinstallieren mit: sudo $VENV_BIN/pip install -e '$INSTALL_DIR/backend[tray]'"
    fi

    local uid runtime
    uid="$(id -u "$target_user")" || {
        log_warn "Keine UID fuer $target_user — Tray-Unit abgelegt, aber nicht aktiviert."
        return 0
    }
    runtime="/run/user/$uid"
    if [ -d "$runtime" ] && sudo -u "$target_user" \
        XDG_RUNTIME_DIR="$runtime" systemctl --user daemon-reload 2>/dev/null; then
        sudo -u "$target_user" XDG_RUNTIME_DIR="$runtime" \
            systemctl --user enable baluhost-tray.service || {
            log_warn "Tray-Unit abgelegt, aber 'systemctl --user enable' schlug fehl."
            log_warn "Nachtraeglich als $target_user: systemctl --user enable baluhost-tray.service"
            return 0
        }
        log_info "Tray-Unit installiert und aktiviert fuer $target_user"
    else
        # Hier hat der Zielbenutzer keine laufende Sitzung — bei einer
        # Erstinstallation per SSH als root der Normalfall. `systemctl --user
        # enable` ist also nie gelaufen: es gibt keinen Symlink in
        # graphical-session.target.wants/, und `WantedBy=` bleibt wirkungslos.
        # Die Unit liegt da und startet beim naechsten Login trotzdem nicht.
        # Ein log_info an dieser Stelle laese sich wie Erfolg und haelt genau
        # den Menschen vom Nachsehen ab, der den Befehl noch ausfuehren muss.
        log_warn "Tray-Unit fuer $target_user abgelegt, aber Autostart NICHT eingerichtet"
        log_warn "(keine laufende Sitzung fuer $target_user — das ist bei einer Installation per SSH normal)."
        log_warn "Nachtraeglich als $target_user: systemctl --user enable baluhost-tray.service"
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

# --- Summary ---
log_step "Systemd Summary"
log_info "VENV_BIN:   $VENV_BIN"
log_info "Services:   ${SERVICES[*]}"
log_info "Status:     all installed and enabled (not yet started)"
log_info "Systemd service setup complete."

exit 0
