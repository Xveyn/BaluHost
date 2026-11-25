#!/bin/bash
# Installiert lego (ACME-Client) aus trixie-backports fuer das Plugin local_tls.
# lego >= 4.35 wird gebraucht; Debian 13 (trixie) liefert in main eine aeltere
# Version, daher -t trixie-backports. Die Backports-Quelle wird nur ergaenzt,
# wenn sie fehlt. Laeuft als root (vom Installer, Modul 14, Feature LEGO).
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "install-lego.sh muss als root laufen" >&2
    exit 1
fi

if ! grep -rqs 'trixie-backports' /etc/apt/sources.list /etc/apt/sources.list.d/ 2>/dev/null; then
    echo "Ergaenze trixie-backports-Quelle"
    echo "deb http://deb.debian.org/debian trixie-backports main" \
        > /etc/apt/sources.list.d/trixie-backports.list
    apt-get update -qq
fi

DEBIAN_FRONTEND=noninteractive apt-get install -y -qq -t trixie-backports lego
lego --version
echo "lego installiert. Plugin local_tls in den Einstellungen aktivieren."
