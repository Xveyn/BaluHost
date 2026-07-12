export interface RaidLevelInfo {
  level: string;
  name: string;
  description: string;
  minDisks: number;
  redundancy: string;
  capacity: string;
  performance: string;
  recommended?: boolean;
}

export const RAID_LEVELS: RaidLevelInfo[] = [
  {
    level: 'raid1',
    name: 'RAID 1 (Mirroring)',
    description: 'All data is mirrored across multiple disks. Maximum security through redundancy.',
    minDisks: 2,
    redundancy: 'High (n-1 disks can fail)',
    capacity: '50% (with 2 disks)',
    performance: 'Read: Good / Write: Medium',
    recommended: true,
  },
  {
    level: 'raid0',
    name: 'RAID 0 (Striping)',
    description: 'Data is distributed across multiple disks. Maximum speed but no redundancy.',
    minDisks: 2,
    redundancy: 'None (failure = data loss)',
    capacity: '100%',
    performance: 'Read: Excellent / Write: Excellent',
  },
  {
    level: 'raid5',
    name: 'RAID 5 (Parity)',
    description: 'Data distributed with parity information. Good balance between speed and security.',
    minDisks: 3,
    redundancy: 'Medium (1 disk can fail)',
    capacity: '(n-1)/n × 100%',
    performance: 'Read: Good / Write: Medium',
  },
  {
    level: 'raid6',
    name: 'RAID 6 (Double Parity)',
    description: 'Like RAID 5, but with double parity information. Higher security than RAID 5.',
    minDisks: 4,
    redundancy: 'High (2 disks can fail)',
    capacity: '(n-2)/n × 100%',
    performance: 'Read: Good / Write: Low',
  },
  {
    level: 'raid10',
    name: 'RAID 10 (Mirrored Stripe)',
    description: 'Combination of RAID 0 and RAID 1. High speed with redundancy.',
    minDisks: 4,
    redundancy: 'High (n/2 disks can fail)',
    capacity: '50%',
    performance: 'Read: Excellent / Write: Good',
  },
];
