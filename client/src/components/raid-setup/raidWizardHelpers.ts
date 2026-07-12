import { formatBytes } from '../../lib/formatters';
import { RAID_LEVELS } from './raidLevels';

const MDADM_NAME_REGEX = /^md([0-9]+|_[a-zA-Z0-9]+)$/;

export function isValidArrayName(name: string): boolean {
  return MDADM_NAME_REGEX.test(name) && name.length <= 32;
}

export function calculateArrayCapacity(level: string, diskCount: number): string {
  const raidInfo = RAID_LEVELS.find((r) => r.level === level);
  if (!raidInfo || diskCount === 0) return '0 GB';

  const diskSize = 5 * 1024 ** 3; // 5 GB per disk in dev mode
  const count = diskCount;

  let capacity = 0;
  switch (raidInfo.level) {
    case 'raid0':
      capacity = diskSize * count;
      break;
    case 'raid1':
      capacity = diskSize;
      break;
    case 'raid5':
      capacity = diskSize * (count - 1);
      break;
    case 'raid6':
      capacity = diskSize * (count - 2);
      break;
    case 'raid10':
      capacity = diskSize * (count / 2);
      break;
    default:
      capacity = diskSize;
  }

  return formatBytes(capacity);
}
