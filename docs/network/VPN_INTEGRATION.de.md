# VPN (WireGuard) einrichten

BaluHost integriert WireGuard VPN für sicheren Fernzugriff auf Ihr NAS — auch von unterwegs.

## Voraussetzungen

- WireGuard muss auf dem Server installiert sein (Produktion)
- Admin-Zugang zu BaluHost
- WireGuard-App auf dem Client-Gerät (Windows, macOS, Linux, Android, iOS)

## VPN-Client erstellen

1. Melden Sie sich als Admin an
2. Navigieren Sie zu **VPN** in der Seitenleiste
3. Klicken Sie auf **"Client hinzufügen"**
4. Vergeben Sie einen Namen für den Client (z.B. "Laptop-Arbeit", "Handy")
5. Die Konfiguration wird automatisch generiert

### Konfiguration übertragen

**Per QR-Code (Mobile):**
- Der QR-Code wird direkt angezeigt
- WireGuard-App öffnen → "Tunnel hinzufügen" → "QR-Code scannen"

**Per Datei (Desktop):**
- Klicken Sie auf "Konfiguration herunterladen"
- Die `.conf`-Datei in der WireGuard-App importieren

## Netzwerk-Konfiguration

| Einstellung | Standardwert |
|-------------|-------------|
| **Subnetz** | 10.8.0.0/24 |
| **DNS** | Wird vom Server übernommen |
| **Endpoint** | Server-IP bzw. DynDNS-Adresse |
| **Keepalive** | 25 Sekunden |

Jeder Client erhält automatisch eine eigene IP-Adresse im VPN-Subnetz.

## Client-Verwaltung

Auf der VPN-Seite können Sie:

- **Clients auflisten** — Alle registrierten VPN-Clients mit Status
- **Client bearbeiten** — Name und Einstellungen ändern
- **Client löschen** — Zugang widerrufen
- **QR-Code erneut anzeigen** — Für erneute Einrichtung

## Mobile App Integration

Bei der Geräte-Registrierung über QR-Code (BaluApp) kann die VPN-Konfiguration direkt eingebettet werden:

1. Geräte-Seite → "Neues Gerät registrieren"
2. Option **"VPN-Konfiguration einschließen"** aktivieren
3. QR-Code mit der BaluApp scannen
4. VPN wird automatisch in der App konfiguriert

## Sicherheit

- Alle VPN-Schlüssel werden verschlüsselt gespeichert (Fernet/AES-128-CBC)
- Jeder Client hat ein eigenes Schlüsselpaar (Private Key + Public Key)
- Preshared Keys für zusätzliche Sicherheit
- Private Keys werden niemals in API-Antworten oder Logs offengelegt
- Verschlüsselung erfordert die Umgebungsvariable `VPN_ENCRYPTION_KEY`

## Fritz!Box als VPN-Server

Falls Ihre Fritz!Box als WireGuard-Server dient:

1. Fritz!Box-Oberfläche → Internet → Freigaben → VPN (WireGuard)
2. Verbindung einrichten → "Einzelgerät verbinden"
3. Konfigurationsdatei herunterladen
4. In BaluHost oder direkt in der WireGuard-App importieren

## Fehlerbehebung

### VPN verbindet nicht

1. Prüfen Sie, ob der WireGuard-Dienst auf dem Server läuft
2. Firewall: Port des Endpoints muss offen sein (Standard: 51820/UDP)
3. Endpoint-Adresse korrekt? (DynDNS oder öffentliche IP)
4. Uhrzeit auf Client und Server synchron?

### Verbindung steht, aber kein Zugriff

1. Prüfen Sie die AllowedIPs in der Client-Konfiguration
2. DNS-Auflösung testen: `nslookup baluhost.local`
3. IP-Routing auf dem Server prüfen (`ip forwarding` aktiviert?)

### Langsame Verbindung

1. Keepalive zu niedrig kann bei NAT-Traversal helfen (Standard: 25s)
2. MTU-Probleme: In der WireGuard-Config MTU auf 1280 setzen

---

**Version:** 1.23.0  
**Letzte Aktualisierung:** April 2026
