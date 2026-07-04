import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useSmartData } from '../../hooks/useSmartData';
import * as smartApi from '../../api/smart';
import type { SmartStatusResponse } from '../../api/smart';

vi.mock('../../api/smart');
const api = vi.mocked(smartApi);

const sample: SmartStatusResponse = {
  checked_at: '2026-01-01T00:00:00Z',
  devices: [],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useSmartData', () => {
  it('maps the SMART status into the result shape', async () => {
    api.fetchSmartStatus.mockResolvedValue(sample);
    const { result } = renderHook(() => useSmartData(999999), { wrapper: createQueryWrapper() });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.smartData).toEqual(sample);
    expect(result.current.error).toBeNull();
    expect(result.current.lastUpdated).toBeInstanceOf(Date);
  });

  it('surfaces an error string when the fetch rejects', async () => {
    api.fetchSmartStatus.mockRejectedValue(new Error('smart boom'));
    const { result } = renderHook(() => useSmartData(999999), { wrapper: createQueryWrapper() });

    await waitFor(() => expect(result.current.error).toBe('smart boom'));
    expect(result.current.smartData).toBeNull();
  });
});
