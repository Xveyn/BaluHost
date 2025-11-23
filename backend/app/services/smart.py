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

# Dev-Mode: Toggle zwischen Mock und Real SMART Daten
_DEV_USE_MOCK_DATA = True  # Default: Mock-Daten im Dev-Mode

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


def get_dev_mode_state() -> str:
    """Gibt den aktuellen Dev-Mode Status zurück: 'mock' oder 'real'."""
    return "mock" if _DEV_USE_MOCK_DATA else "real"


def toggle_dev_mode() -> str:
    """Wechselt zwischen Mock und Real SMART-Daten im Dev-Mode.
    
    Returns:
        str: Neuer Modus ('mock' oder 'real')
    """
    global _DEV_USE_MOCK_DATA
    _DEV_USE_MOCK_DATA = not _DEV_USE_MOCK_DATA
    invalidate_smart_cache()  # Cache invalidieren beim Toggle
    new_mode = get_dev_mode_state()
    logger.info(f"Dev-Mode SMART data toggled to: {new_mode}")
    return new_mode


def _enrich_with_filesystem_usage(devices: list[SmartDevice]) -> None:
    """Fügt used_bytes, used_percent und mount_point zu SMART-Geräten hinzu.
    
    Nutzt psutil um Partitionen und deren Nutzung zu ermitteln und gleicht sie
    mit den physischen SMART-Geräten ab.
    """
    try:
        import psutil
    except ImportError:
        logger.warning("psutil nicht verfügbar - keine Filesystem-Nutzungsdaten")
        return
    
    try:
        partitions = psutil.disk_partitions(all=False)
        
        # Erstelle Mapping: device_name -> usage_info
        partition_usage: dict[str, tuple[int, int, str]] = {}  # {device: (used, total, mountpoint)}
        
        for partition in partitions:
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                device_key = partition.device.lower()
                
                # Windows: Normalisiere Laufwerksbuchstaben (C:\ -> c)
                if platform.system().lower() == 'windows':
                    if ':' in device_key:
                        device_key = device_key.split(':')[0].strip()
                
                # Aggregiere Nutzung pro physischem Gerät
                if device_key in partition_usage:
                    old_used, old_total, old_mount = partition_usage[device_key]
                    partition_usage[device_key] = (
                        old_used + usage.used,
                        old_total + usage.total,
                        f"{old_mount}, {partition.mountpoint}"
                    )
                else:
                    partition_usage[device_key] = (usage.used, usage.total, partition.mountpoint)
                    
            except (PermissionError, OSError) as e:
                logger.debug(f"Konnte Partition {partition.mountpoint} nicht lesen: {e}")
                continue
        
        # Windows-spezifisch: Versuche Disk-Nummer zu Laufwerksbuchstaben-Mapping
        windows_disk_map: dict[str, str] = {}  # {"/dev/sda": "c", ...}
        if platform.system().lower() == 'windows' and partition_usage:
            import subprocess
            try:
                # Get-PhysicalDisk und Get-Partition Mapping
                ps_cmd = """
                Get-PhysicalDisk | ForEach-Object {
                    $disk = $_
                    Get-Partition -DiskNumber $disk.DeviceId -ErrorAction SilentlyContinue | 
                    Where-Object {$_.DriveLetter} | ForEach-Object {
                        Write-Output "$($disk.DeviceId),$($_.DriveLetter)"
                    }
                }
                """
                result = subprocess.run(
                    ['powershell', '-Command', ps_cmd],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10
                )
                
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        if ',' in line:
                            disk_num, drive_letter = line.strip().split(',')
                            # /dev/sda = Disk 0, /dev/sdb = Disk 1, etc.
                            device_name = f"/dev/sd{chr(ord('a') + int(disk_num))}"
                            windows_disk_map[device_name] = drive_letter.lower()
                            
            except Exception as e:
                logger.debug(f"Windows disk mapping failed: {e}")
        
        # Anreichere SMART-Geräte mit Nutzungsdaten
        for device in devices:
            # Versuche verschiedene Matching-Strategien
            matched = False
            
            # 1. Windows: Nutze Disk-Mapping
            if device.name in windows_disk_map:
                drive_letter = windows_disk_map[device.name]
                if drive_letter in partition_usage:
                    used, total, mount = partition_usage[drive_letter]
                    device.used_bytes = used
                    device.used_percent = (used / total * 100) if total > 0 else 0
                    device.mount_point = mount
                    matched = True
                    logger.debug(f"Matched {device.name} -> {drive_letter}: {used / (1024**3):.2f} GB used")
            
            # 2. Linux: Direkte Device-Namen (/dev/sda -> sda)
            if not matched:
                device_key = device.name.replace('/dev/', '').lower()
                for partition_dev, (used, total, mount) in partition_usage.items():
                    if device_key in partition_dev or partition_dev in device_key:
                        device.used_bytes = used
                        device.used_percent = (used / total * 100) if total > 0 else 0
                        device.mount_point = mount
                        matched = True
                        logger.debug(f"Matched {device.name} -> {partition_dev}: {used / (1024**3):.2f} GB used")
                        break
            
            # 3. Fallback: Wenn keine Nutzungsdaten gefunden, lasse None
            if not matched:
                logger.debug(f"No filesystem usage found for {device.name}")
                
    except Exception as e:
        logger.error(f"Failed to enrich SMART data with filesystem usage: {e}")


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
    
    # Anreichere Geräte mit Filesystem-Nutzungsdaten
    _enrich_with_filesystem_usage(devices)
    
    return SmartStatusResponse(checked_at=now, devices=devices)


def _mock_status() -> SmartStatusResponse:
    from app.core.config import settings
    from app.services import files as file_service
    
    now = datetime.now(tz=timezone.utc)
    
    # Berechne tatsächlich genutzte Bytes aus dev-storage
    try:
        actual_used_bytes = file_service.calculate_used_bytes()
    except Exception:
        actual_used_bytes = 0
    
    # Bei RAID1: Daten werden gespiegelt, also beide Disks zeigen gleiche Nutzung
    # Effektive Nutzung = actual_used_bytes (nicht verdoppelt)
    disk_capacity_5gb = 5 * 1024 * 1024 * 1024  # 5 GB
    disk_capacity_10gb = 10 * 1024 * 1024 * 1024  # 10 GB
    disk_capacity_20gb = 20 * 1024 * 1024 * 1024  # 20 GB
    
    disk_used = min(actual_used_bytes, disk_capacity_5gb)  # Cap bei Kapazität
    disk_used_percent = (disk_used / disk_capacity_5gb * 100) if disk_capacity_5gb > 0 else 0
    
    # Mock-Daten für Dev-Mode: Mehrere Festplatten-Konfigurationen
    # - RAID1 Pool 1: 2x5GB (md0) - Aktiver Storage
    # - RAID1 Pool 2: 2x10GB (md1) - Backup Storage
    # - RAID5 Pool: 3x20GB (md2) - Archiv Storage
    devices = [
        # === RAID1 Pool 1 (md0) - 2x5GB ===
        SmartDevice(
            name="/dev/sda",
            model="BaluHost Dev Disk 5GB (Mirror A)",
            serial="BALU-DEV-5GB-A",
            temperature=28,
            status="PASSED",
            capacity_bytes=disk_capacity_5gb,
            used_bytes=disk_used,
            used_percent=disk_used_percent,
            mount_point=None,
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
                    value=72,
                    worst=55,
                    threshold=0,
                    raw="28",
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
            model="BaluHost Dev Disk 5GB (Mirror B)",
            serial="BALU-DEV-5GB-B",
            temperature=29,
            status="PASSED",
            capacity_bytes=disk_capacity_5gb,
            used_bytes=disk_used,
            used_percent=disk_used_percent,
            mount_point=None,
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
                    value=71,
                    worst=56,
                    threshold=0,
                    raw="29",
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
        
        # === RAID1 Pool 2 (md1) - 2x10GB ===
        SmartDevice(
            name="/dev/sdc",
            model="BaluHost Dev Disk 10GB (Backup A)",
            serial="BALU-DEV-10GB-A",
            temperature=30,
            status="PASSED",
            capacity_bytes=disk_capacity_10gb,
            used_bytes=int(disk_capacity_10gb * 0.45),  # 45% genutzt
            used_percent=45.0,
            mount_point=None,
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
                    value=70,
                    worst=54,
                    threshold=0,
                    raw="30",
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
            name="/dev/sdd",
            model="BaluHost Dev Disk 10GB (Backup B)",
            serial="BALU-DEV-10GB-B",
            temperature=31,
            status="PASSED",
            capacity_bytes=disk_capacity_10gb,
            used_bytes=int(disk_capacity_10gb * 0.45),  # 45% genutzt
            used_percent=45.0,
            mount_point=None,
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
                    worst=53,
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
        
        # === RAID5 Pool (md2) - 3x20GB ===
        SmartDevice(
            name="/dev/sde",
            model="BaluHost Dev Disk 20GB (Archive A)",
            serial="BALU-DEV-20GB-A",
            temperature=32,
            status="PASSED",
            capacity_bytes=disk_capacity_20gb,
            used_bytes=int(disk_capacity_20gb * 0.28),  # 28% genutzt
            used_percent=28.0,
            mount_point=None,
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
                    worst=52,
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
            name="/dev/sdf",
            model="BaluHost Dev Disk 20GB (Archive B)",
            serial="BALU-DEV-20GB-B",
            temperature=33,
            status="PASSED",
            capacity_bytes=disk_capacity_20gb,
            used_bytes=int(disk_capacity_20gb * 0.28),  # 28% genutzt
            used_percent=28.0,
            mount_point=None,
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
                    worst=51,
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
        SmartDevice(
            name="/dev/sdg",
            model="BaluHost Dev Disk 20GB (Archive C)",
            serial="BALU-DEV-20GB-C",
            temperature=34,
            status="PASSED",
            capacity_bytes=disk_capacity_20gb,
            used_bytes=int(disk_capacity_20gb * 0.28),  # 28% genutzt
            used_percent=28.0,
            mount_point=None,
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
                    value=66,
                    worst=50,
                    threshold=0,
                    raw="34",
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

    In Dev-Mode: Respektiert _DEV_USE_MOCK_DATA Toggle.
    In Production: Versucht immer echte SMART-Daten zu lesen, Fallback zu Mock bei Fehlern.
    """
    cached = get_cached_smart_status()
    if cached:
        return cached
    
    # Dev-Mode: Respektiere Toggle
    if settings.is_dev_mode:
        if _DEV_USE_MOCK_DATA:
            logger.debug("Dev-Mode: Using mock SMART data (toggled)")
            mock = _mock_status()
            _set_smart_cache(mock)
            return mock
        else:
            logger.debug("Dev-Mode: Using real SMART data (toggled)")
            try:
                data = _read_real_smart_data()
                if not data.devices:
                    logger.warning("No real SMART devices found, using mock as fallback")
                    mock = _mock_status()
                    _set_smart_cache(mock)
                    return mock
                _set_smart_cache(data)
                return data
            except Exception as e:
                logger.warning("Failed to read real SMART data in dev-mode: %s", e)
                mock = _mock_status()
                _set_smart_cache(mock)
                return mock
    
    # Production: Versuche echte Daten, Fallback zu Mock
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


def get_smart_device_order() -> list[str]:
    """Get ordered list of device names as returned by smartctl --scan.
    
    This is useful for mapping psutil disk indices to SMART device names.
    On Windows, the order corresponds to PhysicalDrive0, PhysicalDrive1, etc.
    
    Returns:
        list[str]: Ordered list of device names (e.g., ['/dev/sda', '/dev/sdb', ...])
    """
    status = get_smart_status()
    # Die Reihenfolge der Devices im SmartStatusResponse entspricht der Scan-Reihenfolge
    return [dev.name for dev in status.devices]
