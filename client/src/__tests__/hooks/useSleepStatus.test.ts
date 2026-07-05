import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { sleepPollInterval, useSleepStatus } from '../../hooks/useSleepStatus';

vi.mock('../../api/sleep', () => ({ getSleepStatus: vi.fn() }));
vi.mock('../../api/fritzbox', () => ({ getFritzBoxConfig: vi.fn() }));

import { getSleepStatus } from '../../api/sleep';
import { getFritzBoxConfig } from '../../api/fritzbox';

describe('sleepPollInterval', () => {
  it('polls slowly (30s) while in soft sleep to avoid auto-wake', () => {
    expect(sleepPollInterval('soft_sleep')).toBe(30000);
  });

  it('polls quickly (5s) while awake', () => {
    expect(sleepPollInterval('awake')).toBe(5000);
  });

  it('defaults to the fast poll for unknown/undefined state', () => {
    expect(sleepPollInterval(undefined)).toBe(5000);
    expect(sleepPollInterval('deep_idle')).toBe(5000);
  });
});

describe('useSleepStatus', () => {
  beforeEach(() => vi.clearAllMocks());

  it('returns the sleep status and the Fritz!Box config', async () => {
    (getSleepStatus as any).mockResolvedValue({ current_state: 'awake' });
    (getFritzBoxConfig as any).mockResolvedValue({ host: '192.168.1.1' });

    const { result } = renderHook(() => useSleepStatus(), { wrapper: createQueryWrapper() });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.status).toEqual({ current_state: 'awake' });
    await waitFor(() => expect(result.current.fbConfig).toEqual({ host: '192.168.1.1' }));
  });

  it('keeps fbConfig null when Fritz!Box is not configured (no throw)', async () => {
    (getSleepStatus as any).mockResolvedValue({ current_state: 'awake' });
    (getFritzBoxConfig as any).mockRejectedValue(new Error('not configured'));

    const { result } = renderHook(() => useSleepStatus(), { wrapper: createQueryWrapper() });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.fbConfig).toBeNull();
  });
});
