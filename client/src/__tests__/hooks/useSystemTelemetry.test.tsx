import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { createQueryWrapper } from '../helpers/queryClient';
import { useSystemTelemetry } from '../../hooks/useSystemTelemetry';
import * as systemApi from '../../api/system';

vi.mock('../../api/system');
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ token: 'test-token' }),
}));
const api = vi.mocked(systemApi);

const sampleSystem = {
  cpu: { usage: 5, cores: 4 },
  memory: { total: 100, used: 40, free: 60 },
  disk: { total: 200, used: 50, free: 150 },
  uptime: 10,
  dev_mode: true,
};
const sampleStorage = {
  filesystem: '/dev/md0',
  total: 200,
  used: 50,
  available: 150,
  use_percent: '25%',
  mount_point: '/',
};
const sampleHistory = { cpu: [{ timestamp: 1, usage: 5 }], memory: [], network: [] };

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
});

describe('useSystemTelemetry', () => {
  it('maps system/storage/history into the legacy shape', async () => {
    api.getSystemInfo.mockResolvedValue(sampleSystem);
    api.getAggregatedStorage.mockResolvedValue(sampleStorage);
    api.getTelemetryHistory.mockResolvedValue(sampleHistory);

    const { result } = renderHook(() => useSystemTelemetry(999999), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.system?.cpu.usage).toBe(5);
    expect(result.current.storage?.percent).toBe(25); // 50 / 200
    expect(result.current.history.cpu).toHaveLength(1);
    expect(result.current.error).toBeNull();
    expect(result.current.lastUpdated).toBeInstanceOf(Date);
  });

  it('is loading on first render with an empty cache', async () => {
    api.getSystemInfo.mockResolvedValue(sampleSystem);
    api.getAggregatedStorage.mockResolvedValue(sampleStorage);
    api.getTelemetryHistory.mockResolvedValue(sampleHistory);

    const { result } = renderHook(() => useSystemTelemetry(999999), {
      wrapper: createQueryWrapper(),
    });

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
  });

  it('surfaces an error string when a fetch rejects', async () => {
    api.getSystemInfo.mockRejectedValue(new Error('telemetry boom'));
    api.getAggregatedStorage.mockResolvedValue(sampleStorage);
    api.getTelemetryHistory.mockResolvedValue(sampleHistory);

    const { result } = renderHook(() => useSystemTelemetry(999999), {
      wrapper: createQueryWrapper(),
    });

    await waitFor(() => expect(result.current.error).toBe('telemetry boom'));
  });
});
