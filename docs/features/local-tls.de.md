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
  optional mit `ENABLE_LEGO=true` (Modul `14-optional-features`, nur auf
  Debian 13). Danach `lego --version` ausführen und auf der Karte prüfen, dass
  „installiert (4.35…)“ steht — „die Version ließ sich nicht lesen“ heißt, `lego --version`
  liefert keine verwertbare Ausgabe.
- `nginx` läuft bereits mit HTTPS (`deploy/nginx/baluhost-https.conf`).
- Eine E-Mail-Adresse für Let's Encrypt ist optional (lego ≥ 4.30).

## Einrichtung

1. Plugin aktivieren (Einstellungen → Plugins) und danach
   `sudo systemctl restart baluhost-backend` — die Routen des Plugins werden nur
   beim Start eingehängt; ohne Neustart meldet die Karte „Status konnte nicht
   geladen werden“.
2. In den Plugin-Einstellungen Domain und Anbieter setzen (optional:
   Netzwerkschnittstelle, E-Mail, `staging` zum Testen).
3. Einstellungen → Integrationen → Karte „Feste Adresse im Heimnetz“: DuckDNS-Token
   speichern. Das Token wird verschlüsselt abgelegt und nie wieder angezeigt.
4. „Jetzt erneuern“ drücken. Das Zertifikat wird ausgestellt und unter
   `/var/lib/baluhost/plugins/local_tls/live/` abgelegt.
5. Die Karte zeigt „Ausgeliefert von nginx: nein“, als Grund „installiert,
   nginx liefert es noch nicht aus“ und das passende nginx-Snippet. nginx
   umstellen (siehe unten).

Mit `staging` lässt sich der Ablauf gegen die Let's-Encrypt-Testumgebung
prüfen (eigener lego-Zustand, Zertifikat wird nicht vertraut). Wechsel zurück
auf Produktion stellt neu aus.

## nginx umstellen

In **beiden** TLS-Blöcken (`:443` und `:8443`) die Domain an die bestehende
`server_name`-Zeile anhängen (nicht ersetzen) und die Zertifikatspfade ersetzen:

```nginx
server_name meinnas.duckdns.org <bisherige Namen>;
ssl_certificate     /var/lib/baluhost/plugins/local_tls/live/fullchain.pem;
ssl_certificate_key /var/lib/baluhost/plugins/local_tls/live/privkey.pem;
```

Dann `sudo nginx -t && sudo systemctl reload nginx`. Die Karte muss danach
„Ausgeliefert von nginx: ja“ zeigen. Hinweis: Auf BaluNode ist `sites-enabled/baluhost`
eine eigene Datei neben `sites-available/baluhost` — beide anpassen.

## Was im Hintergrund passiert

- Alle 300 s prüft das Plugin die LAN-IP und aktualisiert DuckDNS bei Änderung
  der IP oder der Domain, außerdem einmal täglich zur Bestätigung. Das Ergebnis
  jedes Versuchs (auch ein Fehlschlag samt Grund) steht auf der Karte unter
  „Letzte DNS-Aktualisierung“.
- Täglich (und beim Start, mit bis zu 60 s Wartezeit auf den Lauf-Lock) prüft es
  das Zertifikat: `lego run` bei der Erstausstellung, sonst `renew --days 30`.
- Ein neues Zertifikat landet in `releases/<UTC-Zeitstempel>/`, `live` zeigt
  atomar darauf; die letzten 3 Releases bleiben. Danach lädt das Plugin nginx
  über das bestehende `sudo -n /usr/bin/systemctl reload nginx`. Keine neue
  sudoers-Regel. Weil nginx sanft neu lädt (alte Worker liefern kurz noch das
  alte Zertifikat), fragt das Plugin bis zu 15 s lang ab, was ausgeliefert wird,
  bevor es entscheidet.
- Erster Einsatz bzw. nginx noch nicht umgestellt: das Zertifikat wird nur
  installiert, kein Rollback. Zurückgesetzt (`live` zeigt wieder auf den
  vorigen Release, erneuter Reload) wird in zwei Fällen: (a) nginx lieferte
  vorher das frühere Zertifikat des Plugins aus und liefert nach dem Reload das
  neue auch nach 15 s nicht aus; (b) der nginx-Reload scheitert und es gibt einen vorigen
  Release. Ohne vorigen Release bleibt `live` beim Reload-Fehler stehen und der
  Fehler wird gemeldet.
- Weicht der Fingerabdruck des lego-Zertifikats vom installierten ab, wird neu
  ausgeliefert — fehlgeschlagene Auslieferungen werden also täglich wiederholt.
- Im Entwicklungsmodus (`NAS_MODE=dev`) liegt das Datenverzeichnis unter
  `dev-storage/.system/local_tls`, nginx wird nicht neu geladen und
  „Ausgeliefert von nginx“ bleibt „unbekannt“.
- Benachrichtigungen an Admins: `cert_expiring` (ab 21 Tagen vor Ablauf, auch
  wenn Token oder Domain inzwischen entfernt sind),
  `renew_failed`, `dns_update_failed`, `address_changed`; mit Abklingzeiten,
  die nach einem Neustart zurückgesetzt sind.

## Ablösung auf BaluNode

Das bisherige certbot-Zertifikat für `baluhost.duckdns.org` gilt bis
2027-02-23.

Voraussetzung: Der Dienstnutzer darf `sudo -n /usr/bin/systemctl reload nginx`
(Eintrag aus `baluhost-deploy-sudoers`). Prüfen als Dienstnutzer:
`sudo -n -l | awk '/reload nginx/'` — fehlt die Zeile, einmalig
`deploy/scripts/install-deploy-sudoers.sh` als root ausführen. Ohne dieses Recht
scheitert jeder Reload.

1. lego installieren (`sudo apt install -t trixie-backports lego`).
2. Plugin aktivieren, `sudo systemctl restart baluhost-backend`, Domain und
   Anbieter in den Plugin-Einstellungen setzen.
3. Token unter Einstellungen → Integrationen speichern.
4. „Jetzt erneuern“.
5. Reload-Recht prüfen (siehe oben), dann nginx umstellen (beide TLS-Blöcke `:443`/`:8443` samt `server_name`;
   `sites-enabled` und `sites-available` beachten), `nginx -t`, Reload.
6. Prüfen: Karte zeigt „Ausgeliefert von nginx: ja“.
7. Alte Erneuerung stilllegen, die alten Zertifikatsdateien aber **behalten**:
   `/etc/letsencrypt/renewal/baluhost.duckdns.org.conf` wegverschieben (nicht
   `certbot delete` — das löscht auch die Dateien, auf die der Rückfall zeigt).
8. Erst wenn ein Zertifikatswechsel durch das Plugin gelaufen ist, die alten
   Dateien und das pipx-certbot entfernen. Ein Wechsel ist entweder eine echte
   Erneuerung (frühestens 30 Tage vor Ablauf) oder ein Staging-Test mit einem
   zweiten, anderen Zertifikat: `staging` einschalten, „Jetzt erneuern“ (Karte:
   ausgeliefert ja; der Browser warnt, das Staging-Zertifikat ist nicht
   vertrauenswürdig), `staging` wieder aus, „Jetzt erneuern“ (Karte:
   ausgeliefert ja, Browser ohne Warnung). Dann
   `sudo certbot delete --cert-name baluhost.duckdns.org` und
   `sudo pipx uninstall certbot` bzw. `/usr/local/bin/certbot` löschen. Debians
   `certbot.timer` kann für andere Zertifikate bestehen bleiben.

Rückfall: Die alten Zertifikatspfade bleiben bis 2027-02-23 gültig, solange
Schritt 8 nicht ausgeführt ist. Schlägt Schritt 6 oder der Wechsel in Schritt 8 fehl, die nginx-Site auf die alten Pfade zurückstellen und neu laden.

## DNS-Rebind-Schutz

Fritz!Boxen verwerfen DNS-Antworten, die auf private IPs zeigen. Ohne Pi-hole
die Domain in der Fritz!Box als Ausnahme eintragen (Heimnetz → Netzwerk →
Netzwerkeinstellungen → DNS-Rebind-Schutz).

## Fehlerbilder

| Karte zeigt | Ursache / Abhilfe |
|---|---|
| lego fehlt / zu alt | `sudo apt install -t trixie-backports lego` |
| lego „Version ließ sich nicht lesen“ | `lego --version` von Hand ausführen; die Ausgabe muss eine Version enthalten |
| „Status konnte nicht geladen werden“ direkt nach dem Aktivieren | `sudo systemctl restart baluhost-backend` |
| Letzte DNS-Aktualisierung „fehlgeschlagen“ | Grund steht daneben; meist Token falsch oder keine private LAN-IP |
| Token „nicht gesetzt“ | Token in der Karte speichern |
| „Kein Schlüssel konfiguriert“ | `VPN_ENCRYPTION_KEY` fehlt; das Token wird sonst nicht gespeichert |
| „Ein Lauf läuft bereits“ | Kurz warten, erneut versuchen |
| „Ausgeliefert von nginx: nein“ | nginx-Snippet übernehmen und neu laden |
| Browser findet die Domain nicht | DNS-Rebind-Schutz (siehe oben) |

## Sicherheit

Nur Admins erreichen die Routen. Das Token wird mit Fernet verschlüsselt und
weder zurückgegeben noch geloggt oder auditiert. Der Dienstnutzer kann die
nginx-Site grundsätzlich selbst umschreiben (#862); das Plugin ändert daran
nichts. Echte Secret-Felder in der generischen Plugin-Konfiguration sind #863.
