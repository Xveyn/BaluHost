# Feature-Abhängigkeiten

Zentrale Referenz, welche Systempakete jedes BaluHost-Feature benötigt,
wie es aktiviert wird und welches Setup-Skript es konfiguriert.

## Unterstütztes OS

Der Produktions-Installer von BaluHost unterstützt ausschließlich **Debian 12 (bookworm)
und Debian 13 (trixie)**. Der Preflight-Check (`deploy/install/modules/01-preflight.sh`)
bricht bei jedem anderen Betriebssystem ab. Dies ist bewusst so: Paketnamen, systemd-Unit-
Annahmen und die Deploy-Skripte sind nur auf Debian getestet. Ubuntu, Fedora, Arch und
RHEL werden nicht unterstützt. (Das mDNS-Skript `install-avahi.sh` behandelt zufällig
mehrere Distributionen, der Rest der Installations-Kette jedoch nicht — es gibt keinen
halb-unterstützten Pfad.)

## Was eine Standard-Installation liefert

Wenn `sudo ./install.sh` ohne Aktivierung optionaler Features ausgeführt wird, wird
das **Core-NAS** installiert: PostgreSQL, Nginx, das FastAPI-Backend, das gebaute
Frontend und das Basis-Toolchain (Python, Node, git, build-essential, curl). Dateien,
Benutzer, Monitoring und die Web-Oberfläche funktionieren sofort.

Alles in der folgenden Tabelle ist **standardmäßig deaktiviert** und bleibt inaktiv,
bis es explizit eingeschaltet wird.

## Abhängigkeits-Matrix

| Feature | Pakete | Setup-Skript | Standard-Installation |
|---|---|---|---|
| RAID-Array-Verwaltung | `mdadm` | `deploy/scripts/install-hardware-sudoers.sh` | aus |
| Festplattengesundheit (SMART) | `smartmontools` | `deploy/scripts/install-hardware-sudoers.sh` | aus |
| WireGuard VPN | `wireguard-tools` | `deploy/scripts/setup-wireguard.sh` | aus |
| Cloud-Import | `rclone` | (keines — läuft als Service-Benutzer) | aus |
| Samba / SMB-Freigabe | `samba`, `samba-common-bin` | `deploy/samba/setup-samba.sh` | aus |
| NFS-Freigabe | `nfs-kernel-server` | `deploy/nfs/setup-nfs.sh` | aus |
| Windows-Erkennung (WS-Discovery) | `wsdd2` / `wsdd` | `deploy/wsdd/setup-wsdd.sh` | aus |
| mDNS / Bonjour (`baluhost.local`) | `avahi-daemon`, `avahi-utils` | `deploy/scripts/install-avahi.sh` | aus |

RAID und SMART teilen sich eine sudoers-Datei (`/etc/sudoers.d/baluhost-hardware`);
der Installer rendert sie einmalig, sobald eines der beiden aktiviert wird.

## Features aktivieren

### Während der Installation (interaktiv)

Der Installer fragt je Feature, ob es aktiviert werden soll. Mit `y` werden die
Pakete installiert und das jeweilige Setup ausgeführt.

### Nicht-interaktiv / nach der Installation

Die entsprechenden Flag(s) in `/etc/baluhost/install.conf` setzen und das
Optional-Features-Modul erneut ausführen:

```bash
# /etc/baluhost/install.conf
ENABLE_RAID=true
ENABLE_VPN=true
```

```bash
sudo /opt/baluhost/deploy/install/install.sh --module 14-optional-features
```

Verfügbare Flags: `ENABLE_RAID`, `ENABLE_SMART`, `ENABLE_VPN`, `ENABLE_CLOUD`,
`ENABLE_SAMBA`, `ENABLE_NFS`, `ENABLE_WSDD`, `ENABLE_MDNS`. Nicht gesetzt = `false`.

### Manuelle Alternative

Jedes Setup-Skript kann direkt (als root) ausgeführt werden, z. B.:

```bash
sudo SERVICE_USER=<baluhost-user> STORAGE_GROUP=<baluhost-group> \
    bash /opt/baluhost/deploy/samba/setup-samba.sh
```

## Hinweise pro Feature

- **RAID / SMART** — das Backend nutzt `mdadm` und `smartctl`; ohne diese beiden
  zeigen die RAID- und Festplattengesundheits-Seiten keine Daten. Die gemeinsame
  Hardware-sudoers-Datei gewährt dem Service-Benutzer die benötigten Befehle.
- **VPN** — `wireguard-tools` stellt `wg`/`wg-quick` bereit; `setup-wireguard.sh`
  installiert die befehlsspezifische sudoers-Datei und aktiviert IP-Forwarding.
  Für das WireGuard-Kernel-Modul kann ein Neustart erforderlich sein.
- **Cloud-Import** — nur `rclone`; keine sudoers, läuft als Service-Benutzer.
- **Samba / NFS** — jedes Setup-Skript installiert sein Paket, schreibt eine
  gehärtete Konfiguration, erstellt die Freigabe-/Export-Konfiguration im Besitz
  des Service-Benutzers und installiert eine eingeschränkte sudoers-Datei.
- **WS-Discovery / mDNS** — macht BaluHost im Windows Explorer bzw. für
  Bonjour/Zeroconf-Clients auffindbar.

## Aktiviertes Feature prüfen

Nach der Aktivierung Paket und (sofern zutreffend) den Service bestätigen:

```bash
dpkg -s mdadm | grep Status        # Paket installiert
systemctl status smbd              # Samba läuft (SAMBA)
sudo -n -u <baluhost-user> wg show  # VPN sudoers vorhanden (VPN)
```
