"""Real SMART data collection via smartctl.

Depends on: utils, enrichment, cache.
"""
from __future__ import annotations

import logging
import platform
from datetime import datetime, timezone

from app.schemas.system import SmartAttribute, SmartDevice, SmartStatusResponse

from app.services.hardware.smart.cache import SmartUnavailableError
from app.services.hardware.smart.enrichment import _enrich_with_filesystem_usage
from app.services.hardware.smart.utils import (
    _get_model_from_lsblk,
    _get_smartctl_path,
    _get_windows_disk_capacity,
    _parse_self_test_log,
    _run_smartctl,
)

logger = logging.getLogger(__name__)


def _read_real_smart_data() -> SmartStatusResponse:
    """Optimierte SMART-Erfassung mit paralleler Verarbeitung und reduzierten Flags."""
    import json, subprocess, re
    from concurrent.futures import ThreadPoolExecutor, as_completed

    smartctl_path = _get_smartctl_path()
    if not smartctl_path:
        raise FileNotFoundError("smartctl not found in PATH")

    now = datetime.now(tz=timezone.utc)
    scan_result = subprocess.run(["sudo", "-n", smartctl_path, '--scan', '-j'], capture_output=True, text=True, check=False, timeout=10)
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
        protocol = dev_info.get('protocol', '')
        if not device_name:
            return None

        # SATA drives behind Linux SCSI layer: use SAT for correct health status
        original_type = dev_type
        if dev_type == 'scsi' and protocol.upper() == 'ATA':
            dev_type = 'sat'
            logger.debug("SMART: overriding type scsi→sat for ATA device %s", device_name)

        _result, data = _run_smartctl(smartctl_path, dev_type, device_name)
        if data is None:
            return None

        # Fallback: if no smart_status.passed and original type was scsi, retry with SAT
        smart_status_raw = data.get('smart_status', {})
        if smart_status_raw.get('passed') is None and original_type == 'scsi' and dev_type != 'sat':
            logger.info("SMART: no health status with -d %s for %s, retrying with -d sat", dev_type, device_name)
            _result_sat, data_sat = _run_smartctl(smartctl_path, 'sat', device_name)
            if data_sat is not None:
                data = data_sat

        logger.debug("SMART raw JSON keys for %s: %s", device_name, list(data.keys()))
        logger.debug("SMART smart_status for %s: %s", device_name, data.get('smart_status'))

        model_info = data.get('model_name') or data.get('model_family') or _get_model_from_lsblk(device_name) or 'Unknown Model'
        if model_info == 'Unknown Model':
            logger.info("SMART: no model found for %s (smartctl + lsblk)", device_name)
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
        # Temperature — primary: JSON temperature object, fallback: ATA attribute 194
        temperature = None
        if isinstance(data.get('temperature'), dict):
            temperature = data['temperature'].get('current')
        if temperature is None:
            # Fallback: search ATA attributes for ID 194 (Temperature_Celsius)
            ata_attrs_raw = data.get('ata_smart_attributes', {})
            if isinstance(ata_attrs_raw, dict):
                for attr in ata_attrs_raw.get('table', []):
                    if isinstance(attr, dict) and attr.get('id') == 194:
                        raw_val = attr.get('raw', {})
                        if isinstance(raw_val, dict):
                            try:
                                temperature = int(raw_val.get('value', 0))
                            except (ValueError, TypeError):
                                pass
                        break
        # Status — distinguish between absent (UNKNOWN) and explicitly False (FAILED)
        smart_status = data.get('smart_status', {})
        passed_value = smart_status.get('passed')
        if passed_value is True:
            status = 'PASSED'
        elif passed_value is False:
            status = 'FAILED'
        else:
            status = 'UNKNOWN'
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
                    temp_val = None
                else:
                    try:
                        temp_val = int(temp_raw)
                    except Exception:
                        temp_val = None
                if temperature is None:
                    temperature = temp_val
                if temp_val is not None:
                    attributes.append(SmartAttribute(id=194, name='Temperature', value=temp_val, worst=0, threshold=0, raw=str(temp_val), status='OK'))
            if 'available_spare' in nvme_log:
                attributes.append(SmartAttribute(id=5, name='Available_Spare', value=nvme_log.get('available_spare', 0), worst=0, threshold=nvme_log.get('available_spare_threshold', 0), raw=str(nvme_log.get('available_spare', 0)), status='OK'))
        logger.debug("SMART parsed %s: model=%s, status=%s, temp=%s, attrs=%d", device_name, model_info, status, temperature, len(attributes))
        return SmartDevice(name=device_name, model=model_info, serial=serial, temperature=temperature, status=status, capacity_bytes=capacity_bytes, used_bytes=None, used_percent=None, mount_point=None, last_self_test=_parse_self_test_log(data), attributes=attributes)

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
