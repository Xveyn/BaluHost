import type { SmartDevice } from '../../api/smart';

export function computeSmartDeviceUsage(
  device: SmartDevice,
  allDevices: SmartDevice[],
  storageUsed: number,
): { usedBytes: number; usagePercent: number } {
  let usagePercent = device.used_percent ?? 0;
  let usedBytes = device.used_bytes ?? 0;

  if (usedBytes === 0 && storageUsed > 0) {
    const deviceCapacity = device.capacity_bytes || 0;

    if (device.raid_member_of && deviceCapacity > 0) {
      usedBytes = storageUsed;
      usagePercent = (usedBytes / deviceCapacity) * 100;
    } else if (deviceCapacity > 0) {
      const nonRaidCapacity = allDevices
        .filter(d => !d.raid_member_of)
        .reduce((sum, d) => sum + (d.capacity_bytes || 0), 0);

      if (nonRaidCapacity > 0) {
        const deviceShare = deviceCapacity / nonRaidCapacity;
        usedBytes = Math.round(storageUsed * deviceShare);
        usagePercent = (usedBytes / deviceCapacity) * 100;
      }
    }
  }

  return { usedBytes, usagePercent };
}
