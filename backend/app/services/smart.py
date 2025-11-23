from __future__ import annotations

import logging
import platform
from datetime import datetime, timezone

from app.core.config import settings
from app.schemas.system import SmartAttribute, SmartDevice, SmartStatusResponse

logger = logging.getLogger(__name__)


class SmartUnavailableError(RuntimeError):
    """Raised when SMART diagnostics cannot be accessed."""


# Cache-Konfiguration (vereinfacht, klare Typen)
_SMART_CACHE_TTL_SECONDS = 120  # Wie lange SMART Daten gültig bleiben
_SMART_CACHE_TIMESTAMP: datetime | None = None
_SMART_CACHE_DATA: SmartStatusResponse | None = None

def _smart_cache_valid() -> bool:
    if _SMART_CACHE_TIMESTAMP is None:
        return False
    return (datetime.now(timezone.utc) - _SMART_CACHE_TIMESTAMP).total_seconds() < _SMART_CACHE_TTL_SECONDS

def _set_smart_cache(payload: SmartStatusResponse) -> None:
    global _SMART_CACHE_TIMESTAMP, _SMART_CACHE_DATA
    _SMART_CACHE_TIMESTAMP = datetime.now(timezone.utc)
    _SMART_CACHE_DATA = payload

def get_cached_smart_status() -> SmartStatusResponse | None:
    if _smart_cache_valid():
        return _SMART_CACHE_DATA
    return None

def invalidate_smart_cache() -> None:
    global _SMART_CACHE_TIMESTAMP, _SMART_CACHE_DATA
    _SMART_CACHE_TIMESTAMP = None
    _SMART_CACHE_DATA = None


def _get_smartctl_path() -> str | None:
    """Find smartctl executable path."""
    import os
    import shutil
    
    # Try to find smartctl in PATH
    smartctl = shutil.which('smartctl')
    if smartctl:
        return smartctl
    
    # Check common Windows installation path
    if platform.system().lower() == "windows":
        windows_path = r"C:\Program Files\smartmontools\bin\smartctl.exe"
        if os.path.exists(windows_path):
            return windows_path
    
    return None


def _get_windows_disk_capacity(device_name: str) -> int | None:
    """Get disk capacity from Windows WMI for a specific device."""
    try:
        import subprocess
        
        # Convert /dev/sdX to drive number
        # /dev/sda = 0, /dev/sdb = 1, etc.
        if not device_name.startswith('/dev/sd'):
            return None
        
        drive_letter = device_name[-1]  # Get last character (a, b, c, etc.)
        drive_number = ord(drive_letter) - ord('a')
        
        # Use PowerShell to query WMI
        ps_cmd = f"Get-PhysicalDisk | Where-Object {{$_.DeviceId -eq {drive_number}}} | Select-Object -ExpandProperty Size"
        result = subprocess.run(
            ['powershell', '-Command', ps_cmd],
            capture_output=True,
            text=True,
            check=False,
            timeout=5
        )
        
        if result.returncode == 0 and result.stdout.strip():
            try:
                return int(result.stdout.strip())
            except ValueError:
                pass
                
    except Exception as e:
        logger.debug("Failed to get Windows disk capacity: %s", e)
    
    return None


def _read_real_smart_data() -> SmartStatusResponse:
    """Optimierte SMART-Erfassung mit paralleler Verarbeitung und reduzierten Flags."""
    import json, subprocess, re
    from concurrent.futures import ThreadPoolExecutor, as_completed

    smartctl_path = _get_smartctl_path()
    if not smartctl_path:
        raise FileNotFoundError("smartctl not found in PATH")

    now = datetime.now(tz=timezone.utc)
    scan_result = subprocess.run([smartctl_path, '--scan', '-j'], capture_output=True, text=True, check=False, timeout=10)
    if scan_result.returncode not in [0, 4]:
        raise SmartUnavailableError("Scan failed")
    try:
        scan_data = json.loads(scan_result.stdout)
    except json.JSONDecodeError as e:
        raise SmartUnavailableError("Scan JSON parse failed") from e
    device_list = scan_data.get('devices', [])

    def fetch_device(dev_info: dict) -> SmartDevice | None:
        device_name = dev_info.get('name')
        dev_type = dev_info.get('type', 'auto')
        if not device_name:
            return None
        # Flags reduzieren
        base_args = [smartctl_path, '-H', '-i', '-j', '-d', dev_type, device_name]
        # Für ATA zusätzliche Attribute
        if not re.search(r'nvme', dev_type, re.IGNORECASE) and 'nvme' not in device_name.lower():
            base_args.insert(1, '-A')
        result = subprocess.run(base_args, capture_output=True, text=True, check=False, timeout=20)
        if result.returncode > 64:
            return None
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None
        model_info = data.get('model_name') or data.get('model_family') or 'Unknown Model'
        serial = data.get('serial_number', 'Unknown')
        # Capacity
        capacity_bytes = None
        uc = data.get('user_capacity', {})
        if isinstance(uc, dict):
            capacity_bytes = uc.get('bytes')
        if not capacity_bytes and platform.system().lower() == 'windows':
            try:
                capacity_bytes = _get_windows_disk_capacity(device_name)
            except Exception:
                pass
        # Temperature
        temperature = None
        if isinstance(data.get('temperature'), dict):
            temperature = data['temperature'].get('current')
        # Status
        smart_status = data.get('smart_status', {})
        status = 'PASSED' if smart_status.get('passed') else 'FAILED'
        attributes: list[SmartAttribute] = []
        ata_attributes = data.get('ata_smart_attributes', {})
        if isinstance(ata_attributes, dict):
            for attr in ata_attributes.get('table', []):
                if not isinstance(attr, dict):
                    continue
                when_failed = attr.get('when_failed', '')
                attr_status = 'FAILING' if when_failed and when_failed != '-' else 'OK'
                attributes.append(SmartAttribute(
                    id=attr.get('id', 0),
                    name=attr.get('name', 'Unknown'),
                    value=attr.get('value', 0),
                    worst=attr.get('worst', 0),
                    threshold=attr.get('thresh', 0),
                    raw=str(attr.get('raw', {}).get('value', 0)) if isinstance(attr.get('raw'), dict) else str(attr.get('raw', '0')),
                    status=attr_status,
                ))
        nvme_log = data.get('nvme_smart_health_information_log', {})
        if isinstance(nvme_log, dict) and not attributes:
            # Minimal NVMe Attribute Auswahl
            if 'temperature' in nvme_log:
                temp_raw = nvme_log.get('temperature')
                if temp_raw is None:
                    temp_val = 0
                else:
                    try:
                        temp_val = int(temp_raw)
                    except Exception:
                        temp_val = 0
                if temperature is None:
                    temperature = temp_val
                attributes.append(SmartAttribute(id=194, name='Temperature', value=temp_val, worst=0, threshold=0, raw=str(temp_val), status='OK'))
            if 'available_spare' in nvme_log:
                attributes.append(SmartAttribute(id=5, name='Available_Spare', value=nvme_log.get('available_spare', 0), worst=0, threshold=nvme_log.get('available_spare_threshold', 0), raw=str(nvme_log.get('available_spare', 0)), status='OK'))
        return SmartDevice(name=device_name, model=model_info, serial=serial, temperature=temperature, status=status, capacity_bytes=capacity_bytes, used_bytes=None, used_percent=None, mount_point=None, attributes=attributes)

    devices: list[SmartDevice] = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(device_list)))) as executor:
        futures = [executor.submit(fetch_device, dev) for dev in device_list]
        for fut in as_completed(futures):
            try:
                dev_obj = fut.result()
                if dev_obj:
                    devices.append(dev_obj)
            except Exception as e:
                logger.debug("SMART device future failed: %s", e)
    return SmartStatusResponse(checked_at=now, devices=devices)


def _mock_status() -> SmartStatusResponse:
    now = datetime.now(tz=timezone.utc)
    # Mock-Daten basierend auf echten System-Festplatten
    devices = [
        SmartDevice(
            name="/dev/sda",
            model="Samsung SSD 840 EVO 250GB",
            serial="S1DBNSAF732716P",
            temperature=33,
            status="PASSED",
            capacity_bytes=250059350016,  # 232 GB
            used_bytes=172161261568,  # 160.3 GB genutzt (69%)
            used_percent=69.0,
            mount_point="C:",
            attributes=[
                SmartAttribute(
                    id=5,
                    name="Reallocated_Sector_Ct",
                    value=100,
                    worst=100,
                    threshold=36,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=194,
                    name="Temperature_Celsius",
                    value=68,
                    worst=45,
                    threshold=0,
                    raw="32",
                    status="OK",
                ),
                SmartAttribute(
                    id=197,
                    name="Current_Pending_Sector",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=198,
                    name="Uncorrectable_Error_Cnt",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
            ],
        ),
        SmartDevice(
            name="/dev/sdb",
            model="WD Red Plus 4TB (WD40EFPX)",
            serial="WD-WCC7K5HZTQ48",
            temperature=31,
            status="PASSED",
            capacity_bytes=4000787030016,  # 4 TB
            used_bytes=2400000000000,  # ~2.4 TB genutzt
            used_percent=60.0,
            mount_point="/mnt/disk2",
            attributes=[
                SmartAttribute(
                    id=5,
                    name="Reallocated_Sector_Ct",
                    value=100,
                    worst=100,
                    threshold=36,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=194,
                    name="Temperature_Celsius",
                    value=69,
                    worst=44,
                    threshold=0,
                    raw="31",
                    status="OK",
                ),
                SmartAttribute(
                    id=197,
                    name="Current_Pending_Sector",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=198,
                    name="Uncorrectable_Error_Cnt",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
            ],
        ),
        SmartDevice(
            name="/dev/sdc",
            model="WD Red Plus 4TB (WD40EFPX)",
            serial="WD-WCC7K5HZTR15",
            temperature=33,
            status="PASSED",
            capacity_bytes=4000787030016,  # 4 TB
            used_bytes=800000000000,  # ~800 GB genutzt
            used_percent=20.0,
            mount_point="/mnt/disk3",
            attributes=[
                SmartAttribute(
                    id=5,
                    name="Reallocated_Sector_Ct",
                    value=100,
                    worst=100,
                    threshold=36,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=194,
                    name="Temperature_Celsius",
                    value=67,
                    worst=46,
                    threshold=0,
                    raw="33",
                    status="OK",
                ),
                SmartAttribute(
                    id=197,
                    name="Current_Pending_Sector",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
                SmartAttribute(
                    id=198,
                    name="Uncorrectable_Error_Cnt",
                    value=100,
                    worst=100,
                    threshold=0,
                    raw="0",
                    status="OK",
                ),
            ],
        ),
    ]
    return SmartStatusResponse(checked_at=now, devices=devices)


def get_smart_status() -> SmartStatusResponse:
    """Return SMART diagnostics information.

    Attempts to read real SMART data using pySMART. Falls back to mock data
    if reading fails or no devices are found. This works on Windows, Linux, and macOS.
    """
    cached = get_cached_smart_status()
    if cached:
        return cached
    try:
        data = _read_real_smart_data()
        if not data.devices:
            raise SmartUnavailableError("No devices")
        _set_smart_cache(data)
        return data
    except SmartUnavailableError as e:
        logger.warning("SMART fallback to mock: %s", e)
        mock = _mock_status()
        _set_smart_cache(mock)
        return mock
    except Exception as e:
        logger.error("SMART unexpected error fallback: %s", e)
        mock = _mock_status()
        _set_smart_cache(mock)
        return mock


def get_smart_device_models() -> dict[str, str]:
    """Lightweight mapping disk name -> model (cached)."""
    status = get_smart_status()
    mapping: dict[str, str] = {}
    for dev in status.devices:
        mapping[dev.name.lower()] = dev.model
    return mapping
