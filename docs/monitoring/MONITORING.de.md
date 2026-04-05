# Monitoring-Anleitung für BaluHost

Vollständige Anleitung zur Einrichtung von produktionsreifem Monitoring mit Prometheus und Grafana.

## Inhaltsverzeichnis

1. [Überblick](#überblick)
2. [Schnellstart](#schnellstart)
3. [Metriken](#metriken)
4. [Dashboards](#dashboards)
5. [Alarme](#alarme)
6. [Konfiguration](#konfiguration)
7. [Best Practices](#best-practices)
8. [Fehlerbehebung](#fehlerbehebung)

---

## Überblick

BaluHost bietet eine umfassende Monitoring-Infrastruktur:

- **Prometheus**: Metrik-Erfassung und Alarmierung
- **Grafana**: Visualisierungs-Dashboards
- **Benutzerdefinierter Metriken-Endpunkt**: `/api/metrics` mit über 40 Metriken
- **Vorkonfigurierte Dashboards**: Systemübersicht, RAID, Anwendung
- **Alarmregeln**: Über 20 Alarmregeln für kritische Ereignisse

### Architektur

```
┌──────────────────┐
│  Grafana         │
│  (Dashboards)    │
│  Port 3001       │
└────────┬─────────┘
         │
         │ Abfragen
         ▼
┌──────────────────┐
│  Prometheus      │
│  (Metriken-DB)   │
│  Port 9090       │
└────────┬─────────┘
         │
         │ Scraping (alle 15s)
         ▼
┌──────────────────┐
│  BaluHost        │
│  /api/metrics    │
│  Port 8000       │
└──────────────────┘
```

---

## Schnellstart

### Schritt 1: Monitoring aktivieren

Aktualisieren Sie Ihre `.env`-Datei:

```bash
# Monitoring-Ports
PROMETHEUS_PORT=9090
GRAFANA_PORT=3001

# Grafana-Zugangsdaten
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=changeme  # Ändern Sie dies!
GRAFANA_ROOT_URL=http://localhost:3001
```

### Schritt 2: Monitoring-Stack starten

```bash
# BaluHost mit Monitoring starten
docker-compose --profile monitoring up -d

# Oder bestehende Bereitstellung aktualisieren
docker-compose up -d prometheus grafana
```

### Schritt 3: Dashboards aufrufen

**Grafana** (Dashboards):
- URL: http://localhost:3001
- Anmeldung: `admin` / `admin` (oder Ihr konfiguriertes Passwort)
- Vorgeladenes Dashboard: "BaluHost - System Overview"

**Prometheus** (Rohe Metriken):
- URL: http://localhost:9090
- Keine Authentifizierung erforderlich
- Abfrage-Oberfläche: http://localhost:9090/graph

**Roher Metriken-Endpunkt**:
- URL: http://localhost:8000/api/metrics
- Prometheus-Format
- Keine Authentifizierung erforderlich (kann in Nginx eingeschraenkt werden)

### Schritt 4: Metrik-Erfassung überprüfen

**Überprüfen Sie, ob Prometheus Daten sammelt**:
```bash
# Im Browser oeffnen
http://localhost:9090/targets

# Sollte anzeigen:
# - prometheus: UP
# - baluhost-backend: UP
```

**Metriken-Endpunkt testen**:
```bash
curl http://localhost:8000/api/metrics

# Sollte Metriken im Prometheus-Format zurückgeben wie:
# baluhost_cpu_usage_percent 15.3
# baluhost_memory_usage_percent 45.2
# ...
```

---

## Metriken

BaluHost stellt über 40 benutzerdefinierte Metriken unter `/api/metrics` bereit.

### System-Metriken

| Metrik | Typ | Beschreibung |
|--------|-----|-------------|
| `baluhost_cpu_usage_percent` | Gauge | Aktuelle CPU-Auslastung (0-100%) |
| `baluhost_cpu_count` | Gauge | Anzahl der CPU-Kerne |
| `baluhost_memory_total_bytes` | Gauge | Gesamter Systemspeicher |
| `baluhost_memory_used_bytes` | Gauge | Belegter Systemspeicher |
| `baluhost_memory_available_bytes` | Gauge | Verfügbarer Systemspeicher |
| `baluhost_memory_usage_percent` | Gauge | Speicherauslastung in Prozent |

### Festplatten-Metriken

| Metrik | Typ | Labels | Beschreibung |
|--------|-----|--------|-------------|
| `baluhost_disk_total_bytes` | Gauge | `path` | Gesamter Festplattenplatz |
| `baluhost_disk_used_bytes` | Gauge | `path` | Belegter Festplattenplatz |
| `baluhost_disk_free_bytes` | Gauge | `path` | Freier Festplattenplatz |
| `baluhost_disk_usage_percent` | Gauge | `path` | Festplattenauslastung in Prozent |
| `baluhost_disk_read_bytes_total` | Counter | `device` | Gesamte gelesene Bytes |
| `baluhost_disk_write_bytes_total` | Counter | `device` | Gesamte geschriebene Bytes |

### RAID-Metriken

| Metrik | Typ | Labels | Beschreibung |
|--------|-----|--------|-------------|
| `baluhost_raid_array_status` | Gauge | `device, level, status` | RAID-Array-Status (1=aktiv, 0=degradiert) |
| `baluhost_raid_disk_count` | Gauge | `device, type` | Anzahl der Festplatten (gesamt/aktiv) |
| `baluhost_raid_sync_progress_percent` | Gauge | `device` | Resync-/Wiederherstellungsfortschritt |

### SMART-Festplattengesundheit

| Metrik | Typ | Labels | Beschreibung |
|--------|-----|--------|-------------|
| `baluhost_disk_smart_health` | Gauge | `device, serial` | SMART-Gesundheit (1=gesund, 0=fehlerhaft) |
| `baluhost_disk_temperature_celsius` | Gauge | `device` | Festplattentemperatur |
| `baluhost_disk_power_on_hours` | Gauge | `device` | Betriebsstunden |

### Netzwerk-Metriken

| Metrik | Typ | Labels | Beschreibung |
|--------|-----|--------|-------------|
| `baluhost_network_received_bytes_total` | Counter | `interface` | Gesamte empfangene Bytes |
| `baluhost_network_sent_bytes_total` | Counter | `interface` | Gesamte gesendete Bytes |

### Anwendungs-Metriken

| Metrik | Typ | Labels | Beschreibung |
|--------|-----|--------|-------------|
| `baluhost_http_requests_total` | Counter | `method, endpoint, status` | Gesamte HTTP-Anfragen |
| `baluhost_http_request_duration_seconds` | Histogram | `method, endpoint` | Anfragedauer |
| `baluhost_file_uploads_total` | Counter | `status` | Gesamte Datei-Uploads |
| `baluhost_file_downloads_total` | Counter | `status` | Gesamte Datei-Downloads |

### Datenbank-Metriken

| Metrik | Typ | Beschreibung |
|--------|-----|-------------|
| `baluhost_database_connections` | Gauge | Aktive DB-Verbindungen |
| `baluhost_database_query_duration_seconds` | Histogram | Abfragedauer |

### Benutzer-Metriken

| Metrik | Typ | Labels | Beschreibung |
|--------|-----|--------|-------------|
| `baluhost_users_total` | Gauge | `role` | Gesamte Benutzer nach Rolle |
| `baluhost_users_active_sessions` | Gauge | - | Aktive Benutzersitzungen |

### Anwendungsinformationen

| Metrik | Typ | Labels | Beschreibung |
|--------|-----|--------|-------------|
| `baluhost_app_info` | Gauge | `version, mode, python_version` | Anwendungsinformationen |
| `baluhost_app_uptime_seconds` | Gauge | - | Anwendungs-Laufzeit |

---

## Dashboards

### Vorkonfigurierte Dashboards

#### 1. Systemübersicht
**Datei**: `deploy/grafana/dashboards/system-overview.json`

**Panels**:
- CPU-Auslastung (Gauge)
- Speicherauslastung (Gauge)
- Festplattenauslastung (Gauge)
- CPU und Speicher im Zeitverlauf (Time Series)
- Festplattenplatz im Zeitverlauf (Time Series)
- Festplatten-I/O (Time Series)
- Netzwerk-Traffic (Time Series)

**Aktualisierung**: 10 Sekunden
**Zeitbereich**: Letzte Stunde

### Benutzerdefinierte Dashboards erstellen

**Beispiel: RAID-Gesundheits-Dashboard**

1. Bei Grafana anmelden
2. Neues Dashboard erstellen
3. Panel mit Abfrage hinzufügen:

```promql
baluhost_raid_array_status{device="md0"}
```

4. Panel konfigurieren:
   - Typ: Stat
   - Schwellenwerte: 0 = Rot (degradiert), 1 = Grün (gesund)
   - Wertezuordnung: 0 = "Degradiert", 1 = "Aktiv"

5. Weitere Panels hinzufügen:
   - Festplattenanzahl: `baluhost_raid_disk_count`
   - Sync-Fortschritt: `baluhost_raid_sync_progress_percent`
   - Festplattentemperatur: `baluhost_disk_temperature_celsius`

6. Dashboard speichern
7. JSON exportieren: Einstellungen → JSON Model
8. Speichern unter `deploy/grafana/dashboards/raid.json`

**Beispiel-Abfragen**:

```promql
# CPU-Auslastung im Zeitverlauf
baluhost_cpu_usage_percent

# Speicherauslastungs-Trend
baluhost_memory_usage_percent

# Festplatten-I/O-Rate (Bytes/s)
rate(baluhost_disk_read_bytes_total[5m])
rate(baluhost_disk_write_bytes_total[5m])

# Netzwerk-Traffic (Bytes/s)
rate(baluhost_network_received_bytes_total[5m])
rate(baluhost_network_sent_bytes_total[5m])

# HTTP-Anfragerate nach Status
sum(rate(baluhost_http_requests_total[5m])) by (status)

# Anzahl fehlerhafter Festplatten
count(baluhost_disk_smart_health == 0)

# Durchschnittliche Festplattentemperatur
avg(baluhost_disk_temperature_celsius)

# Speicherplatzauslastung in Prozent
(baluhost_storage_used_bytes / baluhost_storage_quota_bytes) * 100
```

---

## Alarme

BaluHost enthält über 20 vorkonfigurierte Alarmregeln.

### Alarm-Schweregrade

- **Critical**: Sofortiges Handeln erforderlich (rot)
- **Warning**: Erfordert Aufmerksamkeit (gelb)
- **Info**: Nur informativ (blau)

### Wichtige Alarme

#### Systemressourcen

| Alarm | Bedingung | Dauer | Schweregrad |
|-------|-----------|-------|-------------|
| HighCPUUsage | CPU > 85% | 5 Min. | Warning |
| CriticalCPUUsage | CPU > 95% | 2 Min. | Critical |
| HighMemoryUsage | Speicher > 80% | 5 Min. | Warning |
| CriticalMemoryUsage | Speicher > 95% | 2 Min. | Critical |

#### Festplattenplatz

| Alarm | Bedingung | Dauer | Schweregrad |
|-------|-----------|-------|-------------|
| LowDiskSpace | Festplatte > 75% | 10 Min. | Warning |
| CriticalDiskSpace | Festplatte > 90% | 5 Min. | Critical |
| DiskWillBeFull | Wird in 4 Std. voll sein | 10 Min. | Warning |

#### RAID

| Alarm | Bedingung | Dauer | Schweregrad |
|-------|-----------|-------|-------------|
| RAIDArrayDegraded | Status != aktiv | 1 Min. | Critical |
| RAIDDiskMissing | Aktiv < Gesamt-Festplatten | 2 Min. | Critical |
| RAIDResyncInProgress | 0% < Fortschritt < 100% | 5 Min. | Info |

#### SMART-Festplattengesundheit

| Alarm | Bedingung | Dauer | Schweregrad |
|-------|-----------|-------|-------------|
| DiskFailing | Gesundheit == 0 | 1 Min. | Critical |
| DiskTemperatureHigh | Temp > 55°C | 10 Min. | Warning |
| DiskTemperatureCritical | Temp > 65°C | 5 Min. | Critical |

#### Anwendung

| Alarm | Bedingung | Dauer | Schweregrad |
|-------|-----------|-------|-------------|
| BackendDown | up == 0 | 1 Min. | Critical |
| HighErrorRate | 5xx-Fehler > 5% | 5 Min. | Warning |
| ApplicationRestarted | Laufzeit < 5 Min. | 1 Min. | Info |

### Aktive Alarme anzeigen

**Prometheus**:
```bash
# Im Browser oeffnen
http://localhost:9090/alerts
```

**Grafana**:
- Navigieren Sie zu **Alerting** → **Alert Rules**
- Alarmverlauf und aktuellen Status einsehen

### Alarm-Benachrichtigungen (optional)

Um Alarm-Benachrichtigungen zu erhalten, konfigurieren Sie den Alertmanager:

1. Erstellen Sie `deploy/prometheus/alertmanager.yml`
2. Konfigurieren Sie Benachrichtigungskanäle (E-Mail, Slack, PagerDuty, etc.)
3. Fuegen Sie den Alertmanager zur docker-compose.yml hinzu
4. Aktualisieren Sie die Prometheus-Konfiguration mit dem Verweis auf den Alertmanager

**Beispiel-Alertmanager-Konfiguration**:
```yaml
global:
  resolve_timeout: 5m

route:
  receiver: 'email'
  group_by: ['alertname', 'severity']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h

receivers:
  - name: 'email'
    email_configs:
      - to: 'admin@example.com'
        from: 'baluhost@example.com'
        smarthost: 'smtp.example.com:587'
        auth_username: 'baluhost@example.com'
        auth_password: 'password'
```

---

## Konfiguration

### Prometheus-Konfiguration

**Datei**: `deploy/prometheus/prometheus.yml`

**Wichtige Einstellungen**:
```yaml
global:
  scrape_interval: 15s      # Wie oft Metriken abgerufen werden
  evaluation_interval: 15s  # Wie oft Regeln ausgewertet werden

scrape_configs:
  - job_name: 'baluhost-backend'
    scrape_interval: 15s
    scrape_timeout: 10s
    metrics_path: '/api/metrics'
    static_configs:
      - targets: ['backend:8000']
```

**Optimierung**:
- Erhöhen Sie `scrape_interval` zur Lastreduzierung (z.B. 30s)
- Verringern Sie es für granularere Metriken (z.B. 10s)
- Passen Sie `storage.tsdb.retention.time` für die Datenaufbewahrung an (Standard: 15d)

### Grafana-Konfiguration

**Umgebungsvariablen** (`.env`):
```bash
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=changeme
GRAFANA_ROOT_URL=http://localhost:3001
```

**Datenquelle**: Automatisch konfiguriert über Provisioning
**Dashboards**: Automatisch geladen aus `deploy/grafana/dashboards/`

---

## Best Practices

### 1. Grafana absichern

**Standardpasswort ändern**:
```bash
# In .env aktualisieren
GRAFANA_ADMIN_PASSWORD=starkes-zufälliges-passwort
```

**Zugriff einschränken** (in Nginx):
```nginx
location /grafana/ {
    allow 192.168.1.0/24;  # Nur lokales Netzwerk
    deny all;
    proxy_pass http://grafana:3000/;
}
```

### 2. Datenaufbewahrung verwalten

**Prometheus** (Standard: 15 Tage):
```yaml
# In docker-compose.yml
command:
  - '--storage.tsdb.retention.time=30d'  # 30 Tage aufbewahren
  - '--storage.tsdb.retention.size=10GB'  # Oder nach Größe begrenzen
```

### 3. Sinnvolle Alarm-Schwellenwerte setzen

Passen Sie die Werte an Ihre Hardware und Nutzung an:
- CPU: 85% Warnung, 95% kritisch
- Speicher: 80% Warnung, 95% kritisch
- Festplatte: 75% Warnung, 90% kritisch
- Festplattentemperatur: 55°C Warnung, 65°C kritisch

### 4. Die Überwachung überwachen

- Prometheus-Selbstüberwachung: http://localhost:9090/metrics
- Grafana-Gesundheit: http://localhost:3001/api/health
- Richten Sie Alarme für den Monitoring-Stack selbst ein

### 5. Regelmaessige Backups

Sichern Sie Grafana-Dashboards und Prometheus-Daten:
```bash
# Grafana sichern
docker run --rm -v baluhost_grafana_data:/data -v $(pwd)/backups:/backup \
  alpine tar czf /backup/grafana_$(date +%Y%m%d).tar.gz -C /data .

# Prometheus sichern
docker run --rm -v baluhost_prometheus_data:/data -v $(pwd)/backups:/backup \
  alpine tar czf /backup/prometheus_$(date +%Y%m%d).tar.gz -C /data .
```

---

## Fehlerbehebung

### Metriken werden nicht angezeigt

**Backend-Metriken-Endpunkt prüfen**:
```bash
curl http://localhost:8000/api/metrics

# Sollte Text im Prometheus-Format zurückgeben
```

**Überprüfen, ob Prometheus Daten sammelt**:
```bash
# Im Browser oeffnen
http://localhost:9090/targets

# baluhost-backend sollte UP sein
```

**Prometheus-Logs prüfen**:
```bash
docker-compose logs prometheus | grep -i error
```

### Dashboards zeigen "No Data"

**Prometheus-Datenquelle überprüfen**:
- Grafana → Configuration → Data Sources
- Sollte "Prometheus" als Standard anzeigen
- Verbindung testen

**Zeitbereich prüfen**:
- Stellen Sie sicher, dass der Dashboard-Zeitbereich aktuelle Daten enthält
- Versuchen Sie "Letzte 5 Minuten"

**Abfrage in Prometheus testen**:
```bash
# http://localhost:9090/graph oeffnen
# Abfrage eingeben: baluhost_cpu_usage_percent
# Sollte Daten anzeigen
```

### Hoher Speicherverbrauch (Prometheus)

**Aufbewahrung reduzieren**:
```yaml
command:
  - '--storage.tsdb.retention.time=7d'  # Auf 7 Tage reduzieren
```

**Scrape-Häufigkeit reduzieren**:
```yaml
scrape_interval: 30s  # Auf 30s erhöhen
```

### Alarme werden nicht ausgelöst

**Alarmregel-Syntax prüfen**:
```bash
docker-compose exec prometheus promtool check rules /etc/prometheus/alerts.yml
```

**Alarm-Status prüfen**:
```bash
# http://localhost:9090/alerts oeffnen
# Zeigt: Inactive, Pending oder Firing
```

**Auswertungs-Logs prüfen**:
```bash
docker-compose logs prometheus | grep -i alert
```

### Grafana kann keine Verbindung zu Prometheus herstellen

**Netzwerk prüfen**:
```bash
docker-compose exec grafana ping prometheus
```

**Datenquellen-URL prüfen**:
- Sollte sein: `http://prometheus:9090`
- NICHT: `http://localhost:9090`

**Stack neu erstellen**:
```bash
docker-compose down
docker-compose --profile monitoring up -d
```

---

## Erweiterte Themen

### Benutzerdefinierte Metriken

Fuegen Sie eigene Metriken in `backend/app/api/routes/metrics.py` hinzu:

```python
from prometheus_client import Counter

# Metrik definieren
my_custom_counter = Counter(
    'baluhost_my_custom_total',
    'Description of my custom metric',
    ['label1', 'label2'],
    registry=registry
)

# Im Code inkrementieren
my_custom_counter.labels(label1='value1', label2='value2').inc()
```

### Recording Rules

Erstellen Sie vorberechnete Metriken in `deploy/prometheus/recording_rules.yml`:

```yaml
groups:
  - name: recording_rules
    interval: 30s
    rules:
      - record: baluhost:disk_usage:avg
        expr: avg(baluhost_disk_usage_percent)
```

### Externer Prometheus

Metriken an einen externen Prometheus senden:

```yaml
# In prometheus.yml
remote_write:
  - url: 'https://prometheus.example.com/api/v1/write'
    basic_auth:
      username: 'user'
      password: 'pass'
```

---

## Ressourcen

- **Prometheus-Dokumentation**: https://prometheus.io/docs/
- **Grafana-Dokumentation**: https://grafana.com/docs/
- **PromQL-Tutorial**: https://prometheus.io/docs/prometheus/latest/querying/basics/
- **Alarmregel-Beispiele**: https://awesome-prometheus-alerts.grep.to/

---

**Zuletzt aktualisiert**: 13. Januar 2026
**BaluHost Monitoring Version**: 1.0
