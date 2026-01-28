"""
Power monitoring service for Tapo smart plugs.

Manages background power consumption monitoring with historical data collection.
Follows the telemetry service pattern with circular buffer and async monitoring.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime
from threading import Lock
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.tapo_device import TapoDevice
from app.schemas.tapo import (
    PowerSample,
    PowerHistory,
    PowerMonitoringResponse,
    CurrentPowerResponse,
)
from app.services.vpn_encryption import VPNEncryption
from app.services import energy_stats

logger = logging.getLogger(__name__)

# Configuration
_SAMPLE_INTERVAL_SECONDS = 5.0  # Sample every 5 seconds
_FAST_START_SAMPLES = 3  # Quick initial samples
_FAST_START_INTERVAL = 0.5  # Fast start interval
_MAX_SAMPLES = 120  # 10 minutes of history at 5s intervals
_DEVICE_TIMEOUT = 10.0  # Timeout for device queries
_DB_SAVE_INTERVAL = 60.0  # Save to DB every 60 seconds (reduce DB writes)

# State management
_device_histories: Dict[int, List[PowerSample]] = {}
_monitor_task: Optional[asyncio.Task] = None
_lock = Lock()
_db_session_factory = None
_is_running = False
_samples_since_db_save = 0  # Counter for DB save interval
_started_at: Optional[float] = None
_sample_count: int = 0
_error_count: int = 0
_last_error: Optional[str] = None
_last_error_time: Optional[float] = None

# Plugp100 client cache (avoid repeated auth)
_client_cache: Dict[int, object] = {}


def _push_sample(device_id: int, sample: PowerSample) -> None:
    """Add sample to device history with circular buffer."""
    if device_id not in _device_histories:
        _device_histories[device_id] = []

    _device_histories[device_id].append(sample)
    if len(_device_histories[device_id]) > _MAX_SAMPLES:
        _device_histories[device_id].pop(0)


def _generate_mock_power_sample() -> tuple[float, float, float, float]:
    """
    Generate realistic mock power data for dev mode.

    Simulates NAS power consumption:
    - Base load: 60-180W (typical for home NAS)
    - Voltage: 230V ±5V (EU standard)
    - Current: calculated from watts/voltage
    - Daily energy: 1.5-3.5 kWh

    Returns:
        (watts, voltage, current, energy_today)
    """
    # NAS-typical power consumption with realistic variations
    base_watts = 120.0
    variation = random.uniform(-30, 60)  # Disk spin-up, network activity
    watts = max(60.0, min(180.0, base_watts + variation))

    # EU voltage with small fluctuations
    voltage = 230.0 + random.uniform(-5, 5)

    # Calculate current (P = V * I)
    current = watts / voltage

    # Daily energy accumulation (1.5-3.5 kWh typical for NAS)
    energy_today = random.uniform(1.5, 3.5)

    return (
        round(watts, 1),
        round(voltage, 1),
        round(current, 3),
        round(energy_today, 2)
    )


async def _sample_device(
    device_id: int,
    name: str,
    ip: str,
    email_enc: str,
    password_enc: str
) -> Optional[PowerSample]:
    """
    Sample power data from a single Tapo device.

    Args:
        device_id: Device database ID
        name: Device name
        ip: Device IP address
        email_enc: Encrypted Tapo account email
        password_enc: Encrypted Tapo account password

    Returns:
        PowerSample or None if device is offline/error
    """
    timestamp = datetime.utcnow()

    # Always query real Tapo device (even in dev mode) when a device is configured
    # Mock data is only used for testing without hardware
    try:
        # Import plugp100 v5.x API
        from plugp100.new import device_factory
        from plugp100.new.components.energy_component import EnergyComponent

        # Decrypt credentials
        email = VPNEncryption.decrypt_key(email_enc)
        password = VPNEncryption.decrypt_key(password_enc)

        # Check client cache to avoid repeated auth
        # In v5.x, we cache the connected device directly
        cache_key = f"{device_id}:{ip}"
        if cache_key not in _client_cache:
            # Create credentials and connect
            credentials = device_factory.AuthCredential(email, password)
            config = device_factory.DeviceConnectConfiguration(
                host=ip,
                credentials=credentials
            )

            # Query device with timeout
            device = await asyncio.wait_for(
                device_factory.connect(config),
                timeout=_DEVICE_TIMEOUT
            )

            # Update device to fetch latest state
            await device.update()

            _client_cache[cache_key] = device
        else:
            device = _client_cache[cache_key]
            # Update device to get latest readings
            await asyncio.wait_for(
                device.update(),
                timeout=_DEVICE_TIMEOUT
            )

        # Get energy component
        if not device.has_component(EnergyComponent):
            logger.warning(f"Device '{name}' does not have EnergyComponent")
            return None

        energy = device.get_component(EnergyComponent)

        # Get power and energy data (may be None if device query failed)
        power_info = energy.power_info  # Current power in watts
        energy_info = energy.energy_info  # Today's energy in Wh

        # Validate that we got data
        if power_info is None and energy_info is None:
            logger.warning(f"Device '{name}' returned no power data")
            return None

        # Extract values safely
        current_power = 0
        current_power_mw = 0
        today_energy_wh = 0

        if power_info is not None and hasattr(power_info, 'info') and power_info.info:
            current_power = power_info.info.get('current_power', 0)

        if energy_info is not None and hasattr(energy_info, 'info') and energy_info.info:
            current_power_mw = energy_info.info.get('current_power', 0)
            today_energy_wh = energy_info.info.get('today_energy', 0)

        # Use the more precise value from energy_info (convert mW to W)
        watts = current_power_mw / 1000.0 if current_power_mw > 0 else float(current_power)

        # Convert Wh to kWh
        energy_kwh = today_energy_wh / 1000.0

        # Calculate voltage and current (P = V * I)
        # Assuming EU standard 230V
        voltage = 230.0
        current_amps = watts / voltage if watts > 0 else 0.0

        logger.info(f"Device '{name}': {watts:.1f}W, {energy_kwh:.3f} kWh today")

        return PowerSample(
            timestamp=timestamp,
            watts=round(watts, 1),
            voltage=round(voltage, 1),
            current=round(current_amps, 3),
            energy_today=round(energy_kwh, 2)
        )

    except asyncio.TimeoutError:
        logger.warning(f"Timeout querying Tapo device '{name}' at {ip}")
        # Clear cached device on timeout
        cache_key = f"{device_id}:{ip}"
        if cache_key in _client_cache:
            del _client_cache[cache_key]
        return None

    except ImportError:
        logger.error("plugp100 library not installed. Install with: pip install plugp100")
        return None
    except TypeError as e:
        # Handle plugp100 library bugs (e.g., super() argument error)
        logger.warning(f"Tapo library error for '{name}' ({ip}): {e}")
        cache_key = f"{device_id}:{ip}"
        if cache_key in _client_cache:
            del _client_cache[cache_key]
        return None
    except AttributeError as e:
        # Handle NoneType errors when device doesn't respond properly
        logger.warning(f"Incomplete data from Tapo device '{name}' ({ip}): {e}")
        cache_key = f"{device_id}:{ip}"
        if cache_key in _client_cache:
            del _client_cache[cache_key]
        return None
    except Exception as e:
        # Log connection/auth errors as warning without full traceback (common in production)
        error_str = str(e)
        known_errors = [
            "Cannot write", "Connection", "Errno", "Forbidden",
            "handshake", "authentication", "400", "reset by peer"
        ]
        if any(err in error_str for err in known_errors):
            logger.warning(f"Tapo device '{name}' ({ip}) unavailable: {error_str[:100]}")
        else:
            logger.error(f"Error sampling Tapo device '{name}' ({ip}): {e}", exc_info=True)
        # Clear cached device on error
        cache_key = f"{device_id}:{ip}"
        if cache_key in _client_cache:
            del _client_cache[cache_key]
        return None


async def _sample_all_devices() -> None:
    """Sample all active monitoring-enabled devices."""
    global _sample_count

    _sample_count += 1

    if _db_session_factory is None:
        logger.error("Database session factory not initialized")
        return

    # Get fresh database session
    db = next(_db_session_factory())

    try:
        # Query all active devices with monitoring enabled
        devices = db.query(TapoDevice).filter(
            TapoDevice.is_active == True,
            TapoDevice.is_monitoring == True
        ).all()

        if not devices:
            logger.debug("No active Tapo devices configured for monitoring")
            return

        # Sample all devices concurrently
        tasks = [
            _sample_device(
                device.id,
                device.name,
                device.ip_address,
                device.email_encrypted,
                device.password_encrypted
            )
            for device in devices
        ]

        samples = await asyncio.gather(*tasks, return_exceptions=True)

        # Store samples and update device status
        timestamp_now = datetime.utcnow()
        for device, sample in zip(devices, samples):
            if isinstance(sample, Exception):
                # Handle exception from gather
                logger.error(f"Exception sampling device {device.name}: {sample}")
                device.last_error = str(sample)[:500]
                continue

            if sample is not None:
                # Store sample in circular buffer
                with _lock:
                    _push_sample(device.id, sample)

                # Update device status
                device.last_connected = timestamp_now
                device.last_error = None
            else:
                # Device offline or error
                device.last_error = "Device offline or query failed"

        # Commit status updates
        db.commit()

        # Periodically save samples to database (every _DB_SAVE_INTERVAL seconds)
        global _samples_since_db_save
        _samples_since_db_save += 1
        save_interval_count = int(_DB_SAVE_INTERVAL / _SAMPLE_INTERVAL_SECONDS)

        if _samples_since_db_save >= save_interval_count:
            _samples_since_db_save = 0

            # Save latest sample from each device to DB
            for device, sample in zip(devices, samples):
                if isinstance(sample, Exception):
                    # Save offline sample
                    try:
                        energy_stats.save_power_sample(
                            db=db,
                            device_id=device.id,
                            watts=0.0,
                            voltage=None,
                            current=None,
                            energy_today=None,
                            is_online=False
                        )
                    except Exception as e:
                        logger.error(f"Failed to save offline sample for device {device.id}: {e}")
                elif sample is not None:
                    # Save online sample
                    try:
                        energy_stats.save_power_sample(
                            db=db,
                            device_id=device.id,
                            watts=sample.watts,
                            voltage=sample.voltage,
                            current=sample.current,
                            energy_today=sample.energy_today,
                            is_online=True
                        )
                    except Exception as e:
                        logger.error(f"Failed to save sample for device {device.id}: {e}")

    except Exception as e:
        global _error_count, _last_error, _last_error_time
        _error_count += 1
        _last_error = str(e)
        _last_error_time = time.time()
        logger.error(f"Error in power monitoring sampling: {e}", exc_info=True)
    finally:
        db.close()


async def _monitor_loop() -> None:
    """Background monitoring loop with fast start."""
    logger.info(f"Starting power monitoring (interval={_SAMPLE_INTERVAL_SECONDS}s)")

    # Fast start: 3 quick samples
    for i in range(_FAST_START_SAMPLES):
        try:
            await _sample_all_devices()
        except Exception as e:
            logger.error(f"Fast-start sample {i+1} failed: {e}")

        if i < _FAST_START_SAMPLES - 1:
            await asyncio.sleep(_FAST_START_INTERVAL)

    # Regular monitoring loop
    while _is_running:
        try:
            await _sample_all_devices()
        except Exception as e:
            logger.error(f"Power monitoring iteration failed: {e}", exc_info=True)

        await asyncio.sleep(_SAMPLE_INTERVAL_SECONDS)


async def start_power_monitor(
    db_session_factory,
    interval_seconds: Optional[float] = None
) -> None:
    """
    Start power monitoring background task.

    Args:
        db_session_factory: SQLAlchemy session factory for database access
        interval_seconds: Override default sampling interval
    """
    global _monitor_task, _db_session_factory, _is_running, _SAMPLE_INTERVAL_SECONDS, _started_at

    if _monitor_task is not None:
        logger.warning("Power monitor already running")
        return

    _db_session_factory = db_session_factory
    _is_running = True
    _started_at = time.time()

    if interval_seconds is not None:
        _SAMPLE_INTERVAL_SECONDS = interval_seconds

    _monitor_task = asyncio.create_task(_monitor_loop())
    logger.info("Power monitor started")


async def stop_power_monitor() -> None:
    """Stop power monitoring background task."""
    global _monitor_task, _is_running

    if _monitor_task is None:
        return

    logger.info("Stopping power monitor...")
    _is_running = False

    # Cancel task and wait for cleanup
    _monitor_task.cancel()
    try:
        await _monitor_task
    except asyncio.CancelledError:
        pass

    _monitor_task = None
    _client_cache.clear()
    logger.info("Power monitor stopped")


def get_power_history(db: Session) -> PowerMonitoringResponse:
    """
    Get power monitoring history for all devices.

    Args:
        db: Database session

    Returns:
        PowerMonitoringResponse with all device histories
    """
    # Query all active devices
    devices = db.query(TapoDevice).filter(
        TapoDevice.is_active == True
    ).all()

    device_histories = []
    total_current_power = 0.0

    with _lock:
        for device in devices:
            # Get samples for this device
            samples = _device_histories.get(device.id, [])

            # Calculate current power (latest sample)
            latest_sample = samples[-1] if samples else None
            if latest_sample:
                total_current_power += latest_sample.watts

            device_histories.append(
                PowerHistory(
                    device_id=device.id,
                    device_name=device.name,
                    samples=samples,
                    latest_sample=latest_sample
                )
            )

    return PowerMonitoringResponse(
        devices=device_histories,
        total_current_power=round(total_current_power, 1),
        last_updated=datetime.utcnow()
    )


def get_current_power(device_id: int, db: Session) -> CurrentPowerResponse:
    """
    Get current power consumption for a specific device.

    Args:
        device_id: Device database ID
        db: Database session

    Returns:
        CurrentPowerResponse with latest power data

    Raises:
        ValueError: If device not found
    """
    device = db.query(TapoDevice).filter(TapoDevice.id == device_id).first()
    if not device:
        raise ValueError(f"Device with ID {device_id} not found")

    with _lock:
        samples = _device_histories.get(device_id, [])
        latest_sample = samples[-1] if samples else None

    if latest_sample is None:
        # No data yet
        return CurrentPowerResponse(
            device_id=device_id,
            device_name=device.name,
            current_watts=0.0,
            voltage=None,
            current=None,
            energy_today=None,
            timestamp=datetime.utcnow(),
            is_online=False
        )

    return CurrentPowerResponse(
        device_id=device_id,
        device_name=device.name,
        current_watts=latest_sample.watts,
        voltage=latest_sample.voltage,
        current=latest_sample.current,
        energy_today=latest_sample.energy_today,
        timestamp=latest_sample.timestamp,
        is_online=True
    )


def get_status() -> dict:
    """
    Get power monitor service status.

    Returns:
        Dict with service status information for admin dashboard
    """
    is_running = _monitor_task is not None and not _monitor_task.done() and _is_running

    started_at = None
    uptime_seconds = None
    if _started_at is not None:
        started_at = datetime.utcfromtimestamp(_started_at)
        uptime_seconds = time.time() - _started_at

    last_error_at = None
    if _last_error_time is not None:
        last_error_at = datetime.utcfromtimestamp(_last_error_time)

    return {
        "is_running": is_running,
        "started_at": started_at,
        "uptime_seconds": uptime_seconds,
        "sample_count": _sample_count,
        "error_count": _error_count,
        "last_error": _last_error,
        "last_error_at": last_error_at,
        "interval_seconds": _SAMPLE_INTERVAL_SECONDS,
        "buffer_size": _MAX_SAMPLES,
        "devices_count": len(_device_histories),
    }
