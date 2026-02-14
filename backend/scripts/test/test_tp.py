#!/usr/bin/env python3
"""Test script to check Tapo P115 API response format"""

import asyncio
import sys

# Credentials (ersetzen Sie diese mit Ihren echten Werten)
IP_ADDRESS = "192.168.178.55"
EMAIL = "SvenBirkendahl@outlook.de"
PASSWORD = "98Kacktor10!"

print("=== Checking plugp100 structure ===")
try:
    import plugp100
    print(f"plugp100 version: {plugp100.__version__ if hasattr(plugp100, '__version__') else 'unknown'}")
    print(f"Available modules: {[x for x in dir(plugp100) if not x.startswith('_')]}")
except Exception as e:
    print(f"Error importing plugp100: {e}")
    sys.exit(1)

# Versuche verschiedene Import-Varianten
print("\n=== Trying import methods ===")

API_VERSION = None

# Variante 1: Neue API (v5.x)
try:
    from plugp100.new.tapodevice import TapoDevice
    from plugp100.new.components.energy_component import EnergyComponent
    print("✓ New API (v5.x) available")
    API_VERSION = "new"
except ImportError as e:
    print(f"✗ New API: {e}")

# Variante 2: Alte API mit TapoClient
if API_VERSION is None:
    try:
        from plugp100.api.tapo_client import TapoClient
        print("✓ Old API TapoClient available")
        API_VERSION = "old"
    except ImportError as e:
        print(f"✗ Old API: {e}")

if API_VERSION is None:
    print("❌ No compatible API found!")
    sys.exit(1)

async def test_new_api():
    """Test mit neuer API (v5.x)"""
    from plugp100.new.tapodevice import TapoDevice
    from plugp100.new.components.energy_component import EnergyComponent

    print("\n=== Connecting with NEW API ===")

    # In v5.x wird das Device anders initialisiert
    device = TapoDevice(IP_ADDRESS, EMAIL, PASSWORD)

    # Verfügbare Methoden prüfen
    print(f"Device methods: {[m for m in dir(device) if not m.startswith('_')]}")

    # Versuche verschiedene Verbindungsmethoden
    connected = False
    for method_name in ['update', 'initialize', 'refresh', 'connect']:
        if hasattr(device, method_name):
            try:
                method = getattr(device, method_name)
                if asyncio.iscoroutinefunction(method):
                    await method()
                else:
                    method()
                print(f"✓ Connected using device.{method_name}()")
                connected = True
                break
            except Exception as e:
                print(f"✗ {method_name}: {e}")
                continue

    if not connected:
        print("⚠️  No explicit connection needed, trying to get components directly...")

    # Energy Component holen
    try:
        energy = device.get_component(EnergyComponent)
        if energy is None:
            print("❌ EnergyComponent not available")
            print(f"Available components: {device.get_components() if hasattr(device, 'get_components') else 'unknown'}")
            return

        print("✓ EnergyComponent found")
    except Exception as e:
        print(f"❌ Error getting EnergyComponent: {e}")
        return

    # Current Power
    try:
        current_power = await energy.get_current_power()
        print(f"\n=== CURRENT POWER ===")
        print(f"Value: {current_power}")
        print(f"Type: {type(current_power)}")
    except Exception as e:
        print(f"Error getting current_power: {e}")
        import traceback
        traceback.print_exc()

    # Energy Usage
    try:
        energy_data = await energy.get_energy_usage()
        print(f"\n=== ENERGY USAGE (RAW) ===")
        print(f"Type: {type(energy_data)}")
        print(f"Data: {energy_data}")

        if hasattr(energy_data, '__dict__'):
            print(f"\n=== ATTRIBUTES ===")
            for key, val in energy_data.__dict__.items():
                print(f"  {key}: {val} (type: {type(val).__name__})")
        elif isinstance(energy_data, dict):
            print(f"\n=== DICT BREAKDOWN ===")
            for key, value in energy_data.items():
                print(f"  {key}: {value} (type: {type(value).__name__})")
    except Exception as e:
        print(f"Error getting energy_usage: {e}")
        import traceback
        traceback.print_exc()

async def test_old_api():
    """Test mit alter API (v3.x/v4.x)"""
    from plugp100.api.tapo_client import TapoClient

    print("\n=== Connecting with OLD API ===")
    client = TapoClient(EMAIL, PASSWORD)

    # Versuche verschiedene Device-Methoden
    device = None
    for method_name in ['p115', 'p110', 'p100']:
        if hasattr(client, method_name):
            try:
                method = getattr(client, method_name)
                device = await method(IP_ADDRESS)
                print(f"✓ Connected using client.{method_name}()")
                break
            except Exception as e:
                print(f"✗ {method_name}: {e}")
                continue

    if device is None:
        print("❌ Could not connect")
        return

    # Alle Methoden anzeigen
    print(f"\n=== AVAILABLE METHODS ===")
    methods = [m for m in dir(device) if not m.startswith('_') and callable(getattr(device, m))]
    for m in methods:
        print(f"  - {m}")

    # get_energy_usage versuchen
    if hasattr(device, 'get_energy_usage'):
        try:
            energy_data = await device.get_energy_usage()
            print(f"\n=== ENERGY USAGE (RAW) ===")
            print(f"Type: {type(energy_data)}")
            print(f"Data: {energy_data}")

            if isinstance(energy_data, dict):
                print(f"\n=== DICT BREAKDOWN ===")
                for key, value in energy_data.items():
                    print(f"  {key}: {value} (type: {type(value).__name__})")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("\n⚠️  get_energy_usage method not found")

async def main():
    try:
        if API_VERSION == "new":
            await test_new_api()
        else:
            await test_old_api()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("="*60)
    print("Tapo P115 API Test - Looking for raw power values")
    print("="*60)
    asyncio.run(main())
