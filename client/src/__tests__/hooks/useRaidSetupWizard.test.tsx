import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { AvailableDisk } from '../../api/raid';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../api/raid', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/raid')>();
  return { ...actual, createArray: vi.fn().mockResolvedValue({ success: true }) };
});

import { createArray } from '../../api/raid';
import { useRaidSetupWizard } from '../../hooks/useRaidSetupWizard';

const disk = (name: string, over: Partial<AvailableDisk> = {}): AvailableDisk => ({
  name, size_bytes: 5 * 1024 ** 3, model: null, is_partitioned: true,
  partitions: [`${name}1`], in_raid: false, is_os_disk: false, ...over,
});

describe('useRaidSetupWizard', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('filters out in_raid and os disks from freeDisks', () => {
    const disks = [disk('sda'), disk('sdb', { in_raid: true }), disk('nvme0n1', { is_os_disk: true })];
    const { result } = renderHook(() => useRaidSetupWizard(disks, vi.fn(), vi.fn()));
    expect(result.current.freeDisks.map((d) => d.name)).toEqual(['sda']);
  });

  it('toggleDiskSelection adds then removes a disk', () => {
    const { result } = renderHook(() => useRaidSetupWizard([disk('sda')], vi.fn(), vi.fn()));
    act(() => result.current.toggleDiskSelection('sda'));
    expect(result.current.selectedDisks).toEqual(['sda']);
    act(() => result.current.toggleDiskSelection('sda'));
    expect(result.current.selectedDisks).toEqual([]);
  });

  it('canProceedFromDiskSelection requires >= 2 disks', () => {
    const { result } = renderHook(() => useRaidSetupWizard([disk('sda'), disk('sdb')], vi.fn(), vi.fn()));
    expect(result.current.canProceedFromDiskSelection()).toBe(false);
    act(() => { result.current.toggleDiskSelection('sda'); result.current.toggleDiskSelection('sdb'); });
    expect(result.current.canProceedFromDiskSelection()).toBe(true);
  });

  it('canProceedFromRaidLevel requires >= minDisks for the selected level', () => {
    const { result } = renderHook(() => useRaidSetupWizard([disk('sda'), disk('sdb')], vi.fn(), vi.fn()));
    act(() => { result.current.toggleDiskSelection('sda'); result.current.toggleDiskSelection('sdb'); });
    // default level raid1 (minDisks 2) -> ok with 2
    expect(result.current.canProceedFromRaidLevel()).toBe(true);
    act(() => result.current.setSelectedRaidLevel('raid5')); // minDisks 3
    expect(result.current.canProceedFromRaidLevel()).toBe(false);
  });

  it('handleSubmit calls createArray with the first partition per disk, then onSuccess + onClose', async () => {
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    const { result } = renderHook(() => useRaidSetupWizard([disk('sda'), disk('sdb')], onClose, onSuccess));
    act(() => { result.current.toggleDiskSelection('sda'); result.current.toggleDiskSelection('sdb'); });
    act(() => result.current.setArrayName('md7'));
    await act(async () => { await result.current.handleSubmit({ preventDefault: vi.fn() } as unknown as React.FormEvent); });
    expect(vi.mocked(createArray)).toHaveBeenCalledWith({ name: 'md7', level: 'raid1', devices: ['sda1', 'sdb1'] });
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });
});
