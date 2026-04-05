# Client mDNS Einrichtungsanleitung

Diese Anleitung erklärt, wie Sie verschiedene Client-Geräte (Windows, Mac, Linux, Mobilgeräte) konfigurieren, um auf BaluHost über den Hostnamen `baluhost.local` statt über IP-Adressen zuzugreifen.

## Inhaltsverzeichnis

- [Übersicht](#übersicht)
- [Server-Voraussetzungen](#server-voraussetzungen)
- [Client-Einrichtung nach Plattform](#client-einrichtung-nach-plattform)
  - [Mac/macOS](#macmacos)
  - [Linux](#linux)
  - [Windows](#windows)
  - [iOS (iPhone/iPad)](#ios-iphoneipad)
  - [Android](#android)
- [Fehlerbehebung](#fehlerbehebung)
- [mDNS-Auflösung testen](#mdns-auflösung-testen)

---

## Übersicht

**Was ist mDNS?**

mDNS (Multicast DNS) ist ein Protokoll, das es Geräten in einem lokalen Netzwerk ermöglicht, sich gegenseitig über `.local`-Hostnamen zu finden, ohne einen DNS-Server zu benötigen. Es ist auch bekannt als:
- **Bonjour** (Apples Implementierung)
- **Avahi** (Linux-Implementierung)
- **Zeroconf** (Zero-Configuration Networking)

**Warum mDNS verwenden?**

Anstatt auf BaluHost über folgende Adresse zuzugreifen:
```
http://192.168.1.100:5173
```

Können Sie einen benutzerfreundlichen Hostnamen verwenden:
```
http://baluhost.local
```

Dies erleichtert den Zugriff und macht es überflüssig, sich IP-Adressen zu merken. Besonders nützlich, wenn:
- Sich die Server-IP ändert (DHCP)
- Sie mehrere Geräte haben, die auf BaluHost zugreifen
- Sie Lesezeichen/Verknüpfungen möchten, die immer funktionieren

---

## Server-Voraussetzungen

Bevor Sie Clients konfigurieren, stellen Sie sicher, dass mDNS auf dem BaluHost-Server aktiviert ist:

1. **Server-Betriebssystem**: Linux (empfohlen für den Produktivbetrieb)
2. **Avahi installiert**: Führen Sie `deploy/scripts/install-avahi.sh` oder `deploy/scripts/setup-hostname.sh` aus
3. **Backend konfiguriert**: `MDNS_HOSTNAME=baluhost` in `.env` (Standardwert)
4. **Netzwerkerkennung aktiviert**: Startet automatisch mit dem BaluHost-Backend

Überprüfen Sie, ob der Server mDNS sendet:
```bash
# Auf dem Server
avahi-browse -a -t | grep baluhost
```

---

## Client-Einrichtung nach Plattform

### Mac/macOS

**Funktioniert automatisch** - macOS hat native Bonjour-Unterstützung integriert.

#### Überprüfung

```bash
# Hostname-Auflösung testen
ping baluhost.local

# Verfügbare Dienste durchsuchen
dns-sd -B _baluhost._tcp local.
```

#### Auf BaluHost zugreifen

Öffnen Sie Ihren Browser und navigieren Sie zu:
```
http://baluhost.local
```

Im Produktivbetrieb liefert Nginx alles über Port 80 aus. Kein Port in der URL erforderlich.

---

### Linux

**Funktioniert automatisch** - Die meisten modernen Linux-Distributionen enthalten Avahi standardmäßig.

#### Prüfen, ob Avahi installiert ist

```bash
# Prüfen, ob avahi-daemon läuft
systemctl status avahi-daemon

# Falls nicht installiert:
sudo apt install avahi-daemon avahi-utils  # Debian/Ubuntu
sudo dnf install avahi avahi-tools         # Fedora/RHEL
sudo pacman -S avahi nss-mdns              # Arch
```

#### NSS-mDNS aktivieren (falls nötig)

Einige Distributionen benötigen NSS-mDNS für die `.local`-Auflösung:

```bash
# /etc/nsswitch.conf bearbeiten
sudo nano /etc/nsswitch.conf

# Stellen Sie sicher, dass die "hosts"-Zeile "mdns4_minimal" enthält:
hosts: files mdns4_minimal [NOTFOUND=return] dns mdns4

# Avahi neu starten
sudo systemctl restart avahi-daemon
```

#### Überprüfung

```bash
# Hostname-Auflösung testen
ping baluhost.local

# Dienste durchsuchen
avahi-browse -a -t | grep baluhost
```

#### Auf BaluHost zugreifen

```
http://baluhost.local
```

---

### Windows

**Funktioniert standardmäßig nicht** - Windows enthält keine native mDNS-Unterstützung.

Sie haben **drei Möglichkeiten**:

---

#### Option 1: Bonjour Print Services installieren (Empfohlen)

Dies ist der offizielle Apple mDNS-Client für Windows.

**Download**:
- [Bonjour Print Services für Windows](https://support.apple.com/kb/DL999)
- Offizieller Apple-Download (kostenlos, ~2 MB)

**Installation**:
1. Laden Sie das Installationsprogramm herunter und führen Sie es aus
2. Folgen Sie dem Installationsassistenten
3. Starten Sie Ihren Computer neu (empfohlen)
4. Test: `ping baluhost.local` in der Eingabeaufforderung

**Vorteile**:
- Offizielle Apple-Implementierung
- Funktioniert systemweit für alle Anwendungen
- Automatisch, keine manuelle Konfiguration

**Nachteile**:
- Erfordert Administratorrechte zur Installation
- Zusätzliche Softwareabhängigkeit

---

#### Option 2: Manueller Hosts-Datei-Eintrag (Einfache Alternative)

Fügen Sie einen statischen Eintrag in die Windows-Hosts-Datei ein, um `baluhost.local` aufzulösen.

**Schritte**:

1. **BaluHost-Server-IP-Adresse ermitteln**:
   - Auf dem Server: `ip addr show | grep "inet "`
   - Oder DHCP-Leases im Router prüfen
   - Beispiel: `192.168.1.100`

2. **Hosts-Datei als Administrator bearbeiten**:
   ```powershell
   # Notepad als Administrator öffnen
   notepad C:\Windows\System32\drivers\etc\hosts
   ```

3. **Eintrag hinzufügen**:
   ```
   # BaluHost mDNS Hostname
   192.168.1.100  baluhost baluhost.local
   ```

4. **Speichern und schließen**

5. **Testen**:
   ```powershell
   ping baluhost
   ping baluhost.local
   ```

**Vorteile**:
- Keine zusätzliche Software erforderlich
- Schnell und einfach
- Funktioniert sofort

**Nachteile**:
- Manuelle Aktualisierung nötig, wenn sich die Server-IP ändert
- Erfordert Administratorrechte zum Bearbeiten
- Muss auf jedem Windows-PC konfiguriert werden

---

#### Option 3: Router-DNS-Konfiguration (Am besten für mehrere Geräte)

Konfigurieren Sie Ihren Router, um dem BaluHost-Server einen Hostnamen zuzuweisen.

**Schritte** (variiert je nach Router-Modell):

1. **Router-Administrationsoberfläche aufrufen**:
   - Häufige Adressen: `192.168.1.1`, `192.168.0.1`, `192.168.178.1`

2. **DHCP-Einstellungen** oder **Statische Leases** finden

3. **DHCP-Reservierung erstellen**:
   - MAC-Adresse: (MAC-Adresse der Netzwerkkarte des BaluHost-Servers)
   - IP-Adresse: `192.168.1.100` (wählen Sie eine statische IP)
   - Hostname: `baluhost`

4. **Speichern und Router neu starten** (falls erforderlich)

5. **Von Windows aus testen**:
   ```powershell
   ping baluhost
   ```

**Vorteile**:
- Funktioniert automatisch für alle Geräte im Netzwerk
- Keine clientseitige Konfiguration erforderlich
- IP bleibt statisch

**Nachteile**:
- Routerspezifische Konfiguration
- Erfordert Router-Administratorzugang
- Unterstützt möglicherweise nicht das `.local`-Suffix (routerabhängig)

---

### iOS (iPhone/iPad)

**Funktioniert automatisch** - iOS hat native Bonjour-Unterstützung.

#### Auf BaluHost zugreifen

1. Öffnen Sie Safari (oder einen anderen Browser)
2. Navigieren Sie zu: `http://baluhost.local`
3. Lesezeichen setzen für einfachen Zugriff

#### Überprüfung

Sie können Netzwerk-Utility-Apps verwenden, um mDNS-Dienste zu überprüfen:
- [Discovery - DNS-SD Browser](https://apps.apple.com/app/discovery-dns-sd-browser/id1381004916) (Kostenlos)

**Hinweis**: Die BaluHost-Mobile-App enthält eine automatische Servererkennung und erfordert keine manuelle Hostname-Konfiguration.

---

### Android

**Variiert je nach Version und Hersteller**

- **Android 5.0 (Lollipop) und höher**: Unterstützt mDNS im Allgemeinen
- **Ältere Versionen**: Unterstützen möglicherweise keine `.local`-Auflösung

#### Unterstützung testen

1. **Netzwerk-Utilities-App installieren**:
   - [Network Tools](https://play.google.com/store/apps/details?id=net.he.networktools) (Kostenlos)
   - [Network Discovery](https://play.google.com/store/apps/details?id=info.lamatricexiste.network) (Kostenlos)

2. **Ping-Test versuchen**:
   ```
   ping baluhost.local
   ```

3. **Falls es funktioniert**: Verwenden Sie `http://baluhost.local` im Browser

4. **Falls es nicht funktioniert**: Verwenden Sie die IP-Adresse oder konfigurieren Sie über Router-DNS

#### Alternative: IP-Adresse verwenden

Die BaluHost-Mobile-App ermöglicht die manuelle Servereingabe per IP:
```
http://192.168.1.100
```

---

## Fehlerbehebung

### `baluhost.local` kann nicht aufgelöst werden

**Symptome**: `ping baluhost.local` schlägt fehl mit "Unknown host" oder "Name not found"

**Lösungen**:

1. **Überprüfen Sie, ob der Server sendet**:
   ```bash
   # Auf dem BaluHost-Server
   systemctl status avahi-daemon
   avahi-browse -a -t | grep baluhost
   ```

2. **Netzwerkverbindung prüfen**:
   - Sind Client und Server im selben Netzwerk/VLAN?
   - Blockiert die Firewall UDP-Port 5353?

3. **Avahi auf dem Server neu starten**:
   ```bash
   sudo systemctl restart avahi-daemon
   ```

4. **Windows**: Bonjour installieren oder Hosts-Datei verwenden (siehe oben)

5. **Linux**: Stellen Sie sicher, dass `mdns4_minimal` in `/etc/nsswitch.conf` steht

6. **DNS-Suffix prüfen**:
   - Versuchen Sie es ohne `.local`: `ping baluhost`
   - Versuchen Sie es mit explizitem Suffix: `ping baluhost.local.`

---

### Firewall blockiert mDNS

**Symptome**: Server zeigt veröffentlichten Dienst an, aber Clients können ihn nicht finden

**Lösung**:

**Auf dem Server**:
```bash
# mDNS-Verkehr erlauben (UDP-Port 5353)
sudo ufw allow 5353/udp
# ODER
sudo firewall-cmd --permanent --add-service=mdns
sudo firewall-cmd --reload
```

**Auf dem Windows-Client**:
```powershell
# mDNS in der Windows-Firewall erlauben
New-NetFirewallRule -DisplayName "mDNS (UDP-In)" -Direction Inbound -Protocol UDP -LocalPort 5353 -Action Allow
```

---

### Mehrere BaluHost-Server im Netzwerk

**Symptome**: Verwechslung, wenn mehrere Server `baluhost.local` senden

**Lösung**:

Konfigurieren Sie eindeutige Hostnamen pro Server:

1. **`.env` auf jedem Server bearbeiten**:
   ```bash
   # Server 1
   MDNS_HOSTNAME=baluhost1

   # Server 2
   MDNS_HOSTNAME=baluhost2
   ```

2. **Backend neu starten**:
   ```bash
   systemctl restart baluhost-backend
   ```

3. **Zugriff**:
   ```
   http://baluhost1.local
   http://baluhost2.local
   ```

---

### Langsame Hostname-Auflösung

**Symptome**: `ping baluhost.local` braucht 5-10 Sekunden zur Auflösung

**Ursache**: DNS-Server-Timeout bevor auf mDNS zurückgegriffen wird

**Lösung**:

**Linux**: mDNS in `/etc/nsswitch.conf` priorisieren:
```
# Vorher
hosts: files dns mdns4

# Nachher (mDNS priorisieren)
hosts: files mdns4_minimal [NOTFOUND=return] dns mdns4
```

**Windows**: Hosts-Datei für sofortige Auflösung verwenden (siehe Option 2 oben)

---

## mDNS-Auflösung testen

### Serverseitige Tests

```bash
# 1. Avahi-Daemon-Status prüfen
systemctl status avahi-daemon

# 2. Veröffentlichte Dienste auflisten
avahi-browse -a -t -r

# 3. Eigenen Hostnamen auflösen
avahi-resolve -n baluhost.local

# 4. mDNS-Verkehr prüfen (erfordert tcpdump)
sudo tcpdump -i any port 5353
```

### Clientseitige Tests

**Mac/Linux**:
```bash
# Ping-Test
ping -c 4 baluhost.local

# DNS-Abfrage
nslookup baluhost.local
dig baluhost.local

# Avahi durchsuchen (nur Linux)
avahi-browse -r _baluhost._tcp
```

**Windows** (mit installiertem Bonjour):
```powershell
# Ping-Test
ping baluhost.local

# DNS-Abfrage
nslookup baluhost.local
```

---

## Erweitert: Benutzerdefinierte mDNS-Konfiguration

### mDNS-Hostname ändern

Backend-Konfiguration bearbeiten:

**Option 1: Umgebungsvariable**:
```bash
export MDNS_HOSTNAME=mynas
```

**Option 2: `.env`-Datei**:
```env
MDNS_HOSTNAME=mynas
```

**Option 3: Systemweit (über Avahi)**:
```bash
# Avahi-Konfiguration bearbeiten
sudo nano /etc/avahi/avahi-daemon.conf

# Hostname setzen
[server]
host-name=mynas
```

Dienste neu starten:
```bash
sudo systemctl restart avahi-daemon
# BaluHost-Backend neu starten
```

---

## Zusammenfassung

| Plattform | mDNS-Unterstützung | Erforderliche Aktion |
|-----------|--------------------|-----------------------|
| **macOS** | Nativ (Bonjour) | Keine - funktioniert automatisch |
| **Linux** | Nativ (Avahi) | Sicherstellen, dass avahi-daemon läuft |
| **Windows** | Nicht enthalten | Bonjour installieren oder Hosts-Datei verwenden |
| **iOS** | Nativ (Bonjour) | Keine - funktioniert automatisch |
| **Android** | Variiert | Auf Ihrem Gerät testen, Fallback auf IP |

---

## Verwandte Dokumentation

- [DEPLOYMENT.md](./DEPLOYMENT.md) - Produktivbereitstellung mit Nginx
- [../deploy/scripts/install-avahi.sh](../deploy/scripts/install-avahi.sh) - Serverseitige Avahi-Installation
- [../deploy/scripts/setup-hostname.sh](../deploy/scripts/setup-hostname.sh) - Vollständiges Hostname-Setup-Skript

---

## Hilfe

Falls Sie Probleme mit der mDNS-Erkennung haben:

1. Überprüfen Sie zuerst diese Fehlerbehebungsanleitung
2. Stellen Sie sicher, dass der Server mDNS sendet (`avahi-browse -a -t`)
3. Testen Sie von einem Mac/Linux-Gerät aus (bekannte mDNS-Unterstützung)
4. Erstellen Sie ein Issue auf GitHub mit:
   - Client-Betriebssystem und Version
   - Ausgabe von `ping baluhost.local`
   - Serverseitige `avahi-browse`-Ausgabe

---

**Zuletzt aktualisiert**: April 2026
**BaluHost-Version**: 1.23.0
