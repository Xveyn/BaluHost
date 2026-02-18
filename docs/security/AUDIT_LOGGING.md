# Audit Logging System

Das Audit-Logging-System protokolliert alle wichtigen Operationen im Backend für Sicherheit und Compliance.

## Übersicht

Das System erfasst:
- **Dateizugriffe und -änderungen**: Uploads, Downloads, Löschungen, Verschiebungen, Ordner-Erstellungen
- **Disk-Monitor-Aktivitäten**: Start, Stop, Fehler, periodische Zusammenfassungen
- **System-Ereignisse**: Startup, Shutdown, Konfigurationsänderungen

## Konfiguration

### Dev-Mode vs. Production-Mode

- **Dev-Mode** (`nas_mode=dev`): Logging ist **deaktiviert** - keine Audit-Log-Dateien werden geschrieben
- **Production-Mode** (`nas_mode!=dev`): Logging ist **aktiviert** - alle Events werden protokolliert

### Log-Speicherort

Audit-Logs werden in `{nas_temp_path}/audit/audit.log` gespeichert.

Standardpfade:
- Dev: `./dev-tmp/audit/audit.log`
- Production: `./tmp/audit/audit.log`

## Log-Format

Logs werden im JSON-Format geschrieben, eine Zeile pro Event:

```json
{
  "timestamp": "2025-11-23T10:30:45.123456+00:00",
  "event_type": "FILE_ACCESS",
  "user": "admin",
  "action": "upload",
  "resource": "/documents/report.pdf",
  "success": true,
  "details": {
    "size_bytes": 2048000
  }
}
```

### Event-Typen

#### FILE_ACCESS
Alle Datei- und Ordneroperationen:

**Upload:**
```json
{
  "event_type": "FILE_ACCESS",
  "action": "upload",
  "user": "username",
  "resource": "/path/to/file.txt",
  "details": {"size_bytes": 1024}
}
```

**Delete:**
```json
{
  "event_type": "FILE_ACCESS",
  "action": "delete",
  "user": "username",
  "resource": "/path/to/file.txt",
  "details": {"is_directory": false}
}
```

**Move:**
```json
{
  "event_type": "FILE_ACCESS",
  "action": "move",
  "user": "username",
  "resource": "/old/path.txt",
  "details": {"target_path": "/new/path.txt"}
}
```

**Create Folder:**
```json
{
  "event_type": "FILE_ACCESS",
  "action": "create_folder",
  "user": "username",
  "resource": "/new/folder"
}
```

#### DISK_MONITOR
Disk-Monitor-Operationen:

**Monitor Started:**
```json
{
  "event_type": "DISK_MONITOR",
  "action": "monitor_started",
  "user": "system"
}
```

**Periodic Summary:**
```json
{
  "event_type": "DISK_MONITOR",
  "action": "periodic_summary",
  "user": "system",
  "details": {
    "interval_seconds": 60,
    "disks": {
      "PhysicalDrive0": {
        "avg_read_mbps": 10.5,
        "avg_write_mbps": 5.2,
        "max_read_mbps": 25.0,
        "max_write_mbps": 15.0,
        "avg_read_iops": 100,
        "avg_write_iops": 50
      }
    }
  }
}
```

**Sampling Error:**
```json
{
  "event_type": "DISK_MONITOR",
  "action": "sampling_error",
  "user": "system",
  "success": false,
  "error": "Permission denied"
}
```

#### SYSTEM
System-weite Ereignisse:

```json
{
  "event_type": "SYSTEM",
  "action": "startup",
  "user": "system",
  "details": {"version": "1.0.0"}
}
```

## API-Verwendung

### Grundlegende Verwendung

```python
from app.services.audit_logger import get_audit_logger

audit = get_audit_logger()

# Log Datei-Upload
audit.log_file_access(
    user="admin",
    action="upload",
    file_path="/documents/file.pdf",
    size_bytes=2048000,
    success=True
)

# Log Disk-Monitor-Event
audit.log_disk_monitor(
    action="monitor_started"
)

# Log System-Event
audit.log_system_event(
    action="startup",
    user="system",
    details={"version": "1.0.0"}
)
```

### Fehlerbehandlung

```python
try:
    # Operation durchführen
    delete_file(path)
    
    # Erfolg loggen
    audit.log_file_access(
        user="admin",
        action="delete",
        file_path=path,
        success=True
    )
except Exception as e:
    # Fehler loggen
    audit.log_file_access(
        user="admin",
        action="delete",
        file_path=path,
        success=False,
        error_message=str(e)
    )
    raise
```

### Logs Abrufen

```python
# Alle Logs abrufen (letzte 100)
logs = audit.get_logs(limit=100)

# Nach Event-Typ filtern
file_logs = audit.get_logs(event_type="FILE_ACCESS", limit=50)

# Nach Benutzer filtern
user_logs = audit.get_logs(user="admin", limit=50)
```

## Integration in Services

### files.py

Alle Datei-Operationen werden automatisch geloggt:
- `save_uploads()` - Upload-Events
- `delete_path()` - Lösch-Events
- `create_folder()` - Ordner-Erstellungs-Events
- `move_path()` - Verschiebungs-Events

### disk_monitor.py

Disk-Monitor-Events werden automatisch geloggt:
- `start_monitoring()` - Monitor-Start
- `stop_monitoring()` - Monitor-Stop
- `_sample_disk_io()` - Sampling-Fehler
- `_log_disk_activity()` - Periodische Zusammenfassungen (alle 60s)

## Testing

Das Logging-System ist vollständig getestet:

```bash
# Alle Logging-Tests ausführen
pytest tests/test_audit_logging.py tests/test_file_logging.py tests/test_disk_monitor_logging.py

# Nur Audit-Logger-Tests
pytest tests/test_audit_logging.py

# Nur File-Operation-Tests
pytest tests/test_file_logging.py

# Nur Disk-Monitor-Tests
pytest tests/test_disk_monitor_logging.py
```

### Test-Coverage

- **test_audit_logging.py**: 16 Tests für Core-Audit-Logger
  - Aktivierung/Deaktivierung basierend auf Modus
  - Log-Erstellung und -Abruf
  - Fehlerbehandlung
  - Filterung

- **test_file_logging.py**: 8 Tests für Datei-Operations-Logging
  - Upload-Logging
  - Delete-Logging (Dateien & Ordner)
  - Move-Logging
  - Create-Folder-Logging

- **test_disk_monitor_logging.py**: 9 Tests für Disk-Monitor-Logging
  - Start/Stop-Logging
  - Error-Logging
  - Periodische Summaries
  - Multi-Disk-Support

## Performance

- Logging ist asynchron und blockiert keine Operationen
- Im Dev-Mode ist Logging komplett deaktiviert (kein Overhead)
- Log-Dateien werden gestreamt (keine Memory-Probleme bei großen Logs)
- Alte Logs können über Cronjob oder manuell rotiert/archiviert werden

## Sicherheit

- Logs enthalten keine Passwörter oder sensible Daten
- Nur authentifizierte Benutzer können Logs abrufen (über API)
- Log-Dateien sind nur für den Server-Prozess lesbar
- Logs sind im JSON-Format für maschinelle Verarbeitung

## Zukünftige Erweiterungen

Mögliche Verweiterungen:
- Log-Rotation (nach Größe oder Zeit)
- Export-Funktionen (CSV, Excel)
- Dashboard für Log-Visualisierung
- Alerting bei kritischen Events
- Integration mit externen Logging-Services (Syslog, etc.)
