#!/usr/bin/env python3
"""
Final test script for Tapo P115 integration with plugp100 v5.x

This script demonstrates the correct usage of plugp100 v5.x API for
power monitoring with the Tapo P115 smart plug.

RESULTS:
--------
Device: Tapo P115 (BaluNode Power Monitor)
IP: 192.168.178.55

Correct API Flow:
1. Create credentials with device_factory.AuthCredential
2. Create config with device_factory.DeviceConnectConfiguration
3. Connect using device_factory.connect(config)
4. Call device.update() to fetch latest state and components
5. Get EnergyComponent using device.get_component(EnergyComponent)
6. Access power_info and energy_info attributes (NOT methods!)

Data Structure:
- power_info: PowerInfo(current_power=30) → Watts
- energy_info: EnergyInfo with detailed data:
  * current_power: 30589 mW → 30.589W (more precise)
  * today_energy: 123 Wh → 0.123 kWh
  * today_runtime: 325 minutes
  * month_energy: 123 Wh
  * month_runtime: 325 minutes
"""

import asyncio
import sys
from datetime import datetime


# Test credentials
IP_ADDRESS = "192.168.178.55"
EMAIL = "SvenBirkendahl@outlook.de"
PASSWORD = "98Kacktor10!"


async def main():
    print("="*70)
    print("Tapo P115 Power Monitoring - Final Test")
    print("="*70)

    try:
        from plugp100.new import device_factory
        from plugp100.new.components.energy_component import EnergyComponent

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Connecting to {IP_ADDRESS}...")

        # Step 1: Create credentials
        credentials = device_factory.AuthCredential(EMAIL, PASSWORD)

        # Step 2: Create configuration
        config = device_factory.DeviceConnectConfiguration(
            host=IP_ADDRESS,
            credentials=credentials
        )

        # Step 3: Connect to device
        device = await device_factory.connect(config)
        print(f"✓ Connected: {type(device).__name__}")

        # Step 4: Update device to fetch latest state
        await device.update()
        print(f"✓ Device updated")

        # Display device info
        info = device.device_info
        print(f"\nDevice Information:")
        print(f"  Model: {info.model}")
        print(f"  Nickname: {info.friendly_name}")
        print(f"  MAC: {info.mac}")
        print(f"  Firmware: {info.firmware_version}")
        print(f"  IP: {info.ip}")
        print(f"  RSSI: {info.rssi} dBm (Signal Level: {info.signal_level})")

        # Step 5: Check for energy component
        if not device.has_component(EnergyComponent):
            print("\n❌ ERROR: Device does not have EnergyComponent!")
            sys.exit(1)

        energy = device.get_component(EnergyComponent)
        print(f"\n✓ EnergyComponent available")

        # Step 6: Get power and energy data
        power_info = energy.power_info
        energy_info = energy.energy_info

        # Extract values
        current_power_watts = power_info.info.get('current_power', 0)
        current_power_mw = energy_info.info.get('current_power', 0)
        today_energy_wh = energy_info.info.get('today_energy', 0)
        today_runtime_min = energy_info.info.get('today_runtime', 0)
        month_energy_wh = energy_info.info.get('month_energy', 0)
        month_runtime_min = energy_info.info.get('month_runtime', 0)

        # Use more precise value from energy_info
        watts = current_power_mw / 1000.0 if current_power_mw > 0 else float(current_power_watts)
        energy_kwh = today_energy_wh / 1000.0
        month_kwh = month_energy_wh / 1000.0

        # Calculate voltage and current (assuming EU 230V)
        voltage = 230.0
        current_amps = watts / voltage if watts > 0 else 0.0

        # Display results
        print(f"\n{'='*70}")
        print("POWER MONITORING DATA")
        print(f"{'='*70}")
        print(f"\nCurrent Power Consumption:")
        print(f"  Power: {watts:.1f} W")
        print(f"  Voltage: {voltage:.1f} V (estimated)")
        print(f"  Current: {current_amps:.3f} A (calculated)")

        print(f"\nEnergy Usage (Today):")
        print(f"  Energy: {energy_kwh:.3f} kWh ({today_energy_wh} Wh)")
        print(f"  Runtime: {today_runtime_min} minutes ({today_runtime_min/60:.1f} hours)")
        print(f"  Avg Power: {(today_energy_wh/today_runtime_min*60):.1f} W" if today_runtime_min > 0 else "  Avg Power: N/A")

        print(f"\nEnergy Usage (This Month):")
        print(f"  Energy: {month_kwh:.3f} kWh ({month_energy_wh} Wh)")
        print(f"  Runtime: {month_runtime_min} minutes ({month_runtime_min/60:.1f} hours)")

        # Cost estimation (German average: €0.40/kWh)
        cost_per_kwh = 0.40
        today_cost = energy_kwh * cost_per_kwh
        month_cost = month_kwh * cost_per_kwh
        print(f"\nEstimated Cost (at €{cost_per_kwh:.2f}/kWh):")
        print(f"  Today: €{today_cost:.3f}")
        print(f"  Month: €{month_cost:.2f}")

        print(f"\n{'='*70}")
        print("✓ TEST SUCCESSFUL")
        print(f"{'='*70}")

        # Raw data for debugging
        print(f"\nRaw API Response:")
        print(f"  power_info: {power_info.info}")
        print(f"  energy_info: {energy_info.info}")

    except ImportError as e:
        print(f"\n❌ Import Error: {e}")
        print("\nMake sure plugp100 is installed:")
        print("  pip install plugp100>=5.0.0")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
