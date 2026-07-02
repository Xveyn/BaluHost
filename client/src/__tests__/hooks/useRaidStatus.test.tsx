import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useRaidStatus } from '../../hooks/useRaidStatus';
import * as raidApi from '../../api/raid';

vi.mock('../../api/raid');
const api = vi.mocked(raidApi);

const sample = {
  arrays: [{ name: 'md0', level: 'raid1', size_bytes: 100, status: 'active', devices: [] }],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useRaidStatus', () => {
  it('maps raid status into the result shape', async () => {
    api.getRaidStatus.mockResolvedValue(sample);
    const { result } = renderHook(() => useRaidStatus({ pollInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });
    await waitFor(() => expect(result.current.raidLoading).toBe(false));
    expect(result.current.raidData?.arrays).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });

  it('surfaces an error string when the fetch rejects', async () => {
    api.getRaidStatus.mockRejectedValue(new Error('raid boom'));
    const { result } = renderHook(() => useRaidStatus({ pollInterval: 999999 }), {
      wrapper: createQueryWrapper(),
    });
    await waitFor(() => expect(result.current.error).toBe('raid boom'));
  });

  it('does not fetch when disabled', () => {
    api.getRaidStatus.mockResolvedValue(sample);
    const { result } = renderHook(() => useRaidStatus({ enabled: false }), {
      wrapper: createQueryWrapper(),
    });
    expect(result.current.raidLoading).toBe(false);
    expect(api.getRaidStatus).not.toHaveBeenCalled();
  });
});
