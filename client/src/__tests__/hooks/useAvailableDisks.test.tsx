import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useAvailableDisks } from '../../hooks/useAvailableDisks';
import * as raidApi from '../../api/raid';

vi.mock('../../api/raid');
const api = vi.mocked(raidApi);

const sample = {
  disks: [
    { name: 'sdb', size_bytes: 100, is_partitioned: false, partitions: [], in_raid: false },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useAvailableDisks', () => {
  it('maps the disk list into the result shape', async () => {
    api.getAvailableDisks.mockResolvedValue(sample);
    const { result } = renderHook(() => useAvailableDisks(), {
      wrapper: createQueryWrapper(),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.disks).toHaveLength(1);
    expect(result.current.disks[0].name).toBe('sdb');
    expect(result.current.error).toBeNull();
  });

  it('defaults to an empty list before data arrives', () => {
    api.getAvailableDisks.mockResolvedValue(sample);
    const { result } = renderHook(() => useAvailableDisks(), {
      wrapper: createQueryWrapper(),
    });
    expect(result.current.disks).toEqual([]);
  });

  it('surfaces the raw error when the fetch rejects', async () => {
    const boom = new Error('disks boom');
    api.getAvailableDisks.mockRejectedValue(boom);
    const { result } = renderHook(() => useAvailableDisks(), {
      wrapper: createQueryWrapper(),
    });
    await waitFor(() => expect(result.current.error).toBe(boom));
    expect(result.current.disks).toEqual([]);
  });
});
