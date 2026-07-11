import { describe, it, expect } from 'vitest';
import { computeSmartDeviceUsage } from '../../../components/dashboard/computeSmartDeviceUsage';
import type { SmartDevice } from '../../../api/smart';

function device(overrides: Partial<SmartDevice> = {}): SmartDevice {
  return {
    name: '/dev/sda',
    model: 'Test Disk',
    serial: 'SN-1',
    temperature: 30,
    status: 'PASSED',
    capacity_bytes: 1000,
    used_bytes: null,
    used_percent: null,
    mount_point: null,
    raid_member_of: null,
    last_self_test: null,
    attributes: [],
    ...overrides,
  };
}

describe('computeSmartDeviceUsage', () => {
  it('uses direct backend values when present', () => {
    const d = device({ used_bytes: 400, used_percent: 40 });
    expect(computeSmartDeviceUsage(d, [d], 999)).toEqual({ usedBytes: 400, usagePercent: 40 });
  });

  it('RAID member with no direct usage mirrors full storageUsed', () => {
    const d = device({ capacity_bytes: 2000, raid_member_of: 'md0' });
    expect(computeSmartDeviceUsage(d, [d], 500)).toEqual({ usedBytes: 500, usagePercent: 25 });
  });

  it('non-RAID device gets a proportional share of storageUsed', () => {
    const a = device({ name: '/dev/sda', serial: 'A', capacity_bytes: 1000 });
    const b = device({ name: '/dev/sdb', serial: 'B', capacity_bytes: 3000 });
    // a's share = 1000/4000 = 0.25 -> usedBytes = round(800*0.25)=200, percent = 200/1000*100 = 20
    expect(computeSmartDeviceUsage(a, [a, b], 800)).toEqual({ usedBytes: 200, usagePercent: 20 });
  });

  it('storageUsed 0 leaves zeros', () => {
    const d = device({ capacity_bytes: 1000 });
    expect(computeSmartDeviceUsage(d, [d], 0)).toEqual({ usedBytes: 0, usagePercent: 0 });
  });
});
