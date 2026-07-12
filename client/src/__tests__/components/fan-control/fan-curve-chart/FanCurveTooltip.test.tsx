import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import FanCurveTooltip from '../../../../components/fan-control/fan-curve-chart/FanCurveTooltip';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

describe('FanCurveTooltip', () => {
  it('returns null when inactive', () => {
    const { container } = render(<FanCurveTooltip active={false} payload={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the curve-point label and pwm for an active curve point', () => {
    render(<FanCurveTooltip active payload={[{ payload: { temp: 50, pwm: 70, isCurrentPoint: false } }]} />);
    expect(screen.getByText('system:fanControl.curve.curvePoint')).toBeInTheDocument();
    expect(screen.getByText(/→ 70%/)).toBeInTheDocument();
  });

  it('renders the current label when isCurrentPoint is set', () => {
    render(<FanCurveTooltip active payload={[{ payload: { temp: 50, pwm: 70, isCurrentPoint: true } }]} />);
    expect(screen.getByText('system:fanControl.curve.current')).toBeInTheDocument();
  });
});
