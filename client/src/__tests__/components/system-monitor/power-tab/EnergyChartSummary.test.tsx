import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string, fallback?: string) => fallback ?? k }) }));
vi.mock('../../../../lib/formatters', () => ({ formatNumber: (value: number, decimals: number) => value.toFixed(decimals) }));

import { EnergyChartSummary } from '../../../../components/system-monitor/power-tab/EnergyChartSummary';
import type { CumulativeEnergyResponse } from '../../../../api/energy';

const baseCumulativeData: CumulativeEnergyResponse = {
  device_id: 1,
  device_name: 'Total',
  period: 'today',
  cost_per_kwh: 0.3,
  currency: 'EUR',
  total_kwh: 1.234,
  total_cost: 0.37,
  data_points: [
    { timestamp: '2026-01-01T00:00:00', cumulative_kwh: 0, cumulative_cost: 0, instant_watts: 10 },
    { timestamp: '2026-01-01T01:00:00', cumulative_kwh: 0.1, cumulative_cost: 0.03, instant_watts: 20 },
    { timestamp: '2026-01-01T02:00:00', cumulative_kwh: 0.2, cumulative_cost: 0.06, instant_watts: 30 },
  ],
};

describe('EnergyChartSummary', () => {
  it('renders total, costs, and price in cumulative mode', () => {
    render(<EnergyChartSummary chartMode="cumulative" cumulativeData={baseCumulativeData} />);
    expect(screen.getByText('1.234')).toBeTruthy();
    expect(screen.getByText('0.37')).toBeTruthy();
    expect(screen.getByText('0.30')).toBeTruthy();
    expect(screen.getByText('3')).toBeTruthy();
  });

  it('renders avg/max/min watts in instant mode', () => {
    render(<EnergyChartSummary chartMode="instant" cumulativeData={baseCumulativeData} />);
    expect(screen.getByText('20.0')).toBeTruthy();
    expect(screen.getByText('30.0')).toBeTruthy();
    expect(screen.getByText('10.0')).toBeTruthy();
    expect(screen.getByText('3')).toBeTruthy();
  });
});
