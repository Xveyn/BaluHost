# Monitoring-Schnellstart

Produktionsreifes Monitoring für BaluHost mit Prometheus und Grafana.

## Enthaltene Komponenten

- **Prometheus**: Metrik-Erfassung und Alarmierung (Port 9090)
- **Grafana**: Visualisierungs-Dashboards (Port 3001)
- **Benutzerdefinierte Metriken**: Über 40 Metriken unter `/api/metrics`
- **Vorkonfiguriertes Dashboard**: Systemübersicht
- **Alarmregeln**: Über 20 Regeln für kritische Ereignisse
- **Auto-Provisioning**: Datenquelle und Dashboards

---

## Schnellstart (3 Schritte)

### 1. Monitoring aktivieren

```bash
# Mit Monitoring-Profil starten
docker-compose --profile monitoring up -d

# Oder bestehende Bereitstellung aktualisieren
docker-compose up -d prometheus grafana
```

### 2. Dashboards aufrufen

**Grafana** (Hauptoberfläche):
- URL: http://localhost:3001
- Anmeldung: `admin` / `admin`
- Dashboard: "BaluHost - System Overview"

**Prometheus** (Metriken-Engine):
- URL: http://localhost:9090
- Targets: http://localhost:9090/targets
- Alarme: http://localhost:9090/alerts

**Rohe Metriken**:
- URL: http://localhost:8000/api/metrics

### 3. Überprüfen

```bash
# Prüfen, ob die Dienste laufen
docker-compose ps prometheus grafana

# Metriken-Endpunkt testen
curl http://localhost:8000/api/metrics

# Prometheus-Targets prüfen
curl http://localhost:9090/api/v1/targets | jq
```

---

## Wichtige Metriken

### System
- `baluhost_cpu_usage_percent` - CPU-Auslastung
- `baluhost_memory_usage_percent` - Speicherauslastung
- `baluhost_disk_usage_percent` - Festplattenauslastung

### RAID
- `baluhost_raid_array_status` - RAID-Gesundheit (1=aktiv, 0=degradiert)
- `baluhost_raid_disk_count` - Festplattenanzahl (gesamt/aktiv)
- `baluhost_raid_sync_progress_percent` - Resync-Fortschritt

### Festplatten
- `baluhost_disk_smart_health` - SMART-Status (1=gesund, 0=fehlerhaft)
- `baluhost_disk_temperature_celsius` - Festplattentemperatur
- `baluhost_disk_power_on_hours` - Betriebsstunden

### Anwendung
- `baluhost_http_requests_total` - HTTP-Anfragen
- `baluhost_file_uploads_total` - Datei-Uploads
- `baluhost_app_uptime_seconds` - Anwendungs-Laufzeit

---

## Wichtige Alarme

### Critical (Sofortiges Handeln erforderlich)
- **CPU > 95%** für 2 Minuten
- **Speicher > 95%** für 2 Minuten
- **Festplatte > 90%** für 5 Minuten
- **RAID-Array degradiert**
- **Festplatte SMART fehlerhaft**
- **Festplattentemperatur > 65°C**
- **Backend nicht erreichbar**

### Warning (Erfordert Aufmerksamkeit)
- **CPU > 85%** für 5 Minuten
- **Speicher > 80%** für 5 Minuten
- **Festplatte > 75%** für 10 Minuten
- **Festplattentemperatur > 55°C**
- **HTTP-Fehlerrate > 5%**

Alarme anzeigen: http://localhost:9090/alerts

---

## Häufige Befehle

### Monitoring starten/stoppen

```bash
# Monitoring starten
docker-compose --profile monitoring up -d

# Monitoring stoppen
docker-compose stop prometheus grafana

# Monitoring neu starten
docker-compose restart prometheus grafana

# Logs anzeigen
docker-compose logs -f prometheus
docker-compose logs -f grafana
```

### Status prüfen

```bash
# Dienststatus
docker-compose ps prometheus grafana

# Gesundheitschecks
curl http://localhost:9090/-/healthy
curl http://localhost:3001/api/health

# Prometheus-Targets
curl http://localhost:9090/api/v1/targets
```

### Backup

```bash
# Grafana-Dashboards sichern
docker run --rm \
  -v baluhost_grafana_data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/grafana_$(date +%Y%m%d).tar.gz -C /data .

# Prometheus-Metriken sichern
docker run --rm \
  -v baluhost_prometheus_data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/prometheus_$(date +%Y%m%d).tar.gz -C /data .
```

---

## Konfiguration

### Umgebungsvariablen

Zur `.env` hinzufügen:

```bash
# Prometheus
PROMETHEUS_PORT=9090

# Grafana
GRAFANA_PORT=3001
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=changeme  # AENDERN SIE DIES!
GRAFANA_ROOT_URL=http://localhost:3001
```

### Datenaufbewahrung

In `docker-compose.yml` bearbeiten:

```yaml
prometheus:
  command:
    - '--storage.tsdb.retention.time=30d'  # 30 Tage aufbewahren (Standard: 15d)
    - '--storage.tsdb.retention.size=10GB'  # Oder nach Größe begrenzen
```

### Scrape-Intervall

In `deploy/prometheus/prometheus.yml` bearbeiten:

```yaml
global:
  scrape_interval: 30s  # Erhöhen zur Lastreduzierung (Standard: 15s)
```

---

## Benutzerdefinierte Dashboards erstellen

1. **Bei Grafana anmelden**: http://localhost:3001
2. **Dashboard erstellen**: + → Dashboard
3. **Panel hinzufügen** mit Abfrage:

```promql
# Beispiel-Abfragen

# CPU-Auslastung
baluhost_cpu_usage_percent

# Festplatten-I/O-Rate
rate(baluhost_disk_read_bytes_total[5m])

# HTTP-Anfragen nach Status
sum(rate(baluhost_http_requests_total[5m])) by (status)

# RAID-Status
baluhost_raid_array_status

# Festplattentemperatur
baluhost_disk_temperature_celsius
```

4. **Dashboard speichern**
5. **Exportieren**: Settings → JSON Model
6. **Speichern** unter `deploy/grafana/dashboards/<name>.json`

---

## Fehlerbehebung

### Keine Daten in Dashboards

```bash
# 1. Metriken-Endpunkt prüfen
curl http://localhost:8000/api/metrics

# 2. Prometheus-Targets prüfen
http://localhost:9090/targets
# Sollte anzeigen: baluhost-backend = UP

# 3. Grafana-Datenquelle prüfen
# Grafana → Configuration → Data Sources
# Verbindung testen

# 4. Abfrage in Prometheus testen
http://localhost:9090/graph
# Abfrage: baluhost_cpu_usage_percent
```

### Fehler am Metriken-Endpunkt

```bash
# Backend-Logs prüfen
docker-compose logs backend | grep metrics

# Prüfen, ob das Backend gesund ist
curl http://localhost:8000/api/system/health

# Backend neu starten
docker-compose restart backend
```

### Hoher Ressourcenverbrauch

```bash
# Aufbewahrung reduzieren
# In docker-compose.yml bearbeiten:
# prometheus:
#   command:
#     - '--storage.tsdb.retention.time=7d'

# Scrape-Häufigkeit reduzieren
# In deploy/prometheus/prometheus.yml bearbeiten:
# global:
#   scrape_interval: 30s

# Prometheus neu starten
docker-compose restart prometheus
```

---

## Sicherheit

### 1. Grafana-Passwort ändern

```bash
# .env aktualisieren
GRAFANA_ADMIN_PASSWORD=starkes-zufälliges-passwort

# Grafana neu starten
docker-compose restart grafana
```

### 2. Zugriff einschränken (Nginx)

Zur `deploy/nginx/baluhost.conf` hinzufügen:

```nginx
# Grafana (auf lokales Netzwerk beschränken)
location /grafana/ {
    allow 192.168.1.0/24;
    allow 10.0.0.0/8;
    deny all;

    proxy_pass http://localhost:3001/;
}

# Prometheus (nur auf localhost beschränken)
location /prometheus/ {
    allow 127.0.0.1;
    deny all;

    proxy_pass http://localhost:9090/;
}
```

### 3. Metriken-Endpunkt einschränken

Zur `deploy/nginx/baluhost.conf` hinzufügen:

```nginx
location /api/metrics {
    # Nur von Monitoring-Infrastruktur erlauben
    allow 172.16.0.0/12;  # Docker-Netzwerk
    allow 127.0.0.1;
    deny all;

    proxy_pass http://baluhost_backend;
}
```

---

## Dateistruktur

```
deploy/
├── prometheus/
│   ├── prometheus.yml       # Hauptkonfiguration
│   └── alerts.yml           # Alarmregeln
└── grafana/
    ├── provisioning/
    │   ├── datasources/
    │   │   └── prometheus.yml
    │   └── dashboards/
    │       └── baluhost.yml
    └── dashboards/
        └── system-overview.json
```

---

## Architektur

```
┌─────────────────────┐
│   Grafana           │  Dashboards und Visualisierung
│   Port 3001         │  (Fragt Prometheus ab)
└──────────┬──────────┘
           │
           ▼ Abfragen
┌─────────────────────┐
│   Prometheus        │  Metrik-Erfassung und Alarmierung
│   Port 9090         │  (Scraping von /api/metrics alle 15s)
└──────────┬──────────┘
           │
           ▼ Scraping
┌─────────────────────┐
│   BaluHost Backend  │  Metriken-Endpunkt
│   /api/metrics      │  (Stellt über 40 Metriken bereit)
│   Port 8000         │
└─────────────────────┘
```

---

## Hauptfunktionen

### Metrik-Erfassung
- Über 40 benutzerdefinierte Metriken
- 15-Sekunden-Scrape-Intervall
- 15 Tage Aufbewahrung (konfigurierbar)
- Automatische Service-Erkennung

### Dashboards
- Systemübersicht (CPU, Speicher, Festplatte, Netzwerk)
- Automatisches Provisioning beim Start
- Anpassbar über die Oberfläche
- Exportierbar als JSON

### Alarme
- Über 20 vorkonfigurierte Regeln
- 3 Schweregrade (Critical, Warning, Info)
- Abdeckung: System, Festplatte, RAID, SMART, Anwendung
- Erweiterbar mit benutzerdefinierten Regeln

---

## Naechste Schritte

1. **Grafana-Passwort ändern** (siehe Abschnitt Sicherheit)
2. **Benutzerdefinierte Dashboards erstellen** (RAID, Anwendung)
3. **Alarm-Benachrichtigungen konfigurieren** (optional)
4. **Nginx-Zugriffsbeschränkungen einrichten** (optional)
5. **Die Überwachung überwachen** (Ressourcenlimits setzen)

---

## Ressourcen

- **Vollständige Anleitung**: `docs/MONITORING.md`
- **Metriken-Referenz**: http://localhost:8000/api/metrics
- **Prometheus-Dokumentation**: https://prometheus.io/docs/
- **Grafana-Dokumentation**: https://grafana.com/docs/
- **PromQL-Tutorial**: https://prometheus.io/docs/prometheus/latest/querying/basics/

---

**Status**: Produktionsreifer Monitoring-Stack
**Metriken**: Über 40 benutzerdefinierte Metriken
**Alarme**: Über 20 vorkonfigurierte Regeln
**Dashboards**: Automatisch bereitgestellte Systemübersicht
