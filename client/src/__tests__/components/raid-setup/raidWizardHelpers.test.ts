import { describe, it, expect } from 'vitest';
import { calculateArrayCapacity, isValidArrayName } from '../../../components/raid-setup/raidWizardHelpers';
import { formatBytes } from '../../../lib/formatters';

const DISK = 5 * 1024 ** 3; // 5 GB per disk (dev quirk, preserved)

describe('calculateArrayCapacity', () => {
  it('raid0 = n × disk', () => {
    expect(calculateArrayCapacity('raid0', 3)).toBe(formatBytes(3 * DISK));
  });
  it('raid1 = 1 × disk regardless of count', () => {
    expect(calculateArrayCapacity('raid1', 4)).toBe(formatBytes(DISK));
  });
  it('raid5 = (n-1) × disk', () => {
    expect(calculateArrayCapacity('raid5', 3)).toBe(formatBytes(2 * DISK));
  });
  it('raid6 = (n-2) × disk', () => {
    expect(calculateArrayCapacity('raid6', 4)).toBe(formatBytes(2 * DISK));
  });
  it('raid10 = (n/2) × disk', () => {
    expect(calculateArrayCapacity('raid10', 4)).toBe(formatBytes(2 * DISK));
  });
  it('returns 0 GB for zero disks', () => {
    expect(calculateArrayCapacity('raid1', 0)).toBe('0 GB');
  });
  it('returns 0 GB for an unknown level', () => {
    expect(calculateArrayCapacity('raid99', 3)).toBe('0 GB');
  });
});

describe('isValidArrayName', () => {
  it('accepts md + digits', () => { expect(isValidArrayName('md0')).toBe(true); });
  it('accepts md_ + alphanumerics', () => { expect(isValidArrayName('md_backup')).toBe(true); });
  it('rejects a non-md name', () => { expect(isValidArrayName('raid0')).toBe(false); });
  it('rejects bare "md"', () => { expect(isValidArrayName('md')).toBe(false); });
  it('rejects empty', () => { expect(isValidArrayName('')).toBe(false); });
  it('rejects names longer than 32 chars', () => { expect(isValidArrayName('md' + '1'.repeat(40))).toBe(false); });
  it('rejects special chars', () => { expect(isValidArrayName('md_ab!')).toBe(false); });
});
