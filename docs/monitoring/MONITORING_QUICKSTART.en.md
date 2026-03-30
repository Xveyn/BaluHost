# Monitoring Quick Start

Production-grade monitoring for BaluHost with Prometheus and Grafana.

## What's Included

✅ **Prometheus**: Metrics collection & alerting (Port 9090)
✅ **Grafana**: Visualization dashboards (Port 3001)
✅ **Custom Metrics**: 40+ metrics at `/api/metrics`
✅ **Pre-configured Dashboard**: System Overview
✅ **Alert Rules**: 20+ rules for critical events
✅ **Auto-provisioning**: Datasource & dashboards

---

## Quick Start (3 Steps)

### 1. Enable Monitoring

```bash
# Start with monitoring profile
docker-compose --profile monitoring up -d

# Or update existing deployment
docker-compose up -d prometheus grafana
```

### 2. Access Dashboards

**Grafana** (Main UI):
- URL: http://localhost:3001
- Login: `admin` / `admin`
- Dashboard: "BaluHost - System Overview"

**Prometheus** (Metrics Engine):
- URL: http://localhost:9090
- Targets: http://localhost:9090/targets
- Alerts: http://localhost:9090/alerts

**Raw Metrics**:
- URL: http://localhost:8000/api/metrics

### 3. Verify

```bash
# Check services are running
docker-compose ps prometheus grafana

# Test metrics endpoint
curl http://localhost:8000/api/metrics

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq
```

---

## Key Metrics

### System
- `baluhost_cpu_usage_percent` - CPU usage
- `baluhost_memory_usage_percent` - Memory usage
- `baluhost_disk_usage_percent` - Disk usage

### RAID
- `baluhost_raid_array_status` - RAID health (1=active, 0=degraded)
- `baluhost_raid_disk_count` - Disk count (total/active)
- `baluhost_raid_sync_progress_percent` - Resync progress

### Disks
- `baluhost_disk_smart_health` - SMART status (1=healthy, 0=failing)
- `baluhost_disk_temperature_celsius` - Disk temperature
- `baluhost_disk_power_on_hours` - Power-on hours

### Application
- `baluhost_http_requests_total` - HTTP requests
- `baluhost_file_uploads_total` - File uploads
- `baluhost_app_uptime_seconds` - Application uptime

---

## Key Alerts

### Critical (Immediate Action Required)
- **CPU > 95%** for 2 minutes
- **Memory > 95%** for 2 minutes
- **Disk > 90%** for 5 minutes
- **RAID array degraded**
- **Disk SMART failing**
- **Disk temperature > 65°C**
- **Backend down**

### Warning (Requires Attention)
- **CPU > 85%** for 5 minutes
- **Memory > 80%** for 5 minutes
- **Disk > 75%** for 10 minutes
- **Disk temperature > 55°C**
- **HTTP error rate > 5%**

View alerts: http://localhost:9090/alerts

---

## Common Commands

### Start/Stop Monitoring

```bash
# Start monitoring
docker-compose --profile monitoring up -d

# Stop monitoring
docker-compose stop prometheus grafana

# Restart monitoring
docker-compose restart prometheus grafana

# View logs
docker-compose logs -f prometheus
docker-compose logs -f grafana
```

### Check Status

```bash
# Service status
docker-compose ps prometheus grafana

# Health checks
curl http://localhost:9090/-/healthy
curl http://localhost:3001/api/health

# Prometheus targets
curl http://localhost:9090/api/v1/targets
```

### Backup

```bash
# Backup Grafana dashboards
docker run --rm \
  -v baluhost_grafana_data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/grafana_$(date +%Y%m%d).tar.gz -C /data .

# Backup Prometheus metrics
docker run --rm \
  -v baluhost_prometheus_data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/prometheus_$(date +%Y%m%d).tar.gz -C /data .
```

---

## Configuration

### Environment Variables

Add to `.env`:

```bash
# Prometheus
PROMETHEUS_PORT=9090

# Grafana
GRAFANA_PORT=3001
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=changeme  # CHANGE THIS!
GRAFANA_ROOT_URL=http://localhost:3001
```

### Data Retention

Edit `docker-compose.yml`:

```yaml
prometheus:
  command:
    - '--storage.tsdb.retention.time=30d'  # Keep 30 days (default: 15d)
    - '--storage.tsdb.retention.size=10GB'  # Or limit by size
```

### Scrape Interval

Edit `deploy/prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 30s  # Increase to reduce load (default: 15s)
```

---

## Creating Custom Dashboards

1. **Login to Grafana**: http://localhost:3001
2. **Create Dashboard**: + → Dashboard
3. **Add Panel** with query:

```promql
# Example queries

# CPU usage
baluhost_cpu_usage_percent

# Disk I/O rate
rate(baluhost_disk_read_bytes_total[5m])

# HTTP requests by status
sum(rate(baluhost_http_requests_total[5m])) by (status)

# RAID status
baluhost_raid_array_status

# Disk temperature
baluhost_disk_temperature_celsius
```

4. **Save dashboard**
5. **Export**: Settings → JSON Model
6. **Save** to `deploy/grafana/dashboards/<name>.json`

---

## Troubleshooting

### No Data in Dashboards

```bash
# 1. Check metrics endpoint
curl http://localhost:8000/api/metrics

# 2. Check Prometheus targets
http://localhost:9090/targets
# Should show: baluhost-backend = UP

# 3. Check Grafana datasource
# Grafana → Configuration → Data Sources
# Test connection

# 4. Test query in Prometheus
http://localhost:9090/graph
# Query: baluhost_cpu_usage_percent
```

### Metrics Endpoint Error

```bash
# Check backend logs
docker-compose logs backend | grep metrics

# Check backend is healthy
curl http://localhost:8000/api/system/health

# Restart backend
docker-compose restart backend
```

### High Resource Usage

```bash
# Reduce retention
# Edit docker-compose.yml:
# prometheus:
#   command:
#     - '--storage.tsdb.retention.time=7d'

# Reduce scrape frequency
# Edit deploy/prometheus/prometheus.yml:
# global:
#   scrape_interval: 30s

# Restart Prometheus
docker-compose restart prometheus
```

---

## Security

### 1. Change Grafana Password

```bash
# Update .env
GRAFANA_ADMIN_PASSWORD=strong-random-password

# Restart Grafana
docker-compose restart grafana
```

### 2. Restrict Access (Nginx)

Add to `deploy/nginx/baluhost.conf`:

```nginx
# Grafana (restrict to local network)
location /grafana/ {
    allow 192.168.1.0/24;
    allow 10.0.0.0/8;
    deny all;

    proxy_pass http://localhost:3001/;
}

# Prometheus (restrict to localhost only)
location /prometheus/ {
    allow 127.0.0.1;
    deny all;

    proxy_pass http://localhost:9090/;
}
```

### 3. Restrict Metrics Endpoint

Add to `deploy/nginx/baluhost.conf`:

```nginx
location /api/metrics {
    # Only allow from monitoring infrastructure
    allow 172.16.0.0/12;  # Docker network
    allow 127.0.0.1;
    deny all;

    proxy_pass http://baluhost_backend;
}
```

---

## File Structure

```
deploy/
├── prometheus/
│   ├── prometheus.yml       # Main config
│   └── alerts.yml           # Alert rules
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

## Architecture

```
┌─────────────────────┐
│   Grafana           │  Dashboards & Visualization
│   Port 3001         │  (Queries Prometheus)
└──────────┬──────────┘
           │
           ▼ Queries
┌─────────────────────┐
│   Prometheus        │  Metrics Collection & Alerting
│   Port 9090         │  (Scrapes /api/metrics every 15s)
└──────────┬──────────┘
           │
           ▼ Scrapes
┌─────────────────────┐
│   BaluHost Backend  │  Metrics Endpoint
│   /api/metrics      │  (Exposes 40+ metrics)
│   Port 8000         │
└─────────────────────┘
```

---

## Key Features

### Metrics Collection
- ✅ 40+ custom metrics
- ✅ 15-second scrape interval
- ✅ 15-day retention (configurable)
- ✅ Automatic service discovery

### Dashboards
- ✅ System Overview (CPU, Memory, Disk, Network)
- ✅ Auto-provisioned on startup
- ✅ Customizable via UI
- ✅ Exportable as JSON

### Alerts
- ✅ 20+ pre-configured rules
- ✅ 3 severity levels (Critical, Warning, Info)
- ✅ Covers: System, Disk, RAID, SMART, Application
- ✅ Extensible with custom rules

---

## Next Steps

1. **Change Grafana password** (see Security section)
2. **Create custom dashboards** (RAID, Application)
3. **Configure alert notifications** (optional)
4. **Set up Nginx access restrictions** (optional)
5. **Monitor the monitors** (set resource limits)

---

## Resources

- **Full Guide**: `docs/MONITORING.md`
- **Metrics Reference**: http://localhost:8000/api/metrics
- **Prometheus Docs**: https://prometheus.io/docs/
- **Grafana Docs**: https://grafana.com/docs/
- **PromQL Tutorial**: https://prometheus.io/docs/prometheus/latest/querying/basics/

---

**Status**: Production-ready monitoring stack
**Metrics**: 40+ custom metrics
**Alerts**: 20+ pre-configured rules
**Dashboards**: Auto-provisioned System Overview
