#!/usr/bin/env python3
"""
Test script for CPU sensor integration
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from app.services import telemetry
from app.services.sensors import get_cpu_sensor_data

async def test_sensors():
    print("=== Testing CPU Sensors ===")
    data = get_cpu_sensor_data()
    print(f"Frequency: {data.frequency_mhz} MHz")
    print(f"Temperature: {data.temperature_celsius}°C")
    print(f"Per-core temps: {data.per_core_temps}")
    print(f"Source info: {data.source_info}")
    print()

    print("=== Testing Telemetry Integration ===")
    # Start telemetry briefly
    await telemetry.start_telemetry_monitor(1.0)
    await asyncio.sleep(2.5)  # Let it sample a couple of times
    
    # Get the latest data
    history = telemetry.get_telemetry_history()
    if history.cpu:
        latest = history.cpu[-1]
        print(f"Latest CPU telemetry:")
        print(f"  Usage: {latest.usage}%")
        print(f"  Frequency: {latest.frequency_mhz} MHz")
        print(f"  Temperature: {latest.temperature_celsius}°C")
        print(f"  Timestamp: {latest.timestamp}")
    else:
        print("No telemetry data yet")
    
    # Stop telemetry
    await telemetry.stop_telemetry_monitor()
    print("Test completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_sensors())