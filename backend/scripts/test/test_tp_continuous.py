#!/usr/bin/env python3
"""
Continuous monitoring test for Tapo P115
Samples power every 2 seconds for 30 seconds to verify values are correct
"""

import asyncio
from datetime import datetime

IP_ADDRESS = "192.168.178.55"
EMAIL = "SvenBirkendahl@outlook.de"
PASSWORD = "98Kacktor10!"

async def sample_power(device, energy):
    """Sample power once"""
    await device.update()

    power_info = energy.power_info
    energy_info = energy.energy_info

    current_power_mw = energy_info.info.get('current_power', 0)
    watts = current_power_mw / 1000.0

    return {
        'time': datetime.now().strftime('%H:%M:%S'),
        'watts': watts,
        'raw_mw': current_power_mw,
        'power_info_watts': power_info.info.get('current_power', 0)
    }

async def main():
    print("="*70)
    print("Continuous Power Monitoring Test (30 seconds)")
    print("="*70)

    from plugp100.new import device_factory
    from plugp100.new.components.energy_component import EnergyComponent

    # Connect
    credentials = device_factory.AuthCredential(EMAIL, PASSWORD)
    config = device_factory.DeviceConnectConfiguration(
        host=IP_ADDRESS,
        credentials=credentials
    )
    device = await device_factory.connect(config)
    await device.update()

    energy = device.get_component(EnergyComponent)

    print(f"\nDevice: {device.device_info.friendly_name}")
    print(f"Sampling every 2 seconds...\n")
    print(f"{'Time':<10} {'Watts':<10} {'Raw (mW)':<12} {'PowerInfo':<12}")
    print("-" * 70)

    samples = []
    for i in range(15):  # 15 samples over 30 seconds
        sample = await sample_power(device, energy)
        samples.append(sample['watts'])

        print(f"{sample['time']:<10} {sample['watts']:<10.1f} {sample['raw_mw']:<12} {sample['power_info_watts']:<12}")

        if i < 14:  # Don't sleep after last sample
            await asyncio.sleep(2)

    # Statistics
    print("\n" + "="*70)
    print("STATISTICS")
    print("="*70)
    avg = sum(samples) / len(samples)
    min_w = min(samples)
    max_w = max(samples)

    print(f"Average: {avg:.1f} W")
    print(f"Minimum: {min_w:.1f} W")
    print(f"Maximum: {max_w:.1f} W")
    print(f"Range: {max_w - min_w:.1f} W")
    print(f"\n✓ Values appear {'consistent' if (max_w - min_w) < 10 else 'variable'}")

if __name__ == "__main__":
    asyncio.run(main())
