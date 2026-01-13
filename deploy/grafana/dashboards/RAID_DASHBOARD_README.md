# Grafana Dashboards for BaluHost

This directory contains pre-configured Grafana dashboards for monitoring BaluHost.

## Included Dashboards

### 1. System Overview (`system-overview.json`)
Comprehensive system monitoring dashboard with:
- **Gauges**: Current CPU, Memory, Disk usage
- **Time Series**: CPU & Memory trends
- **Time Series**: Disk space usage trends
- **Time Series**: Disk I/O (read/write rates)
- **Time Series**: Network traffic (sent/received)

**Refresh Rate**: 10 seconds
**Default Time Range**: Last 1 hour

### 2. Custom Dashboards (Create Your Own)

You can create additional dashboards for:
- RAID status and health
- SMART disk monitoring
- Application performance (HTTP requests, errors)
- Database statistics
- User activity
- Storage quotas

## Creating Custom Dashboards

### Via Grafana UI

1. Access Grafana: `http://localhost:3001` (or your configured port)
2. Login (default: `admin` / `admin`)
3. Click **+** → **Create** → **Dashboard**
4. Add panels with queries like:

```promql
# RAID status
baluhost_raid_array_status

# RAID sync progress
baluhost_raid_sync_progress_percent

# SMART health
baluhost_disk_smart_health

# Disk temperature
baluhost_disk_temperature_celsius

# HTTP requests
rate(baluhost_http_requests_total[5m])

# File uploads
rate(baluhost_file_uploads_total[5m])

# Active users
baluhost_users_total
```

5. Save dashboard
6. Export JSON: **Dashboard Settings** → **JSON Model** → Copy
7. Save to `deploy/grafana/dashboards/<name>.json`

### Example Queries

**RAID Health Panel**:
```promql
# Query
baluhost_raid_array_status{device="md0"}

# Panel Type: Stat
# Thresholds: 0 = red, 1 = green
```

**Disk Temperature Panel**:
```promql
# Query
baluhost_disk_temperature_celsius

# Panel Type: Gauge
# Thresholds: 0-50 green, 50-60 yellow, 60+ red
# Unit: Celsius (°C)
```

**HTTP Request Rate**:
```promql
# Query
sum(rate(baluhost_http_requests_total[5m])) by (status)

# Panel Type: Time series
# Legend: {{status}}
```

## Available Metrics

See all available metrics at: `http://localhost:8000/api/metrics`

Key metric prefixes:
- `baluhost_cpu_*` - CPU metrics
- `baluhost_memory_*` - Memory metrics
- `baluhost_disk_*` - Disk metrics (space, I/O, SMART, temperature)
- `baluhost_network_*` - Network metrics
- `baluhost_raid_*` - RAID metrics
- `baluhost_http_*` - HTTP request metrics
- `baluhost_file_*` - File operation metrics
- `baluhost_database_*` - Database metrics
- `baluhost_users_*` - User metrics
- `baluhost_storage_*` - Storage metrics
- `baluhost_app_*` - Application info & uptime

## Dashboard Best Practices

1. **Use appropriate refresh rates**:
   - System resources: 10-15s
   - RAID status: 30s
   - Application metrics: 15s

2. **Set meaningful thresholds**:
   - Disk space: 75% yellow, 90% red
   - CPU/Memory: 80% yellow, 95% red
   - Temperature: 55°C yellow, 65°C red

3. **Use appropriate visualizations**:
   - Current values: Gauge or Stat
   - Trends: Time series
   - Comparisons: Bar gauge
   - Distributions: Histogram

4. **Add helpful annotations**:
   - Document threshold meanings
   - Add links to troubleshooting docs

5. **Organize panels logically**:
   - Group related metrics
   - Most important metrics at top
   - Use rows for organization

## Provisioning

Dashboards in this directory are automatically loaded by Grafana on startup via:
- `deploy/grafana/provisioning/dashboards/baluhost.yml`

To add new dashboards:
1. Create JSON file in this directory
2. Restart Grafana: `docker-compose restart grafana`

## Troubleshooting

**Dashboard not appearing**:
- Check Grafana logs: `docker-compose logs grafana`
- Verify JSON syntax: Use online JSON validator
- Check provisioning config: `deploy/grafana/provisioning/dashboards/baluhost.yml`

**Metrics not showing data**:
- Verify Prometheus is scraping: `http://localhost:9090/targets`
- Check backend metrics endpoint: `http://localhost:8000/api/metrics`
- Verify Prometheus datasource: Grafana → Configuration → Data Sources

**Queries not working**:
- Test in Prometheus: `http://localhost:9090/graph`
- Check metric names: `http://localhost:8000/api/metrics`
- Verify time range in dashboard

## Resources

- Grafana Documentation: https://grafana.com/docs/
- Prometheus Query Examples: https://prometheus.io/docs/prometheus/latest/querying/examples/
- BaluHost Monitoring Docs: `docs/MONITORING.md`
