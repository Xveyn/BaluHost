"""
CPU sensors service for reading CPU frequency and temperature.

Provides robust sensor reading with psutil primary APIs and sysfs fallback
for Linux systems. Designed for production use with graceful degradation
when sensors are unavailable.
"""

import logging
import os
import glob
from typing import Dict, Optional, List, Tuple
from pathlib import Path

import psutil

logger = logging.getLogger(__name__)


class CPUSensorData:
    """Container for CPU sensor readings."""
    
    def __init__(self):
        self.frequency_mhz: Optional[float] = None
        self.temperature_celsius: Optional[float] = None
        self.per_core_temps: Dict[str, float] = {}
        self.source_info: Dict[str, str] = {}


def get_cpu_frequency() -> Optional[float]:
    """
    Get current CPU frequency in MHz.
    
    Uses psutil as primary method with sysfs fallback.
    Returns None if unable to determine frequency.
    """
    # Method 1: psutil (cross-platform)
    try:
        freq_info = psutil.cpu_freq()
        if freq_info and freq_info.current:
            logger.debug("CPU frequency from psutil: %.1f MHz", freq_info.current)
            return float(freq_info.current)
    except Exception as e:
        logger.debug("psutil cpu_freq() failed: %s", e)
    
    # Method 2: sysfs fallback (Linux)
    try:
        freq_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"
        if os.path.exists(freq_path):
            with open(freq_path, 'r') as f:
                freq_khz = int(f.read().strip())
                freq_mhz = freq_khz / 1000.0
                logger.debug("CPU frequency from sysfs: %.1f MHz", freq_mhz)
                return freq_mhz
    except Exception as e:
        logger.debug("sysfs cpu frequency read failed: %s", e)
    
    logger.warning("Unable to determine CPU frequency from any source")
    return None


def get_cpu_temperatures() -> Dict[str, float]:
    """
    Get CPU temperatures from available sensors.
    
    Returns dict with sensor names as keys and temperatures in Celsius as values.
    Uses psutil as primary method with hwmon sysfs fallback.
    """
    temperatures = {}
    
    # Method 1: psutil (uses lm-sensors/hwmon)
    try:
        temp_sensors = psutil.sensors_temperatures()
        if temp_sensors:
            for sensor_name, sensor_list in temp_sensors.items():
                # Focus on CPU-related sensors
                if any(keyword in sensor_name.lower() for keyword in ['cpu', 'core', 'processor']):
                    for sensor in sensor_list:
                        temp_key = f"{sensor_name}_{sensor.label}" if sensor.label else sensor_name
                        temperatures[temp_key] = sensor.current
                        logger.debug("Temperature from psutil: %s = %.1f°C", temp_key, sensor.current)
    except Exception as e:
        logger.debug("psutil sensors_temperatures() failed: %s", e)
    
    # Method 2: hwmon sysfs fallback (Linux)
    if not temperatures:
        try:
            temperatures.update(_read_hwmon_temperatures())
        except Exception as e:
            logger.debug("hwmon temperature reading failed: %s", e)
    
    if not temperatures:
        logger.warning("No CPU temperature sensors found")
    
    return temperatures


def _read_hwmon_temperatures() -> Dict[str, float]:
    """
    Read temperatures directly from hwmon sysfs.
    
    Scans /sys/class/hwmon/hwmon* for temperature sensors and attempts
    to identify CPU-related sensors.
    """
    temperatures = {}
    
    hwmon_pattern = "/sys/class/hwmon/hwmon*"
    for hwmon_dir in glob.glob(hwmon_pattern):
        try:
            # Read the hwmon device name
            name_file = os.path.join(hwmon_dir, "name")
            if not os.path.exists(name_file):
                continue
                
            with open(name_file, 'r') as f:
                device_name = f.read().strip()
            
            # Look for CPU-related devices (common names)
            cpu_keywords = ['coretemp', 'k10temp', 'cpu_thermal', 'acpi']
            if not any(keyword in device_name.lower() for keyword in cpu_keywords):
                continue
            
            # Find temperature input files
            temp_inputs = glob.glob(os.path.join(hwmon_dir, "temp*_input"))
            for temp_input in temp_inputs:
                try:
                    with open(temp_input, 'r') as f:
                        temp_millidegree = int(f.read().strip())
                        temp_celsius = temp_millidegree / 1000.0
                    
                    # Try to get a label for this sensor
                    temp_label_file = temp_input.replace("_input", "_label")
                    if os.path.exists(temp_label_file):
                        with open(temp_label_file, 'r') as f:
                            label = f.read().strip()
                    else:
                        # Extract sensor number from filename (e.g., temp1_input -> 1)
                        sensor_num = os.path.basename(temp_input).split('_')[0]
                        label = sensor_num
                    
                    sensor_key = f"{device_name}_{label}"
                    temperatures[sensor_key] = temp_celsius
                    logger.debug("Temperature from hwmon: %s = %.1f°C", sensor_key, temp_celsius)
                    
                except (ValueError, IOError) as e:
                    logger.debug("Failed to read %s: %s", temp_input, e)
                    
        except Exception as e:
            logger.debug("Failed to process hwmon device %s: %s", hwmon_dir, e)
    
    return temperatures


def get_cpu_sensor_data() -> CPUSensorData:
    """
    Get comprehensive CPU sensor data.
    
    Returns CPUSensorData object with frequency, temperatures, and metadata.
    This is the main entry point for the telemetry service.
    """
    data = CPUSensorData()
    
    # Get frequency
    data.frequency_mhz = get_cpu_frequency()
    if data.frequency_mhz:
        data.source_info['frequency'] = 'psutil' if psutil.cpu_freq() else 'sysfs'
    
    # Get temperatures
    temps = get_cpu_temperatures()
    if temps:
        # Pick the first/primary temperature for the main field
        data.temperature_celsius = next(iter(temps.values()))
        data.per_core_temps = temps
        data.source_info['temperature'] = 'psutil' if psutil.sensors_temperatures() else 'hwmon'
    
    return data


def check_sensor_availability() -> Dict[str, bool]:
    """
    Check availability of different sensor reading methods.
    
    Useful for diagnostics and configuration validation.
    """
    availability = {
        'psutil_cpu_freq': False,
        'psutil_temperatures': False,
        'sysfs_cpufreq': False,
        'hwmon_temperatures': False
    }
    
    # Check psutil CPU frequency
    try:
        freq = psutil.cpu_freq()
        availability['psutil_cpu_freq'] = freq is not None and freq.current is not None
    except Exception:
        pass
    
    # Check psutil temperatures
    try:
        temps = psutil.sensors_temperatures()
        availability['psutil_temperatures'] = bool(temps)
    except Exception:
        pass
    
    # Check sysfs CPU frequency
    availability['sysfs_cpufreq'] = os.path.exists("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    
    # Check hwmon temperatures
    hwmon_dirs = glob.glob("/sys/class/hwmon/hwmon*")
    availability['hwmon_temperatures'] = len(hwmon_dirs) > 0
    
    return availability