import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('recharts', () => new Proxy({}, {
  has: () => true,
  get: (_target, prop) => {
    if (prop === 'then' || typeof prop === 'symbol') return undefined;
    return (props: { children?: unknown }) => props?.children ?? null;
  },
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string, fallback?: string) => fallback ?? k }) }));

import { EnergyChart } from '../../../../components/system-monitor/power-tab/EnergyChart';
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
  ],
};

describe('EnergyChart', () => {
  it('shows the loading spinner (no empty-state text) while cumulativeLoading is true', () => {
    render(
      <EnergyChart
        chartMode="cumulative"
        cumulativeData={null}
        cumulativeLoading={true}
        cumulativePeriod="today"
        language="en"
      />
    );
    expect(screen.queryByText('monitor.noDataForPeriod')).toBeNull();
  });

  it('shows the empty state when data_points is empty and not loading', () => {
    render(
      <EnergyChart
        chartMode="cumulative"
        cumulativeData={{ ...baseCumulativeData, data_points: [] }}
        cumulativeLoading={false}
        cumulativePeriod="today"
        language="en"
      />
    );
    expect(screen.getByText('monitor.noDataForPeriod')).toBeTruthy();
  });

  it('renders the chart without the empty state when a data point exists (cumulative mode)', () => {
    expect(() =>
      render(
        <EnergyChart
          chartMode="cumulative"
          cumulativeData={baseCumulativeData}
          cumulativeLoading={false}
          cumulativePeriod="today"
          language="en"
        />
      )
    ).not.toThrow();
    expect(screen.queryByText('monitor.noDataForPeriod')).toBeNull();
  });

  it('renders the chart without the empty state when a data point exists (instant mode)', () => {
    expect(() =>
      render(
        <EnergyChart
          chartMode="instant"
          cumulativeData={baseCumulativeData}
          cumulativeLoading={false}
          cumulativePeriod="today"
          language="en"
        />
      )
    ).not.toThrow();
    expect(screen.queryByText('monitor.noDataForPeriod')).toBeNull();
  });
});
