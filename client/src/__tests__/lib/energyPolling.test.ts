import { describe, it, expect } from 'vitest';
import { energyChartRefreshInterval } from '../../lib/energyPolling';

describe('energyChartRefreshInterval', () => {
  it('polls the live 10-minute window every 5s', () => {
    expect(energyChartRefreshInterval('10min')).toBe(5000);
  });

  it('polls the historical windows every 30s', () => {
    expect(energyChartRefreshInterval('1hour')).toBe(30000);
    expect(energyChartRefreshInterval('24hours')).toBe(30000);
    expect(energyChartRefreshInterval('7days')).toBe(30000);
  });
});
