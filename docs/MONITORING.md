# Monitoring Guide for BaluHost

Complete guide for setting up production-grade monitoring with Prometheus and Grafana.

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Metrics](#metrics)
4. [Dashboards](#dashboards)
5. [Alerts](#alerts)
6. [Configuration](#configuration)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

---

## Overview

BaluHost includes comprehensive monitoring infrastructure:

- **Prometheus**: Metrics collection and alerting
- **Grafana**: Visualization dashboards
- **Custom Metrics Endpoint**: `/api/metrics` with 40+ metrics
- **Pre-configured Dashboards**: System overview, RAID, Application
- **Alert Rules**: 20+ alert rules for critical events

### Architecture

```
┌──────────────────┐
│  Grafana         │
│  (Dashboards)    │
│  Port 3001       │
└────────┬─────────┘
         │
         │ Queries
         ▼
┌──────────────────┐
│  Prometheus      │
│  (Metrics DB)    │
│  Port 9090       │
└────────┬─────────┘
         │
         │ Scrapes (every 15s)
         ▼
┌──────────────────┐
│  BaluHost        │
│  /api/metrics    │
│  Port 8000       │
└──────────────────┘
```

---

## Quick Start

### Step 1: Enable Monitoring

Update your `.env` file:

```bash
# Monitoring ports
PROMETHEUS_PORT=9090
GRAFANA_PORT=3001

# Grafana credentials
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=changeme  # Change this!
GRAFANA_ROOT_URL=http://localhost:3001
```

### Step 2: Start Monitoring Stack

```bash
# Start BaluHost with monitoring
docker-compose --profile monitoring up -d

# Or update existing deployment
docker-compose up -d prometheus grafana
```

### Step 3: Access Dashboards

**Grafana** (Dashboards):
- URL: http://localhost:3001
- Login: `admin` / `admin` (or your configured password)
- Pre-loaded dashboard: "BaluHost - System Overview"

**Prometheus** (Raw Metrics):
- URL: http://localhost:9090
- No authentication required
- Query interface: http://localhost:9090/graph

**Raw Metrics Endpoint**:
- URL: http://localhost:8000/api/metrics
- Prometheus format
- No authentication required (can be restricted in Nginx)

### Step 4: Verify Metrics Collection

**Check Prometheus is scraping**:
```bash
# Open in browser
http://localhost:9090/targets

# Should show:
# - prometheus: UP
# - baluhost-backend: UP
```

**Test metrics endpoint**:
```bash
curl http://localhost:8000/api/metrics

# Should return Prometheus-format metrics like:
# baluhost_cpu_usage_percent 15.3
# baluhost_memory_usage_percent 45.2
# ...
```

---

## Metrics

BaluHost exposes 40+ custom metrics at `/api/metrics`.

### System Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `baluhost_cpu_usage_percent` | Gauge | Current CPU usage (0-100%) |
| `baluhost_cpu_count` | Gauge | Number of CPU cores |
| `baluhost_memory_total_bytes` | Gauge | Total system memory |
| `baluhost_memory_used_bytes` | Gauge | Used system memory |
| `baluhost_memory_available_bytes` | Gauge | Available system memory |
| `baluhost_memory_usage_percent` | Gauge | Memory usage percentage |

### Disk Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `baluhost_disk_total_bytes` | Gauge | `path` | Total disk space |
| `baluhost_disk_used_bytes` | Gauge | `path` | Used disk space |
| `baluhost_disk_free_bytes` | Gauge | `path` | Free disk space |
| `baluhost_disk_usage_percent` | Gauge | `path` | Disk usage percentage |
| `baluhost_disk_read_bytes_total` | Counter | `device` | Total bytes read |
| `baluhost_disk_write_bytes_total` | Counter | `device` | Total bytes written |

### RAID Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `baluhost_raid_array_status` | Gauge | `device, level, status` | RAID array status (1=active, 0=degraded) |
| `baluhost_raid_disk_count` | Gauge | `device, type` | Number of disks (total/active) |
| `baluhost_raid_sync_progress_percent` | Gauge | `device` | Resync/recovery progress |

### SMART Disk Health

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `baluhost_disk_smart_health` | Gauge | `device, serial` | SMART health (1=healthy, 0=failing) |
| `baluhost_disk_temperature_celsius` | Gauge | `device` | Disk temperature |
| `baluhost_disk_power_on_hours` | Gauge | `device` | Power-on hours |

### Network Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `baluhost_network_received_bytes_total` | Counter | `interface` | Total bytes received |
| `baluhost_network_sent_bytes_total` | Counter | `interface` | Total bytes sent |

### Application Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `baluhost_http_requests_total` | Counter | `method, endpoint, status` | Total HTTP requests |
| `baluhost_http_request_duration_seconds` | Histogram | `method, endpoint` | Request duration |
| `baluhost_file_uploads_total` | Counter | `status` | Total file uploads |
| `baluhost_file_downloads_total` | Counter | `status` | Total file downloads |

### Database Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `baluhost_database_connections` | Gauge | Active DB connections |
| `baluhost_database_query_duration_seconds` | Histogram | Query duration |

### User Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `baluhost_users_total` | Gauge | `role` | Total users by role |
| `baluhost_users_active_sessions` | Gauge | - | Active user sessions |

### Application Info

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `baluhost_app_info` | Gauge | `version, mode, python_version` | Application information |
| `baluhost_app_uptime_seconds` | Gauge | - | Application uptime |

---

## Dashboards

### Pre-configured Dashboards

#### 1. System Overview
**File**: `deploy/grafana/dashboards/system-overview.json`

**Panels**:
- CPU Usage (Gauge)
- Memory Usage (Gauge)
- Disk Usage (Gauge)
- CPU & Memory Over Time (Time Series)
- Disk Space Over Time (Time Series)
- Disk I/O (Time Series)
- Network Traffic (Time Series)

**Refresh**: 10 seconds
**Time Range**: Last 1 hour

### Creating Custom Dashboards

**Example: RAID Health Dashboard**

1. Login to Grafana
2. Create new dashboard
3. Add panel with query:

```promql
baluhost_raid_array_status{device="md0"}
```

4. Configure panel:
   - Type: Stat
   - Thresholds: 0 = Red (degraded), 1 = Green (healthy)
   - Value mappings: 0 = "Degraded", 1 = "Active"

5. Add more panels:
   - Disk count: `baluhost_raid_disk_count`
   - Sync progress: `baluhost_raid_sync_progress_percent`
   - Disk temperature: `baluhost_disk_temperature_celsius`

6. Save dashboard
7. Export JSON: Settings → JSON Model
8. Save to `deploy/grafana/dashboards/raid.json`

**Example Queries**:

```promql
# CPU usage over time
baluhost_cpu_usage_percent

# Memory usage trend
baluhost_memory_usage_percent

# Disk I/O rate (bytes/sec)
rate(baluhost_disk_read_bytes_total[5m])
rate(baluhost_disk_write_bytes_total[5m])

# Network traffic (bytes/sec)
rate(baluhost_network_received_bytes_total[5m])
rate(baluhost_network_sent_bytes_total[5m])

# HTTP request rate by status
sum(rate(baluhost_http_requests_total[5m])) by (status)

# Failed disk count
count(baluhost_disk_smart_health == 0)

# Average disk temperature
avg(baluhost_disk_temperature_celsius)

# Storage usage percentage
(baluhost_storage_used_bytes / baluhost_storage_quota_bytes) * 100
```

---

## Alerts

BaluHost includes 20+ pre-configured alert rules.

### Alert Severities

- **Critical**: Immediate action required (red)
- **Warning**: Requires attention (yellow)
- **Info**: Informational only (blue)

### Key Alerts

#### System Resources

| Alert | Condition | For | Severity |
|-------|-----------|-----|----------|
| HighCPUUsage | CPU > 85% | 5m | Warning |
| CriticalCPUUsage | CPU > 95% | 2m | Critical |
| HighMemoryUsage | Memory > 80% | 5m | Warning |
| CriticalMemoryUsage | Memory > 95% | 2m | Critical |

#### Disk Space

| Alert | Condition | For | Severity |
|-------|-----------|-----|----------|
| LowDiskSpace | Disk > 75% | 10m | Warning |
| CriticalDiskSpace | Disk > 90% | 5m | Critical |
| DiskWillBeFull | Will be full in 4h | 10m | Warning |

#### RAID

| Alert | Condition | For | Severity |
|-------|-----------|-----|----------|
| RAIDArrayDegraded | Status != active | 1m | Critical |
| RAIDDiskMissing | Active < Total disks | 2m | Critical |
| RAIDResyncInProgress | 0% < Progress < 100% | 5m | Info |

#### SMART Disk Health

| Alert | Condition | For | Severity |
|-------|-----------|-----|----------|
| DiskFailing | Health == 0 | 1m | Critical |
| DiskTemperatureHigh | Temp > 55°C | 10m | Warning |
| DiskTemperatureCritical | Temp > 65°C | 5m | Critical |

#### Application

| Alert | Condition | For | Severity |
|-------|-----------|-----|----------|
| BackendDown | up == 0 | 1m | Critical |
| HighErrorRate | 5xx errors > 5% | 5m | Warning |
| ApplicationRestarted | Uptime < 5m | 1m | Info |

### Viewing Active Alerts

**Prometheus**:
```bash
# Open in browser
http://localhost:9090/alerts
```

**Grafana**:
- Navigate to **Alerting** → **Alert Rules**
- View alert history and current state

### Alert Notifications (Optional)

To receive alert notifications, configure Alertmanager:

1. Create `deploy/prometheus/alertmanager.yml`
2. Configure notification channels (email, Slack, PagerDuty, etc.)
3. Add Alertmanager to docker-compose.yml
4. Update Prometheus config to point to Alertmanager

**Example Alertmanager config**:
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

## Configuration

### Prometheus Configuration

**File**: `deploy/prometheus/prometheus.yml`

**Key settings**:
```yaml
global:
  scrape_interval: 15s      # How often to scrape metrics
  evaluation_interval: 15s  # How often to evaluate rules

scrape_configs:
  - job_name: 'baluhost-backend'
    scrape_interval: 15s
    scrape_timeout: 10s
    metrics_path: '/api/metrics'
    static_configs:
      - targets: ['backend:8000']
```

**Tuning**:
- Increase `scrape_interval` to reduce load (e.g., 30s)
- Decrease for more granular metrics (e.g., 10s)
- Adjust `storage.tsdb.retention.time` for data retention (default: 15d)

### Grafana Configuration

**Environment variables** (`.env`):
```bash
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=changeme
GRAFANA_ROOT_URL=http://localhost:3001
```

**Data source**: Auto-configured via provisioning
**Dashboards**: Auto-loaded from `deploy/grafana/dashboards/`

---

## Best Practices

### 1. Secure Grafana

**Change default password**:
```bash
# Update in .env
GRAFANA_ADMIN_PASSWORD=strong-random-password
```

**Restrict access** (in Nginx):
```nginx
location /grafana/ {
    allow 192.168.1.0/24;  # Local network only
    deny all;
    proxy_pass http://grafana:3000/;
}
```

### 2. Manage Data Retention

**Prometheus** (default: 15 days):
```yaml
# In docker-compose.yml
command:
  - '--storage.tsdb.retention.time=30d'  # Keep 30 days
  - '--storage.tsdb.retention.size=10GB'  # Or limit by size
```

### 3. Set Meaningful Alert Thresholds

Adjust based on your hardware and usage:
- CPU: 85% warning, 95% critical
- Memory: 80% warning, 95% critical
- Disk: 75% warning, 90% critical
- Disk temp: 55°C warning, 65°C critical

### 4. Monitor the Monitors

- Prometheus self-monitoring: http://localhost:9090/metrics
- Grafana health: http://localhost:3001/api/health
- Set up alerts for monitoring stack itself

### 5. Regular Backups

Backup Grafana dashboards and Prometheus data:
```bash
# Backup Grafana
docker run --rm -v baluhost_grafana_data:/data -v $(pwd)/backups:/backup \
  alpine tar czf /backup/grafana_$(date +%Y%m%d).tar.gz -C /data .

# Backup Prometheus
docker run --rm -v baluhost_prometheus_data:/data -v $(pwd)/backups:/backup \
  alpine tar czf /backup/prometheus_$(date +%Y%m%d).tar.gz -C /data .
```

---

## Troubleshooting

### Metrics Not Appearing

**Check backend metrics endpoint**:
```bash
curl http://localhost:8000/api/metrics

# Should return Prometheus-format text
```

**Check Prometheus is scraping**:
```bash
# Open in browser
http://localhost:9090/targets

# baluhost-backend should be UP
```

**Check Prometheus logs**:
```bash
docker-compose logs prometheus | grep -i error
```

### Dashboards Show "No Data"

**Verify Prometheus datasource**:
- Grafana → Configuration → Data Sources
- Should show "Prometheus" as default
- Test connection

**Check time range**:
- Ensure dashboard time range includes recent data
- Try "Last 5 minutes"

**Test query in Prometheus**:
```bash
# Open http://localhost:9090/graph
# Enter query: baluhost_cpu_usage_percent
# Should show data
```

### High Memory Usage (Prometheus)

**Reduce retention**:
```yaml
command:
  - '--storage.tsdb.retention.time=7d'  # Reduce to 7 days
```

**Reduce scrape frequency**:
```yaml
scrape_interval: 30s  # Increase to 30s
```

### Alerts Not Firing

**Check alert rules syntax**:
```bash
docker-compose exec prometheus promtool check rules /etc/prometheus/alerts.yml
```

**Check alert state**:
```bash
# Open http://localhost:9090/alerts
# Shows: Inactive, Pending, or Firing
```

**Check evaluation logs**:
```bash
docker-compose logs prometheus | grep -i alert
```

### Grafana Cannot Connect to Prometheus

**Check network**:
```bash
docker-compose exec grafana ping prometheus
```

**Check datasource URL**:
- Should be: `http://prometheus:9090`
- NOT: `http://localhost:9090`

**Recreate stack**:
```bash
docker-compose down
docker-compose --profile monitoring up -d
```

---

## Advanced Topics

### Custom Metrics

Add your own metrics in `backend/app/api/routes/metrics.py`:

```python
from prometheus_client import Counter

# Define metric
my_custom_counter = Counter(
    'baluhost_my_custom_total',
    'Description of my custom metric',
    ['label1', 'label2'],
    registry=registry
)

# Increment in code
my_custom_counter.labels(label1='value1', label2='value2').inc()
```

### Recording Rules

Create pre-computed metrics in `deploy/prometheus/recording_rules.yml`:

```yaml
groups:
  - name: recording_rules
    interval: 30s
    rules:
      - record: baluhost:disk_usage:avg
        expr: avg(baluhost_disk_usage_percent)
```

### External Prometheus

Send metrics to external Prometheus:

```yaml
# In prometheus.yml
remote_write:
  - url: 'https://prometheus.example.com/api/v1/write'
    basic_auth:
      username: 'user'
      password: 'pass'
```

---

## Resources

- **Prometheus Documentation**: https://prometheus.io/docs/
- **Grafana Documentation**: https://grafana.com/docs/
- **PromQL Tutorial**: https://prometheus.io/docs/prometheus/latest/querying/basics/
- **Alert Rule Examples**: https://awesome-prometheus-alerts.grep.to/

---

**Last Updated**: January 13, 2026
**BaluHost Monitoring Version**: 1.0
