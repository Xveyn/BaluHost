# Plan: Fix Samba — BaluHost smb.conf deployen

## Kontext

wsdd2 funktioniert jetzt (BaluHost im Windows-Netzwerk sichtbar), aber beim Zugriff über Windows Explorer wird man als "nobody" angezeigt und kann sich nicht anmelden — weder als Linux-Root noch als BaluHost-Admin.

**Ursache**: `/etc/samba/smb.conf` ist noch die **Debian-Default-Config**, nicht die BaluHost-Config. Das Setup-Script `deploy/samba/setup-samba.sh` wurde nie ausgeführt.

Kritische Unterschiede:
| Setting | Debian-Default (aktuell) | BaluHost-Template (Soll) |
|---------|--------------------------|--------------------------|
| `map to guest` | `bad user` → **erlaubt Guest-Fallback = "nobody"** | `never` |
| `security` | `server role = standalone server` | `security = user` |
| `include` | fehlt | `include = /etc/samba/baluhost-shares.conf` |
| Shares | `[homes]`, `[printers]`, `[print$]` | nur via `baluhost-shares.conf` |

Zusätzlich: **Keine Samba-User existieren** (`pdbedit -L` = leer). Selbst mit korrekter Config gäbe es niemanden zum Authentifizieren.

## Lösung — Keine Code-Änderung nötig

Die Dateien in `deploy/samba/` sind bereits korrekt. Es fehlt nur die Ausführung auf dem Prod-Server.

### Schritt 1: Setup-Script ausführen

```bash
sudo bash ~/projects/BaluHost/deploy/samba/setup-samba.sh
```

Das Script macht:
1. Backup der aktuellen smb.conf
2. Kopiert `deploy/samba/smb.conf` → `/etc/samba/smb.conf`
3. Erstellt leere `baluhost-shares.conf` (existiert bereits → wird überschrieben, aber egal)
4. Installiert sudoers-Datei (`smbpasswd`, `smbcontrol`, etc. ohne Passwort)
5. `systemctl enable smbd && systemctl restart smbd`

### Schritt 2: SMB-User in BaluHost-UI aktivieren

In der BaluHost-Web-UI unter **System Control → SMB/CIFS**:
- Admin-User: SMB aktivieren + Passwort setzen
- Das Backend ruft `smbpasswd -a -s <user>` auf und schreibt `baluhost-shares.conf`

### Schritt 3: (Falls UI nicht bereit) Manuell Samba-User anlegen

```bash
sudo smbpasswd -a admin
# Passwort eingeben (2x)
```

## Verifikation

```bash
# 1. Config korrekt?
sudo testparm -s /etc/samba/smb.conf 2>/dev/null | grep "map to guest"
# → "map to guest = Never"

# 2. Samba läuft?
systemctl is-active smbd
# → active

# 3. Samba-User vorhanden?
sudo pdbedit -L
# → admin:...:...

# 4. Share erreichbar?
smbclient -L localhost -U admin
# → zeigt [BaluHost] Share

# 5. Windows: Netzlaufwerk verbinden
# net use Z: \\<IP>\BaluHost /user:admin
```

## Status

- [ ] Setup-Script ausführen
- [ ] Samba-User anlegen
- [ ] Verifikation
