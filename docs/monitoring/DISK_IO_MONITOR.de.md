# Disk I/O Monitor - Implementierung

## Übersicht

Die Disk I/O Monitor Seite zeigt in Echtzeit die Lese- und Schreibaktivität aller physischen Festplatten an. Die Implementierung basiert auf `psutil` für das Backend und Recharts für die Visualisierung im Frontend.

## Backend-Implementierung

### 1. Disk Monitor Service (`app/services/disk_monitor.py`)

Der Service überwacht kontinuierlich die I/O-Aktivität aller physischen Festplatten:

**Features:**
- Sampling alle 1 Sekunde für Echtzeit-Monitoring
- Speichert 120 Samples (2 Minuten Historie) pro Festplatte
- Berechnet MB/s (Durchsatz) und IOPS (Operations per Second)
- Filtert physische Festplatten (keine Partitionen)
- Automatisches Logging alle 60 Sekunden

**Wichtige Funktionen:**
- `start_monitoring()`: Startet den Background-Task
- `stop_monitoring()`: Stoppt den Background-Task
- `get_disk_io_history()`: Gibt komplette Historie aller Disks zurück
- `get_available_disks()`: Liste aller überwachten Disks
- `_sample_disk_io()`: Nimmt eine Messung aller Disks vor
- `_log_disk_activity()`: Loggt Zusammenfassung der Aktivität

**Plattform-Unterstützung:**
- **Windows**: Erkennt `PhysicalDrive0`, `PhysicalDrive1`, etc.
- **Linux**: Erkennt `sda`, `sdb`, `nvme0n1`, etc. (ohne Partitionsnummern)

### 2. API-Endpunkt (`app/api/routes/system.py`)

**Neuer Endpunkt:**
```
GET /api/system/disk-io/history
```

**Response:**
```json
{
  "disks": [
    {
      "diskName": "PhysicalDrive0",
      "samples": [
        {
          "timestamp": 1700000000000,
          "readMbps": 12.5,
          "writeMbps": 5.3,
          "readIops": 150,
          "writeIops": 75
        }
      ]
    }
  ],
  "interval": 1.0
}
```

### 3. Schemas (`app/schemas/system.py`)

Neue Pydantic-Models:
- `DiskIOSample`: Einzelne Messung mit Timestamp, MB/s und IOPS
- `DiskIOHistory`: Historie für eine Festplatte
- `DiskIOResponse`: Komplette API-Response

### 4. Integration (`app/main.py`)

Der Disk Monitor wird beim Server-Start automatisch initialisiert:
```python
disk_monitor.start_monitoring()  # In _lifespan
```

## Frontend-Implementierung

### 1. SystemMonitor Komponente (`client/src/pages/SystemMonitor.tsx`)

**Features:**
- Echtzeit-Diagramme mit Recharts
- Disk-Auswahl per Button
- Umschaltung zwischen Durchsatz (MB/s) und IOPS
- 4 Stat-Karten: Lesen, Schreiben, Lese-IOPS, Schreib-IOPS
- Live-Chart mit 60 Sekunden Historie
- Auto-Update alle 2 Sekunden

**Komponenten:**
- Disk Selector: Button-Gruppe zur Auswahl der Festplatte
- Stats Cards: 4 Karten mit aktuellen Werten
- Interactive Chart: LineChart mit Read/Write Linien
- View Mode Toggle: Wechsel zwischen MB/s und IOPS Ansicht

### 2. Chart-Konfiguration

**Recharts-Komponenten:**
- `LineChart`: Haupt-Chart Container
- `CartesianGrid`: Gitter im Hintergrund
- `XAxis`: Zeit-Achse (HH:MM:SS Format)
- `YAxis`: Wert-Achse mit dynamischem Label
- `Tooltip`: Hover-Informationen
- `Legend`: Legende für Read/Write
- `Line`: Zwei Linien (blau für Read, grün für Write)

## Logging

### Log-Format

Alle 60 Sekunden wird eine Zusammenfassung geloggt:

```
Disk Activity Log (last 60s):
  PhysicalDrive0: Read=12.50MB/s (max 25.30), Write=5.30MB/s (max 8.90), IOPS R=150/W=75
  PhysicalDrive1: Read=0.00MB/s (max 0.00), Write=0.00MB/s (max 0.00), IOPS R=0/W=0
```

### Log-Level

- `INFO`: Normale Aktivitäts-Logs, Start/Stop des Monitors
- `DEBUG`: Detaillierte Sampling-Informationen
- `ERROR`: Fehler beim Sampling oder in der Monitor-Loop

### Log-Konfiguration

Logs erscheinen im Standard-Backend-Log. Für separate Disk-Logs:

```python
# In logging config
'app.services.disk_monitor': {
    'handlers': ['disk_file'],
    'level': 'INFO',
}
```

## Performance

### Ressourcen-Verbrauch

- **CPU**: Minimal (~0.1% pro Sample)
- **Memory**: ~50KB pro Disk für 120 Samples
- **Disk I/O**: Lesen von `/proc/diskstats` (Linux) oder WMI (Windows)

### Optimierungen

1. **Sampling-Intervall**: 1 Sekunde ist optimal für Echtzeit ohne Overhead
2. **Historie-Größe**: 120 Samples = 2 Minuten sind ausreichend für Charts
3. **Frontend-Update**: 2 Sekunden reduziert API-Calls ohne Datenverlust

## Plattform-Spezifika

### Windows

- Verwendet `psutil.disk_io_counters(perdisk=True)`
- Disk-Namen: `PhysicalDrive0`, `PhysicalDrive1`, etc.
- Funktioniert out-of-the-box, keine Admin-Rechte nötig

### Linux

- Verwendet `/proc/diskstats`
- Disk-Namen: `sda`, `sdb`, `nvme0n1`, etc.
- Filtert automatisch Partitionen (`sda1`, `nvme0n1p1`)

### macOS

- Begrenzte Unterstützung durch psutil
- Disk-Namen: `disk0`, `disk1`, etc.

## Testing

### Backend-Tests

```bash
# Test disk monitor service
python -m pytest tests/test_disk_monitor.py

# Manual test
python -c "
from app.services import disk_monitor
disk_monitor.start_monitoring()
import time
time.sleep(5)
print(disk_monitor.get_disk_io_history())
disk_monitor.stop_monitoring()
"
```

### Frontend-Tests

1. Backend starten
2. Frontend starten
3. Zur System Monitor Seite navigieren
4. Verschiedene Disks auswählen
5. Zwischen MB/s und IOPS umschalten
6. I/O-Last erzeugen und Änderungen beobachten

### Last-Erzeugung für Tests

**Windows (PowerShell):**
```powershell
# Schreib-Last
1..100 | ForEach-Object { 
    [System.IO.File]::WriteAllBytes("test_$_.dat", (New-Object byte[] 10MB))
}

# Lese-Last
1..100 | ForEach-Object {
    Get-Content "test_$_.dat" | Out-Null
}
```

**Linux:**
```bash
# Schreib-Last
dd if=/dev/zero of=test.dat bs=1M count=1000

# Lese-Last  
dd if=test.dat of=/dev/null bs=1M
```

## Zukünftige Erweiterungen

### Mögliche Features

1. **Historische Daten**: Speicherung in Datenbank für langfristige Analyse
2. **Alerts**: Benachrichtigungen bei ungewöhnlich hoher I/O-Last
3. **Export**: CSV/JSON Export der Monitoring-Daten
4. **Per-Process I/O**: Welcher Prozess verursacht die meiste I/O
5. **Latency Monitoring**: Durchschnittliche Read/Write Latenz
6. **Queue Depth**: Wie viele I/O-Requests warten
7. **Disk Temperature**: Integration mit SMART-Daten
8. **Vergleichs-Ansicht**: Mehrere Disks im selben Chart

### Datenbank-Schema für Historie

```sql
CREATE TABLE disk_io_samples (
    id SERIAL PRIMARY KEY,
    disk_name VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    read_mbps DECIMAL(10,2),
    write_mbps DECIMAL(10,2),
    read_iops INTEGER,
    write_iops INTEGER,
    INDEX idx_disk_timestamp (disk_name, timestamp)
);
```

## Troubleshooting

### Problem: Keine Disks erkannt

**Ursache**: psutil kann keine Disk-Counter lesen
**Lösung**: 
- Windows: Prüfe ob `wmi` installiert ist
- Linux: Prüfe Zugriff auf `/proc/diskstats`
- Führe als Administrator/Root aus

### Problem: Nur Nullen in den Werten

**Ursache**: Erster Sample hat keine Referenz
**Lösung**: Warte 2-3 Sekunden, dann werden Deltas berechnet

### Problem: Chart zeigt nichts an

**Ursache**: Frontend erhält keine Daten
**Lösung**:
1. Prüfe Backend-Logs auf Fehler
2. Prüfe API-Response im Browser DevTools
3. Stelle sicher dass Disk Monitor läuft

### Problem: Hohe CPU-Last

**Ursache**: Sampling-Intervall zu kurz
**Lösung**: Erhöhe `_SAMPLE_INTERVAL_SECONDS` in `disk_monitor.py`

## Konfiguration

### Backend-Konfiguration

In `app/services/disk_monitor.py`:

```python
# Sampling-Intervall (Sekunden)
_SAMPLE_INTERVAL_SECONDS = 1.0

# Maximale Anzahl Samples pro Disk
_MAX_SAMPLES = 120

# Log-Intervall (Sekunden)
_LOG_INTERVAL_SECONDS = 60.0
```

### Frontend-Konfiguration

In `client/src/pages/SystemMonitor.tsx`:

```typescript
// Update-Intervall (Millisekunden)
const interval = setInterval(loadDiskIO, 2000);

// Anzahl angezeigter Samples im Chart
const samples = disk.samples.slice(-60);
```

## Dependencies

### Backend

- `psutil >= 5.9.0`: Für Disk I/O Counter
- `asyncio`: Für Background-Task
- `FastAPI`: Für API-Endpunkt
- `Pydantic`: Für Schemas

### Frontend

- `recharts >= 2.0.0`: Chart-Bibliothek
- `react >= 19.0.0`: UI-Framework
- `tailwindcss`: Styling

## Lizenz & Credits

Basiert auf:
- psutil: https://github.com/giampaolo/psutil
- Recharts: https://recharts.org
- Windows Ressourcenmonitor als UI-Inspiration
