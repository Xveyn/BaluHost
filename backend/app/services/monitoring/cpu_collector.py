"""
CPU metrics collector.

Collects CPU usage, frequency, and temperature data.
Supports Intel hybrid CPU P-core/E-core detection.
"""

from __future__ import annotations

import logging
import platform
import re
import subprocess
from datetime import datetime
from functools import lru_cache
from typing import Optional, Tuple, Type

import psutil

from app.models.base import Base
from app.models.monitoring import CpuSample
from app.schemas.monitoring import CpuSampleSchema
from app.services.monitoring.base import MetricCollector
from app.services.sensors import get_cpu_sensor_data

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def detect_intel_hybrid_cores() -> Tuple[Optional[int], Optional[int]]:
    """
    Detect Intel P-cores (Performance) and E-cores (Efficiency) on hybrid CPUs.

    Returns:
        Tuple of (p_core_count, e_core_count) or (None, None) if not a hybrid CPU.
    """
    try:
        system = platform.system()

        if system == "Linux":
            # Try reading from /proc/cpuinfo for hybrid detection
            try:
                with open("/proc/cpuinfo", "r") as f:
                    cpuinfo = f.read()

                # Check CPU model for hybrid indicators (12th gen+, Ultra, etc.)
                model_match = re.search(r"model name\s*:\s*(.+)", cpuinfo)
                if model_match:
                    model = model_match.group(1).lower()
                    # Intel hybrid CPUs: 12th gen (Alder Lake), 13th gen (Raptor Lake),
                    # 14th gen (Meteor Lake), Core Ultra, etc.
                    if "intel" in model and any(x in model for x in ["12th", "13th", "14th", "ultra", "i5-12", "i7-12", "i9-12", "i5-13", "i7-13", "i9-13", "i5-14", "i7-14", "i9-14"]):
                        # Try to get core types from sysfs
                        try:
                            # Read core types from CPU topology
                            import os
                            p_cores = 0
                            e_cores = 0

                            cpu_path = "/sys/devices/system/cpu"
                            for cpu_dir in os.listdir(cpu_path):
                                if cpu_dir.startswith("cpu") and cpu_dir[3:].isdigit():
                                    core_type_path = f"{cpu_path}/{cpu_dir}/topology/core_type"
                                    if os.path.exists(core_type_path):
                                        with open(core_type_path, "r") as ct:
                                            core_type = ct.read().strip()
                                            # Intel_Core = P-core, Intel_Atom = E-core
                                            if "core" in core_type.lower():
                                                p_cores += 1
                                            elif "atom" in core_type.lower():
                                                e_cores += 1

                            if p_cores > 0 or e_cores > 0:
                                # Adjust for hyperthreading (P-cores have HT, E-cores don't)
                                # P-cores report 2x (with HT), E-cores report 1x
                                p_cores = p_cores // 2 if p_cores > 0 else 0
                                return (p_cores, e_cores)
                        except Exception:
                            pass

                        # Fallback: estimate based on known configurations
                        # This is a rough estimate for common Intel hybrid CPUs
                        physical = psutil.cpu_count(logical=False)
                        logical = psutil.cpu_count(logical=True)

                        if physical and logical:
                            # Estimate: P-cores have HT (2 threads each), E-cores don't (1 thread each)
                            # P*2 + E = logical, P + E = physical
                            # Solve: E = physical - P, P*2 + (physical - P) = logical
                            # P + physical = logical, P = logical - physical
                            estimated_p = logical - physical if logical > physical else 0
                            estimated_e = physical - estimated_p if estimated_p > 0 else 0

                            if estimated_p > 0 and estimated_e >= 0:
                                return (estimated_p, estimated_e)
            except Exception:
                pass

        elif system == "Windows":
            # On Windows, try wmic or powershell
            try:
                result = subprocess.run(
                    ["powershell", "-Command",
                     "Get-WmiObject Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors | Format-List"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    output = result.stdout.lower()
                    if "intel" in output and any(x in output for x in ["12th", "13th", "14th", "ultra"]):
                        # Same estimation logic
                        physical = psutil.cpu_count(logical=False)
                        logical = psutil.cpu_count(logical=True)

                        if physical and logical and logical > physical:
                            estimated_p = logical - physical
                            estimated_e = physical - estimated_p
                            if estimated_p > 0 and estimated_e >= 0:
                                return (estimated_p, estimated_e)
            except Exception:
                pass

    except Exception as e:
        logger.debug(f"Could not detect Intel hybrid cores: {e}")

    return (None, None)


class CpuMetricCollector(MetricCollector[CpuSampleSchema]):
    """
    Collector for CPU metrics.

    Collects:
    - CPU usage percentage (overall)
    - CPU frequency (MHz)
    - CPU temperature (Celsius)
    - Core count
    """

    def __init__(
        self,
        buffer_size: int = 120,
        persist_interval: int = 12,
    ):
        super().__init__(
            metric_name="CPU",
            buffer_size=buffer_size,
            persist_interval=persist_interval,
        )
        # Prime psutil CPU stats for accurate first reading
        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass

    def collect_sample(self) -> Optional[CpuSampleSchema]:
        """Collect CPU metrics sample."""
        try:
            timestamp = datetime.utcnow()

            # Get CPU usage
            usage = psutil.cpu_percent(interval=None)

            # Get CPU sensor data (frequency and temperature)
            sensor_data = get_cpu_sensor_data()

            # Get core and thread counts
            core_count = psutil.cpu_count(logical=False) or psutil.cpu_count()
            thread_count = psutil.cpu_count(logical=True) or core_count

            # Detect Intel hybrid P-cores/E-cores
            p_cores, e_cores = detect_intel_hybrid_cores()

            return CpuSampleSchema(
                timestamp=timestamp,
                usage_percent=round(usage, 2),
                frequency_mhz=sensor_data.frequency_mhz,
                temperature_celsius=sensor_data.temperature_celsius,
                core_count=core_count,
                thread_count=thread_count,
                p_core_count=p_cores,
                e_core_count=e_cores,
            )
        except Exception as e:
            logger.error(f"Failed to collect CPU sample: {e}")
            return None

    def get_db_model(self) -> Type[Base]:
        """Get the CpuSample model class."""
        return CpuSample

    def sample_to_db_dict(self, sample: CpuSampleSchema) -> dict:
        """Convert schema to database dict."""
        return {
            "timestamp": sample.timestamp,
            "usage_percent": sample.usage_percent,
            "frequency_mhz": sample.frequency_mhz,
            "temperature_celsius": sample.temperature_celsius,
            "core_count": sample.core_count,
            "thread_count": sample.thread_count,
            "p_core_count": sample.p_core_count,
            "e_core_count": sample.e_core_count,
        }

    def db_to_sample(self, db_record: CpuSample) -> CpuSampleSchema:
        """Convert database record to schema."""
        return CpuSampleSchema(
            timestamp=db_record.timestamp,
            usage_percent=db_record.usage_percent,
            frequency_mhz=db_record.frequency_mhz,
            temperature_celsius=db_record.temperature_celsius,
            core_count=db_record.core_count,
            thread_count=db_record.thread_count,
            p_core_count=db_record.p_core_count,
            e_core_count=db_record.e_core_count,
        )
