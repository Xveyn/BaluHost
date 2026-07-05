import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../api/smart-devices', () => ({ smartDevicesApi: { getHistory: vi.fn() } }));
vi.mock('../../api/energy', () => ({ getHourlySamples: vi.fn() }));

import { smartDevicesApi } from '../../api/smart-devices';
import { getHourlySamples } from '../../api/energy';
import { loadEnergyChart } from '../../components/EnergyMonitor';

beforeEach(() => vi.clearAllMocks());

describe('loadEnergyChart', () => {
  it('maps the live 10-minute window from smart-device history (current_power)', async () => {
    (smartDevicesApi.getHistory as any).mockResolvedValue({
      data: [
        { timestamp: '2026-07-05T10:00:00Z', value: { current_power: 42 } },
        { timestamp: '2026-07-05T10:01:00Z', value: null },
      ],
    });

    const series = await loadEnergyChart(7, '10min', 'de');

    expect(smartDevicesApi.getHistory).toHaveBeenCalledWith(7, 'power_monitor', 1);
    expect(series.map((p) => p.watts)).toEqual([42, 0]);
    expect(series[0].fullTimestamp).toBe('2026-07-05T10:00:00Z');
  });

  it('maps historical windows from hourly samples (avg_watts) with the right hour span', async () => {
    (getHourlySamples as any).mockResolvedValue([
      { timestamp: '2026-07-05T09:00:00Z', avg_watts: 12.5 },
    ]);

    const series = await loadEnergyChart(7, '24hours', 'de');

    expect(getHourlySamples).toHaveBeenCalledWith(7, 24);
    expect(series).toHaveLength(1);
    expect(series[0].watts).toBe(12.5);
    expect(series[0].fullTimestamp).toBe('2026-07-05T09:00:00Z');
  });

  it('requests 168 hours for the 7-day window', async () => {
    (getHourlySamples as any).mockResolvedValue([]);
    await loadEnergyChart(3, '7days', 'de');
    expect(getHourlySamples).toHaveBeenCalledWith(3, 168);
  });
});
