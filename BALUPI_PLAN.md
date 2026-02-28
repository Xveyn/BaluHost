# BaluPi – Projektplan

## Übersicht

BaluPi ist der passive Gegenpart zu BaluHost (NAS). Ein Raspberry Pi 3B+, der **immer läuft** und drei Kernaufgaben erfüllt:

1. **PiHole/DNS-Server** – Netzwerk-weites Ad-Blocking und lokale DNS-Auflösung
2. **Tapo Strommonitoring** – permanente Messung des Stromverbrauchs (insb. NAS)
3. **Wake-on-LAN** – das NAS bei Bedarf aufwecken

Zusätzlich bietet BaluPi ein **minimales, abgespecktes Frontend** (View-Only Dashboard) und einen **eigenständigen SMB-Share** als immer verfügbaren Speicher.

---

## Systemarchitektur

```
Heimnetzwerk
│
├── NAS (BaluHost) ─ 192.168.x.10
│   • Volles Frontend + Backend (FastAPI + PostgreSQL)
│   • 4TB RAID 1 + 2TB Cache + VCL
│   • nginx
│   • Läuft nur bei Bedarf (30-50W)
│
└── Raspberry Pi 3B+ (BaluPi) ─ 192.168.x.20
    • Abgespecktes View-Only Frontend
    • Kein eigenes Backend im klassischen Sinn
    • Kein Datenbankserver
    • PiHole/DNS
    • Tapo Strommonitoring
    • WoL-Steuerung
    • SMB-Share (1TB HDD, eigenständig)
    • Läuft immer (~3-5W)
```

---

## Repos

| Repo | Zweck |
|---|---|
| [BaluHost](https://github.com/Xveyn/BaluHost) | NAS: Volles Frontend (React/TS) + Backend (FastAPI/Python) |
| [BaluPi](https://github.com/Xveyn/BaluPi) | Pi: Abgespecktes Frontend (React/TS) + Leichtgewichtige Services (Python) |

Das Frontend wird **immer auf dem NAS gebaut** (auch die Pi-Variante) und als fertige statische Dateien auf den Pi deployed. Der Pi braucht kein Node.js und führt keinen Build-Prozess aus.

### Frontend: Zwei Build-Varianten aus einer Codebasis

Das React/TypeScript-Frontend nutzt eine Build-Zeit-Variable (`VITE_DEVICE_MODE`), um zwei Varianten zu erzeugen:

- `npm run build:desktop` → volles NAS-Frontend
- `npm run build:raspi` → abgespecktes Pi-Frontend (View-Only)

Die Pi-Variante wird per `rsync` auf den Pi kopiert und von nginx ausgeliefert.

---

## Dienste auf dem Pi

### Permanent laufend (systemd)

| Dienst | Aufgabe | RAM (ca.) |
|---|---|---|
| PiHole | DNS-Server, Ad-Blocking, lokale DNS-Einträge | ~120 MB |
| balu-tapo | Tapo P110 auslesen, Stromverbrauch loggen | ~40 MB |
| balu-handshake | WoL, NAS-Heartbeat, DNS-Umschaltung, Inbox-Flush | ~30 MB |
| nginx | Statisches Pi-Frontend ausliefern | ~5 MB |
| smbd | SMB-Share für die 1TB HDD | ~20 MB |

**Kein FastAPI-Backend, keine Datenbank.** Der Handshake-Service ist ein minimaler HTTP-Server nur für die Kommunikation mit dem NAS.

### Geschätzter Gesamt-RAM: ~365 MB von 1 GB

---

## Speicherkonzept

### Prinzip: Zwei getrennte Welten

```
NAS (4TB RAID 1 + 2TB Cache)          Pi (1TB HDD + microSD)
┌─────────────────────────┐           ┌──────────────────────┐
│ Volles Dateisystem       │           │ microSD: OS + Configs│
│ PostgreSQL               │           │                      │
│ Medien, Backups, VCL     │           │ HDD:                 │
│                          │           │  ├── /smb/share/      │
│                          │           │  ├── /smb/inbox/      │
│                          │           │  └── /data/snapshot/  │
└─────────────────────────┘           └──────────────────────┘
```

### Pi-Speicher im Detail

- **`/smb/share/`** – Eigenständiger SMB-Share, immer verfügbar. Kein Abbild des NAS, sondern ein separater Speicherort für Dateien die auch bei ausgeschaltetem NAS erreichbar sein sollen.
- **`/smb/inbox/`** – Eingangsordner. Dateien die hier landen, werden automatisch aufs NAS geschoben sobald es wach ist. Einbahnstraße: Pi → NAS.
- **`/data/snapshot/`** – Metadaten-Snapshot vom NAS. Wird beim Handshake aktualisiert. Read-Only, dient dem View-Only-Frontend als Datenquelle.

### Kein Sync, kein Konflikt

Es gibt keine bidirektionale Synchronisation. Der Pi hat entweder eigene Daten (SMB-Share) oder einen Read-Only-Snapshot vom NAS. Die Inbox ist eine simple Einbahnstraße. Damit entfallen Sync-Logik, Change-Tracking und Konfliktbehandlung komplett.

---

## Snapshot-Konzept

Das NAS erstellt beim Herunterfahren einen Metadaten-Snapshot und schickt ihn an den Pi. Dieser enthält **keine Dateien**, sondern nur Informationen die das View-Only-Frontend braucht, z.B.:

- Systemstatus, Konfigurationen
- Zusammenfassungen / Übersichten
- Letzte Aktivitäten
- Smart-Home-Zustände

Format: Einfache JSON-Dateien in `/data/snapshot/`. Das Pi-Frontend liest diese direkt per nginx – kein Backend nötig.

---

## Handshake-Protokoll

### DNS-Umschaltung

Der Pi kontrolliert als DNS-Server den Eintrag `baluhost.local`:

- NAS aktiv → `baluhost.local` zeigt auf NAS-IP
- NAS schläft → `baluhost.local` zeigt auf Pi-IP

TTL wird auf 5 Sekunden gesetzt, damit der Wechsel schnell greift.

### NAS fährt runter

```
1. NAS sendet Snapshot (Metadaten-JSON) an Pi
2. Pi speichert Snapshot in /data/snapshot/
3. NAS sendet: POST /api/nas-going-offline
4. Pi schaltet DNS: baluhost.local → Pi-IP
5. Pi bestätigt: { acknowledged: true }
6. NAS fährt herunter
```

### NAS fährt hoch

```
1. Nutzer/Cronjob: POST /api/wake-nas auf Pi
2. Pi sendet WoL-Paket
3. Pi pollt NAS /api/health (Timeout: 90s)
4. NAS meldet: POST /api/nas-coming-online
5. Pi flusht Inbox (rsync Pi → NAS, --remove-source-files)
6. Pi schaltet DNS: baluhost.local → NAS-IP
7. Pi bestätigt: { acknowledged: true }
```

### Absicherung

- **Heartbeat:** Pi prüft alle 30s den NAS-Health-Endpoint. Fällt das NAS unerwartet aus (3x keine Antwort), übernimmt der Pi automatisch per DNS-Switch.
- **Kein Shutdown ohne Ack:** NAS fährt erst nach Pi-Bestätigung herunter.
- **Inbox-Flush nur bei Erfolg:** `rsync --remove-source-files` löscht nur erfolgreich übertragene Dateien.

---

## Frontend

### NAS-Variante (BaluHost)

Volles Frontend mit allen Features. Wird auf dem NAS gebaut und gehostet.

### Pi-Variante (BaluPi)

Abgespecktes View-Only-Dashboard:

- NAS-Status (online/offline) + WoL-Button
- Stromverbrauch (Tapo, live)
- PiHole-Statistiken
- Snapshot-Daten vom NAS (read-only)
- SMB-Share-Status / Inbox-Status

Datenquellen im Pi-Frontend:

- Tapo-Service: lokale API oder JSON-Files
- PiHole: bestehende PiHole-API
- Snapshot: statische JSON-Dateien via nginx
- Handshake-Status: Handshake-Service API

Kein Backend, keine Datenbank. Alles entweder statisch oder von den ohnehin laufenden Services bereitgestellt.

### Build & Deploy

```bash
# Auf dem NAS:
VITE_DEVICE_MODE=raspi npx vite build --outDir dist-raspi
rsync -avz --delete dist-raspi/ pi@<pi-ip>:/home/pi/balupi/dist/
```

---

## Phasenplan

### Phase 1 – Fundament (jetzt starten)

- [ ] PiHole vom NAS auf den Pi umziehen
- [ ] Tapo-Service: Stromverbrauch des NAS messen und loggen
- [ ] WoL-Endpoint: NAS per HTTP-Call aufwecken
- [ ] Echte Nutzungsdaten sammeln (wann/wie oft/wie lange läuft das NAS?)

### Phase 2 – Handshake & DNS

- [ ] Handshake-Service auf dem Pi
- [ ] DNS-Umschaltung via PiHole (baluhost.local)
- [ ] Heartbeat-Monitoring
- [ ] NAS-seitiger Shutdown-Hook (sendet Snapshot + meldet sich ab)

### Phase 3 – Pi-Frontend & SMB

- [ ] Build-Variable `VITE_DEVICE_MODE` im Frontend einrichten
- [ ] Abgespecktes Pi-Dashboard bauen (View-Only)
- [ ] SMB-Share auf der 1TB HDD einrichten
- [ ] Inbox-Mechanismus (rsync Pi → NAS bei Handshake)

### Phase 4 – Snapshot & Polish

- [ ] Snapshot-Format definieren (welche Metadaten braucht das Pi-Frontend?)
- [ ] NAS: Snapshot-Export beim Herunterfahren
- [ ] Pi-Frontend: Snapshot-Daten anzeigen
- [ ] Deploy-Script finalisieren (ein Befehl baut + deployed Pi-Frontend)

---

## Designprinzipien

- **Kein Sync.** Der Pi ist kein Spiegel des NAS. Getrennter Speicher, keine bidirektionale Datenbank-Synchronisation.
- **Kein Build auf dem Pi.** Alles wird auf dem NAS gebaut und als fertige Dateien deployed.
- **Minimal.** Jeder Service tut genau eine Sache. Kein overengineering.
- **Graceful Degradation.** Wenn das NAS schläft, hat der Nutzer ein eingeschränktes aber funktionales Dashboard. Für volle Funktionalität → WoL-Button drücken, 30s warten.
- **Inbox statt Sync.** Dateien vom Pi zum NAS sind eine Einbahnstraße, kein Zwei-Wege-Abgleich.
