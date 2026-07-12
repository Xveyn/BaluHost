import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import FanChartHint from '../../../../components/fan-control/fan-curve-chart/FanChartHint';

describe('FanChartHint', () => {
  it('appends the min hint at minPoints', () => {
    render(<FanChartHint pointCount={2} minPoints={2} maxPoints={10} />);
    expect(screen.getByText(/min 2 points/)).toBeInTheDocument();
  });

  it('appends the max hint at maxPoints', () => {
    render(<FanChartHint pointCount={10} minPoints={2} maxPoints={10} />);
    expect(screen.getByText(/max 10 points/)).toBeInTheDocument();
  });

  it('shows neither hint in the middle of the range', () => {
    render(<FanChartHint pointCount={5} minPoints={2} maxPoints={10} />);
    expect(screen.queryByText(/min 2 points/)).not.toBeInTheDocument();
    expect(screen.queryByText(/max 10 points/)).not.toBeInTheDocument();
  });
});
