import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from '../../lib/api';
import { getCumulativeEnergy, getCumulativeEnergyTotal } from '../../api/energy';

describe('energy cumulative API — custom range', () => {
  beforeEach(() => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { data_points: [] } });
  });

  it('sends period when no range given', async () => {
    await getCumulativeEnergy(5, 'week');
    expect(apiClient.get).toHaveBeenCalledWith('/api/energy/cumulative/5?period=week');
  });

  it('sends start/end (not period) when range given', async () => {
    await getCumulativeEnergy(5, 'today', '2026-06-01T00:00:00.000Z', '2026-06-04T00:00:00.000Z');
    expect(apiClient.get).toHaveBeenCalledWith(
      '/api/energy/cumulative/5?start=2026-06-01T00%3A00%3A00.000Z&end=2026-06-04T00%3A00%3A00.000Z',
    );
  });

  it('total sends start/end when range given', async () => {
    await getCumulativeEnergyTotal('today', '2026-06-01T00:00:00.000Z', '2026-06-04T00:00:00.000Z');
    expect(apiClient.get).toHaveBeenCalledWith(
      '/api/energy/cumulative/total?start=2026-06-01T00%3A00%3A00.000Z&end=2026-06-04T00%3A00%3A00.000Z',
    );
  });
});
