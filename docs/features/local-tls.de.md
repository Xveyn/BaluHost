# Feste Adresse im Heimnetz (Plugin `local_tls`)

Das Plugin hält einen DuckDNS-Namen (z. B. `meinnas.duckdns.org`) auf der
LAN-IP der Box und besorgt dafür ein echtes Let's-Encrypt-Zertifikat per
DNS-01 (`lego`). Der Browser vertraut dem Zertifikat ohne Warnung, obwohl die
Box nie aus dem Internet erreichbar sein muss. Das Plugin ist standardmäßig
**aus**.

## Voraussetzungen

- Eine Domain bei DuckDNS und das zugehörige Token.
- `lego` ab Version 4.35 (Debian 13: `trixie-backports`):
  `sudo apt install -t trixie-backports lego`. Der Installer erledigt das
  optional mit `ENABLE_LEGO=true` (Modul `14-optional-features`).
- `nginx` läuft bereits mit HTTPS (`deploy/nginx/baluhost-https.conf`).
- Eine E-Mail-Adresse für Let's Encrypt ist optional (lego ≥ 4.30).

## Einrichtung

1. Plugin aktivieren (Einstellungen → Plugins).
2. In den Plugin-Einstellungen Domain und Anbieter setzen (optional:
   Netzwerkschnittstelle, E-Mail, `staging` zum Testen).
3. Einstellungen → Integrationen → Karte „Feste Adresse im Heimnetz“: DuckDNS-Token
   speichern. Das Token wird verschlüsselt abgelegt und nie wieder angezeigt.
4. „Jetzt erneuern“ drücken. Das Zertifikat wird ausgestellt und unter
   `/var/lib/baluhost/plugins/local_tls/live/` abgelegt.
5. Die Karte zeigt „nginx liefert es noch nicht aus“ und das passende
   nginx-Snippet. nginx umstellen (siehe unten).

Mit `staging` lässt sich der Ablauf gegen die Let's-Encrypt-Testumgebung
prüfen (eigener lego-Zustand, Zertifikat wird nicht vertraut). Wechsel zurück
auf Produktion stellt neu aus.

## nginx umstellen

In **beiden** TLS-Blöcken (`:443` und `:8443`) den `server_name` um die Domain
ergänzen und die Zertifikatspfade ersetzen:

```nginx
server_name meinnas.duckdns.org <bisherige Namen>;
ssl_certificate     /var/lib/baluhost/plugins/local_tls/live/fullchain.pem;
ssl_certificate_key /var/lib/baluhost/plugins/local_tls/live/privkey.pem;
```

Dann `sudo nginx -t && sudo systemctl reload nginx`. Die Karte muss danach
„wird ausgeliefert“ zeigen. Hinweis: Auf BaluNode ist `sites-enabled/baluhost`
eine eigene Datei neben `sites-available/baluhost` — beide anpassen.

## Was im Hintergrund passiert

- Alle 300 s prüft das Plugin die LAN-IP und aktualisiert DuckDNS bei Änderung,
  außerdem einmal täglich zur Bestätigung.
- Täglich (und beim Start, mit bis zu 60 s Wartezeit auf den Lauf-Lock) prüft es
  das Zertifikat: `lego run` bei der Erstausstellung, sonst `renew --days 30`.
- Ein neues Zertifikat landet in `releases/<UTC-Zeitstempel>/`, `live` zeigt
  atomar darauf; die letzten 3 Releases bleiben. Danach lädt das Plugin nginx
  über das bestehende `sudo -n /usr/bin/systemctl reload nginx`. Keine neue
  sudoers-Regel.
- Erster Einsatz bzw. nginx noch nicht umgestellt: das Zertifikat wird nur
  installiert, kein Rollback. Ein Rollback gibt es nur, wenn nginx vorher das
  frühere Zertifikat des Plugins auslieferte und nach dem Reload nicht mehr
  ausliefert.
- Weicht der Fingerabdruck des lego-Zertifikats vom installierten ab, wird neu
  ausgeliefert — fehlgeschlagene Auslieferungen werden also täglich wiederholt.
- Benachrichtigungen an Admins: `cert_expiring` (ab 21 Tagen vor Ablauf),
  `renew_failed`, `dns_update_failed`, `address_changed`; mit Abklingzeiten,
  die nach einem Neustart zurückgesetzt sind.

## Ablösung auf BaluNode

Das bisherige certbot-Zertifikat für `baluhost.duckdns.org` gilt bis
2027-02-23.

1. lego installieren (`sudo apt install -t trixie-backports lego`).
2. Plugin aktivieren, Domain und Anbieter in den Plugin-Einstellungen setzen.
3. Token unter Einstellungen → Integrationen speichern.
4. „Jetzt erneuern“.
5. nginx umstellen (beide TLS-Blöcke `:443`/`:8443` samt `server_name`;
   `sites-enabled` und `sites-available` beachten), `nginx -t`, Reload.
6. Prüfen: Karte zeigt „wird ausgeliefert“.
7. Alte certbot-Erneuerung für `baluhost.duckdns.org` stilllegen und das
   pipx-certbot entfernen.

## DNS-Rebind-Schutz

Fritz!Boxen verwerfen DNS-Antworten, die auf private IPs zeigen. Ohne Pi-hole
die Domain in der Fritz!Box als Ausnahme eintragen (Heimnetz → Netzwerk →
Netzwerkeinstellungen → DNS-Rebind-Schutz).

## Fehlerbilder

| Karte zeigt | Ursache / Abhilfe |
|---|---|
| lego fehlt / zu alt | `sudo apt install -t trixie-backports lego` |
| Token „nicht gesetzt“ | Token in der Karte speichern |
| „Kein Schlüssel konfiguriert“ | `VPN_ENCRYPTION_KEY` fehlt; das Token wird sonst nicht gespeichert |
| „Ein Lauf läuft bereits“ | Kurz warten, erneut versuchen |
| „nginx liefert es noch nicht aus“ | nginx-Snippet übernehmen und neu laden |
| Browser findet die Domain nicht | DNS-Rebind-Schutz (siehe oben) |

## Sicherheit

Nur Admins erreichen die Routen. Das Token wird mit Fernet verschlüsselt und
weder zurückgegeben noch geloggt oder auditiert. Der Dienstnutzer kann die
nginx-Site grundsätzlich selbst umschreiben (#862); das Plugin ändert daran
nichts. Echte Secret-Felder in der generischen Plugin-Konfiguration sind #863.
