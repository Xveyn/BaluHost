import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';

vi.mock('../../api/power-management', () => ({
  getPowerStatus: vi.fn(),
  listPresets: vi.fn(),
  getPowerDemands: vi.fn(),
  getServiceIntensities: vi.fn(),
  getPowerMgmtHistory: vi.fn(),
  getAutoScalingConfig: vi.fn(),
  getDynamicModeConfig: vi.fn(),
}));

import {
  getPowerStatus,
  listPresets,
  getPowerDemands,
  getServiceIntensities,
  getPowerMgmtHistory,
  getAutoScalingConfig,
  getDynamicModeConfig,
} from '../../api/power-management';
import { usePowerManagementData } from '../../hooks/usePowerManagementData';

const statusMock = vi.mocked(getPowerStatus);
const presetsMock = vi.mocked(listPresets);
const demandsMock = vi.mocked(getPowerDemands);
const intensitiesMock = vi.mocked(getServiceIntensities);
const historyMock = vi.mocked(getPowerMgmtHistory);
const autoScalingMock = vi.mocked(getAutoScalingConfig);
const dynamicMock = vi.mocked(getDynamicModeConfig);

function seedSuccess() {
  statusMock.mockResolvedValue({ current_profile: 'balanced' } as never);
  presetsMock.mockResolvedValue({ presets: [{ id: 1, name: 'Balanced', is_active: true }] } as never);
  demandsMock.mockResolvedValue([{ source: 'x', level: 'low' }] as never);
  intensitiesMock.mockResolvedValue({ services: [{ name: 's1' }] } as never);
  historyMock.mockResolvedValue({ entries: [{ id: 9 }] } as never);
  autoScalingMock.mockResolvedValue({ config: { enabled: true } } as never);
  dynamicMock.mockResolvedValue({ enabled: false } as never);
}

describe('usePowerManagementData', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    seedSuccess();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('maps the seven endpoints into a combined snapshot', async () => {
    const { result } = renderHook(() => usePowerManagementData(), { wrapper: createQueryWrapper() });

    await waitFor(() => {
      expect(result.current.status).not.toBeNull();
    });

    expect(result.current.presets).toHaveLength(1);
    expect(result.current.demands).toHaveLength(1);
    expect(result.current.intensities).toHaveLength(1);
    expect(result.current.history).toHaveLength(1);
    expect(result.current.autoScaling?.enabled).toBe(true);
    expect(result.current.dynamicConfig).not.toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.lastUpdated).toBeInstanceOf(Date);
  });

  it('surfaces an error and no status when any endpoint fails (Promise.all)', async () => {
    historyMock.mockRejectedValue(new Error('history down'));

    const { result } = renderHook(() => usePowerManagementData(), { wrapper: createQueryWrapper() });

    await waitFor(() => {
      expect(result.current.error).toBe('history down');
    });
    expect(result.current.status).toBeNull();
  });

  it('refetch() re-requests the endpoints', async () => {
    const { result } = renderHook(() => usePowerManagementData(), { wrapper: createQueryWrapper() });

    await waitFor(() => expect(result.current.status).not.toBeNull());
    expect(getPowerStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.refetch();
    });

    expect(getPowerStatus).toHaveBeenCalledTimes(2);
    expect(getDynamicModeConfig).toHaveBeenCalledTimes(2);
  });

  it('polls on the interval', async () => {
    vi.useFakeTimers();

    renderHook(() => usePowerManagementData(5000), { wrapper: createQueryWrapper() });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(getPowerStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(getPowerStatus).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });
});
