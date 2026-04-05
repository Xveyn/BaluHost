# WebDAV-Netzlaufwerk

Binden Sie Ihren BaluHost-Speicher als Netzlaufwerk unter Windows, macOS und Linux ein.

## Architektur

Der WebDAV-Server laeuft als **separater Worker-Prozess** neben dem Haupt-Backend:

```
┌─────────────────────┐     ┌─────────────────────────┐
│  FastAPI Backend     │     │  WebDAV Worker           │
│  (Uvicorn, Port 8000)│     │  (cheroot WSGI, Port 8080)│
│                     │     │                         │
│  /api/webdav/status ─┼──── │  webdav_state (DB)      │
│  /api/webdav/        │ IPC │                         │
│    connection-info   │     │  WsgiDAV + BaluHost Auth│
└─────────────────────┘     └─────────────────────────┘
```

- **Server**: cheroot WSGI mit einer WsgiDAV-Anwendung
- **Authentifizierung**: HTTP Basic Auth, validiert gegen die BaluHost-Benutzerdatenbank (bcrypt)
- **Benutzerisolierung**: Administratoren sehen den gesamten Speicher, normale Benutzer nur `<storage>/<benutzername>/`
- **IPC**: Der Worker schreibt alle 10 Sekunden einen Heartbeat in die Tabelle `webdav_state`; die Web-API liest diesen fuer den Status
- **SSL**: Selbstsigniertes Zertifikat wird beim ersten Start automatisch generiert (standardmaessig aktiviert)

## Konfiguration

Umgebungsvariablen (oder `Settings` in `backend/app/core/config.py`):

| Variable | Standard | Beschreibung |
|---|---|---|
| `WEBDAV_ENABLED` | `true` | WebDAV-Server aktivieren/deaktivieren |
| `WEBDAV_PORT` | `8080` | Listening-Port |
| `WEBDAV_SSL_ENABLED` | `true` | HTTPS mit selbstsigniertem Zertifikat |
| `WEBDAV_VERBOSE_LOGGING` | `false` | Jeden Request protokollieren (Methode, Pfad, Auth) |

## Server starten

### Entwicklung

```bash
python start_dev.py
# Startet Backend, Scheduler, WebDAV-Worker und Frontend
```

Der WebDAV-Worker wird automatisch als Unterprozess gestartet.

### Produktion

**Systemd-Service** (`deploy/systemd/baluhost-webdav.service`):

```bash
sudo systemctl enable baluhost-webdav
sudo systemctl start baluhost-webdav

# Status pruefen
sudo systemctl status baluhost-webdav
sudo journalctl -u baluhost-webdav -f
```

Oder ueber den Launcher:

```bash
python start_prod.py    # Startet Backend + Scheduler + WebDAV
python kill_prod.py     # Stoppt alles
```

## Verbindung von Clients

Verwenden Sie Ihre **BaluHost-Anmeldedaten** (Benutzername + Passwort). Der WebDAV-Tab in der BaluHost-Oberflaeche (System Control Page) zeigt die genauen Befehle fuer Ihren Benutzernamen an.

Standard-Verbindungs-URL: `https://<NAS-IP>:8080/`

### Windows

#### Methode 1: Kommandozeile

```cmd
net use Z: https://192.168.178.53:8080/ /user:admin *
```

#### Methode 2: Datei-Explorer (GUI)

1. Datei-Explorer oeffnen (Win+E) -> "Dieser PC"
2. "Netzlaufwerk verbinden" in der Symbolleiste anklicken
3. Laufwerksbuchstabe: `Z:` (oder ein anderer verfuegbarer)
4. Ordner: `https://192.168.178.53:8080/`
5. "Verbindung mit anderen Anmeldeinformationen herstellen" aktivieren -> Fertig stellen
6. BaluHost-Benutzername und -Passwort eingeben

#### Windows: SSL-Zertifikat importieren

Bei selbstsignierten Zertifikaten muss das Zertifikat unter Windows importiert werden:

1. `backend/webdav-certs/webdav.crt` vom NAS auf Ihren Windows-PC kopieren
2. Die `.crt`-Datei doppelklicken -> "Zertifikat installieren"
3. Speicherort: **Lokaler Computer**
4. Ablegen in: **Vertrauenswuerdige Stammzertifizierungsstellen**
5. Fertig stellen -> `WebClient`-Dienst neu starten:

```powershell
Restart-Service WebClient
```

#### Windows: WebClient-Dienst

Der `WebClient`-Dienst muss aktiv sein:

```powershell
# Status pruefen
Get-Service WebClient

# Starten und Autostart einrichten
Start-Service WebClient
Set-Service WebClient -StartupType Automatic
```

#### Windows: Performance-Optimierung

```powershell
# Dateigroessenlimit erhoehen (Standard 50 MB -> 4 GB)
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\WebClient\Parameters" `
  -Name "FileSizeLimitInBytes" -Value 4294967295

Restart-Service WebClient
```

### macOS

#### Finder (GUI)

1. Finder -> Gehe zu -> Mit Server verbinden (Cmd+K)
2. Eingeben: `https://192.168.178.53:8080/`
3. "Verbinden" klicken
4. "Registrierter Benutzer" waehlen -> BaluHost-Anmeldedaten eingeben
5. Volume wird unter `/Volumes/<hostname>` eingebunden

#### Kommandozeile

```bash
sudo mkdir -p /Volumes/baluhost
mount -t webdav https://192.168.178.53:8080/ /Volumes/baluhost
```

#### .DS_Store auf Netzwerk-Volumes deaktivieren

```bash
defaults write com.apple.desktopservices DSDontWriteNetworkStores -bool TRUE
```

### Linux

#### davfs2 installieren

```bash
# Debian/Ubuntu
sudo apt install davfs2

# Fedora/RHEL
sudo dnf install davfs2

# Arch
sudo pacman -S davfs2
```

#### Einbinden

```bash
sudo mkdir -p /mnt/baluhost
sudo mount -t davfs https://192.168.178.53:8080/ /mnt/baluhost
# Benutzername + Passwort bei Aufforderung eingeben
```

#### Selbstsigniertes Zertifikat vertrauen

Folgendes in `/etc/davfs2/davfs2.conf` eintragen:

```
trust_server_cert /path/to/webdav.crt
```

Oder das Zertifikat in den System-Zertifikatsspeicher kopieren:

```bash
sudo cp webdav.crt /usr/local/share/ca-certificates/baluhost-webdav.crt
sudo update-ca-certificates
```

#### Permanentes Einbinden (fstab)

```bash
# Anmeldedaten hinterlegen
echo "https://192.168.178.53:8080/ admin yourpassword" | sudo tee -a /etc/davfs2/secrets
sudo chmod 600 /etc/davfs2/secrets

# In fstab eintragen
echo "https://192.168.178.53:8080/ /mnt/baluhost davfs user,noauto,uid=1000,gid=1000 0 0" | sudo tee -a /etc/fstab

# Einbinden (nach fstab-Eintrag kein sudo noetig)
mount /mnt/baluhost
```

## SSL / HTTPS

SSL ist **standardmaessig aktiviert**. Beim ersten Start generiert der WebDAV-Worker automatisch ein selbstsigniertes Zertifikat:

- **Speicherort**: `backend/webdav-certs/webdav.crt` + `webdav.key`
- **Gueltigkeit**: 10 Jahre
- **SAN**: `localhost`, `127.0.0.1` und die erkannte LAN-IP des Servers
- **Algorithmus**: RSA 2048-Bit, SHA256

Um das Zertifikat neu zu generieren (z. B. nach IP-Aenderung):

```bash
rm -rf backend/webdav-certs/
sudo systemctl restart baluhost-webdav
```

Um SSL zu deaktivieren:

```bash
export WEBDAV_SSL_ENABLED=false
```

## Benutzerisolierung

Die Zugriffskontrolle wird pro Anfrage im `BaluHostDAVProvider` durchgesetzt:

| Rolle | Sichtbar | Pfad |
|---|---|---|
| `admin` | Gesamter Speicher | `<NAS_STORAGE_PATH>/` |
| `user` | Nur eigenes Home-Verzeichnis | `<NAS_STORAGE_PATH>/<benutzername>/` |

- Home-Verzeichnisse werden beim ersten WebDAV-Zugriff automatisch erstellt
- Path-Traversal wird durch `os.path.normpath()`-Validierung verhindert
- Thread-sicher: Der Benutzerkontext wird pro Anfrage aus der WSGI-Umgebung gelesen

## API-Endpunkte

### `GET /api/webdav/status` (Nur Administratoren)

Gibt detaillierten Serverstatus inklusive Heartbeat und PID zurueck.

```json
{
  "is_running": true,
  "port": 8080,
  "ssl_enabled": true,
  "started_at": "2026-02-14T10:30:00+00:00",
  "worker_pid": 12345,
  "last_heartbeat": "2026-02-14T10:35:45+00:00",
  "error_message": null,
  "connection_url": "https://192.168.178.53:8080/"
}
```

### `GET /api/webdav/connection-info` (Authentifizierte Benutzer)

Gibt betriebssystemspezifische Mount-Anleitungen mit dem Benutzernamen des aktuellen Benutzers zurueck.

```json
{
  "is_running": true,
  "port": 8080,
  "ssl_enabled": true,
  "username": "admin",
  "connection_url": "https://192.168.178.53:8080/",
  "instructions": [
    {
      "os": "windows",
      "label": "Windows",
      "command": "net use Z: https://192.168.178.53:8080/ /user:admin *",
      "notes": "Or use File Explorer..."
    }
  ]
}
```

## Zustandsueberwachung

Der WebDAV-Server registriert sich im Service-Status-System von BaluHost:

- Heartbeat-Intervall: **10 Sekunden**
- Veraltungsschwelle: **30 Sekunden** (kein Heartbeat = gilt als offline)
- Sichtbar in: Admin-Dashboard -> Services-Tab
- Systemd: Automatischer Neustart bei Absturz (`Restart=always`, `RestartSec=10s`)

## Frontend-Oberflaeche

Der WebDAV-Tab ist Teil der **System Control Page** (`client/src/pages/SystemControlPage.tsx`):

- `WebdavConnectionCard` -- zeigt Status, Verbindungs-URL und betriebssystemspezifische Mount-Anleitungen mit Kopier-Buttons
- Bezieht Daten von `/api/webdav/connection-info`
- i18n-Schluessel: `system.webdav.*` (Englisch + Deutsch)

## Wichtige Dateien

| Datei | Zweck |
|---|---|
| `backend/app/core/config.py` | Konfiguration (Port, SSL, aktiviert) |
| `backend/scripts/webdav_worker.py` | Worker-Einstiegspunkt |
| `backend/app/services/webdav_service.py` | cheroot-Server, SSL-Zertifikatsgenerierung, Heartbeat |
| `backend/app/compat/webdav_asgi.py` | WsgiDAV-App, Auth-Controller |
| `backend/app/compat/webdav_provider.py` | Storage-Provider mit Benutzerisolierung |
| `backend/app/api/routes/webdav.py` | REST-API-Endpunkte |
| `backend/app/schemas/webdav.py` | Pydantic-Antwortmodelle |
| `backend/app/models/webdav_state.py` | Datenbankmodell |
| `deploy/systemd/baluhost-webdav.service` | Systemd-Unit-Datei |
| `client/src/components/webdav/WebdavConnectionCard.tsx` | Frontend-Komponente |
| `client/src/api/webdav.ts` | Frontend-API-Client |

## Fehlerbehebung

### Server startet nicht

```bash
# Pruefen, ob Port 8080 bereits belegt ist
ss -tlnp | grep 8080

# Worker-Logs pruefen
journalctl -u baluhost-webdav --no-pager -n 50
```

### Windows Fehler 67: "Der Netzwerkname wurde nicht gefunden"

1. Stellen Sie sicher, dass der WebDAV-Worker auf dem NAS laeuft
2. Stellen Sie sicher, dass der `WebClient`-Dienst unter Windows aktiv ist
3. Bei Verwendung von HTTP (nicht HTTPS): `BasicAuthLevel` auf `2` setzen:
   ```powershell
   Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\WebClient\Parameters" -Name "BasicAuthLevel" -Value 2
   Restart-Service WebClient
   ```

### Windows: Zertifikatsfehler bei selbstsigniertem Zertifikat

Importieren Sie `webdav.crt` in die vertrauenswuerdigen Stammzertifizierungsstellen (siehe [SSL-Zertifikat importieren](#windows-ssl-zertifikat-importieren) oben).

### macOS: "Verbindung fehlgeschlagen"

Versuchen Sie die IP-Adresse anstelle des Hostnamens. Pruefen Sie, ob der Server erreichbar ist:

```bash
curl -k https://192.168.178.53:8080/
```

### Linux: mount.davfs schlaegt mit SSL-Fehler fehl

Fuegen Sie die `trust_server_cert`-Direktive in davfs2.conf hinzu oder installieren Sie das Zertifikat systemweit (siehe [Linux-SSL-Abschnitt](#selbstsigniertes-zertifikat-vertrauen) oben).

### Veralteter Status in der Oberflaeche (zeigt "Nicht aktiv" obwohl der Worker laeuft)

Der Heartbeat ist moeglicherweise veraltet. Starten Sie den Worker neu:

```bash
sudo systemctl restart baluhost-webdav
```

### SSL-Zertifikat neu generieren

```bash
rm -rf backend/webdav-certs/
sudo systemctl restart baluhost-webdav
# Neues Zertifikat wird mit aktueller LAN-IP im SAN generiert
```
