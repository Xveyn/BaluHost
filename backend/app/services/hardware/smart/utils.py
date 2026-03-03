"""SMART utility functions.

Leaf module — smartctl path discovery, lsblk, Windows WMI, parsing helpers.
"""
from __future__ import annotations

import logging
import platform

from app.schemas.system import SmartSelfTest

logger = logging.getLogger(__name__)


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


def _get_model_from_lsblk(device_name: str) -> str | None:
    """Fallback: read disk model via lsblk when smartctl doesn't provide it."""
    import subprocess
    try:
        result = subprocess.run(
            ['lsblk', device_name, '--nodeps', '--noheadings', '--output', 'MODEL'],
            capture_output=True, text=True, check=False, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        logger.debug("lsblk model fallback failed for %s: %s", device_name, e)
    return None


def _run_smartctl(smartctl_path: str, dev_type: str, device_name: str) -> tuple[object, dict | None]:
    """Run smartctl and return (subprocess_result, parsed_json_or_None).

    Uses bitmask return-code check: only bits 0 (command-line error) and
    1 (device open failed) cause the result to be discarded.  Higher bits
    (SMART command failed, disk failing, error-log entries, self-test log
    entries) are informational — the JSON output is still valid.
    """
    import json, subprocess, re as _re
    base_args = ["sudo", "-n", smartctl_path, '-H', '-i', '-l', 'selftest', '-j', '-d', dev_type, device_name]
    if not _re.search(r'nvme', dev_type, _re.IGNORECASE) and 'nvme' not in device_name.lower():
        base_args.insert(3, '-A')
    result = subprocess.run(base_args, capture_output=True, text=True, check=False, timeout=20)
    # Only abort on bit 0 (parse error) or bit 1 (device open failed)
    if result.returncode & 0b11:
        logger.warning("smartctl error for %s (code %d, bits 0-1 set) — skipping", device_name, result.returncode)
        return result, None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.warning("Failed to parse smartctl JSON for %s", device_name)
        return result, None
    return result, data


def _parse_self_test_log(data: dict) -> SmartSelfTest | None:
    """Parse the most recent self-test result from smartctl JSON output.

    Supports both ATA (ata_smart_self_test_log.standard.table) and
    NVMe (nvme_self_test_log.table) formats.
    """
    # ATA format
    ata_log = data.get('ata_smart_self_test_log', {})
    if isinstance(ata_log, dict):
        table = ata_log.get('standard', {}).get('table', [])
        if table and isinstance(table, list) and isinstance(table[0], dict):
            entry = table[0]
            status = entry.get('status', {})
            status_str = status.get('string', 'Unknown') if isinstance(status, dict) else str(status)
            passed = status.get('passed', False) if isinstance(status, dict) else False
            return SmartSelfTest(
                test_type=entry.get('type', {}).get('string', 'Unknown') if isinstance(entry.get('type'), dict) else str(entry.get('type', 'Unknown')),
                status=status_str,
                passed=passed,
                power_on_hours=int(entry.get('lifetime_hours', 0)),
            )

    # NVMe format
    nvme_log = data.get('nvme_self_test_log', {})
    if isinstance(nvme_log, dict):
        table = nvme_log.get('table', [])
        if table and isinstance(table, list) and isinstance(table[0], dict):
            entry = table[0]
            status = entry.get('status', {})
            status_str = status.get('string', 'Unknown') if isinstance(status, dict) else str(status)
            passed = 'completed without error' in status_str.lower() if status_str else False
            return SmartSelfTest(
                test_type=entry.get('type', {}).get('string', 'Short') if isinstance(entry.get('type'), dict) else str(entry.get('type', 'Short')),
                status=status_str,
                passed=passed,
                power_on_hours=int(entry.get('power_on_hours', 0)),
            )

    return None
