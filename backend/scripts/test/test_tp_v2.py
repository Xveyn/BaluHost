#!/usr/bin/env python3
"""Test script for Tapo P115 with plugp100 v5.x"""

import asyncio
import sys

# Credentials
IP_ADDRESS = "192.168.178.55"
EMAIL = "SvenBirkendahl@outlook.de"
PASSWORD = "98Kacktor10!"

print("="*60)
print("Tapo P115 API Test - plugp100 v5.x")
print("="*60)


async def test_plugp100_v5():
    """Test with plugp100 v5.x API"""
    try:
        from plugp100.new import device_factory
        from plugp100.new.components.energy_component import EnergyComponent

        print("\n=== Connecting to device ===")
        print(f"IP: {IP_ADDRESS}")

        # Create credentials and configuration
        credentials = device_factory.AuthCredential(EMAIL, PASSWORD)
        config = device_factory.DeviceConnectConfiguration(
            host=IP_ADDRESS,
            credentials=credentials
        )

        # Connect to device
        device = await device_factory.connect(config)

        print(f"✓ Connected successfully")
        print(f"Device type: {type(device).__name__}")

        # Update device to fetch latest state and components
        print("\n=== Updating device state ===")
        if hasattr(device, 'update'):
            await device.update()
            print("✓ Device updated")

        print(f"Device info: {device.device_info if hasattr(device, 'device_info') else 'N/A'}")
        print(f"Model: {device.model if hasattr(device, 'model') else 'N/A'}")
        print(f"Device Type: {device.device_type if hasattr(device, 'device_type') else 'N/A'}")

        # Try to get components
        print("\n=== Getting components ===")
        if hasattr(device, 'components'):
            components = device.components
            print(f"Available components: {components}")

        # Try to get energy component
        print("\n=== Getting Energy Component ===")
        if hasattr(device, 'has_component'):
            has_energy = device.has_component(EnergyComponent)
            print(f"Has EnergyComponent: {has_energy}")

        if hasattr(device, 'get_component'):
            energy = device.get_component(EnergyComponent)
            if energy:
                print("✓ EnergyComponent found")

                # List all methods on energy component
                energy_methods = [m for m in dir(energy) if not m.startswith('_')]
                print(f"EnergyComponent methods: {energy_methods}")

                # Get power info
                print(f"\n=== Power Info ===")
                if hasattr(energy, 'power_info'):
                    power_info = energy.power_info
                    print(f"Type: {type(power_info)}")
                    print(f"Data: {power_info}")

                    if hasattr(power_info, '__dict__'):
                        print(f"\n=== Power Info Attributes ===")
                        for key, val in power_info.__dict__.items():
                            print(f"  {key}: {val} (type: {type(val).__name__})")

                # Get energy info
                print(f"\n=== Energy Info ===")
                if hasattr(energy, 'energy_info'):
                    energy_info = energy.energy_info
                    print(f"Type: {type(energy_info)}")
                    print(f"Data: {energy_info}")

                    if hasattr(energy_info, '__dict__'):
                        print(f"\n=== Energy Info Attributes ===")
                        for key, val in energy_info.__dict__.items():
                            print(f"  {key}: {val} (type: {type(val).__name__})")
            else:
                print("❌ EnergyComponent not found")

        print("\n=== SUCCESS ===")
        print("✓ All data retrieved successfully")

    except ImportError as e:
        print(f"❌ Import error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(test_plugp100_v5())
