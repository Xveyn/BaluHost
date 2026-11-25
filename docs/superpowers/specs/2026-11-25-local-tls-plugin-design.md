# Plugin „Feste Adresse im Heimnetz“ (DNS-Name + Let's-Encrypt-Zertifikat)

Stand: 2026-11-25 · Paket 2 (Paket 1 war #847 / PR #858)

## Absicht

Die Box soll im Heimnetz immer unter **derselben Adresse** erreichbar sein, und
zwar mit einem Zertifikat, dem jedes Gerät **ohne Einrichtung** vertraut. Das ist
keine Pflichtfunktion — BaluHost läuft ohne sie —, aber im Betrieb deutlich
angenehmer: Win11 (Browser, Samba, WebDAV im Explorer), die Android-App und
künftig iOS-Clients sprechen einen festen Namen an, und der ändert sich nicht,
wenn DHCP der Box eine neue IP gibt.

Der Weg dahin ist der, der auf BaluNode heute schon (halb) läuft: ein öffentlicher
DNS-Name (z. B. `baluhost.duckdns.org`), der auf die **LAN-IP** der Box zeigt
(`192.168.178.53`), plus ein Let's-Encrypt-Zertifikat über die **DNS-Prüfung**
(eine HTTP-Prüfung kann eine private IP nie erreichen).

Self-signed wurde verworfen: Es hieße, eine eigene CA auf jeder Plattform
einzeln einzurichten — beim Windows-WebClient (WebDAV) und bei iOS besonders
fummelig, und Android-Apps vertrauen selbst installierten CAs standardmäßig nicht.

### Was heute kaputt bzw. halb ist (Befund 2026-11-25)

- Das Zertifikat lief am 2026-11-21 ab: `certbot.timer` ruft Debians
  `/usr/bin/certbot` auf, dem das Plugin `dns-duckdns` fehlt; ausgestellt wurde es
  von einem separat per pipx installierten certbot. Kein Deploy-Hook lädt nginx neu.
  Am 2026-11-25 von Hand erneuert (gültig bis 2027-02-23) — die Ablösung ist also
  nicht eilig. Der DuckDNS-Token liegt heute root-only in
  `/etc/letsencrypt/duckdns.ini` und muss im Plugin neu eingetragen werden.
- **Es gibt keinen Updater für den DNS-Eintrag.** Ändert sich die LAN-IP, zeigt
  der Name ins Leere. Dass es funktioniert, liegt nur an einer stabilen
  Fritz!Box-Zuweisung.
- Backend und Web-UI wissen nichts von Domain oder Zertifikat; HTTPS wird von
  Hand über `deploy/ssl/setup-*.sh` eingerichtet.

## Ziele

- Mitgeliefertes Plugin (bundled, `backend/app/plugins/installed/local_tls/`),
  **standardmäßig aus**.
- Hält den DNS-Namen auf der aktuellen LAN-IP der Box (prüft periodisch,
  aktualisiert nur bei Änderung, bestätigt einmal täglich).
- Holt und erneuert das Zertifikat per ACME DNS-01 über **lego** und übergibt es
  an nginx — **ohne neue sudoers-Regel** (siehe „Übergabe an nginx“).
- Unterstützt **DuckDNS nativ** (Svens Fall) und hat eine **Adapter-Schnittstelle**
  für weitere DNS-Anbieter mit festen Regeln, ähnlich den Plugin-Regeln.
- Web-UI für Admins: Domain, Anbieter, Zugangsdaten eintragen; Status sehen
  (aktuelle LAN-IP, DNS-Eintrag, Zertifikat gültig bis, letzte Erneuerung und ihr
  Ergebnis); „Jetzt erneuern“ und „DNS jetzt aktualisieren“.
- Warnungen über das bestehende Benachrichtigungssystem, bevor etwas ausläuft
  oder wenn etwas scheitert.
- Löst Svens bisherigen Handbetrieb (pipx-certbot) ab.

## Nicht-Ziele

- Keine eigene CA / kein self-signed (dafür gibt es weiter `setup-selfsigned.sh`).
- Kein HTTP-01 (Port 80 von außen), keine öffentliche Erreichbarkeit der Box.
- Keine statische IP auf der Box setzen; keine Router-Konfiguration.
- Keine externen (Marketplace-)Adapter in v1 — Adapter sind Teil des
  mitgelieferten Plugins.
- Keine Verwaltung mehrerer Domains/Zertifikate; genau ein Name.
- VPN-DNS (#Memory-TODO „baluhost.local per VPN“) wird nicht gelöst — der Name
  zeigt auf die LAN-IP und funktioniert über VPN nur, wenn das LAN-Subnetz
  geroutet wird.

## Anti-Ziele

- Ein Zertifikat läuft wieder still ab: Jeder Fehlschlag muss laut sein
  (Benachrichtigung + Status in der UI), und Warnungen kommen deutlich vor Ablauf.
- Ein kaputtes oder fremdes Zertifikat legt nginx lahm: Das Plugin prüft vor dem
  Austausch und rollt zurück, wenn nginx danach nicht das neue Zertifikat ausliefert.
- Das Feature braucht neue Root-Rechte — es gibt keine neue sudoers-Regel und
  kein certbot/lego als root.
- API-Token des DNS-Anbieters landen im Klartext in der DB, in einer
  API-Antwort, in Logs oder im Audit.
- Das Plugin erneuert parallel aus mehreren Prozessen.

## Ansätze (gewählt: 1)

1. **lego als Hilfsprogramm (gewählt).** Debian-Paket `lego` (trixie 4.9.1,
   Backports 4.35), über 100 DNS-Anbieter eingebaut (DuckDNS, Cloudflare, deSEC …).
   Läuft als Dienstnutzer ohne root, schreibt in ein Plugin-Verzeichnis; nginx
   wird über das bereits bestehende Reload-Recht neu geladen. Ein Adapter ist fast
   nur Beschreibung. Nachteil: externe Abhängigkeit; ein Anbieter geht nur, wenn
   lego ihn kennt.
2. Reines Python mit `acme` (python3-acme): kein fremdes Programm, aber ACME-Ablauf
   und je Anbieter TXT-API selbst bauen — viel eigener Code an der heiklen Stelle.
3. certbot weiterverwenden per sudo: verworfen — certbot als root mit Hooks
   (`--deploy-hook` …) wäre über sudoers praktisch Root für das Backend.

## Design

### Bausteine

```
backend/app/plugins/installed/local_tls/
├── __init__.py        # PluginBase: Metadaten, Hintergrundaufgaben, Events, Router
├── providers/         # Adapter, je Anbieter eine Datei + Registry
│   ├── base.py        # DnsProvider-Schnittstelle + Regeln
│   └── duckdns.py
├── address.py         # LAN-IP bestimmen
├── lego.py            # einziger Kontakt zu lego (subprocess, Listen-Args)
├── deploy_cert.py     # Prüfen, atomar tauschen, nginx neu laden, verifizieren, ggf. zurück
├── models.py          # Tabelle local_tls_config (+ Statusfelder), Alembic-Migration
├── routes.py          # Admin-API
└── CLAUDE.md
client/src/…           # UI als normaler Client-Code (Muster bluetooth/audio_control)
```

Muster wie bei den anderen bundled Plugins: ein Modul kapselt den gesamten
Kontakt zu einem externen Programm (vgl. `pactl.py`, `kscreen.py`).

### Adapter-Schnittstelle (`providers/base.py`)

Ein Adapter beschreibt einen DNS-Anbieter:

- `id` (`^[a-z0-9_]+$`), `display_name`
- `credential_fields`: Liste von Feldern (Name, Label-Key, `secret: bool`,
  Validierungsregex/Länge)
- `lego_provider`: der Anbieter-Name in lego (z. B. `duckdns`)
- `lego_env(credentials) -> dict[str, str]`: Umgebungsvariablen für lego
  (z. B. `DUCKDNS_TOKEN`)
- `update_address(domain, ip, credentials) -> None`: setzt den A-Eintrag auf `ip`
  (DuckDNS: `GET https://www.duckdns.org/update?domains=…&token=…&ip=…`,
  Antwort `OK`/`KO`)
- `validate_domain(domain) -> bool` (DuckDNS: genau `<sub>.duckdns.org`)

**Regeln für Adapter** (im Docstring von `base.py` und in der Plugin-`CLAUDE.md`
festgehalten, per Test durchgesetzt wo möglich):

- Nur HTTPS zum eigenen Anbieter-Host, feste Timeouts (≤ 15 s), kein Shell-Aufruf,
  keine Dateizugriffe.
- Zugangsdaten nie loggen; Fehlermeldungen ohne Token/URL mit Token.
- Domain und IP werden vor jedem Aufruf validiert (IP: privat/IPv4 in v1).
- Registrierung nur über die Registry in `providers/__init__.py`; ein Test prüft,
  dass jeder registrierte Adapter die Schnittstelle vollständig erfüllt.

v1 liefert nur `duckdns`. Ein weiterer Anbieter = eine Datei + Registry-Eintrag.

### LAN-IP bestimmen (`address.py`)

IPv4-Adresse des Interfaces der Default-Route (ohne Fremd-Abhängigkeit, z. B. über
`ip -j route get 1.1.1.1` mit Listen-Args oder Socket-Trick ohne Senden).
Optional ein Interface-Override in den Einstellungen. Ergebnis muss eine private
Adresse sein (`is_private_or_local_ip`), sonst Fehler statt Update.

### Zertifikat (`lego.py`)

- lego läuft als Dienstnutzer mit `--path <plugin-data>/lego`, Konto-Daten
  ebenda (Modus 0700/0600).
- Erstausstellung `lego run`, danach täglich `lego renew --days 30`.
- Optional Staging-Schalter (Let's-Encrypt-Staging) zum Ausprobieren.
- E-Mail optional (Let's Encrypt verschickt keine Ablauf-Mails mehr).
- Aufruf nur mit Listen-Args, Zugangsdaten nur über `env`, Timeout.
- Ergebnis: `<plugin-data>/lego/certificates/<domain>.crt|.key`.

### Übergabe an nginx (ohne neue Rechte)

Entscheidung des Besitzers (2026-11-25): **keine neue sudoers-Regel**, wenn es ohne
geht. Begründung: Der Dienstnutzer darf `systemctl reload nginx` bereits
(`baluhost-deploy-sudoers`), und die nginx-Site-Datei gehört auf BaluNode dem
Dienstnutzer (Nebenbefund, Issue #862). Ein Root-Helfer, der „nur ein geprüftes
Zertifikat“ installiert, brächte deshalb keine echte Grenze, nur Deploy-Aufwand.

- nginx zeigt **dauerhaft** auf `/var/lib/baluhost/plugins/local_tls/live/fullchain.pem`
  und `…/live/privkey.pem`. `live` ist ein Symlink auf ein versioniertes
  Verzeichnis (`releases/<zeitstempel>/`); Tausch = atomares Umbiegen des
  Symlinks (`os.replace` eines temporären Symlinks).
- `/var/lib/baluhost/plugins` gehört bereits dem Dienstnutzer; Verzeichnisse
  0700, Schlüssel 0600. Der nginx-Master läuft als root und liest den Schlüssel
  beim Laden — Gruppenrechte sind nicht nötig.
- Vor dem Tausch prüft das Plugin (`deploy_cert.py`): PEM parsebar, Schlüssel
  passt zum Zertifikat, SAN enthält die konfigurierte Domain, nicht abgelaufen,
  Kette vollständig. Bei Fehler: kein Tausch, `renew_failed`.
- Neu laden über `sudo -n systemctl reload nginx` (Listen-Args, Timeout). nginx
  prüft beim Reload die Konfiguration und behält bei einem Fehler die laufende.
- Danach Verifikation: TLS-Handshake gegen `127.0.0.1:443` mit SNI = Domain,
  ausgeliefertes Zertifikat == neues Zertifikat (Fingerabdruck). Wenn nicht:
  Symlink auf die vorige Version zurück, erneut reload, `renew_failed` mit Grund.
- Die letzten drei Releases bleiben liegen, ältere werden gelöscht.
- Fehlt das Reload-Recht (`sudo -n` scheitert), ist das ein klarer Status
  („nginx-Reload nicht erlaubt“) plus Benachrichtigung, kein stiller Fehler.
- nginx muss **einmalig** auf diesen Pfad umgestellt werden (Betriebsschritt,
  siehe unten). Das Plugin schreibt die nginx-Konfiguration **nicht** selbst.
- Ein Hinweis-Snippet für die nginx-Site (beide TLS-Blöcke, `ssl_certificate`,
  `ssl_certificate_key`, `server_name` mit der Domain) steht in der Plugin-Doku
  und wird in der UI angezeigt, solange :443 noch ein anderes Zertifikat
  ausliefert als das des Plugins.

### Ablauf und Zeitplan (Hintergrundaufgaben, primary-only)

- **Adress-Check** alle 5 Minuten: LAN-IP bestimmen; bei Änderung gegenüber dem
  zuletzt gesetzten Wert `update_address`; zusätzlich einmal täglich bestätigen.
- **Zertifikats-Check** täglich (und beim Aktivieren bzw. auf Knopfdruck):
  fehlt das Zertifikat → `lego run`, sonst `lego renew --days 30`; bei neuem
  Zertifikat → prüfen → tauschen → nginx neu laden → verifizieren.
- Ein Datei-Lock im Plugin-Datenverzeichnis verhindert parallele lego-Läufe
  (auch Knopfdruck während Hintergrundlauf).
- Hintergrundaufgaben laufen nur im Primary-Worker (Plugin-Framework, #448/#465).

### Zugangsdaten und Einstellungen

- **Eigene Tabelle** `local_tls_config` (eine Zeile; Alembic-Migration) für
  Domain, Anbieter, nicht-geheime Felder, Interface-Override, Staging, E-Mail und
  die Statusfelder (zuletzt gesetzte IP + Zeitpunkt, letzte Erneuerung + Ergebnis).
  *Meine Entscheidung:* `InstalledPlugin.config` liefert `GET /api/plugins/{name}`
  an jeden eingeloggten Nutzer aus und ist über den Core-`PUT …/config`
  überschreibbar; `_storage` ist pro Nutzer. Das Plugin deklariert daher **kein**
  `get_config_schema()` (sonst gäbe es einen zweiten, nicht auditierten Schreibweg).
- Geheimnisse verschlüsselt (Fernet über `VPNEncryption`, wie bei Tapos
  `SmartDevice.config_secret`) in einer Spalte, deren Name `REDACT_PATTERN`
  trifft (z. B. `provider_secret`).
- **Write-only:** Die API gibt nur „gesetzt ja/nein“ zurück, nie den Wert.
- Ohne `VPN_ENCRYPTION_KEY` lässt sich das Plugin nicht konfigurieren (klare
  Fehlermeldung), statt Klartext zu speichern.

### Admin-API (`routes.py`, alle `get_current_admin`, Rate-Limits, Pydantic, Audit)

- `GET /api/plugins/local_tls/settings` — Domain, Anbieter, welche Felder gesetzt
  sind, Interface-Override, Staging, E-Mail.
- `PUT /api/plugins/local_tls/settings` — dieselben Felder; Secrets nur schreibend.
  Audit `local_tls_settings_changed` (ohne Secrets).
- `GET /api/plugins/local_tls/status` — aktuelle LAN-IP, zuletzt gesetzte IP und
  Zeitpunkt, Zertifikat (Aussteller, gültig bis, SAN), letzte Erneuerung + Ergebnis,
  nginx-Reload erlaubt ja/nein, ausgeliefertes Zertifikat == Plugin-Zertifikat ja/nein, lego installiert ja/nein + Version.
- `POST /api/plugins/local_tls/renew` und `POST /api/plugins/local_tls/update-dns`
  — sofort ausführen; Audit.
- Pfad `settings` statt `config` (reservierter Core-Pfad, siehe plugins/CLAUDE.md).

### Benachrichtigungen (`get_notification_events`, an Admins)

- `cert_expiring` — ab 21 Tagen vor Ablauf, Cooldown 1 Tag.
- `renew_failed` — jeder gescheiterte Erneuerungs- oder Installationsversuch.
- `dns_update_failed` — Adress-Update gescheitert.
- `address_changed` — LAN-IP hat sich geändert und wurde nachgezogen (info).

### Web-UI

Normaler Client-Code wie bei `bluetooth`/`audio_control` (Komponenten +
`client/src/api/localTls.ts`, eigener i18n-Namespace `de` + `en`), *meine
Entscheidung* — das vorgebaute iframe-Bundle (`optical_drive`) hat keine i18n und
keine Build-Pipeline. Einstellungsformular und Statuskarte; optional ein
Dashboard-Panel/Status-Pill „Zertifikat gültig bis …“ (Builder entscheidet).

### Installation von lego

`lego` ist kein Pflichtpaket. `deploy/install/modules/14-optional-features.sh`
bekommt einen optionalen Schritt (`apt install -t trixie-backports lego`); die
Statusanzeige sagt klar „lego fehlt“ bzw. „lego zu alt“ mit dem Befehl.
**Mindestversion 4.35** (Backports), *meine Entscheidung*: 4.9.1 aus trixie (2022)
kennt ARI und Zertifikatsprofile nicht, und Let's Encrypt verkürzt die Laufzeiten
(64 Tage ab 2027, später 45). Ob lego eine E-Mail verlangt, prüft der Umsetzer an
4.35; falls ja, wird das Feld Pflicht.

### Ablösung auf BaluNode (Betrieb, einmalig)

1. `lego` aus den Backports installieren.
2. Plugin aktivieren, DuckDNS-Domain + Token eintragen, „Jetzt erneuern“.
3. nginx-Site auf `/var/lib/baluhost/plugins/local_tls/live/…` umstellen — beide
   TLS-Blöcke (:443 und :8443), `baluhost.duckdns.org` in `server_name`
   aufnehmen; auf BaluNode ist `sites-enabled/baluhost` eine eigene Datei, nicht
   ein Link auf `sites-available/baluhost` — beide abgleichen. `nginx -t`, reload.
4. Alte certbot-Erneuerung für `baluhost.duckdns.org` stilllegen (Renewal-Conf
   entfernen bzw. Zertifikat löschen), pipx-certbot entfernen.

Wird als Abschnitt in der Plugin-Doku beschrieben. Dort auch: Auf einer Box ohne
eigenen DNS-Resolver (BaluNode hat Pi-hole) kann die DNS-Rebind-Sperre des Routers
(Fritz!Box) Namen, die auf private IPs zeigen, blockieren — dann die Domain dort
als Ausnahme eintragen. `deploy/ssl/setup-letsencrypt.sh` (HTTP-01/certbot) wird
als Altlast markiert, nicht entfernt.

### Sicherheit (für `security-agent.md`)

- Keine neuen Root-Rechte. Genutzt wird nur das bestehende
  `systemctl reload nginx` (NOPASSWD). Ehrliche Grenze: Wer als Dienstnutzer Code
  ausführt, kann schon heute die nginx-Site umschreiben und neu laden (#862);
  das Plugin erweitert das nicht.
- Der Zertifikatsschlüssel liegt 0600 beim Dienstnutzer — derselbe Nutzer hält
  ohnehin den DNS-Token, mit dem sich jederzeit ein neues Zertifikat holen ließe.
- Neue Routen admin-only, rate-limited, Pydantic, auditiert; Token nie in
  Antworten/Logs/Audit.
- Ausgehende Verbindungen nur zu Let's Encrypt (über lego) und zur Anbieter-API.
- lego und `systemctl` nur mit Listen-Args und Timeout, Zugangsdaten nur per `env`.

## Dem Umsetzer überlassen

- Spalten der Tabelle `local_tls_config` im Einzelnen.
- Form der UI (eigene Seite vs. Einstellungs-Tab).
- Ob ein Status-Pill/Dashboard-Panel dazukommt.
- Wie die LAN-IP technisch ermittelt wird, solange ohne Root und ohne neue
  Python-Abhängigkeit.
