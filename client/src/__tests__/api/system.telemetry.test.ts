import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from '../../lib/api';
import { getAggregatedStorage, getTelemetryHistory } from '../../api/system';

vi.mock('../../lib/api', () => ({
  apiClient: { get: vi.fn() },
}));
const mockedGet = vi.mocked(apiClient.get);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('telemetry api', () => {
  it('getAggregatedStorage calls the aggregated endpoint and unwraps data', async () => {
    mockedGet.mockResolvedValue({ data: { total: 100, used: 10, available: 90 } });
    const res = await getAggregatedStorage();
    expect(mockedGet).toHaveBeenCalledWith('/api/system/storage/aggregated');
    expect(res.total).toBe(100);
  });

  it('getTelemetryHistory calls the history endpoint and unwraps data', async () => {
    mockedGet.mockResolvedValue({ data: { cpu: [], memory: [], network: [] } });
    const res = await getTelemetryHistory();
    expect(mockedGet).toHaveBeenCalledWith('/api/system/telemetry/history');
    expect(res.cpu).toEqual([]);
  });
});
