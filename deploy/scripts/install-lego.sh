#!/bin/bash
# Installiert lego (ACME-Client) aus trixie-backports fuer das Plugin local_tls.
# lego >= 4.35 wird gebraucht; Debian 13 (trixie) liefert in main eine aeltere
# Version, daher -t trixie-backports. Die Backports-Quelle wird nur ergaenzt,
# wenn sie fehlt. Laeuft als root (vom Installer, Modul 14, Feature LEGO).
#
# Die Funktionen lassen sich ohne Seiteneffekte einbinden (source), damit die
# Tests sie pruefen koennen; installiert wird nur beim direkten Aufruf.
set -euo pipefail

# Bricht ab, wenn das System nicht Debian 13 (trixie) ist: trixie-backports
# auf einem anderen Release einzutragen wuerde fremde Pakete mischen.
check_codename() {
    local os_release="${OS_RELEASE_FILE:-/etc/os-release}"
    local codename=""
    if [[ -r "$os_release" ]]; then
        codename="$(. "$os_release" && echo "${VERSION_CODENAME:-}")"
    fi
    if [[ "$codename" != "trixie" ]]; then
        echo "install-lego.sh: nur fuer Debian 13 (trixie), gefunden: '${codename:-unbekannt}'." >&2
        echo "lego >= 4.35 bitte manuell installieren (z. B. Release von github.com/go-acme/lego)." >&2
        return 1
    fi
}

# Ist trixie-backports in einer der Dateien aktiv eingetragen? Zaehlt aktive
# deb-Zeilen (einzeiliges Format) und deb822-Stanzas mit "Suites: ...
# trixie-backports", ausser die Stanza hat "Enabled: no". Kommentare zaehlen nie.
has_trixie_backports() {
    local files=() f
    for f in "$@"; do
        [[ -f "$f" ]] && files+=("$f")
    done
    (( ${#files[@]} )) || return 1
    awk '
        function flush() { if (suites && enabled) found = 1; suites = 0; enabled = 1 }
        FNR == 1 { flush() }
        /^[[:space:]]*#/ { next }
        /^[[:space:]]*$/ { flush(); next }
        /^[[:space:]]*deb(-src)?[[:space:]].*trixie-backports/ { found = 1; next }
        /^[[:space:]]*Suites:.*trixie-backports/ { suites = 1; next }
        tolower($0) ~ /^[[:space:]]*enabled:[[:space:]]*no[[:space:]]*$/ { enabled = 0; next }
        END { flush(); exit(found ? 0 : 1) }
    ' "${files[@]}"
}

main() {
    if [[ $EUID -ne 0 ]]; then
        echo "install-lego.sh muss als root laufen" >&2
        exit 1
    fi
    check_codename || exit 1

    if ! has_trixie_backports /etc/apt/sources.list /etc/apt/sources.list.d/*; then
        echo "Ergaenze trixie-backports-Quelle"
        echo "deb http://deb.debian.org/debian trixie-backports main" \
            > /etc/apt/sources.list.d/trixie-backports.list
        apt-get update -qq
    fi

    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq -t trixie-backports lego
    lego --version
    echo "lego installiert. Plugin local_tls in den Einstellungen aktivieren und"
    echo "danach baluhost-backend neu starten (die Routen werden beim Start eingehängt)."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
