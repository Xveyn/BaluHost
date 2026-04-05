# Disk I/O Monitor - Implementation

## Overview

The Disk I/O Monitor page displays real-time read and write activity for all physical disks. The implementation is based on `psutil` for the backend and Recharts for frontend visualization.

## Backend Implementation

### 1. Disk Monitor Service (`app/services/disk_monitor.py`)

The service continuously monitors I/O activity across all physical disks:

**Features:**
- Sampling every 1 second for real-time monitoring
- Stores 120 samples (2 minutes of history) per disk
- Calculates MB/s (throughput) and IOPS (Operations per Second)
- Filters physical disks (no partitions)
- Automatic logging every 60 seconds

**Key Functions:**
- `start_monitoring()`: Starts the background task
- `stop_monitoring()`: Stops the background task
- `get_disk_io_history()`: Returns the complete history for all disks
- `get_available_disks()`: List of all monitored disks
- `_sample_disk_io()`: Takes a measurement of all disks
- `_log_disk_activity()`: Logs an activity summary

**Platform Support:**
- **Windows**: Detects `PhysicalDrive0`, `PhysicalDrive1`, etc.
- **Linux**: Detects `sda`, `sdb`, `nvme0n1`, etc. (without partition numbers)

### 2. API Endpoint (`app/api/routes/system.py`)

**New Endpoint:**
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

New Pydantic models:
- `DiskIOSample`: Single measurement with timestamp, MB/s, and IOPS
- `DiskIOHistory`: History for a single disk
- `DiskIOResponse`: Complete API response

### 4. Integration (`app/main.py`)

The Disk Monitor is automatically initialized at server startup:
```python
disk_monitor.start_monitoring()  # In _lifespan
```

## Frontend Implementation

### 1. SystemMonitor Component (`client/src/pages/SystemMonitor.tsx`)

**Features:**
- Real-time charts with Recharts
- Disk selection via buttons
- Toggle between throughput (MB/s) and IOPS
- 4 stat cards: Read, Write, Read IOPS, Write IOPS
- Live chart with 60 seconds of history
- Auto-update every 2 seconds

**Components:**
- Disk Selector: Button group for disk selection
- Stats Cards: 4 cards with current values
- Interactive Chart: LineChart with Read/Write lines
- View Mode Toggle: Switch between MB/s and IOPS view

### 2. Chart Configuration

**Recharts Components:**
- `LineChart`: Main chart container
- `CartesianGrid`: Background grid
- `XAxis`: Time axis (HH:MM:SS format)
- `YAxis`: Value axis with dynamic label
- `Tooltip`: Hover information
- `Legend`: Legend for Read/Write
- `Line`: Two lines (blue for Read, green for Write)

## Logging

### Log Format

An activity summary is logged every 60 seconds:

```
Disk Activity Log (last 60s):
  PhysicalDrive0: Read=12.50MB/s (max 25.30), Write=5.30MB/s (max 8.90), IOPS R=150/W=75
  PhysicalDrive1: Read=0.00MB/s (max 0.00), Write=0.00MB/s (max 0.00), IOPS R=0/W=0
```

### Log Levels

- `INFO`: Normal activity logs, monitor start/stop
- `DEBUG`: Detailed sampling information
- `ERROR`: Errors during sampling or in the monitor loop

### Log Configuration

Logs appear in the standard backend log. For separate disk logs:

```python
# In logging config
'app.services.disk_monitor': {
    'handlers': ['disk_file'],
    'level': 'INFO',
}
```

## Performance

### Resource Consumption

- **CPU**: Minimal (~0.1% per sample)
- **Memory**: ~50KB per disk for 120 samples
- **Disk I/O**: Reading from `/proc/diskstats` (Linux) or WMI (Windows)

### Optimizations

1. **Sampling interval**: 1 second is optimal for real-time monitoring without overhead
2. **History size**: 120 samples = 2 minutes is sufficient for charts
3. **Frontend update**: 2 seconds reduces API calls without data loss

## Platform Specifics

### Windows

- Uses `psutil.disk_io_counters(perdisk=True)`
- Disk names: `PhysicalDrive0`, `PhysicalDrive1`, etc.
- Works out of the box, no administrator privileges required

### Linux

- Uses `/proc/diskstats`
- Disk names: `sda`, `sdb`, `nvme0n1`, etc.
- Automatically filters partitions (`sda1`, `nvme0n1p1`)

### macOS

- Limited support through psutil
- Disk names: `disk0`, `disk1`, etc.

## Testing

### Backend Tests

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

### Frontend Tests

1. Start the backend
2. Start the frontend
3. Navigate to the System Monitor page
4. Select different disks
5. Switch between MB/s and IOPS
6. Generate I/O load and observe changes

### Generating Load for Tests

**Windows (PowerShell):**
```powershell
# Write load
1..100 | ForEach-Object { 
    [System.IO.File]::WriteAllBytes("test_$_.dat", (New-Object byte[] 10MB))
}

# Read load
1..100 | ForEach-Object {
    Get-Content "test_$_.dat" | Out-Null
}
```

**Linux:**
```bash
# Write load
dd if=/dev/zero of=test.dat bs=1M count=1000

# Read load  
dd if=test.dat of=/dev/null bs=1M
```

## Features

- Historical data is stored in the database (`disk_io_samples` table)
- SMART data and disk temperatures are collected via the Monitoring Orchestrator
- Retention is configurable

## Troubleshooting

### Problem: No Disks Detected

**Cause**: psutil cannot read disk counters
**Solution**: 
- Windows: Check if `wmi` is installed
- Linux: Check access to `/proc/diskstats`
- Run as administrator/root

### Problem: Only Zeros in Values

**Cause**: First sample has no reference point
**Solution**: Wait 2-3 seconds, then deltas will be calculated

### Problem: Chart Shows Nothing

**Cause**: Frontend is not receiving data
**Solution**:
1. Check backend logs for errors
2. Check API response in browser DevTools
3. Ensure the Disk Monitor is running

### Problem: High CPU Load

**Cause**: Sampling interval too short
**Solution**: Increase `_SAMPLE_INTERVAL_SECONDS` in `disk_monitor.py`

## Configuration

### Backend Configuration

In `app/services/disk_monitor.py`:

```python
# Sampling interval (seconds)
_SAMPLE_INTERVAL_SECONDS = 1.0

# Maximum number of samples per disk
_MAX_SAMPLES = 120

# Log interval (seconds)
_LOG_INTERVAL_SECONDS = 60.0
```

### Frontend Configuration

In `client/src/pages/SystemMonitor.tsx`:

```typescript
// Update interval (milliseconds)
const interval = setInterval(loadDiskIO, 2000);

// Number of displayed samples in the chart
const samples = disk.samples.slice(-60);
```

## Dependencies

### Backend

- `psutil >= 5.9.0`: For disk I/O counters
- `asyncio`: For background task
- `FastAPI`: For API endpoint
- `Pydantic`: For schemas

### Frontend

- `recharts >= 2.0.0`: Chart library
- `react >= 18.2.0`: UI framework
- `tailwindcss`: Styling

## License and Credits

Based on:
- psutil: https://github.com/giampaolo/psutil
- Recharts: https://recharts.org
- Windows Resource Monitor as UI inspiration
