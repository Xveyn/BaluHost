import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import FanChartLegend from '../../../../components/fan-control/fan-curve-chart/FanChartLegend';

describe('FanChartLegend', () => {
  it('shows the current operating point entry only when currentTemp is set', () => {
    const { rerender } = render(<FanChartLegend currentTemp={45} emergencyTemp={90} />);
    expect(screen.getByText('Current Operating Point')).toBeInTheDocument();
    expect(screen.getByText('Emergency Temp (90°C)')).toBeInTheDocument();

    rerender(<FanChartLegend currentTemp={null} emergencyTemp={90} />);
    expect(screen.queryByText('Current Operating Point')).not.toBeInTheDocument();
  });
});
